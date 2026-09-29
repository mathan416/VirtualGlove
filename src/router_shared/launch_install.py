"""Installer-only integration for the session adapter and owned profiles."""
from __future__ import annotations

import re
import os
import pwd
from pathlib import Path

from .storage import atomic_write


def wrap_commands(text, adapter="/opt/controller-router/bin/retroarch-route", system=None):
    """Replace only the frontend token and its existing Router-owned prefix."""
    from .systems import system_id
    binary = "/opt/retropie/emulators/retroarch/bin/retroarch"
    prefix = adapter + (" --system " + system_id(system) if system else "")
    pattern = r"(?<![\w/.-])(?:" + re.escape(adapter) + r"(?: --system [a-z0-9_-]+)? )?" + re.escape(binary) + r"(?=\s)"
    return re.sub(pattern, lambda match: prefix + " " + binary, text)


def replace_owned(path, content, mode=0o644):
    """Keep one recoverable copy before an installer changes a file."""
    if path.is_file() and path.read_text() == content:
        # A repeat upgrade must also repair ownership left by an old root
        # installer, without replacing an otherwise unchanged config file.
        if os.geteuid() == 0 and str(path).startswith('/opt/retropie/configs/'):
            account = pwd.getpwnam('pi')
            previous = path.stat()
            if (previous.st_uid, previous.st_gid) != (account.pw_uid, account.pw_gid):
                os.chown(path, account.pw_uid, account.pw_gid)
        return False
    if path.is_file():
        backup = path.with_name(path.name + ".before-router-session-routing")
        if not backup.exists():
            atomic_write(backup, path.read_text(), path.stat().st_mode & 0o777)
    atomic_write(path, content, mode)
    return True


def repair_profiles(folder):
    """Repair Router filenames only, preserving extra hotkeys and button fields."""
    from .controller_router import output_name, DEVICE_PRODUCT_BASE
    from .merged_gamepad import MERGED_RETROARCH_BINDINGS, RETROPIE_HOTKEY_BINDINGS
    folder.mkdir(parents=True, exist_ok=True)
    for player in range(1, 5):
        path = folder / (output_name(player) + ".cfg")
        current = path.read_text() if path.exists() else ""
        fields = {"input_device": output_name(player), "input_driver": "udev",
                  "input_vendor_id": "4617", "input_product_id": str(DEVICE_PRODUCT_BASE + player)}
        fields.update({key.replace("input_player1_", "input_"): value
                       for key, value in MERGED_RETROARCH_BINDINGS.items()
                       if key.endswith(("_btn", "_axis")) and key != "input_enable_hotkey_btn"})
        if player == 1:
            fields["input_enable_hotkey_btn"] = "12"
            for key, value in RETROPIE_HOTKEY_BINDINGS.items():
                if not re.search(r"(?m)^" + re.escape(key) + r"\s*=", current):
                    fields[key] = value
        for key, value in fields.items():
            pattern = r"(?m)^" + re.escape(key) + r"\s*=.*$"
            line = '%s = "%s"' % (key, value)
            current = re.sub(pattern, lambda _: line, current) if re.search(pattern, current) else current + line + "\n"
        replace_owned(path, current)


def retire_core_indexes(text):
    """Remove obsolete Router-owned indexes that override session routing."""
    begin = '# VirtualGlove Controller Router'
    end = '# End VirtualGlove Controller Router'
    if text.count(begin) != 1 or text.count(end) != 1:
        return text
    start = text.index(begin)
    finish = text.index(end)
    if finish < start:
        return text
    block = re.sub(r'(?m)^input_player[1-4]_joypad_index\s*=.*\n?', '', text[start:finish])
    return text[:start] + block + text[finish:]


def migrate_core_overrides(configs):
    """Installer-only retirement of old core port indexes; keep user binds."""
    changed = []
    for core in ('FCEUmm', 'Nestopia'):
        path = configs / 'all/retroarch/config' / core / (core + '.cfg')
        if path.is_file():
            current = path.read_text()
            updated = retire_core_indexes(current)
            if updated != current and replace_owned(path, updated):
                changed.append(str(path))
    return changed


