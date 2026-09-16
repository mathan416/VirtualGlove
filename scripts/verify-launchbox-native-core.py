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
import struct
from pathlib import Path


def verify(path: Path) -> None:
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
    if b"Nestopia PowerGlove\0" not in payload:
        raise ValueError("LaunchBox core does not expose the VirtualGlove core identity")


def main() -> int:
    """Verify one built DLL from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    args = parser.parse_args()
    verify(args.core)
    print(f"PASS  LaunchBox Windows x86-64 core: {args.core}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
