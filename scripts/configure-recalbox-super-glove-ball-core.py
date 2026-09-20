#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/configure-recalbox-super-glove-ball-core.py
# Purpose: Register and select the isolated native core on Recalbox.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added temporary core registration and exact-ROM selection.
# Full history: docs/CHANGELOG.md and Git history.

"""Build Recalbox's temporary core list and exact-ROM selection safely."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET


DEFAULT_TEMPLATE = Path("/recalbox/share_init/system/.emulationstation/systemlist.xml")
DEFAULT_RUNTIME = Path("/run/virtualglove-core/systemlist.xml")
DEFAULT_CORE = Path("/usr/lib/libretro/nestopia_powerglove_libretro.so")
DEFAULT_REGISTRY = Path("/recalbox/share/system/virtualglove/data/games.json")
DEFAULT_ROM_ROOT = Path("/recalbox/share/roms/nes")


def _indent_xml(element, level=0):
    """Indent XML on Python versions that predate ElementTree.indent()."""
    if hasattr(ET, "indent"):
        ET.indent(element, space="  ")
        return
    whitespace = "\n" + level * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = whitespace + "  "
        for child in element:
            _indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = whitespace
    if level and (not element.tail or not element.tail.strip()):
        element.tail = whitespace


def systemlist_text(current: str) -> str:
    """Add the separate core to NES while preserving every other system."""
    root = ET.fromstring(current)
    systems = [node for node in root.findall("system") if node.get("name") == "nes"]
    if len(systems) != 1:
        raise ValueError("Recalbox system list must contain exactly one NES system")
    emulator_list = systems[0].find("emulatorList")
    if emulator_list is None:
        raise ValueError("Recalbox NES system has no emulator list")
    emulators = [node for node in emulator_list.findall("emulator")
                 if node.get("name") == "libretro"]
    if len(emulators) != 1:
        raise ValueError("Recalbox NES system has no unique libretro emulator")
    emulator = emulators[0]
    matches = [node for node in emulator.findall("core")
               if node.get("name") == "nestopia_powerglove"]
    if len(matches) > 1:
        raise ValueError("Recalbox NES system has duplicate VirtualGlove cores")
    attributes = {
        "name": "nestopia_powerglove", "priority": "250",
        "extensions": ".nes .unf .unif .zip! .7z!", "netplay": "0",
        "softpatching": "1", "compatibility": "high", "speed": "high",
        "crt.available": "1", "video.backend": "default",
    }
    if matches:
        matches[0].attrib.clear()
        matches[0].attrib.update(attributes)
    else:
        ET.SubElement(emulator, "core", attributes)
    _indent_xml(root)
    return '<?xml version="1.0" ?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def selection_text(current: str, mode: str) -> str:
    """Replace only NES emulator/core keys in one exact-ROM sidecar."""
    managed = {"nes.emulator", "nes.core"}
    lines = []
    for line in current.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key not in managed and line != "# VirtualGlove Super Glove Ball core":
            lines.append(line)
    if lines and lines[-1]:
        lines.append("")
    lines.extend(("# VirtualGlove Super Glove Ball core", "nes.emulator=libretro",
                  "nes.core=" + ("nestopia_powerglove" if mode == "native" else "fceumm")))
    return "\n".join(lines).rstrip() + "\n"


def has_core_selection(current: str) -> bool:
    """Return whether an exact-ROM sidecar already chooses an NES core."""
    return any(line.split("=", 1)[0].strip() == "nes.core"
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
    """Find registered ordinary ROM files without following directory symlinks."""
    matches = []
    if not rom_root.is_dir() or rom_root.is_symlink():
        return matches
    for directory, subdirectories, filenames in os.walk(rom_root, followlinks=False):
        base = Path(directory)
        subdirectories[:] = [name for name in subdirectories
                             if not (base / name).is_symlink()]
        for filename in filenames:
            candidate = base / filename
            if filename.casefold() in names and candidate.is_file() and not candidate.is_symlink():
                matches.append(candidate)
    return sorted(matches, key=lambda path: str(path).casefold())


def auto_select(registry: Path, rom_root: Path, mode: str, apply: bool) -> tuple[int, int]:
    """Select native input for registered ROMs that have no explicit core choice."""
    if not registry.is_file() or registry.is_symlink():
        raise ValueError("Installed game registry was not found")
    names = registered_native_names(registry.read_text())
    selected = skipped = 0
    for rom in matching_roms(rom_root, names):
        sidecar = rom.with_name(rom.name + ".recalbox.conf")
        current = sidecar.read_text() if sidecar.is_file() else ""
        if has_core_selection(current):
            print("Preserved existing core selection for " + rom.name)
            skipped += 1
            continue
        updated = selection_text(current, mode)
        if apply:
            atomic_write(sidecar, updated)
        else:
            print(updated, end="")
        print("Selected " + ("Nestopia (VirtualGlove)" if mode == "native"
                              else "FCEUmm") + " for " + rom.name)
        selected += 1
    return selected, skipped


def atomic_write(path: Path, text: str) -> None:
    """Replace one ordinary file atomically without following a symlink."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("refusing symbolic Recalbox configuration path")
    with tempfile.NamedTemporaryFile("w", dir=str(path.parent),
                                     prefix=".virtualglove-recalbox-",
                                     delete=False) as stream:
        stream.write(text)
        stream.flush()
        temporary = Path(stream.name)
    temporary.chmod(0o644)
    temporary.replace(path)


def main(argv=None) -> int:
    """Preview or apply the runtime system list and optional ROM selection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--systemlist-source", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--systemlist-output", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--mode", choices=("native", "fceumm"), default="native")
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--auto-select", action="store_true")
    parser.add_argument("--selection-only", action="store_true")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--rom-root", type=Path, default=DEFAULT_ROM_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.selection_only and not (args.rom or args.auto_select):
        raise ValueError("Selection-only mode requires a ROM or automatic selection")
    if args.mode == "native" and not args.core.is_file():
        raise ValueError("Nestopia (VirtualGlove) is not mounted and ready")
    if not args.selection_only:
        if not args.systemlist_source.is_file():
            raise ValueError("Recalbox system list was not found")
        updated_systems = systemlist_text(args.systemlist_source.read_text())
        if args.apply:
            atomic_write(args.systemlist_output, updated_systems)
        else:
            print(updated_systems, end="")
    if args.rom is not None:
        if not args.rom.is_file():
            raise ValueError("Super Glove Ball ROM was not found: " + str(args.rom))
        sidecar = args.rom.with_name(args.rom.name + ".recalbox.conf")
        selected = selection_text(sidecar.read_text() if sidecar.is_file() else "", args.mode)
        if args.apply:
            atomic_write(sidecar, selected)
            print("Selected " + ("Nestopia (VirtualGlove)" if args.mode == "native"
                                  else "FCEUmm") + " for " + args.rom.name)
        else:
            print(selected, end="")
    if args.auto_select:
        selected, skipped = auto_select(args.registry, args.rom_root, args.mode, args.apply)
        print("Automatic exact-ROM selection: %d selected, %d preserved." %
              (selected, skipped))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ET.ParseError, OSError, ValueError) as error:
        import sys
        print("FAIL  " + str(error), file=sys.stderr)
        raise SystemExit(1)
