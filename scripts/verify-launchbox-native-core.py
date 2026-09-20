#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/verify-launchbox-native-core.py
# Purpose: Verify that a LaunchBox native core is a Windows x86-64 DLL.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added PE32+ AMD64 and core-identity verification.
# Full history: docs/CHANGELOG.md and Git history.

"""Reject mislabeled or wrong-architecture LaunchBox native-core artifacts."""

from __future__ import annotations

import argparse
import ctypes
import struct
from pathlib import Path


def verify(path: Path, load: bool = False) -> None:
    """Validate the PE signature, AMD64 machine, PE32+ format, and core identity."""
    payload = Path(path).read_bytes()
    if len(payload) < 512 or payload[:2] != b"MZ":
        raise ValueError("LaunchBox core is not a Windows executable image")
    pe = struct.unpack_from("<I", payload, 0x3C)[0]
    if pe > len(payload) - 26 or payload[pe:pe + 4] != b"PE\0\0":
        raise ValueError("LaunchBox core has an invalid PE header")
    machine = struct.unpack_from("<H", payload, pe + 4)[0]
    optional = struct.unpack_from("<H", payload, pe + 24)[0]
    if machine != 0x8664 or optional != 0x20B:
        raise ValueError("LaunchBox core must be a PE32+ x86-64 DLL")
    if b"Nestopia VirtualGlove\0" not in payload:
        raise ValueError("LaunchBox core does not expose the VirtualGlove core identity")
    if load:
        library = ctypes.CDLL(str(Path(path).resolve()))
        for symbol in ("retro_api_version", "retro_get_system_info", "retro_init"):
            getattr(library, symbol)
        library.retro_api_version.restype = ctypes.c_uint
        if library.retro_api_version() != 1:
            raise ValueError("LaunchBox core exposes an unsupported libretro API")

        class SystemInfo(ctypes.Structure):
            """Subset of libretro_system_info returned by the core."""
            _fields_ = [("library_name", ctypes.c_char_p),
                        ("library_version", ctypes.c_char_p),
                        ("valid_extensions", ctypes.c_char_p),
                        ("need_fullpath", ctypes.c_bool),
                        ("block_extract", ctypes.c_bool)]

        info = SystemInfo()
        library.retro_get_system_info(ctypes.byref(info))
        if info.library_name != b"Nestopia VirtualGlove":
            raise ValueError("LaunchBox core identity is not Nestopia VirtualGlove")


def main() -> int:
    """Verify one built DLL from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--load", action="store_true",
                        help="load the DLL and verify its libretro identity")
    args = parser.parse_args()
    verify(args.core, args.load)
    print(f"PASS  LaunchBox Windows x86-64 core: {args.core}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
