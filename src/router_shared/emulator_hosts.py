"""Opt-in host provider for qualified emulator-specific behavior.

Install as an administrator-owned native provider. Configuration is never read
from player assignments or browser requests.
"""
import json
from pathlib import Path
from router_shared.loader_session import loader_session

CONFIG = Path('/etc/controller-router/emulator-hosts.json')


def read_config():
    try:
        data = json.loads(CONFIG.read_text())
        if data.get('schema') != 1:
            return {}
        return data
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def native_session(proc_root=Path('/proc')):
    entries = read_config().get('loader_sessions', [])
    if not isinstance(entries, list):
        return None, None
    for entry in entries:
        try:
            if not isinstance(entry, dict):
                continue
            match = loader_session(proc_root, **entry)
            if match[0] is not None:
                return match
        except (ValueError, TypeError):
            continue
    return None, None


def transform_controls(buttons, axes, core, system):
    settings = read_config()
    if settings.get('flycast_dreamcast_controls') is not True:
        return buttons, axes
    if core != 'flycast-native' and not (system == 'dreamcast' and core in (
            'native-merged', 'dreamcast-native', 'flycast_libretro.so', 'reicast_libretro.so')):
        return buttons, axes
    buttons, axes = set(buttons), dict(axes)
    if 'l1' in buttons:
        buttons.add('l2')
    if 'r1' in buttons:
        buttons.add('r2')
    for analog, hat in (('lx', 'hat_x'), ('ly', 'hat_y')):
        if not axes.get(analog, 0) and axes.get(hat, 0):
            axes[analog] = 32767 if axes[hat] > 0 else -32768
    return buttons, axes
