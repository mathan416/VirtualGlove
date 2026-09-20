#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/verify-retropie-native-core.py
# Purpose: Verify and resolve packaged RetroPie Nestopia PowerGlove cores.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-20 - Added RetroPie target, source, ELF, and runtime verification.
# Full history: docs/CHANGELOG.md and Git history.

"""Validate RetroPie core metadata, bytes, architecture, source, and identity."""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import struct
import tarfile


TARGET_ELF = {
    "armv6": (32, "arm"),
    "armv7": (32, "arm"),
    "armv8_32": (32, "arm"),
    "aarch64": (64, "aarch64"),
    "x86_64": (64, "x86_64"),
}

REQUIRED_FIELDS = {
    "build_environment", "cpu_arch", "elf_class", "elf_machine", "file",
    "float_abi", "max_glibc_symbol", "nestopia_revision", "patch_sha256",
    "sha256", "size", "source_file", "source_sha256", "source_size",
    "validation",
}


def _runtime_elf(runtime):
    """Return the runtime executable's ELF class and machine, if available."""
    if runtime is None:
        return None
    try:
        raw = Path(runtime).read_bytes()[:20]
    except OSError:
        return None
    if len(raw) < 20 or raw[:4] != b"\x7fELF" or raw[4] not in (1, 2) or raw[5] != 1:
        raise ValueError("RetroArch runtime is not a supported little-endian ELF file")
    return raw[4], struct.unpack("<H", raw[18:20])[0]


def detect_target(machine, cpuinfo="", runtime=None):
    """Resolve the core ABI from RetroArch first, then the kernel and CPU."""
    machine = machine.strip().lower()
    runtime_elf = _runtime_elf(runtime)
    if runtime_elf == (2, 62):
        return "x86_64"
    if runtime_elf == (2, 183):
        return "aarch64"
    if runtime_elf is not None and runtime_elf != (1, 40):
        raise ValueError("Unsupported RetroArch runtime architecture")
    runtime_is_arm32 = runtime_elf == (1, 40)
    architecture = re.search(r"^CPU architecture\s*:\s*(\d+)", cpuinfo,
                             flags=re.MULTILINE | re.IGNORECASE)
    cpu_generation = int(architecture.group(1)) if architecture else None
    if runtime_is_arm32:
        if machine.startswith("armv6") or cpu_generation == 6:
            return "armv6"
        return "armv8_32" if (machine in ("aarch64", "arm64", "armv8", "armv8l")
                              or cpu_generation is not None and cpu_generation >= 8) else "armv7"
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    if machine.startswith("armv6"):
        return "armv6"
    if machine in ("armv8l", "armv8"):
        return "armv8_32"
    if machine.startswith("armv7"):
        return "armv8_32" if cpu_generation is not None and cpu_generation >= 8 else "armv7"
    raise ValueError("Unsupported RetroPie CPU architecture: " + machine)


