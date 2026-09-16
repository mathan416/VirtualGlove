#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/configure-batocera-super-glove-ball-core.py
# Purpose: Select the isolated native core for one Batocera Super Glove Ball ROM.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added reversible exact-ROM Batocera core selection.
# Full history: docs/CHANGELOG.md and Git history.

"""Atomically set or remove Batocera's exact per-ROM native-core selection."""

import argparse
from pathlib import Path
import re
import tempfile


DEFAULT_CONFIG = Path("/userdata/system/batocera.conf")
DEFAULT_CORE = Path("/usr/lib/libretro/nestopia_powerglove_libretro.so")
DEFAULT_INFO = Path("/usr/share/libretro/info/nestopia_powerglove_libretro.info")


def _prefix(rom: Path) -> str:
    """Return one safely quoted exact-ROM Batocera configuration prefix."""
    name = rom.name
    if not name or any(character in name for character in '\n\r"'):
        raise ValueError("ROM filename cannot be represented safely in batocera.conf")
    return 'nes["' + name + '"]'


def configured_text(current: str, rom: Path, mode: str) -> str:
    """Replace only the exact ROM's emulator/core keys and preserve all others."""
    prefix = _prefix(rom)
    matcher = re.compile(r"^\s*" + re.escape(prefix) + r"\.(?:emulator|core)\s*=")
    lines = [line for line in current.splitlines()
             if not matcher.match(line) and line != "# VirtualGlove Super Glove Ball core"]
    if lines and lines[-1]:
        lines.append("")
    lines.append("# VirtualGlove Super Glove Ball core")
    lines.append(prefix + ".emulator=libretro")
    lines.append(prefix + ".core=" +
                 ("nestopia_powerglove" if mode == "native" else "fceumm"))
    return "\n".join(lines).rstrip() + "\n"


def atomic_write(path: Path, text: str) -> None:
    """Replace one regular configuration file without following symbolic paths."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("refusing symbolic Batocera configuration path")
    with tempfile.NamedTemporaryFile("w", dir=str(path.parent),
                                     prefix=".virtualglove-batocera-",
                                     delete=False) as stream:
        stream.write(text)
        stream.flush()
        temporary = Path(stream.name)
    temporary.chmod(0o644)
    temporary.replace(path)


def main(argv=None) -> int:
    """Preview or atomically apply one exact-ROM core selection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("native", "fceumm"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--info", type=Path, default=DEFAULT_INFO)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if not args.rom.is_file():
        raise ValueError("Super Glove Ball ROM was not found: " + str(args.rom))
    if args.mode == "native" and (not args.core.is_file() or not args.info.is_file()):
        raise ValueError("Nestopia (VirtualGlove) is not mounted and ready")
    updated = configured_text(
        args.config.read_text() if args.config.is_file() else "", args.rom, args.mode)
    if args.apply:
        atomic_write(args.config, updated)
        print("Selected " + ("Nestopia (VirtualGlove)" if args.mode == "native" else
                             "FCEUmm") + " for " + args.rom.name)
    else:
        print(updated, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        import sys
        print("FAIL  " + str(error), file=sys.stderr)
        raise SystemExit(1)