def install_retropie(configs=Path("/opt/retropie/configs"),
                     root=Path("/opt/controller-router")):
    """Install shared library and register every existing Libretro launch."""
    library = root / "lib/router_shared"
    library.mkdir(parents=True, exist_ok=True)
    for source in Path(__file__).parent.glob("[!.]*.py"):
        replace_owned(library / source.name, source.read_text())
    adapter = root / "bin/retroarch-route"
    code = '''#!/usr/bin/python3
import sys
sys.path.insert(0, %r)
from router_shared.launch import main
if len(sys.argv) < 2:
    sys.exit("Controller Router adapter needs a RetroArch executable")
system = []
if sys.argv[1:2] == ["--system"]:
    system = sys.argv[1:3]
    del sys.argv[1:3]
sys.argv = [sys.argv[0]] + system + ["--config", "/etc/virtualglove/controller-router.json",
            "--retroarch", sys.argv[1], "--"] + sys.argv[2:]
sys.exit(main())
''' % str(root / "lib")
    replace_owned(adapter, code, 0o755)
    changed = []
    for path in configs.glob("*/emulators.cfg"):
        if any(marker in path.parent.name for marker in (".backup", ".before", ".bak")):
            continue
        if replace_owned(path, wrap_commands(path.read_text(), str(adapter), path.parent.name)):
            changed.append(str(path))
    profiles = configs / "all/retroarch/autoconfig"
    repair_profiles(profiles)
    repair_profiles(profiles / "udev")
    changed.extend(migrate_core_overrides(configs))
    return changed


def patch_batocera_generator(text, adapter):
    """Wrap only the final Libretro command, after Batocera's generation."""
    marker = '# Controller Router session adapter'
    if marker in text:
        # A repeat upgrade must also update the adapter path.
        text = re.sub(r"(?m)^        # Controller Router session adapter\n        if .*\n            commandArray = .*\n", '', text)
    anchor = re.compile(r'(?m)^(        return Command\.Command\(array=commandArray, env=.+\))$')
    if len(anchor.findall(text)) != 1:
        raise RuntimeError('Unsupported Batocera configgen layout; saved configuration was not changed.')
    block = ('        ' + marker + '\n'
             '        if commandArray and str(commandArray[0]) == "/usr/bin/retroarch":\n'
             '            commandArray = [%r, "--system", system.name] + commandArray\n' % str(adapter))
    return anchor.sub(lambda match: block + match.group(0), text)


def install_batocera(root=Path('/userdata/system/controller-router'), generator=None):
    """Persist the integration; runtime activation mounts this narrow overlay."""
    if generator is None:
        candidates = list(Path('/usr/lib').glob('python*/site-packages/configgen/generators/libretro/libretroGenerator.py'))
        if len(candidates) != 1:
            raise RuntimeError('Cannot identify Batocera Libretro generator; installation stopped.')
        generator = candidates[0]
    adapter = root / 'bin/retroarch-route'
    # Validate before changing installer-owned files.
    patched = patch_batocera_generator(generator.read_text(), adapter)
    library = root / 'lib/router_shared'
    for source in Path(__file__).parent.glob('[!.]*.py'):
        replace_owned(library / source.name, source.read_text())
    code = '''#!/usr/bin/python3
import sys
sys.path.insert(0, %r)
from router_shared.launch import main
system = []
if sys.argv[1:2] == ["--system"]:
    system = sys.argv[1:3]
    del sys.argv[1:3]
sys.argv = [sys.argv[0]] + system + ["--config", "/userdata/system/virtualglove/data/controller-router.json",
            "--retroarch", sys.argv[1], "--"] + sys.argv[2:]
sys.exit(main())
''' % str(root / 'lib')
    replace_owned(adapter, code, 0o755)
    replace_owned(root / 'libretroGenerator.py', patched)
    replace_owned(root / 'generator-path', str(generator) + '\n')
    repair_profiles(Path('/userdata/system/configs/retroarch/autoconfig'))
    return generator


