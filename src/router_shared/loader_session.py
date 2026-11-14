"""Explicit identity-checked loader sessions for host adapters."""
import os
from pathlib import Path


def loader_session(proc_root, *, loader, frontend, core_argument, config_argument,
                   installed_core, system, core_name):
    """Detect a configured session; never infer support from executable names."""
    if not all(Path(p).is_absolute() for p in (loader, frontend, core_argument, config_argument, installed_core)):
        raise ValueError('All paths must be absolute')
    try:
        processes = tuple(Path(proc_root).iterdir())
    except OSError:
        return None, None
    for process in processes:
        if not process.name.isdigit():
            continue
        try:
            args = [os.fsdecode(x) for x in (process / 'cmdline').read_bytes().split(b'\0') if x]
            if not args or args[0] != str(loader) or str(frontend) not in args:
                continue
            if args.count('-L') != 1 or args.count('--config') != 1:
                continue
            if args[args.index('-L') + 1] != str(core_argument) or args[args.index('--config') + 1] != str(config_argument):
                continue
            root = process / 'root'
            if not os.path.samefile(root / str(core_argument).lstrip('/'), installed_core):
                continue
            if not os.path.samefile(process / 'exe', root / str(loader).lstrip('/')):
                continue
            return core_name, system
        except (OSError, ValueError, IndexError):
            continue
    return None, None
