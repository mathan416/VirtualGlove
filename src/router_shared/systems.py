"""Console system discovery and shared per-system routing policy."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

# Display labels do not change the IDs stored in routing settings.
LABELS = {
    'amiga': 'Amiga', 'amigacd32': 'Amiga CD32', 'amstradcpc': 'Amstrad CPC',
    'apple2': 'Apple II', 'arcade': 'Arcade', 'atari2600': 'Atari 2600',
    'atari5200': 'Atari 5200', 'atari7800': 'Atari 7800', 'atari800': 'Atari 800',
    'atarijaguar': 'Atari Jaguar', 'atarilynx': 'Atari Lynx', 'atarist': 'Atari ST',
    'c64': 'Commodore 64', 'colecovision': 'ColecoVision', 'dreamcast': 'Dreamcast',
    'famicom': 'Famicom', 'fds': 'Famicom Disk System', 'gameandwatch': 'Game & Watch',
    'gamegear': 'Game Gear', 'gb': 'Game Boy', 'gba': 'Game Boy Advance',
    'gbc': 'Game Boy Color', 'gc': 'GameCube', 'intellivision': 'Intellivision',
    'mame': 'MAME', 'mastersystem': 'Master System', 'megadrive': 'Mega Drive / Genesis',
    'msx': 'MSX', 'msx1': 'MSX', 'msx2': 'MSX2', 'n64': 'Nintendo 64',
    'naomi': 'NAOMI', 'nds': 'Nintendo DS', 'neogeo': 'Neo Geo',
    'neogeocd': 'Neo Geo CD', 'nes': 'NES', 'ngp': 'Neo Geo Pocket',
    'ngpc': 'Neo Geo Pocket Color', 'odyssey2': 'Odyssey²', 'pc88': 'PC-88',
    'pc98': 'PC-98', 'pcengine': 'PC Engine', 'pcenginecd': 'PC Engine CD',
    'pcfx': 'PC-FX', 'ps2': 'PlayStation 2', 'psp': 'PSP', 'psx': 'PlayStation',
    'saturn': 'Sega Saturn', 'scummvm': 'ScummVM', 'sega32x': 'Sega 32X',
    'segacd': 'Sega CD', 'sg-1000': 'SG-1000', 'sg1000': 'SG-1000',
    'snes': 'Super Nintendo', 'supergrafx': 'SuperGrafx', 'vectrex': 'Vectrex',
    'virtualboy': 'Virtual Boy', 'wii': 'Wii', 'wonderswan': 'WonderSwan',
    'wonderswancolor': 'WonderSwan Color', 'x68000': 'Sharp X68000',
    'zmachine': 'Z-Machine', 'zx81': 'ZX81', 'zxspectrum': 'ZX Spectrum',
}


def system_label(ident, fullname=None):
    """Use familiar names, then the console's own display name for custom systems."""
    return LABELS.get(ident) or (fullname.strip() if fullname else '') or ident.replace('_', ' ').title()


def retropie_names(systems_file=None):
    """Read EmulationStation names without changing its configuration."""
    candidates = ([Path(systems_file)] if systems_file else
                  [Path('/home/pi/.emulationstation/es_systems.cfg'),
                   Path('/etc/emulationstation/es_systems.cfg')])
    for candidate in candidates:
        try:
            items = ET.parse(candidate).getroot().findall('system')
        except (OSError, ET.ParseError):
            continue
        names = {}
        for item in items:
            try:
                ident = system_id(item.findtext('name', ''))
            except ValueError:
                continue
            names[ident] = item.findtext('fullname', '')
        return names
    return {}


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


def catalog(platform, config, root=None, systems_file=None):
    """Discover console-local systems; retain saved selections when absent."""
    found = {'nes': LABELS['nes']}
    native = set()
    names = retropie_names(systems_file) if platform == 'retropie' else {}
    if platform == 'retropie':
        base = Path(root or '/opt/retropie/configs')
        for path in base.glob('*/emulators.cfg'):
            try:
                ident = system_id(path.parent.name)
            except ValueError:
                continue
            try:
                text = path.read_text(errors='replace')
            except OSError:
                continue
            entries = dict(re.findall(r'^\s*([\w-]+)\s*=\s*"([^"\n]*)"', text, re.M))
            default = entries.get('default')
            commands = [entries.get(default, '')] if default else list(entries.values())
            if any('/retroarch' in command for command in commands):
                found[ident] = system_label(ident, names.get(ident))
            else:
                native.add(ident)
                found.pop(ident, None)
    else:
        base = Path(root or '/usr/share/emulationstation/es_systems.cfg')
        try:
            for item in ET.parse(base).getroot().findall('system'):
                try:
                    ident = system_id(item.findtext('name', ''))
                except ValueError:
                    continue
                if not item.findall("./emulators/emulator[@name='libretro']"):
                    native.add(ident)
                    found.pop(ident, None)
                    continue
                found[ident] = system_label(ident, item.findtext('fullname'))
        except (OSError, ET.ParseError, ValueError):
            pass
    scope, selected = policy(config)
    for ident in selected:
        if ident not in native:
            found.setdefault(ident, system_label(ident, names.get(ident)))
    return [{'id': ident, 'name': label, 'enabled': scope == 'all' or
             ident in (['nes'] if scope == 'nes' else selected)}
            for ident, label in sorted(found.items(), key=lambda row: row[1])]
