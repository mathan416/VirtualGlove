"""Qualify and install one explicit native emulator route on RetroPie.

The original launch command is retained as the disabled-routing fallback. The
operator must independently test that exact original command before setup.
"""
import argparse
import fcntl
import hashlib
import json
import os
import pwd
import re
import shlex
import tempfile
from pathlib import Path

from .storage import atomic_write

PROFILES = {'arcem': 'archimedes', 'gsplus': 'apple2gs', 'simcoupe': 'samcoupe'}


class Plan(dict):
    def __init__(self, changes, baseline):
        super().__init__(changes)
        self.baseline = baseline


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _document(path, default):
    if not path.exists():
        return default
    if path.is_symlink() or not path.is_file():
        raise ValueError('Configuration must be a regular file: ' + str(path))
    return json.loads(path.read_text())


def _validated_route(command, profile, computer_launcher):
    """Accept only a directly invoked Router computer launcher, not shell code."""
    args = shlex.split(command)
    offset = 1
    if len(args) > 1 and args[1] == '--player':
        if len(args) < 3 or args[2] not in ('1', '2', '3', '4'):
            raise ValueError('Player must be between 1 and 4')
        offset = 3
    if (len(args) < offset + 3 or Path(args[0]) != computer_launcher or args[offset] != profile
            or args[offset+1] != '--' or not Path(args[offset+2]).is_absolute() or not Path(args[offset+2]).is_file()
            or not os.access(args[offset+2], os.X_OK)):
        raise ValueError('Routed command must directly invoke the installed computer-launch, selected profile and an installed absolute emulator executable')
    placeholders = ('%ROM%', '%BASENAME%', '%XRES%', '%YRES%', '%QUAKEDIR%')
    for arg in args:
        if any(marker in arg and arg != marker for marker in placeholders):
            raise ValueError('Launcher placeholders must be separate arguments')
    return ' '.join(shlex.quote(arg) for arg in args)



def _validate_fallback_syntax(command):
    """Allow a simple shell invocation with only unquoted standalone placeholders."""
    placeholders = ('%ROM%', '%BASENAME%', '%XRES%', '%YRES%', '%QUAKEDIR%')
    quote = None
    at_boundary = True
    i = 0
    while i < len(command):
        ch = command[i]
        marker = next((m for m in placeholders if command.startswith(m, i)), None)
        if marker is not None:
            left = at_boundary
            right = i + len(marker) == len(command) or command[i+len(marker)].isspace()
            if quote is not None or not left or not right:
                raise ValueError('Fallback placeholders must be standalone, unquoted arguments')
            at_boundary = False
            i += len(marker)
            continue
        if quote == "'":
            if ch == "'": quote = None
            i += 1
            continue
        if ch == '\\':
            if i + 1 >= len(command) or command[i+1] in '\r\n': raise ValueError('Invalid fallback escape')
            if any(command.startswith(m, i+1) for m in placeholders):
                raise ValueError('Fallback placeholders must be standalone, unquoted arguments')
            at_boundary = False
            i += 2
            continue
        if quote == '"':
            if ch == '"': quote = None
            elif ch in '$`': raise ValueError('Fallback shell expansion is unsupported')
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            at_boundary = False
        elif ch in '|&;<>(){}[]*?~#\n\r' or ch in '$`':
            raise ValueError('Fallback shell operators or expansion are unsupported')
        elif ch.isspace():
            at_boundary = True
        else:
            at_boundary = False
        i += 1
    if quote is not None: raise ValueError('Invalid fallback quoting')
    try:
        tokens = shlex.split(command)
    except ValueError:
        raise ValueError('Invalid fallback command')
    if not tokens: raise ValueError('Fallback command is empty')


