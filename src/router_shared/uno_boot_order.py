#!/usr/bin/env python3
"""Install an ordering-only UNO Q App Lab systemd drop-in on eligible boards."""
import os
from pathlib import Path
import subprocess

UNIT = 'arduino-burn-bootloader-unoq.service'
DROPIN = '50-controller-router-boot-order.conf'
CONTENT = ('# Let the enabled first-boot bootloader writer finish before App Lab starts.\n'
           '# Ordering only: do not enable, pull in, or otherwise start a disabled writer.\n'
           '[Unit]\nAfter=arduino-burn-bootloader-unoq.service\n').encode()


def _effective_order(runner):
    """Read the manager's effective ordering, not only our drop-in file."""
    result = runner(['systemctl', 'show', 'arduino-app-cli.service', '-p', 'After', '--value'],
                    check=True, text=True, capture_output=True, timeout=10)
    return UNIT in result.stdout.split()


def install(root=Path('/'), runner=subprocess.run):
    root = Path(root).resolve()
    if root == Path('/') and os.geteuid() != 0:
        raise ValueError('Root is required to install the UNO Q system service drop-in')
    compatible = root / 'proc/device-tree/compatible'
    if b'arduino,imola' not in compatible.read_bytes().split(b'\0'):
        raise ValueError('This ordering rule supports Arduino UNO Q only')
    app = runner(['systemctl', 'show', 'arduino-app-cli.service', '-p', 'LoadState'],
                 check=True, text=True, capture_output=True, timeout=10)
    if 'LoadState=loaded' not in app.stdout.splitlines():
        return 'App Lab system service is not loaded; no ordering drop-in installed.'
    result = runner(['systemctl', 'show', UNIT, '-p', 'LoadState', '-p', 'UnitFileState', '-p', 'Type'],
                    check=True, text=True, capture_output=True, timeout=10)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if fields.get('LoadState') != 'loaded':
        return 'Bootloader writer not present; no ordering drop-in installed.'
    if fields.get('Type') != 'oneshot':
        raise ValueError('Bootloader writer has unexpected unit type; no changes made')
    base = root / 'etc/systemd/system'
    directory = base / 'arduino-app-cli.service.d'
    target = directory / DROPIN
    if any(p.is_symlink() for p in (base, directory, target, *base.parents) if p != root and root in p.parents):
        raise ValueError('Refusing symlink in systemd drop-in path')
    directory.mkdir(mode=0o755, exist_ok=True)
    if target.exists():
        if not target.is_file() or target.read_bytes() != CONTENT:
            raise ValueError('Existing Controller Router drop-in differs; no changes made')
        if not _effective_order(runner):
            runner(['systemctl', 'daemon-reload'], check=True, timeout=30)
            if not _effective_order(runner):
                raise RuntimeError('App Lab bootloader ordering is not effective; existing drop-in retained')
        return 'Bootloader ordering drop-in already installed and effective.'
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'wb') as out:
            out.write(CONTENT)
            out.flush()
            os.fsync(out.fileno())
        runner(['systemctl', 'daemon-reload'], check=True, timeout=30)
        if not _effective_order(runner):
            raise RuntimeError('App Lab bootloader ordering is not effective; new drop-in rolled back')
    except BaseException:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        try:
            runner(['systemctl', 'daemon-reload'], check=True, timeout=30)
        except Exception:
            pass
        raise
    return 'Installed ordering-only drop-in; it takes effect on the next service start or boot.'


if __name__ == '__main__':
    print(install())
