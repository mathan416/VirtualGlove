"""Merge administrator-qualified emulator providers into the native catalogue."""
import hashlib
import json
import re
from pathlib import Path
from .launch_install import replace_owned
from .systems import system_id


def register(provider, specification, manifest):
    """Register explicit host entries without replacing unrelated registrations.

    The administrator-owned specification lists exact emulators.cfg commands.
    Missing specifications are an intentional no-op. Refuse stale or malformed
    qualifications before writing anything.
    """
    provider, specification, manifest = map(Path, (provider, specification, manifest))
    if not specification.exists():
        return False
    doc = json.loads(specification.read_text())
    if doc.get('schema') != 1 or not isinstance(doc.get('systems'), list):
        raise ValueError('Invalid emulator host qualification')
    if not provider.is_absolute() or not provider.is_file():
        raise ValueError('Installed emulator provider is missing')
    existing = json.loads(manifest.read_text()) if manifest.exists() else {'schema': 1, 'providers': [], 'systems': {}}
    if existing.get('schema') != 1 or not isinstance(existing.get('providers'), list) or not isinstance(existing.get('systems'), dict):
        raise ValueError('Invalid existing native adapter manifest')
    additions = {}
    for row in doc['systems']:
        path = Path(row['config'])
        ident = system_id(row['system'])
        kind = row['kind']
        hashes = row['command_sha256']
        if not path.is_absolute() or kind not in ('native', 'custom-libretro') or not isinstance(hashes, list) or not hashes:
            raise ValueError('Invalid qualified system')
        if any(not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h) for h in hashes):
            raise ValueError('Invalid qualified command hash')
        commands = re.findall(r'^\s*[\w-]+\s*=\s*"([^"\n]*)"', path.read_text(), re.M)
        current = {hashlib.sha256(command.encode()).hexdigest() for command in commands}
        if not set(hashes).issubset(current):
            raise ValueError('Qualified emulator command changed: ' + str(path))
        previous = existing['systems'].get(str(path))
        if previous and (previous.get('system') != ident or previous.get('kind') != kind):
            raise ValueError('Existing native registration conflicts: ' + str(path))
        merged = dict(previous or {})
        merged.update(system=ident, kind=kind, command_sha256=sorted(set((previous or {}).get('command_sha256', []) + hashes)))
        additions[str(path)] = merged
    if not any(p.get('path') == str(provider) for p in existing['providers'] if isinstance(p, dict)):
        existing['providers'].append({'path': str(provider)})
    existing['systems'].update(additions)
    return replace_owned(manifest, json.dumps(existing, indent=2) + '\n')


def discover_native_hosts(configs, registry):
    """Identify already registered private bridges using exact installed commands."""
    import shlex
    profiles = {'archimedes': 'arcem', 'apple2gs': 'gsplus', 'samcoupe': 'simcoupe'}
    data = json.loads(Path(registry).read_text())
    entries, runtime = data.get('entries', {}), data.get('runtime', {})
    launcher = Path(runtime.get('launcher', ''))
    if not isinstance(entries, dict) or not launcher.is_absolute() or not launcher.is_file():
        raise ValueError('Invalid installed native registry')
    found = []
    for system, emulator in profiles.items():
        config = Path(configs) / system / 'emulators.cfg'
        if not config.is_file():
            continue
        rows = dict(re.findall(r'^\s*([\w-]+)\s*=\s*"([^"\n]*)"', config.read_text(), re.M))
        command = rows.get(emulator)
        if not command:
            continue
        try:
            args = shlex.split(command)
            start = 1 if args and Path(args[0]).name.startswith('python3') else 0
            if len(args) <= start or Path(args[start]) != launcher or args.count('--entry') != 1:
                continue
            entry_id = args[args.index('--entry') + 1]
            entry = entries[entry_id]
            original = shlex.split(entry['command'])
            original_start = 1 if original and Path(original[0]).name.startswith('python3') else 0
            if (entry.get('system') != system or entry.get('emulator') != emulator
                    or Path(entry.get('config', '')) != config or not entry.get('private_bridge')
                    or len(original) <= original_start or not Path(original[original_start]).is_file()):
                continue
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        found.append({'config': str(config), 'system': system, 'kind': 'native',
                      'command_sha256': [hashlib.sha256(command.encode()).hexdigest()]})
    return found


def auto_register(provider, configs, registry, manifest):
    """Merge known installed host bridges, leaving unrecognized hosts unchanged."""
    import tempfile
    registry = Path(registry)
    if not registry.is_file():
        return False
    rows = discover_native_hosts(configs, registry)
    if not rows:
        return False
    # Reuse the existing validated merge without leaving a qualification file.
    with tempfile.TemporaryDirectory(prefix='router-host-qualification-') as tmp:
        spec = Path(tmp) / 'qualification.json'
        spec.write_text(json.dumps({'schema': 1, 'systems': rows}))
        return register(provider, spec, manifest)
