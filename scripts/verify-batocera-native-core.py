#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/verify-batocera-native-core.py
# Purpose: Verify and resolve packaged Batocera Nestopia PowerGlove cores.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-18 - Added Batocera target, source, ELF, and runtime verification.
# Full history: docs/CHANGELOG.md and Git history.

"""Validate Batocera core metadata, bytes, architecture, and runtime identity."""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import struct


TARGET_ELF = {
    "bcm2835": (32, "arm"),
    "bcm2836": (32, "arm"),
    "bcm2837": (64, "aarch64"),
    "bcm2711": (64, "aarch64"),
    "bcm2712": (64, "aarch64"),
    "x86_64": (64, "x86_64"),
    "rk3326": (64, "aarch64"),
    "rk3399": (64, "aarch64"),
    "rk3568": (64, "aarch64"),
    "rk3588": (64, "aarch64"),
    "s905": (64, "aarch64"),
    "s905gen2": (64, "aarch64"),
    "s905gen3": (64, "aarch64"),
    "s922x": (64, "aarch64"),
    "sm8250": (64, "aarch64"),
}


def version_tuple(value):
    """Return the leading numeric Batocera release tuple."""
    if not isinstance(value, str):
        raise ValueError("Invalid Batocera version")
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", value)
    if not match:
        raise ValueError("Invalid Batocera version")
    return tuple(int(part) for part in match.group(1).split("."))


def compatible_version(versions, requested):
    """Prefer an exact release, then the newest packaged build for this target."""
    requested_parts = version_tuple(requested)
    exact = ".".join(str(part) for part in requested_parts)
    if exact in versions:
        return exact
    candidates = [(version_tuple(candidate), candidate) for candidate in versions]
    return max(candidates)[1] if candidates else None


def manifest_entry(manifest_path, architecture, version):
    """Return and validate the selected target/version manifest entry."""
    data = json.loads(Path(manifest_path).read_text())
    if data.get("format") != 2 or not isinstance(data.get("cores"), dict):
        raise ValueError("Unsupported Batocera native-core manifest")
    versions = data["cores"].get(architecture)
    if versions is not None and not isinstance(versions, dict):
        raise ValueError("Malformed Batocera native-core target")
    selected = compatible_version(versions, version) if versions else None
    entry = versions.get(selected) if selected else None
    if entry is None:
        return None
    required = {
        "file", "sha256", "size", "elf_class", "elf_machine", "source_file",
        "source_sha256", "source_size", "batocera_version", "batocera_revision",
        "nestopia_revision", "patch_sha256", "build_image",
    }
    if set(entry) != required:
        raise ValueError("Malformed Batocera native-core manifest entry")
    for name in ("file", "source_file"):
        path = Path(entry[name]) if isinstance(entry[name], str) else None
        if path is None or path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe Batocera native-core path")
        if path.parent != Path(architecture) / selected:
            raise ValueError("Batocera native-core path does not match target and version")
    if entry["batocera_version"] != selected:
        raise ValueError("Batocera native-core version key does not match its entry")
    if (entry["elf_class"], entry["elf_machine"]) != TARGET_ELF.get(architecture):
        raise ValueError("Batocera target and native-core ELF identity do not match")
    for name in ("size", "source_size"):
        if not isinstance(entry[name], int) or entry[name] <= 0:
            raise ValueError("Invalid Batocera native-core size")
    for name in ("sha256", "source_sha256", "patch_sha256"):
        value = entry[name]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid Batocera native-core checksum")
    for name in ("batocera_revision", "nestopia_revision"):
        if not isinstance(entry[name], str) or not re.fullmatch(r"[0-9a-f]{40}", entry[name]):
            raise ValueError("Invalid Batocera native-core source revision")
    if not isinstance(entry["build_image"], str) or "@sha256:" not in entry["build_image"]:
        raise ValueError("Invalid Batocera native-core build image")
    return entry


def verify(manifest_path, core_path, architecture, version, load=False):
    """Verify bytes, corresponding source, ELF identity, and optional loading."""
    entry = manifest_entry(manifest_path, architecture, version)
    if entry is None:
        raise ValueError("No packaged native core for Batocera " + architecture)
    manifest_root = Path(manifest_path).resolve().parent
    core = Path(core_path).resolve()
    source = (manifest_root / entry["source_file"]).resolve()
    if manifest_root not in source.parents:
        raise ValueError("Unsafe Batocera native-core source path")
    for path, size, digest, label in (
        (core, entry["size"], entry["sha256"], "core"),
        (source, entry["source_size"], entry["source_sha256"], "source archive"),
    ):
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Batocera native-core " + label + " does not match its manifest")
    raw = core.read_bytes()
    classes = {32: 1, 64: 2}
    machines = {"arm": 40, "x86_64": 62, "aarch64": 183}
    if (len(raw) < 20 or raw[:4] != b"\x7fELF" or raw[5] != 1
            or raw[4] != classes[entry["elf_class"]]
            or struct.unpack("<H", raw[18:20])[0] != machines[entry["elf_machine"]]):
        raise ValueError("Batocera native core ELF identity does not match its manifest")
    if load:
        library = ctypes.CDLL(str(core))
        for symbol in ("retro_api_version", "retro_get_system_info", "retro_init"):
            getattr(library, symbol)
        library.retro_api_version.restype = ctypes.c_uint
        if library.retro_api_version() != 1:
            raise ValueError("Batocera native core exposes an unsupported libretro API")

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
            raise ValueError("Batocera native core identity is not Nestopia PowerGlove")
    return entry


def main(argv=None):
    """Run the command-line verifier or resolver."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--core", type=Path)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--resolve-core", action="store_true")
    args = parser.parse_args(argv)
    entry = manifest_entry(args.manifest, args.arch, args.version)
    if entry is None:
        raise ValueError("No compatible packaged native core for Batocera " + args.arch)
    if args.resolve_core:
        if args.core is not None or args.load:
            parser.error("--resolve-core cannot be combined with --core or --load")
        print((args.manifest.resolve().parent / entry["file"]).resolve())
        return 0
    if args.core is None:
        parser.error("--core is required unless --resolve-core is used")
    verify(args.manifest, args.core, args.arch, args.version, args.load)
    requested = ".".join(str(part) for part in version_tuple(args.version))
    suffix = ("" if entry["batocera_version"] == requested
              else " using compatible build " + entry["batocera_version"])
    print("PASS  Batocera native core verified for " + args.arch + " " +
          args.version.strip() + suffix)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        import sys
        print("FAIL  " + str(error), file=sys.stderr)
        raise SystemExit(1)
