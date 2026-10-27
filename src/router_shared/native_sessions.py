"""Explicit installed host adapters; no emulator-name guessing or ROM discovery."""
import importlib.util
import json
import os
from pathlib import Path

_PROVIDERS = {}
_DOCUMENTS = {}
ADAPTERS = Path('/etc/controller-router/native-adapters.json')

def read_adapters(path=None):
    try:
        source = Path(path or ADAPTERS)
        info = source.stat()
        key = (str(source), info.st_mtime_ns, info.st_size)
        if key in _DOCUMENTS:
            return _DOCUMENTS[key]
        data = json.loads(source.read_text())
        if data.get('schema') != 1 or not isinstance(data.get('providers', []), list):
            return {}
        _DOCUMENTS.clear()
        _DOCUMENTS[key] = data
        return data
    except (OSError, ValueError, TypeError):
        return {}

def running_native_session(proc_root=Path('/proc'), adapters=None):
    """Consult explicitly installed host providers, sharing detection with Setup."""
    from .systems import system_id
    providers = read_adapters(adapters).get('providers', [])
    from .retropie_native import native_session
    found = native_session(proc_root)
    if found[0] is not None:
        return found
    for provider in providers:
        try:
            path = Path(provider['path'])
            if not path.is_absolute() or not path.is_file():
                continue
            # Installed provider paths are administrator-owned configuration,
            # never supplied by the web page or saved player assignments.
            module = load_provider(path)
            core, system = module.native_session(Path(proc_root))
            if core and system:
                return str(core), system_id(system)
        except (OSError, ValueError, KeyError, TypeError, ImportError, AttributeError):
            continue
    return None, None

def registered_systems(path=None):
    return read_adapters(path).get('systems', {})


def launch_policy(path=Path('/run/virtualglove/controller-router-launch.json')):
    """Read the daemon's public launch policy without exposing private assignments."""
    from .systems import policy
    data = json.loads(Path(path).read_text())
    policy(data)
    return data


def load_provider(path):
    path = Path(path)
    info = path.stat()
    key = (str(path), info.st_mtime_ns, info.st_size)
    module = _PROVIDERS.get(key)
    if module is None:
        spec = importlib.util.spec_from_file_location('_router_native_host', str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _PROVIDERS.clear()
        _PROVIDERS[key] = module
    return module


def transform_controls(buttons, axes, core, system, adapters=None):
    """Apply explicitly installed host interpretation outside the generic engine."""
    for provider in read_adapters(adapters).get('providers', []):
        module = load_provider(provider['path'])
        transform = getattr(module, 'transform_controls', None)
        if transform is not None:
            buttons, axes = transform(set(buttons), dict(axes), core, system)
    return buttons, axes
