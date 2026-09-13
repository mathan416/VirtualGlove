#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/configure-uno-q-avahi.py
# Purpose: Restrict Controller mDNS advertisement to physical interfaces.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Added physical-interface allowlisting for host Avahi.
# Full history: docs/CHANGELOG.md and Git history.
"""Keep host mDNS advertisements off Docker bridges and virtual interfaces."""
import argparse
import os
from pathlib import Path
import re
import shutil
import tempfile


def physical_interfaces(root=Path('/sys/class/net')):
    """Return physical Linux interfaces beneath the supplied sysfs root."""
    return sorted(p.name for p in root.iterdir() if (p / 'device').exists())


def configure_text(text, interfaces):
    """Return Avahi configuration with one validated physical allowlist."""
    if not interfaces or any(not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', n) for n in interfaces):
        raise ValueError('At least one valid physical interface is required')
    lines = text.splitlines()
    section = None
    found = False
    output = []
    for line in lines:
        header = re.fullmatch(r'\s*\[([^]]+)\]\s*', line)
        if header:
            section = header[1].strip()
            output.append(line)
            if section == 'server':
                if found:
                    raise ValueError('Duplicate Avahi server section')
                found = True
                output.append('allow-interfaces=' + ','.join(sorted(set(interfaces))))
            continue
        if section == 'server' and re.match(r'\s*allow-interfaces\s*=', line):
            continue
        output.append(line)
    if not found:
        output = ['[server]', 'allow-interfaces=' + ','.join(sorted(set(interfaces))), ''] + output
    return '\n'.join(output) + '\n'


def configure(path, interfaces):
    """Back up and atomically replace Avahi configuration when it changes."""
    if path.is_symlink():
        raise ValueError('Refusing a symbolic Avahi configuration path')
    original = path.read_text()
    updated = configure_text(original, interfaces)
    if original == updated:
        return False
    backup = path.with_name(path.name + '.virtualglove-backup')
    if not backup.exists():
        shutil.copy2(path, backup)
    info = path.stat()
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix='.virtualglove-avahi-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(updated)
        os.chmod(temporary, info.st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/avahi/avahi-daemon.conf'))
    parser.add_argument('--interfaces', nargs='+')
    args = parser.parse_args()
    interfaces = args.interfaces or physical_interfaces()
    changed = configure(args.config, interfaces)
    print(('Updated' if changed else 'Already configured') + ' physical mDNS interfaces: ' + ', '.join(interfaces))
