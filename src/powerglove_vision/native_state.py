# Project: VirtualGlove
# File: src/powerglove_vision/native_state.py
# Purpose: Publish authenticated controller samples for the custom Nestopia core.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Add opt-in correlated latency diagnostics without changing input formats.
#   2026-09-05 - Added native closed-hand and index-point recognition flags.
#   2026-09-04 - Added a guarded read-only latest-sample record for custom Nestopia.
# Full history: docs/CHANGELOG.md and Git history.

"""Expose the latest validated controller sample through a fixed local record."""

from __future__ import annotations

import mmap
import os
import struct
import time
from pathlib import Path


MAGIC = b"PGV1"
VERSION = 1
RECORD_SIZE = 64
DEFAULT_PATH = Path("/run/virtualglove/native-state")
_RECORD = struct.Struct("<4sHHIIQhhhh7B21xI")

FLAG_DETECTED = 1 << 0
FLAG_CALIBRATED = 1 << 1

BUTTON_A = 1 << 0
BUTTON_B = 1 << 1
BUTTON_START = 1 << 2
BUTTON_SELECT = 1 << 3
BUTTON_GLOVE_ZAP = 1 << 4
BUTTON_MENU_GUARD = 1 << 5
BUTTON_CLOSED_HAND = 1 << 6
BUTTON_INDEX_POINT = 1 << 7

PROFILE_OTHER = 0
PROFILE_SUPER_GLOVE_BALL = 1


def monotonic_ns() -> int:
    """Use the same CLOCK_MONOTONIC epoch consumed by the native C core."""
    try:
        return time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    except (AttributeError, OSError):
        return time.monotonic_ns()


def _bounded(value, low, high) -> int:
    """Return one integer safely restricted to the native record's range."""
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


def encode_record(state: dict, guard: int, arrived_ns: int | None = None) -> bytes:
    """Encode one validated transport state without trusting optional fields."""
    axes = state.get("axes", {})
    fingers = state.get("fingers", {})
    buttons = state.get("buttons", {})
    flags = (FLAG_DETECTED if state.get("detected") else 0) | (
        FLAG_CALIBRATED if state.get("calibrated") else 0
    )
    button_mask = sum(
        bit for name, bit in (
            ("a", BUTTON_A), ("b", BUTTON_B), ("start", BUTTON_START),
            ("select", BUTTON_SELECT), ("glove_zap", BUTTON_GLOVE_ZAP),
            ("menu_guard", BUTTON_MENU_GUARD), ("closed_hand", BUTTON_CLOSED_HAND),
            ("index_point", BUTTON_INDEX_POINT),
        ) if buttons.get(name)
    )
    profile = PROFILE_SUPER_GLOVE_BALL if state.get("profile") == "super_glove_ball" else PROFILE_OTHER
    fingers4 = [_bounded(fingers.get(name, 0), 0, 3) for name in ("thumb", "index", "middle", "ring")]
    return _RECORD.pack(
        MAGIC, VERSION, RECORD_SIZE, guard, _bounded(state.get("sequence", 0), 0, 0xFFFFFFFF),
        arrived_ns if arrived_ns is not None else monotonic_ns(),
        *[_bounded(axes.get(name, 0), -32767, 32767) for name in ("x", "y", "z", "roll")],
        flags, *fingers4, button_mask, profile, guard,
    )


def decode_record(payload: bytes) -> dict:
    """Decode a complete stable record for tests and diagnostic tools."""
    if len(payload) != RECORD_SIZE:
        raise ValueError("native state record must be exactly 64 bytes")
    values = _RECORD.unpack(payload)
    if values[0] != MAGIC or values[1] != VERSION or values[2] != RECORD_SIZE:
        raise ValueError("unsupported native state record")
    if values[3] & 1 or values[3] != values[-1]:
        raise ValueError("native state record changed during the read")
    return {
        "guard": values[3], "sequence": values[4], "arrived_ns": values[5],
        "axes": dict(zip(("x", "y", "z", "roll"), values[6:10])),
        "detected": bool(values[10] & FLAG_DETECTED),
        "calibrated": bool(values[10] & FLAG_CALIBRATED),
        "fingers": dict(zip(("thumb", "index", "middle", "ring"), values[11:15])),
        "buttons": values[15], "profile": values[16],
    }


class NativeStateWriter:
    """Maintain one coherently readable latest-sample record for Nestopia."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            os.fchmod(descriptor, 0o644)
            os.ftruncate(descriptor, RECORD_SIZE)
            self.mapping = mmap.mmap(descriptor, RECORD_SIZE, access=mmap.ACCESS_WRITE)
        finally:
            os.close(descriptor)
        self.guard = 0
        self.write({"sequence": 0})

    def write(self, state: dict, arrived_ns: int | None = None) -> None:
        """Publish payload between odd/in-progress and even/complete guards."""
        odd = self.guard + 1
        if arrived_ns is None:
            arrived_ns = monotonic_ns()
        self.mapping[:] = encode_record(state, odd, arrived_ns)
        self.guard = odd + 1
        self.mapping[:] = encode_record(state, self.guard, arrived_ns)
        self.published_ns = arrived_ns

    def release(self, sequence: int = 0) -> None:
        """Publish a neutral stale-safe record."""
        self.write({"sequence": sequence, "detected": False, "calibrated": False})

    def close(self) -> None:
        """Neutralize and close the local mapping without removing its stable path."""
        self.release()
        self.mapping.close()
