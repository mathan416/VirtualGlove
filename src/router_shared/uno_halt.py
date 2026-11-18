#!/usr/bin/env python3
"""Install Controller Router's fixed-purpose UNO Q halt helper.

The Router service runs as the unprivileged arduino user and cannot halt Linux.
This root-owned systemd path unit watches one fixed request file in Router's
private state directory and runs ``systemctl --no-block halt``. Router writes
that file only after a paired console's verified shutdown request passes its
checks. Halt stops Linux; it does not remove power from the board.
"""
import os
from pathlib import Path
import subprocess

STATE = '/home/arduino/.local/state/controller-router'
REQUEST = STATE + '/halt-request'
MARKER = STATE + '/.halt-enabled'
PATH_UNIT = 'controller-router-halt.path'
SERVICE_UNIT = 'controller-router-halt.service'
TMPFILES = 'controller-router-halt.conf'

FILES = {
    'etc/systemd/system/' + PATH_UNIT: (
        '# Controller Router: watch for a verified console shutdown request.\n'
        '[Unit]\nDescription=Watch for a Controller Router halt request\n'
        '[Path]\nPathExists=' + REQUEST + '\nUnit=' + SERVICE_UNIT + '\n'
        '[Install]\nWantedBy=multi-user.target\n').encode(),
    'etc/systemd/system/' + SERVICE_UNIT: (
        '# Controller Router: halt Linux after a verified console shutdown request.\n'
        '[Unit]\nDescription=Halt the UNO Q for Controller Router\n'
        'ConditionPathExists=' + MARKER + '\n'
        '[Service]\nType=oneshot\n'
        'ExecStart=/usr/bin/rm -f ' + REQUEST + '\n'
        'ExecStart=/usr/bin/systemctl --no-block halt\n').encode(),
    'etc/tmpfiles.d/' + TMPFILES: (
        '# Controller Router halt helper readiness marker.\n'
        'd ' + STATE + ' 0700 arduino arduino - -\n'
        'f ' + MARKER + ' 0644 arduino arduino - -\n').encode(),
}


def _write(target, content):
    """Write a root-owned file atomically without following symlinks."""
    temporary = target.with_name('.' + target.name + '.tmp')
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'wb') as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(str(temporary), str(target))
    finally:
        if temporary.exists():
            temporary.unlink()


def install(root=Path('/'), runner=subprocess.run, apply=None):
    """Write the helper files; on the live system also create the marker and enable the watcher."""
    root = Path(root).resolve()
    if root == Path('/') and os.geteuid() != 0:
        raise ValueError('Root is required to install the UNO Q halt helper')
    compatible = root / 'proc/device-tree/compatible'
    if b'arduino,imola' not in compatible.read_bytes().split(b'\0'):
        raise ValueError('The halt helper supports Arduino UNO Q only')
    if (root / REQUEST.lstrip('/')).exists():
        raise ValueError('A Controller Router halt request is pending; remove it deliberately before setup')
    changed = False
    for relative, content in FILES.items():
        target = root / relative
        if any(p.is_symlink() for p in (target, *target.parents) if p != root and root in p.parents):
            raise ValueError('Refusing symlink in halt helper path')
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file():
                raise ValueError('Existing halt helper path is not a file; no changes made')
            existing = target.read_bytes()
            if existing == content:
                continue
            if not existing.startswith(b'# Controller Router'):
                raise ValueError('An unrelated file uses the halt helper name; no changes made')
        _write(target, content)
        changed = True
    if not (root == Path('/') if apply is None else apply):
        return 'Halt helper files written.'
    runner(['systemd-tmpfiles', '--create', '/etc/tmpfiles.d/' + TMPFILES], check=True, timeout=30)
    if changed:
        runner(['systemctl', 'daemon-reload'], check=True, timeout=30)
    runner(['systemctl', 'enable', '--now', PATH_UNIT], check=True, timeout=30)
    return ('Installed the Controller Router halt helper.' if changed
            else 'Controller Router halt helper already installed.')


if __name__ == '__main__':
    print(install())
