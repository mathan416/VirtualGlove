# Project: VirtualGlove
# File: src/virtualglove/runtime_assets.py
# Purpose: Download, verify, cache, and atomically install third-party runtime model assets.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-03 - Added with standardized source documentation.
# Full history: docs/CHANGELOG.md and Git history.

"""Verified first-run retrieval of third-party runtime assets."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional


HAND_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
BUNDLED_HAND_LANDMARKER = Path(__file__).resolve().parents[2] / "models" / "hand_landmarker.task"
HAND_LANDMARKER_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file read in bounded blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_hand_landmarker_model(
    data_directory: Path,
    url: str = HAND_LANDMARKER_URL,
    expected_sha256: str = HAND_LANDMARKER_SHA256,
    opener: Optional[Callable] = None,
    bundled_path: Optional[Path] = None,
) -> Path:
    """Reuse cache, then install the bundled model; download only if absent."""
    destination = Path(data_directory) / "models" / "hand_landmarker.task"
    if destination.is_file() and sha256_file(destination) == expected_sha256:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="hand_landmarker.task.", suffix=".download", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    open_url = opener or urllib.request.urlopen
    try:
        bundle = Path(bundled_path) if bundled_path is not None else BUNDLED_HAND_LANDMARKER
        with os.fdopen(descriptor, "wb") as output:
            if bundle.is_file():
                with bundle.open("rb") as source:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            else:
                with open_url(url, timeout=60) as response:
                    shutil.copyfileobj(response, output, 1024 * 1024)
        actual_sha256 = sha256_file(temporary)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                "Hand Landmarker checksum mismatch "
                f"(expected {expected_sha256}, received {actual_sha256})"
            )
        temporary.chmod(0o600)
        os.replace(temporary, destination)
        return destination
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
