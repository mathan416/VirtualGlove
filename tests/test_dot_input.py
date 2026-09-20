# Project: VirtualGlove
# File: tests/test_dot_input.py
# Purpose: Verify read-only native-state measurement for the diagnostic dot core.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Added dot-input diagnostic regression coverage.
# Full history: docs/CHANGELOG.md and Git history.
"""Validate diagnostic rejection, recovery and receiver-to-dot range reporting."""
import importlib.util
from pathlib import Path
import struct
import unittest

from virtualglove.native_state import encode_record

spec = importlib.util.spec_from_file_location("dot_input", Path(__file__).resolve().parents[1] / "scripts/measure-dot-input.py")
dot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dot)


class DotInputTests(unittest.TestCase):
    def sample(self, x=0, y=0, **changes):
        state = dict(sequence=1, detected=True, calibrated=True,
                     profile="super_glove_ball", axes=dict(x=x, y=y))
        state.update(changes)
        return encode_record(state, 2, 1_000_000_000)

    def test_first_frame_mapping_and_ranges(self):
        window = dot.Window()
        for x, y, expected in [(-32767, -32767, (16, 24)), (32767, 32767, (239, 207)), (0, 0, (127, 115))]:
            reason, state = dot.inspect(self.sample(x, y, sequence=x+32768), 1_000_000_001)
            self.assertEqual(reason, "tracking")
            self.assertEqual((state['dot']['x'], state['dot']['y']), expected)
            window.observe(reason, state)
        self.assertEqual(window.ranges['dot_x'], [16, 239])
        self.assertEqual(window.ranges['dot_y'], [24, 207])

    def test_invalid_records_and_freshness_boundary(self):
        payload = self.sample()
        cases = [(payload[:63], 'invalid_record'),
                 (b'NOPE'+payload[4:], 'invalid_record'),
                 (self.sample(detected=False), 'undetected'),
                 (self.sample(calibrated=False), 'uncalibrated'),
                 (self.sample(profile='other'), 'wrong_profile')]
        for offset, fmt, value in [(4, '<H', 2), (6, '<H', 63), (8, '<I', 3), (60, '<I', 4)]:
            bad = bytearray(payload)
            struct.pack_into(fmt, bad, offset, value)
            cases.append((bad, 'invalid_record'))
        for raw, expected in cases:
            self.assertEqual(dot.inspect(raw, 1_000_000_000), (expected, None))
        self.assertEqual(dot.inspect(payload, 999_999_999), ('future', None))
        self.assertEqual(dot.inspect(payload, 1_250_000_001), ('stale', None))
        self.assertEqual(dot.inspect(payload, 1_250_000_000)[0], 'tracking')

    def test_duplicates_loss_and_recovery_never_hold_position(self):
        window = dot.Window()
        valid = dot.inspect(self.sample(), 1_000_000_001)
        window.observe(*valid)
        window.observe(*valid)
        invalid = dot.inspect(self.sample(), 1_300_000_000)
        self.assertIsNone(invalid[1])
        window.observe(*invalid)
        window.observe('missing', None)
        window.observe(*dot.inspect(self.sample(sequence=2), 1_000_000_001))
        self.assertEqual(window.publications, 2)
        self.assertEqual((window.losses, window.recoveries), (1, 1))


if __name__ == '__main__':
    unittest.main()
