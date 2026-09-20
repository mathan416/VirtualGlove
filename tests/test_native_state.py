# Project: VirtualGlove
# File: tests/test_native_state.py
# Purpose: Verify the fixed latest-sample interface used by custom Nestopia.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Verified native closed-hand and index-point pose flags.
#   2026-09-04 - Added native latest-sample encoding and safety coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify the guarded latest-sample record used by custom Nestopia."""

import tempfile
import time
import unittest
from pathlib import Path

from virtualglove.native_state import (
    BUTTON_CLOSED_HAND, BUTTON_INDEX_POINT, BUTTON_MENU_GUARD, BUTTON_SELECT,
    PROFILE_SUPER_GLOVE_BALL, RECORD_SIZE,
    NativeStateWriter, decode_record, encode_record,
    monotonic_ns,
)


class NativeStateTests(unittest.TestCase):
    def sample(self):
        return {
            "sequence": 42, "profile": "super_glove_ball",
            "detected": True, "calibrated": True,
            "axes": {"x": -32767, "y": 123, "z": 32767, "roll": -456},
            "fingers": {"thumb": 0, "index": 1, "middle": 2, "ring": 3, "pinky": 3},
            "buttons": {
                "select": True, "menu_guard": True,
                "closed_hand": True, "index_point": True,
            },
        }

    def test_record_is_fixed_versioned_and_complete(self):
        payload = encode_record(self.sample(), 8, 123456)
        self.assertEqual(len(payload), RECORD_SIZE)
        decoded = decode_record(payload)
        self.assertEqual(decoded["sequence"], 42)
        self.assertEqual(decoded["axes"]["x"], -32767)
        self.assertEqual(decoded["fingers"], {"thumb": 0, "index": 1, "middle": 2, "ring": 3})
        self.assertEqual(
            decoded["buttons"],
            BUTTON_SELECT | BUTTON_MENU_GUARD | BUTTON_CLOSED_HAND | BUTTON_INDEX_POINT,
        )
        self.assertEqual(decoded["profile"], PROFILE_SUPER_GLOVE_BALL)

    def test_odd_or_mismatched_guard_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_record(encode_record(self.sample(), 9, 1))

    def test_writer_publishes_and_neutralizes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native-state"
            writer = NativeStateWriter(path)
            writer.write(self.sample())
            self.assertTrue(decode_record(path.read_bytes())["detected"])
            writer.release(43)
            neutral = decode_record(path.read_bytes())
            self.assertFalse(neutral["detected"])
            self.assertFalse(neutral["calibrated"])
            writer.close()

    def test_writer_clock_matches_native_clock_monotonic_epoch(self):
        before = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        measured = monotonic_ns()
        after = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        self.assertLessEqual(before, measured)
        self.assertLessEqual(measured, after)

    def test_writer_can_publish_a_controlled_stale_timestamp_for_tracing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native-state"
            writer = NativeStateWriter(path)
            writer.write(self.sample(), arrived_ns=1)
            self.assertEqual(decode_record(path.read_bytes())["arrived_ns"], 1)
            writer.close()

    def test_writer_recreates_a_native_record_removed_by_another_service(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run" / "native-state"
            writer = NativeStateWriter(path)
            original_identity = writer.identity
            path.unlink()
            writer.write(self.sample())
            self.assertTrue(path.is_file())
            self.assertNotEqual(writer.identity, original_identity)
            self.assertTrue(decode_record(path.read_bytes())["detected"])
            writer.close()
