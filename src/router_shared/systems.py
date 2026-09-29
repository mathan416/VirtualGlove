"""Console system discovery and shared per-system routing policy."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

LABELS = {'nes': 'NES', 'megadrive': 'Mega Drive / Genesis', 'psp': 'PSP',
          'snes': 'Super Nintendo', 'gb': 'Game Boy', 'gbc': 'Game Boy Color',
          'gba': 'Game Boy Advance', 'mastersystem': 'Master System',
          'gamegear': 'Game Gear', 'pcengine': 'PC Engine', 'psx': 'PlayStation'}


def system_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,47}', value):
        raise ValueError('Invalid console system ID.')
    return {'genesis': 'megadrive'}.get(value, value)


def policy(data):
    scope = data.get('physical_scope', 'all')  # Preserve released legacy behavior.
    if scope not in ('nes', 'all', 'systems'):
        raise ValueError('Choose NES, all Libretro systems, or selected systems.')
    selected = data.get('physical_systems', [])
    if not isinstance(selected, list) or len(selected) > 256:
        raise ValueError('Invalid selected systems.')
    return scope, sorted(set(system_id(item) for item in selected))


def routes(config, core, system=None, nes_cores=()):
    if core is None:
        return False
    scope, selected = policy(config)
    if scope == 'all':
        return True
    if system is None:
        # Compatibility for existing NES integrations before explicit identity.
        return scope == 'nes' and core in nes_cores
    return system_id(system) in (['nes'] if scope == 'nes' else selected)


def argument_system(arguments):
    """Read old RetroPie launches without guessing from a shared emulator core."""
    for index, value in enumerate(arguments):
        candidate = value.split('=', 1)[1] if value.startswith('--config=') else (
            arguments[index + 1] if value in ('--config', '-c') and index + 1 < len(arguments) else None)
        if candidate:
            parts = Path(candidate).parts
            if parts[:4] == ('/', 'opt', 'retropie', 'configs') and len(parts) > 5:
                return system_id(parts[4])
    return None


def catalog(platform, config, root=None):
    """Discover console-local systems; retain saved selections when absent."""
    found = {'nes': LABELS['nes']}
    native = set()
    if platform == 'retropie':
        base = Path(root or '/opt/retropie/configs')
        for path in base.glob('*/emulators.cfg'):
            try:
                ident = system_id(path.parent.name)
            except ValueError:
                continue
            entries = dict(re.findall(r'^\s*([\w-]+)\s*=\s*"([^"\n]*)"',
                                      path.read_text(errors='replace'), re.M))
            default = entries.get('default')
            commands = [entries.get(default, '')] if default else list(entries.values())
            if any('/retroarch' in command for command in commands):
                found[ident] = LABELS.get(ident, ident.replace('_', ' ').title())
            else:
                native.add(ident)
                found.pop(ident, None)
    else:
        base = Path(root or '/usr/share/emulationstation/es_systems.cfg')
        try:
            for item in ET.parse(base).getroot().findall('system'):
                ident = system_id(item.findtext('name', ''))
                if not item.findall("./emulators/emulator[@name='libretro']"):
                    native.add(ident)
                    found.pop(ident, None)
                    continue
                found[ident] = LABELS.get(ident, item.findtext('fullname') or ident.title())
        except (OSError, ET.ParseError, ValueError):
            pass
    scope, selected = policy(config)
    for ident in selected:
        if ident not in native:
            found.setdefault(ident, LABELS.get(ident, ident.title()))
    return [{'id': ident, 'name': label, 'enabled': scope == 'all' or
             ident in (['nes'] if scope == 'nes' else selected)}
            for ident, label in sorted(found.items(), key=lambda row: row[1])]
