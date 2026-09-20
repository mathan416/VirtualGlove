#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/build-engineering-tools-package.py
# Purpose: Build a separate source toolkit for repeatable research and diagnostics.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Curated a reproducible, self-checking toolkit with technical onboarding.
#   2026-09-09 - Added the optional Engineering Tools archive.
# Full history: docs/CHANGELOG.md and Git history.

"""Package development tools without adding them to ordinary installers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = runpy.run_path(str(Path(__file__).with_name("package-inventory.py")))
ENGINEERING_TOOLKIT_FILES = INVENTORY["ENGINEERING_TOOLKIT_FILES"]
TOOLKIT_CATEGORIES = INVENTORY["TOOLKIT_CATEGORIES"]
SUPPORT_ROOTS = ("src/virtualglove/", "config/")
SUPPORT_FILES = {
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "docs/ENGINEERING_TOOLKIT.md",
    "native/nestopia-powerglove/diagnostic_trace.h",
    "native/nestopia-powerglove/nestopia-powerglove.patch",
    "pyproject.toml",
}
ARCHIVE_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
FORBIDDEN_ARCHIVE_SUFFIXES = (".so", ".dll", ".dylib", ".a", ".tar.gz")


def write_member(
    archive: zipfile.ZipFile, name: str, content: bytes | str, mode: int = 0o644
) -> None:
    """Write one member with normalized metadata for reproducible archives."""
    info = zipfile.ZipInfo(name)
    info.date_time = ARCHIVE_TIMESTAMP
    info.create_system = 3
    info.external_attr = mode << 16
    payload = content.encode() if isinstance(content, str) else content
    archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED)


def selected_files(root: Path = ROOT) -> list[str]:
    """Return the self-contained, source-only engineering toolkit."""
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    ).decode().split("\0")
    selected = []
    for name in tracked:
        path = root / name
        if not name or not path.is_file() or path.is_symlink():
            continue
        if (
            name in ENGINEERING_TOOLKIT_FILES
            or name in SUPPORT_FILES
            or name.startswith(SUPPORT_ROOTS)
        ):
            selected.append(name)
    missing = sorted(
        name for name in ENGINEERING_TOOLKIT_FILES | SUPPORT_FILES
        if not (root / name).is_file()
    )
    if missing:
        raise ValueError("Engineering inventory is missing: " + ", ".join(missing))
    forbidden = [
        name for name in selected
        if name.endswith(FORBIDDEN_ARCHIVE_SUFFIXES)
    ]
    if forbidden:
        raise ValueError(
            "Engineering Toolkit must not contain compiled cores or platform source "
            "archives: " + ", ".join(sorted(forbidden))
        )
    return sorted(set(selected))


def build(version: str, output: Path) -> Path:
    """Create and verify one deterministic-path Engineering Tools ZIP."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", version):
        raise ValueError("Use a release tag without slashes or whitespace")
    output.parent.mkdir(parents=True, exist_ok=True)
    root_name = "VirtualGlove-Engineering-Tools"
    files = selected_files()
    readme = f"""# VirtualGlove Engineering Toolkit

Version: `{version}`

This optional toolkit is for developers investigating camera delivery, hand
recognition, latency, controller transport, and native emulation. It is not
needed to install, configure, calibrate, or play VirtualGlove.

Start with [`docs/ENGINEERING_TOOLKIT.md`](docs/ENGINEERING_TOOLKIT.md). The
shortest safe check, which uses no camera or network connection, is:

```sh
python3 scripts/check-engineering-toolkit.py
```

Set up the offline and video-analysis environment:

```sh
python3 scripts/setup-engineering-tools.py
```

MediaPipe replay experiments use the validated Python 3.12 toolchain:

```sh
python3.12 scripts/setup-engineering-tools.py --with-mediapipe
```

No ROMs, recordings, credentials, device settings, cached models, compiled
cores, platform core source archives, or personal calibration data are included.
"""
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        write_member(archive, root_name + "/README.md", readme)
        write_member(archive, root_name + "/engineering-tools.json", json.dumps({
            "format": 2,
            "version": version,
            "categories": {
                category: sorted(names)
                for category, names in sorted(TOOLKIT_CATEGORIES.items())
            },
            "tool_files": sorted(ENGINEERING_TOOLKIT_FILES),
            "files": files,
        }, indent=2) + "\n")
        for name in files:
            mode = 0o755 if (ROOT / name).stat().st_mode & stat.S_IXUSR else 0o644
            write_member(archive, root_name + "/" + name, (ROOT / name).read_bytes(), mode)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or "../" in "\n".join(archive.namelist()):
            raise ValueError("Engineering Tools archive validation failed")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(digest + "  " + output.name + "\n")
    return output


def main() -> None:
    """Build the optional source toolkit without publishing it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output/install/VirtualGlove-Engineering-Tools.zip")
    args = parser.parse_args()
    print("Built " + str(build(args.version, args.output)))


if __name__ == "__main__":
    main()