def activate_batocera(root=Path('/userdata/system/controller-router')):
    """Bind only the generator module; never write saved RetroArch settings."""
    import subprocess
    # Derive against the installed Batocera module on every boot so upgrades
    # retain upstream changes, rather than mounting an old generator wholesale.
    target = Path((root / 'generator-path').read_text().strip())
    if not target.is_file():
        raise RuntimeError('Batocera configgen changed; rerun the controller installer.')
    patched = patch_batocera_generator(target.read_text(), root / 'bin/retroarch-route')
    mounted = any(line.split()[4] == str(target)
                  for line in Path('/proc/self/mountinfo').read_text().splitlines())
    if mounted:
        # Existing binding already refers to this integration; avoid replacing
        # the backing inode under a live mount during the other app's startup.
        return
    replace_owned(root / 'libretroGenerator.py', patched)
    subprocess.run(['mount', '--bind', str(root / 'libretroGenerator.py'), str(target)], check=True)


def patch_recalbox_generator(text, adapter):
    """Wrap Recalbox's generated Libretro command without changing saved settings."""
    marker = '        # Controller Router session adapter\n'
    if marker in text:
        text = re.sub(r'(?m)^        # Controller Router session adapter\n        if .+\n            commandArray = .+\n', '', text)
    anchor = re.compile(r'(?m)^(        return Command\(videomode=system\.VideoMode, array=commandArray, env=env, preExec=pre, postExec=post\))$')
    if len(anchor.findall(text)) != 1:
        raise RuntimeError('Unsupported Recalbox configgen layout; saved configuration was not changed.')
    block = (marker +
             '        if commandArray and str(commandArray[0]) == "/usr/bin/retroarch":\n'
             '            commandArray = ["/usr/bin/python3", %r, "--system", system.Name] + commandArray\n' % str(adapter))
    return anchor.sub(lambda match: block + match.group(0), text)


def install_recalbox(root=Path('/recalbox/share/system/controller-router'), generator=None):
    """Stage Recalbox's launch adapter in the persistent share."""
    if generator is None:
        candidates = list(Path('/usr/lib').glob('python*/site-packages/configgen/generators/libretro/libretroGenerator.py'))
        if len(candidates) != 1:
            raise RuntimeError('Cannot identify Recalbox Libretro generator; installation stopped.')
        generator = candidates[0]
    adapter = root / 'bin/retroarch-route'
    patched = patch_recalbox_generator(generator.read_text(), adapter)
    library = root / 'lib/router_shared'
    for source in Path(__file__).parent.glob('[!.]*.py'):
        replace_owned(library / source.name, source.read_text())
    code = '''#!/usr/bin/python3
import sys
sys.path.insert(0, %r)
from router_shared.launch import main
system = []
if sys.argv[1:2] == ["--system"]:
    system = sys.argv[1:3]
    del sys.argv[1:3]
sys.argv = [sys.argv[0]] + system + ["--config", "/recalbox/share/system/virtualglove/data/controller-router.json",
            "--retroarch", sys.argv[1], "--"] + sys.argv[2:]
sys.exit(main())
''' % str(root / 'lib')
    replace_owned(adapter, code, 0o755)
    replace_owned(root / 'libretroGenerator.py', patched)
    replace_owned(root / 'generator-path', str(generator) + '\n')
    repair_profiles(Path('/recalbox/share/system/configs/retroarch/autoconfig'))
    return generator


def activate_recalbox(root=Path('/recalbox/share/system/controller-router')):
    """Bind only Recalbox's Libretro generator for this boot."""
    import subprocess
    target = Path((root / 'generator-path').read_text().strip())
    if not target.is_file():
        raise RuntimeError('Recalbox configgen changed; rerun the controller installer.')
    mounted = any(line.split()[4] == str(target)
                  for line in Path('/proc/self/mountinfo').read_text().splitlines())
    if mounted:
        return
    replace_owned(root / 'libretroGenerator.py',
                  patch_recalbox_generator(target.read_text(), root / 'bin/retroarch-route'))
    subprocess.run(['mount', '--bind', str(root / 'libretroGenerator.py'), str(target)], check=True)