def plan(profile, choice, routed_command, fallback_sha256, configs, registry_path,
         manifest_path, provider, native_launcher, runtime_user, state_root, computer_launcher):
    """Prepare an idempotent change without modifying any file."""
    from . import retropie_native
    if getattr(retropie_native, 'FALLBACK_COMMAND_SCHEMA', None) != 1:
        raise ValueError('Installed native route does not support qualified fallback commands; upgrade Router first')
    if profile not in PROFILES or choice == 'default' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}', choice):
        raise ValueError('Unsupported profile or emulator choice')
    if not re.fullmatch(r'[0-9a-f]{64}', fallback_sha256):
        raise ValueError('A SHA-256 of the independently tested fallback is required')
    configs, registry_path, manifest_path, provider, native_launcher, state_root, computer_launcher = map(
        Path, (configs, registry_path, manifest_path, provider, native_launcher, state_root, computer_launcher))
    if not all(p.is_absolute() for p in (configs, registry_path, manifest_path, provider, native_launcher, state_root, computer_launcher)):
        raise ValueError('All installation paths must be absolute')
    if not provider.is_file() or not native_launcher.is_file() or not os.access(str(native_launcher), os.X_OK):
        raise ValueError('The installed Router provider and native launcher are required')
    native_module = provider.parent / 'retropie_native.py'
    if (native_module.is_symlink() or not native_module.is_file()
            or Path(retropie_native.__file__).resolve() != native_module.resolve()):
        raise ValueError('Setup must run from the Router library installed beside the provider')
    expected_launcher = ("#!/usr/bin/python3\nimport sys\nsys.path.insert(0, %r)\nfrom router_shared.retropie_native import main\nsys.exit(main())\n" % str(provider.parent.parent))
    try:
        if native_launcher.read_text() != expected_launcher:
            raise ValueError('Native launcher is not the matching Router installer-owned stub')
    except UnicodeError:
        raise ValueError('Native launcher is not the matching Router installer-owned stub')
    try:
        pwd.getpwnam(runtime_user)
    except KeyError:
        raise ValueError('The configured runtime user does not exist')
    stub = ("#!/usr/bin/python3\n# Controller Router emulator launcher\nimport sys\nsys.path.insert(0, %r)\nfrom router_shared.computer_launch import main\nsys.exit(main())\n" % str(provider.parent.parent))
    if computer_launcher.is_symlink() or (computer_launcher.exists() and (not computer_launcher.is_file() or computer_launcher.read_text() != stub)):
        raise ValueError('Existing computer launcher conflicts')
    if computer_launcher.exists() and not os.access(str(computer_launcher),os.X_OK):
        raise ValueError('Existing computer launcher is not executable')
    route = _validated_route(routed_command, profile, computer_launcher)
    system = PROFILES[profile]
    config = configs / system / 'emulators.cfg'
    paths = (computer_launcher, registry_path, config, manifest_path)
    if len(set(paths)) != len(paths):
        raise ValueError('Installation paths must be distinct')
    for path in paths:
        if path.is_symlink():
            raise ValueError('Refusing a symlink: ' + str(path))
    baseline = {path: path.read_bytes() if path.exists() else None for path in paths}
    if config.is_symlink() or not config.is_file():
        raise ValueError('Expected a regular emulator configuration file')
    text = config.read_text()
    pattern = re.compile(r'^(\s*' + re.escape(choice) + r'\s*=\s*")([^"\n]*)("\s*)$', re.M)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError('Expected exactly one selected emulator entry')
    original = matches[0].group(2)
    registry = _document(registry_path, {'entries': {}, 'runtime': {
        'user': runtime_user, 'state_root': str(state_root), 'launcher': str(native_launcher)}})
    if not isinstance(registry, dict) or not isinstance(registry.get('entries'), dict) or not isinstance(registry.get('runtime'), dict):
        raise ValueError('Invalid existing native registry')
    runtime = registry['runtime']
    if (runtime.get('user') != runtime_user or Path(runtime.get('state_root', '')) != state_root
            or Path(runtime.get('launcher', '')) != native_launcher):
        raise ValueError('Existing native runtime differs; preserve its configuration and use its exact paths')
    entry_id = 'router-%s-%s' % (system, choice)
    current = registry['entries'].get(entry_id)
    wrapper = '%s --entry %s --rom %%ROM%% --basename %%BASENAME%% --xres %%XRES%% --yres %%YRES%%' % (
        shlex.quote(str(native_launcher)), shlex.quote(entry_id))
    if current is not None:
        if not isinstance(current, dict) or current.get('router_emulator_setup') != 1 or original != wrapper:
            raise ValueError('An existing registration conflicts; no changes made')
        fallback = current.get('fallback_command')
        if not isinstance(fallback, str) or current.get('fallback_sha256') != digest(fallback):
            raise ValueError('Existing fallback was altered')
        if (current.get('command') != route or current.get('system') != system or current.get('config') != str(config)
                or current.get('emulator') != choice or current.get('private_bridge') is not True):
            raise ValueError('Existing routed command differs; remove it deliberately before reconfiguring')
    else:
        if original.lstrip().startswith(('CON:', 'XINIT:', 'XINIT-WMC:')) or 'native-route' in original or 'computer-launch' in original or 'router_shared.computer_launch' in original:
            raise ValueError('Original command requires a separate qualified host adapter; it cannot be used as an independent fallback')
        fallback = original
    _validate_fallback_syntax(fallback)
    if digest(fallback) != fallback_sha256:
        raise ValueError('Fallback hash does not match the independently tested original command')
    entry = {'system': system, 'emulator': choice, 'config': str(config), 'source': 'emulator',
             'prefix': '', 'command': route, 'private_bridge': True, 'fallback_command': fallback,
             'fallback_sha256': fallback_sha256, 'router_emulator_setup': 1}
    registry['entries'][entry_id] = entry
    replacement = matches[0].group(1) + wrapper + matches[0].group(3)
    updated = text[:matches[0].start()] + replacement + text[matches[0].end():]
    manifest = _document(manifest_path, {'schema': 1, 'providers': [], 'systems': {}})
    if not isinstance(manifest, dict) or manifest.get('schema') != 1 or not isinstance(manifest.get('providers'), list) or not isinstance(manifest.get('systems'), dict):
        raise ValueError('Invalid existing native adapter manifest')
    old = manifest['systems'].get(str(config))
    if old and (old.get('system') != system or old.get('kind') != 'native'):
        raise ValueError('Existing native system registration conflicts')
    row = dict(old or {})
    row.update(system=system, kind='native', command_sha256=sorted(set((old or {}).get('command_sha256', []) + [digest(wrapper)])))
    manifest['systems'][str(config)] = row
    if not any(isinstance(p, dict) and p.get('path') == str(provider) for p in manifest['providers']):
        manifest['providers'].append({'path': str(provider)})
    if any((path.read_bytes() if path.exists() else None) != original for path,original in baseline.items()):
        raise RuntimeError('Configuration changed during preparation; retry')
    return Plan({computer_launcher: stub, registry_path: json.dumps(registry, indent=2)+'\n', config: updated,
                 manifest_path: json.dumps(manifest, indent=2)+'\n'}, baseline)


