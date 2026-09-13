#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/installation-manifest.py
# Purpose: Track and transactionally update application-owned files without deleting local changes.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added managed installation inventory and recovery.
# Full history: docs/CHANGELOG.md and Git history.

"""Manage application payloads; private settings and host service configuration are excluded."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile

MANIFEST = '.virtualglove-install.json'
JOURNAL = '.virtualglove-install-pending.json'
LOCK = '.virtualglove-install.lock'
LEGACY_MANIFEST = '.powerglove-install.json'
LEGACY_JOURNAL = '.powerglove-install-pending.json'
LEGACY_LOCK = '.powerglove-install.lock'
PRIVATE = {'data', '.cache', '.git', '.venv', '__pycache__'}
PRESERVED = {'docs/cheatsheet.md'}
REPLACED = {'config/profiles.json'}


def relative(name):
    """Reject noncanonical, private, and installer-control paths before any mutation."""
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name or '..' in path.parts
            or '\\' in name or set(path.parts) & PRIVATE or name in PRESERVED
            or any(part.startswith(('.virtualglove-install', '.powerglove-install')) for part in path.parts)):
        raise ValueError('Unsafe managed path: ' + name)
    return name


def safe(path):
    """Reject symlink ancestors and special files, including dangling links."""
    for part in [path] + list(path.parents):
        if part.is_symlink():
            raise ValueError('Refusing symbolic installation path: ' + str(part))
        if part != path and part.exists() and not part.is_dir():
            raise ValueError('Expected a directory: ' + str(part))
    if path.exists() and not path.is_file():
        raise ValueError('Expected a regular file: ' + str(path))
    return path


def fingerprint(path):
    """Hash bytes and permissions without loading large assets into memory."""
    safe(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode > 0o777: raise ValueError('Unsupported managed permissions: ' + str(path))
    return {'sha256': digest.hexdigest(), 'mode': mode}


def atomic(path, data, mode=0o644):
    """Replace one regular file atomically, retaining an existing file's owner."""
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = path.stat() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix='.virtualglove-install-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if owner and os.geteuid() == 0:
            os.chown(temporary, owner.st_uid, owner.st_gid)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def read_manifest(root):
    """Read a strict root-bound inventory; never treat invalid data as a fresh install."""
    current = safe(root / MANIFEST)
    legacy = safe(root / LEGACY_MANIFEST)
    path = current if current.exists() else legacy
    if not path.exists(): return {'format': 1, 'root': str(root), 'files': {}}
    value = json.loads(path.read_text())
    if (not isinstance(value, dict) or value.get('format') != 1 or value.get('root') != str(root)
            or not isinstance(value.get('files'), dict)):
        raise ValueError('Invalid installation manifest')
    for name, record in value['files'].items():
        relative(name)
        if (not isinstance(record, dict) or set(record) != {'sha256', 'mode'}
                or not isinstance(record['sha256'], str) or len(record['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in record['sha256'])
                or type(record['mode']) is not int or not 0 <= record['mode'] <= 0o777):
            raise ValueError('Invalid manifest fingerprint: ' + name)
        safe(root / name)
    return value


def check(root):
    """Report missing, modified, and interrupted installations without writing anything."""
    root = Path(root).absolute()
    result = []
    if not safe(root / MANIFEST).exists() and not safe(root / LEGACY_MANIFEST).exists():
        result.append('No installation manifest; next update establishes a baseline')
    if safe(root / JOURNAL).exists() or safe(root / LEGACY_JOURNAL).exists():
        result.append('Interrupted update: run the matching installed installation-manifest.py ROOT --recover')
    for name, record in read_manifest(root)['files'].items():
        path = root / name
        if not path.exists(): result.append('Missing: ' + name)
        elif fingerprint(path) != record: result.append('Locally modified: ' + name)
    return result


@contextlib.contextmanager
def locked(root):
    """Serialize payload mutations without following a substituted lock symlink."""
    root.mkdir(parents=True, exist_ok=True)
    legacy_lock = root / LEGACY_LOCK
    paths = ([legacy_lock] if legacy_lock.exists() or (root / LEGACY_MANIFEST).exists()
             or (root / LEGACY_JOURNAL).exists() else []) + [root / LOCK]
    for path in paths:
        safe(path)
    fds = []
    try:
        for path in paths:
            fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fds.append(fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        for fd in reversed(fds):
            os.close(fd)


def rollback(root):
    """Restore the backed-up payload after a failed or interrupted transaction."""
    journal = safe(root / JOURNAL)
    if not journal.exists(): return
    state = json.loads(journal.read_text())
    if not isinstance(state, dict) or state.get('root') != str(root) or state.get('format') != 1:
        raise ValueError('Invalid recovery journal')
    backup = Path(state['backup'])
    entries = state['entries']
    for name, existed in entries.items():
        if name not in (MANIFEST, LEGACY_MANIFEST, LEGACY_LOCK) and not (name in PRESERVED and existed is False):
            relative(name)
        safe(root / name)
        if type(existed) is not bool: raise ValueError('Invalid recovery entry')
        if existed: safe(backup / name).read_bytes()
    for name, existed in entries.items():
        target = root / name
        if existed:
            saved = backup / name
            atomic(target, saved.read_bytes(), stat.S_IMODE(saved.stat().st_mode))
            if os.geteuid() == 0: os.chown(str(target), saved.stat().st_uid, saved.stat().st_gid)
        elif target.exists(): target.unlink()
    journal.unlink()


def apply(source, root, backup, names=None):
    """Back up, replace and prune a payload, then commit its inventory last."""
    source, root, backup = Path(source).absolute(), Path(root).absolute(), Path(backup).absolute()
    safe(backup / 'transaction.json')
    if root == backup or root in backup.parents or source == backup or source in backup.parents:
        raise ValueError('Backups must be outside source and installation trees')
    if source == root: raise ValueError('Use a separate release staging directory')
    with locked(root):
        if safe(root / JOURNAL).exists():
            raise ValueError('Interrupted update; recover before retrying: ' + str(root / JOURNAL))
        if safe(root / LEGACY_JOURNAL).exists():
            raise ValueError('Interrupted legacy update; recover it with the previously installed updater first: ' + str(root / LEGACY_JOURNAL))
        previous = read_manifest(root)
        if names is None:
            names = []
            for path in source.rglob('*'):
                if path.is_symlink(): raise ValueError('Refusing symbolic release path: ' + str(path))
                if path.is_dir(): continue
                safe(path)
                names.append(str(path.relative_to(source)))
        incoming = {}
        for name in names:
            if name in PRESERVED:
                safe(source / name); safe(root / name)
                if (root / name).exists() and fingerprint(source / name) != fingerprint(root / name):
                    print('ACTION  Personal settings preserved; review new defaults separately: ' + name)
                continue
            relative(name)
            incoming[name] = fingerprint(source / name)
        names = sorted(set(names))
        inventory, writes, deletes, kept = {}, [], [], []
        for name, record in incoming.items():
            target = safe(root / name)
            old = previous['files'].get(name)
            current = fingerprint(target) if target.exists() else None
            if old and current is not None and current != old and current != record and name not in REPLACED:
                inventory[name] = old
                kept.append(name)
            else:
                inventory[name] = record
                if current != record: writes.append(name)
        for name, record in previous['files'].items():
            if name in incoming: continue
            target = safe(root / name)
            if target.exists():
                if fingerprint(target) == record: deletes.append(name)
                else:
                    kept.append(name)
                    inventory[name] = record
        for name in names:
            if name in PRESERVED and not (root / name).exists(): writes.append(name)
        # Preserved settings are never entered into the ownership inventory.
        for name in writes:
            if name not in PRESERVED: relative(name)
        release = json.loads((source / 'install-release.json').read_text()).get('version', 'development') if (source / 'install-release.json').is_file() else 'development'
        new = {'format': 1, 'root': str(root), 'release': release, 'files': inventory}
        data = (json.dumps(new, sort_keys=True, indent=2) + '\n').encode()
        if not writes and not deletes and (root / MANIFEST).exists() and (root / MANIFEST).read_bytes() == data:
            for name in kept: print('ACTION  Local change preserved: ' + name)
            return {'removed': [], 'preserved': kept}
        backup.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup.chmod(0o700)
        entries = {}
        control_files = [MANIFEST]
        if (root / LEGACY_MANIFEST).exists(): control_files.append(LEGACY_MANIFEST)
        if (root / LEGACY_LOCK).exists(): control_files.append(LEGACY_LOCK)
        for name in writes + deletes + control_files:
            target = safe(root / name)
            entries[name] = target.exists()
            if target.exists():
                saved = safe(backup / name)
                if saved.exists(): raise ValueError('Use a new backup directory: ' + str(backup))
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(target), str(saved))
                if os.geteuid() == 0: os.chown(str(saved), target.stat().st_uid, target.stat().st_gid)
        (backup / 'RESTORE.txt').write_text('Payload root: '+str(root)+'\nFor an interrupted update, run installation-manifest.py ROOT --recover.\nFor a completed update, stop the app and restore selected backed-up files and the previous manifest; restart afterward.\n')
        recovery = (json.dumps({'format':1,'root':str(root),'backup':str(backup),'entries':entries})+'\n').encode()
        atomic(backup / 'transaction.json', recovery, 0o600)
        atomic(root / JOURNAL, recovery, 0o600)
        try:
            for name in writes:
                atomic(root / name, (source / name).read_bytes(), fingerprint(source / name)['mode'])
            for name in writes:
                if name in incoming and fingerprint(root / name) != incoming[name]:
                    raise ValueError('Release changed during installation: ' + name)
            for name in deletes: safe(root / name).unlink()
            atomic(root / MANIFEST, data)
            for legacy in (LEGACY_MANIFEST, LEGACY_LOCK):
                if (root / legacy).exists(): safe(root / legacy).unlink()
            (root / JOURNAL).unlink()
        except BaseException:
            rollback(root)
            raise
        print('Manifest: %d files; removed %d obsolete files; retained %d local changes. Backup: %s' % (len(inventory),len(deletes),len(kept),backup))
        for name in kept: print('ACTION  Local change preserved: ' + name)
        return {'removed': deletes, 'preserved': kept}


def main():
    """Expose the same inventory checks and update logic to Wi-Fi deployment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument('--source', type=Path)
    options.add_argument('--check', action='store_true')
    options.add_argument('--recover', action='store_true')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if args.check:
        issues = check(args.root)
        for issue in issues: print(issue)
        return int(bool(issues))
    if args.recover:
        with locked(args.root): rollback(args.root.absolute())
    else:
        if args.backup is None: parser.error('--source requires --backup')
        apply(args.source, args.root, args.backup)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
