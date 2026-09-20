#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/verify-recalbox-native-core.py
# Purpose: Verify one packaged, architecture-specific Recalbox native core.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-15 - Added target/version, ELF, and source verification.
#   2026-09-17 - Allowed load-tested native cores across one Recalbox major series.
# Full history: docs/CHANGELOG.md and Git history.

"""Validate packaged Recalbox core metadata, bytes, and optional runtime identity."""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct


TARGET_ELF = {
    "rpizero2": (32, "arm"),
    "rpi3": (32, "arm"),
    "rpi4_64": (64, "aarch64"),
    "rpi5_64": (64, "aarch64"),
    "rg353x": (64, "aarch64"),
    "odroidgo2": (64, "aarch64"),
    "x86_64": (64, "x86_64"),
}


def version_tuple(version):
    """Return a numeric Recalbox version tuple or reject ambiguous versions."""
    if not isinstance(version, str) or not version or any(
            not part.isdigit() for part in version.split(".")):
        raise ValueError("Invalid Recalbox version")
    return tuple(int(part) for part in version.split("."))


def compatible_version(versions, requested):
    """Prefer an exact build, then the newest build from the same major series."""
    requested_parts = version_tuple(requested)
    if requested in versions:
        return requested
    candidates = []
    for candidate in versions:
        parts = version_tuple(candidate)
        if parts[0] == requested_parts[0]:
            candidates.append((parts, candidate))
    return max(candidates)[1] if candidates else None


def manifest_entry(manifest_path, architecture, version):
    """Return and validate the best compatible target/version manifest entry."""
    data = json.loads(Path(manifest_path).read_text())
    if data.get("format") != 2 or not isinstance(data.get("cores"), dict):
        raise ValueError("Unsupported Recalbox native-core manifest")
    versions = data["cores"].get(architecture)
    if versions is not None and not isinstance(versions, dict):
        raise ValueError("Malformed Recalbox native-core target")
    selected_version = compatible_version(versions, version) if versions else None
    entry = versions.get(selected_version) if selected_version else None
    if entry is None:
        return None
    required = {"file", "sha256", "size", "elf_class", "elf_machine",
                "source_file", "source_sha256", "source_size", "recalbox_version",
                "recalbox_revision", "nestopia_revision", "patch_sha256"}
    if set(entry) != required:
        raise ValueError("Malformed Recalbox native-core manifest entry")
    for name in ("file", "source_file"):
        if (not isinstance(entry[name], str) or Path(entry[name]).is_absolute()
                or ".." in Path(entry[name]).parts):
            raise ValueError("Unsafe Recalbox native-core path")
    if (not isinstance(entry["size"], int) or entry["size"] <= 0
            or not isinstance(entry["source_size"], int) or entry["source_size"] <= 0):
        raise ValueError("Invalid Recalbox native-core size")
    if entry["elf_class"] not in (32, 64) or entry["elf_machine"] not in (
            "arm", "aarch64", "x86_64"):
        raise ValueError("Invalid Recalbox native-core ELF identity")
    expected_elf = TARGET_ELF.get(architecture)
    if expected_elf is None:
        raise ValueError("Unsupported Recalbox native-core target")
    if (entry["elf_class"], entry["elf_machine"]) != expected_elf:
        raise ValueError("Recalbox target and native-core ELF identity do not match")
    expected_prefix = Path(architecture) / selected_version
    if any(Path(entry[name]).parent != expected_prefix
           for name in ("file", "source_file")):
        raise ValueError("Recalbox native-core path does not match target and version")
    if entry["recalbox_version"] != selected_version:
        raise ValueError("Recalbox native-core version key does not match its entry")
    for name in ("sha256", "source_sha256", "patch_sha256"):
        value = entry[name]
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError("Invalid Recalbox native-core checksum")
        int(value, 16)
    return entry


def verify(manifest_path, core_path, architecture, version, load=False):
    """Verify packaged bytes, source, ELF identity, and optionally load the core."""
    entry = manifest_entry(manifest_path, architecture, version)
    if entry is None:
        raise ValueError("No packaged native core for Recalbox " + architecture + " " + version)
    core = Path(core_path).resolve()
    manifest_root = Path(manifest_path).resolve().parent
    source = (manifest_root / entry["source_file"]).resolve()
    if manifest_root not in source.parents:
        raise ValueError("Unsafe Recalbox native-core source path")
    source_raw = source.read_bytes()
    if (len(source_raw) != entry["source_size"]
            or hashlib.sha256(source_raw).hexdigest() != entry["source_sha256"]):
        raise ValueError("Recalbox native-core source archive does not match its manifest")
    raw = core.read_bytes()
    if len(raw) != entry["size"]:
        raise ValueError("Recalbox native-core size does not match its manifest")
    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise ValueError("Recalbox native-core checksum does not match its manifest")
    elf_classes = {32: 1, 64: 2}
    elf_machines = {"arm": 40, "x86_64": 62, "aarch64": 183}
    if (len(raw) < 20 or raw[:4] != b"\x7fELF" or raw[5] != 1
            or raw[4] != elf_classes[entry["elf_class"]]
            or struct.unpack("<H", raw[18:20])[0] != elf_machines[entry["elf_machine"]]):
        raise ValueError("Recalbox native core ELF identity does not match its manifest")
    if load:
        library = ctypes.CDLL(str(core))
        for symbol in ("retro_api_version", "retro_get_system_info", "retro_init"):
            getattr(library, symbol)
        library.retro_api_version.restype = ctypes.c_uint
        if library.retro_api_version() != 1:
            raise ValueError("Recalbox native core exposes an unsupported libretro API")
        class SystemInfo(ctypes.Structure):
            """Subset of libretro_system_info returned by the core."""
            _fields_ = [("library_name", ctypes.c_char_p),
                        ("library_version", ctypes.c_char_p),
                        ("valid_extensions", ctypes.c_char_p),
                        ("need_fullpath", ctypes.c_bool),
                        ("block_extract", ctypes.c_bool)]
        info = SystemInfo()
        library.retro_get_system_info(ctypes.byref(info))
        if info.library_name != b"Nestopia PowerGlove":
            raise ValueError("Recalbox native core identity is not Nestopia PowerGlove")
    return entry


def main(argv=None):
    """Run the command-line verifier."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--core", type=Path)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--resolve-core", action="store_true",
                        help="print the selected packaged core path")
    args = parser.parse_args(argv)
    if args.resolve_core:
        if args.core is not None or args.load:
            parser.error("--resolve-core cannot be combined with --core or --load")
        entry = manifest_entry(args.manifest, args.arch, args.version)
        if entry is None:
            raise ValueError("No compatible packaged native core for Recalbox " +
                             args.arch + " " + args.version)
        print((args.manifest.resolve().parent / entry["file"]).resolve())
        return 0
    if args.core is None:
        parser.error("--core is required unless --resolve-core is used")
    verify(args.manifest, args.core, args.arch, args.version, args.load)
    entry = manifest_entry(args.manifest, args.arch, args.version)
    built_for = entry["recalbox_version"]
    suffix = "" if built_for == args.version else " using compatible build " + built_for
    print("PASS  Recalbox native core verified for " + args.arch + " " + args.version + suffix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
