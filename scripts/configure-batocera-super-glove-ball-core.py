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

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile


DEFAULT_CONFIG = Path("/userdata/system/batocera.conf")
DEFAULT_CORE = Path("/usr/lib/libretro/nestopia_powerglove_libretro.so")
DEFAULT_INFO = Path("/usr/share/libretro/info/nestopia_powerglove_libretro.info")
DEFAULT_REGISTRY = Path("/userdata/system/virtualglove/data/games.json")
DEFAULT_ROM_ROOT = Path("/userdata/roms/nes")


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


def has_core_selection(current: str, rom: Path) -> bool:
    """Return whether the exact ROM already has an explicit Batocera core."""
    prefix = _prefix(rom) + ".core"
    return any(line.split("=", 1)[0].strip() == prefix
               for line in current.splitlines()
               if "=" in line and not line.lstrip().startswith(("#", ";")))


def registered_native_names(registry_text: str) -> set[str]:
    """Return exact case-insensitive ROM basenames registered for native input."""
    data = json.loads(registry_text)
    games = data.get("games") if isinstance(data, dict) else None
    if not isinstance(games, dict):
        raise ValueError("Game registry must contain a games object")
    names = set()
    for name, entry in games.items():
        profile = entry.get("profile") if isinstance(entry, dict) else entry
        if profile == "super_glove_ball" and isinstance(name, str) and Path(name).name == name:
            names.add(name.casefold())
    return names


def matching_roms(rom_root: Path, names: set[str]) -> list[Path]:
    """Find registered ordinary ROM files without following symbolic directories."""
    matches = []
    if not rom_root.is_dir() or rom_root.is_symlink():
        return matches
    for directory, subdirectories, filenames in os.walk(rom_root, followlinks=False):
        base = Path(directory)
        subdirectories[:] = [name for name in subdirectories if not (base / name).is_symlink()]
        for filename in filenames:
            candidate = base / filename
            if filename.casefold() in names and candidate.is_file() and not candidate.is_symlink():
                matches.append(candidate)
    return sorted(matches, key=lambda path: str(path).casefold())


def auto_select(config: Path, registry: Path, rom_root: Path, mode: str,
                apply: bool) -> tuple[int, int]:
    """Select native input only for registered ROMs without an explicit choice."""
    if not registry.is_file() or registry.is_symlink():
        raise ValueError("Installed game registry was not found")
    current = config.read_text() if config.is_file() else ""
    selected = skipped = 0
    for rom in matching_roms(rom_root, registered_native_names(registry.read_text())):
        if has_core_selection(current, rom):
            print("Preserved existing core selection for " + rom.name)
            skipped += 1
            continue
        current = configured_text(current, rom, mode)
        print("Selected " + ("Nestopia (VirtualGlove)" if mode == "native" else
                             "FCEUmm") + " for " + rom.name)
        selected += 1
    if apply and selected:
        atomic_write(config, current)
    elif not apply and selected:
        print(current, end="")
    return selected, skipped


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
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--mode", required=True, choices=("native", "fceumm"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--info", type=Path, default=DEFAULT_INFO)
    parser.add_argument("--auto-select", action="store_true")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--rom-root", type=Path, default=DEFAULT_ROM_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.rom is None and not args.auto_select:
        raise ValueError("Choose a ROM or automatic selection")
    if args.mode == "native" and (not args.core.is_file() or not args.info.is_file()):
        raise ValueError("Nestopia (VirtualGlove) is not mounted and ready")
    if args.rom is not None:
        if not args.rom.is_file():
            raise ValueError("Super Glove Ball ROM was not found: " + str(args.rom))
        updated = configured_text(
            args.config.read_text() if args.config.is_file() else "", args.rom, args.mode)
        if args.apply:
            atomic_write(args.config, updated)
            print("Selected " + ("Nestopia (VirtualGlove)" if args.mode == "native" else
                                 "FCEUmm") + " for " + args.rom.name)
        else:
            print(updated, end="")
    if args.auto_select:
        selected, skipped = auto_select(
            args.config, args.registry, args.rom_root, args.mode, args.apply)
        print("Automatic exact-ROM selection: %d selected, %d preserved." %
              (selected, skipped))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        import sys
        print("FAIL  " + str(error), file=sys.stderr)
        raise SystemExit(1)
