#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/rotate-deployment-backups.py
# Purpose: Bound routine deployment backups without touching named engineering evidence.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Deferred annotations for Python 3.7 runtime compatibility.
#   2026-09-10 - Added conservative post-deployment payload-backup rotation.
# Full history: docs/CHANGELOG.md and Git history.

"""Retain recent routine payload backups and preserve every specially named backup."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil


ROUTINE_BACKUP = re.compile(r"(?:payload-)?(\d{8})-(\d{6})-(\d+)")
KEEP_MARKER = ".virtualglove-keep"


def _routine_backups(root: Path) -> list[Path]:
    """Return strictly named routine backups from newest to oldest."""
    found = []
    for path in root.iterdir():
        match = ROUTINE_BACKUP.fullmatch(path.name)
        if (not match or path.is_symlink() or not path.is_dir()
                or (path / KEEP_MARKER).exists()):
            continue
        found.append((match.groups(), path))
    return [path for _key, path in sorted(found, reverse=True)]


def rotate(root: Path, keep: int = 12, *, dry_run: bool = False) -> list[Path]:
    """Remove old routine backups only; return the selected paths."""
    if not 2 <= keep <= 100:
        raise ValueError("keep must be between 2 and 100")
    root = root.absolute()
    if root == Path(root.anchor) or root == Path.home() or root.is_symlink():
        raise ValueError("refusing unsafe backup root")
    if not root.exists():
        return []
    if not root.is_dir():
        raise ValueError("backup root is not a directory")
    stale = _routine_backups(root)[keep:]
    for path in stale:
        if path.parent != root or not ROUTINE_BACKUP.fullmatch(path.name):
            raise ValueError("refusing unsafe backup path")
        if not dry_run:
            shutil.rmtree(path)
    return stale


def main() -> int:
    """Parse rotation policy, remove selected routine backups, and report it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--keep", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    removed = rotate(args.root, args.keep, dry_run=args.dry_run)
    verb = "Would remove" if args.dry_run else "Removed"
    print(f"Deployment backup rotation: {verb.lower()} {len(removed)} old routine backup(s); kept the newest {args.keep} and every named backup.")
    for path in removed:
        print(f"  {verb}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
