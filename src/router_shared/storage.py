"""Atomic Router configuration writes that preserve console file ownership."""

from __future__ import annotations

import os
import pwd
import re
import tempfile
import time
from pathlib import Path


# mkstemp names are "." + target name + "." + 8 characters from this set.
_TEMPORARY_SUFFIX = re.compile(r"\.[a-z0-9_]{8}$")


def remove_stale_temporaries(path: Path, older_than: float = 60) -> None:
    """Delete temporaries a killed writer left beside path; keep recent ones."""
    path = Path(path)
    prefix = "." + path.name
    cutoff = time.time() - older_than
    try:
        candidates = list(path.parent.iterdir())
    except OSError:
        return
    for candidate in candidates:
        name = candidate.name
        if not name.startswith(prefix) or not _TEMPORARY_SUFFIX.fullmatch(name[len(prefix):]):
            continue
        try:
            if candidate.is_file() and not candidate.is_symlink() and candidate.stat().st_mtime < cutoff:
                candidate.unlink()
        except OSError:
            pass


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    remove_stale_temporaries(path)
    previous = path.stat() if path.exists() else None
    retro_pie_config = str(path).startswith("/opt/retropie/configs/")
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), previous.st_mode & 0o777 if previous else mode)
            if os.geteuid() == 0:
                if retro_pie_config:
                    account = pwd.getpwnam("pi")
                    os.fchown(stream.fileno(), account.pw_uid, account.pw_gid)
                elif previous:
                    os.fchown(stream.fileno(), previous.st_uid, previous.st_gid)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