def manifest_entry(manifest_path, target):
    """Return one strictly validated target entry."""
    data = json.loads(Path(manifest_path).read_text())
    if data.get("format") != 1 or not isinstance(data.get("cores"), dict):
        raise ValueError("Unsupported RetroPie native-core manifest")
    if set(data["cores"]) != set(TARGET_ELF):
        raise ValueError("Incomplete RetroPie native-core target matrix")
    entry = data["cores"].get(target)
    if entry is None:
        return None
    if not isinstance(entry, dict) or set(entry) != REQUIRED_FIELDS:
        raise ValueError("Malformed RetroPie native-core manifest entry")
    for field in ("file", "source_file"):
        value = entry[field]
        path = Path(value) if isinstance(value, str) else None
        if (path is None or path.is_absolute() or ".." in path.parts
                or path.parent != Path(target)):
            raise ValueError("Unsafe RetroPie native-core path")
    if (entry["elf_class"], entry["elf_machine"]) != TARGET_ELF[target]:
        raise ValueError("RetroPie target and native-core ELF identity do not match")
    for field in ("size", "source_size"):
        if not isinstance(entry[field], int) or entry[field] <= 0:
            raise ValueError("Invalid RetroPie native-core size")
    for field in ("sha256", "source_sha256", "patch_sha256"):
        if (not isinstance(entry[field], str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry[field])):
            raise ValueError("Invalid RetroPie native-core checksum")
    if (not isinstance(entry["nestopia_revision"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", entry["nestopia_revision"])):
        raise ValueError("Invalid RetroPie Nestopia revision")
    if (not isinstance(entry["max_glibc_symbol"], str)
            or not re.fullmatch(r"\d+\.\d+", entry["max_glibc_symbol"])):
        raise ValueError("Invalid RetroPie glibc compatibility level")
    for field in ("build_environment", "cpu_arch", "float_abi", "validation"):
        if not isinstance(entry[field], str) or not entry[field]:
            raise ValueError("Invalid RetroPie native-core provenance")
    return entry


def _verify_file(path, expected_size, expected_hash, label):
    """Read one artifact only after its size and digest match the manifest."""
    raw = path.read_bytes()
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("RetroPie native-core " + label + " does not match its manifest")
    return raw


def verify(manifest_path, core_path, target, load=False):
    """Verify bytes, corresponding source, ELF identity, and optional loading."""
    entry = manifest_entry(manifest_path, target)
    if entry is None:
        raise ValueError("No packaged native core for RetroPie " + target)
    manifest_root = Path(manifest_path).resolve().parent
    core = Path(core_path).resolve()
    source = (manifest_root / entry["source_file"]).resolve()
    expected_core = (manifest_root / entry["file"]).resolve()
    if manifest_root not in source.parents or manifest_root not in expected_core.parents:
        raise ValueError("Unsafe RetroPie native-core artifact path")
    if core != expected_core:
        raise ValueError("RetroPie native-core path does not match its manifest")
    raw = _verify_file(core, entry["size"], entry["sha256"], "core")
    _verify_file(source, entry["source_size"], entry["source_sha256"], "source archive")
    with tarfile.open(source, "r:gz") as archive:
        names = {name[2:] if name.startswith("./") else name
                 for name in archive.getnames()}
        if "COPYING" not in names or "source/core/input/NstInpPowerGlove.cpp" not in names:
            raise ValueError("RetroPie native-core source archive is incomplete")
    classes = {32: 1, 64: 2}
    machines = {"arm": 40, "x86_64": 62, "aarch64": 183}
    if (len(raw) < 20 or raw[:4] != b"\x7fELF" or raw[5] != 1
            or raw[4] != classes[entry["elf_class"]]
            or struct.unpack("<H", raw[18:20])[0] != machines[entry["elf_machine"]]):
        raise ValueError("RetroPie native core ELF identity does not match its manifest")
    if load:
        library = ctypes.CDLL(str(core))
        for symbol in ("retro_api_version", "retro_get_system_info", "retro_init"):
            getattr(library, symbol)
        library.retro_api_version.restype = ctypes.c_uint
        if library.retro_api_version() != 1:
            raise ValueError("RetroPie native core exposes an unsupported libretro API")

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
            raise ValueError("RetroPie native core identity is not Nestopia PowerGlove")
    return entry


def main(argv=None):
    """Run the command-line verifier or architecture resolver."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--core", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--machine")
    parser.add_argument("--cpuinfo", type=Path, default=Path("/proc/cpuinfo"))
    parser.add_argument("--runtime", type=Path,
                        help="RetroArch executable used to resolve 32- versus 64-bit ABI")
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--resolve-core", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.target) == bool(args.machine):
        parser.error("provide exactly one of --target or --machine")
    cpuinfo = args.cpuinfo.read_text(errors="replace") if args.cpuinfo.is_file() else ""
    target = args.target or detect_target(args.machine, cpuinfo, args.runtime)
    entry = manifest_entry(args.manifest, target)
    if entry is None:
        raise ValueError("No packaged native core for RetroPie " + target)
    if args.resolve_core:
        if args.core is not None or args.load:
            parser.error("--resolve-core cannot be combined with --core or --load")
        print((args.manifest.resolve().parent / entry["file"]).resolve())
        return 0
    if args.core is None:
        parser.error("--core is required unless --resolve-core is used")
    verify(args.manifest, args.core, target, args.load)
    print("PASS  RetroPie native core verified for " + target)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, tarfile.TarError) as error:
        import sys
        print("FAIL  " + str(error), file=sys.stderr)
        raise SystemExit(1)
