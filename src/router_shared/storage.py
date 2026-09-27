"""Atomic Router configuration writes that preserve console file ownership."""

from __future__ import annotations

import os
import pwd
import tempfile
from pathlib import Path


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
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