def apply_plan(changes, backup_root, active_check, executable_paths=()):
    """Apply a reviewed plan with backups and rollback; caller coordinates writers."""
    backup_root = Path(backup_root)
    if not backup_root.is_absolute():
        raise ValueError('Backup directory must be absolute')
    if active_check():
        raise RuntimeError('Close the active game before changing emulator registration')
    baseline = getattr(changes, 'baseline', None)
    changes = {Path(p): text for p, text in changes.items()}
    if baseline is None:
        raise ValueError('A prepared installation plan is required')
    for path, original in baseline.items():
        if path.is_symlink() or (path.read_bytes() if path.exists() else None) != original:
            raise RuntimeError('Configuration changed after preparation: ' + str(path))
    for path in changes:
        if path.is_symlink():
            raise ValueError('Refusing to replace a symlink: ' + str(path))
    changed = {p: text for p, text in changes.items() if not p.exists() or p.read_text() != text}
    if not changed:
        return None
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix='emulator-setup-', dir=str(backup_root)))
    os.chmod(str(folder), 0o700)
    originals = {}
    for i, path in enumerate(changed):
        if path.exists():
            data=path.read_bytes(); st=path.stat(); backup=folder/str(i)
            backup.write_bytes(data); os.chmod(str(backup),0o600)
            originals[path]=(data, st.st_mode & 0o777, st.st_uid, st.st_gid)
        else:
            originals[path]=None
    index={str(path): (None if record is None else {'file': str(i), 'mode': record[1], 'uid': record[2], 'gid': record[3]})
           for i,(path,record) in enumerate(originals.items())}
    (folder/'files.json').write_text(json.dumps(index,indent=2)+'\n'); os.chmod(str(folder/'files.json'),0o600)
    applied=[]
    try:
        for path,text in changed.items():
            if active_check():
                raise RuntimeError('A game started during emulator registration')
            before=originals[path]
            if (path.exists() != (before is not None) or
                    (before is not None and path.read_bytes()!=before[0])):
                raise RuntimeError('Configuration changed during setup: '+str(path))
            atomic_write(path,text,0o755 if path in executable_paths else 0o644); applied.append(path)
        if active_check():
            raise RuntimeError('A game started during emulator registration')
    except BaseException:
        for path in reversed(applied):
            # Do not overwrite a concurrent writer during recovery.
            if not path.exists() or path.read_text()!=changed[path]:
                continue
            before=originals[path]
            if before is None:
                path.unlink()
            else:
                atomic_write(path,before[0].decode('utf-8'),before[1])
                if os.geteuid()==0: os.chown(str(path),before[2],before[3])
        raise
    return folder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=sorted(PROFILES))
    parser.add_argument('--choice', required=True, help='Existing emulators.cfg entry to wrap')
    parser.add_argument('--routed-command', required=True)
    parser.add_argument('--fallback-sha256', required=True)
    parser.add_argument('--fallback-tested', action='store_true', help='Attest that the exact original launch command was independently tested')
    parser.add_argument('--runtime-user', required=True)
    parser.add_argument('--state-root', required=True, type=Path)
    parser.add_argument('--configs', default=Path('/opt/retropie/configs'), type=Path)
    parser.add_argument('--registry', default=Path('/opt/retropie/support/launchers/native-router-registry.json'), type=Path)
    parser.add_argument('--manifest', default=Path('/etc/controller-router/native-adapters.json'), type=Path)
    parser.add_argument('--provider', default=Path('/opt/controller-router/lib/router_shared/emulator_hosts.py'), type=Path)
    parser.add_argument('--native-launcher', default=Path('/opt/controller-router/bin/native-route'), type=Path)
    parser.add_argument('--computer-launcher', default=Path('/opt/controller-router/bin/computer-launch'), type=Path)
    parser.add_argument('--backup-root', default=Path('/var/backups/controller-router'), type=Path)
    parser.add_argument('--apply', action='store_true', help='Apply changes after independently testing the exact fallback')
    args=parser.parse_args()
    if not args.fallback_tested:
        parser.error('Independently test the original command, then pass --fallback-tested')
    if args.apply and os.geteuid()!=0:
        parser.error('--apply requires administrator privileges')
    if args.apply:
        args.registry.parent.mkdir(parents=True,exist_ok=True)
        lock_path=args.registry.parent/'.controller-router-emulator-setup.lock'
        lock=lock_path.open('a')
        fcntl.flock(lock,fcntl.LOCK_EX)
    changes=plan(args.profile,args.choice,args.routed_command,args.fallback_sha256,args.configs,args.registry,
                 args.manifest,args.provider,args.native_launcher,args.runtime_user,args.state_root,args.computer_launcher)
    print('Profile: %s; independently tested fallback SHA-256: %s' % (args.profile, args.fallback_sha256))
    print('Routed command SHA-256: ' + digest(_validated_route(args.routed_command, args.profile, args.computer_launcher)))
    for path,text in changes.items():
        print(('UNCHANGED ' if path.exists() and path.read_text()==text else 'UPDATE    ')+str(path))
    if args.apply:
        from .controller_router import running_game_session, retroarch_running
        backup=apply_plan(changes,args.backup_root,lambda: retroarch_running() or running_game_session()[0] is not None, (args.computer_launcher,))
        print('Backup: '+str(backup) if backup else 'Already installed; no changes made')
    else:
        print('Dry run; pass --apply to install.')


if __name__ == '__main__':
    main()
