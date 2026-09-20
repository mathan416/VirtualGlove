# Project: VirtualGlove
# File: tests/test_camera_exposure_soak.py
# Purpose: Verify lab-only exposure control safety and aggregate calculations.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Added safety checks for the camera exposure soak.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify the camera exposure soak remains bounded and output-free."""

import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "camera_exposure_soak",
    Path(__file__).resolve().parents[1] / "scripts" / "soak-camera-exposure.py",
)
soak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(soak)


class ExposureSoakTests(unittest.TestCase):
    def controls(self):
        from virtualglove import camera_controls as controls
        return (controls.EXPOSURE_AUTO, controls.EXPOSURE_AUTO_PRIORITY,
                soak.EXPOSURE_ABSOLUTE, soak.GAIN)

    def ioctl(self, reject=None):
        from virtualglove import camera_controls as controls
        values = {item: 0 for item in self.controls()}
        events = []
        def call(_fd, request, data):
            identifier = struct.unpack_from("I", data, 0)[0]
            if request == controls.VIDIOC_QUERYCTRL:
                events.append(("query", identifier))
                struct.pack_into("II", data, 0, identifier, 1)
                struct.pack_into("iiii", data, 40, 0, 4095, 1, 0)
                struct.pack_into("I", data, 56, 0)
            elif request == controls.VIDIOC_S_CTRL:
                _, value = struct.unpack("Ii", data)
                events.append(("set", identifier, value))
                if (identifier, value) == reject:
                    raise OSError("rejected")
                values[identifier] = value
            elif request == controls.VIDIOC_G_CTRL:
                struct.pack_into("i", data, 4, values[identifier])
        return call, events

    def test_manual_lane_queries_every_control_before_writing(self):
        ioctl, events = self.ioctl()
        report = soak.control_set(7, "manual", 78, 96, ioctl)
        self.assertTrue(report["applied"])
        first_set = next(index for index, event in enumerate(events)
                         if event[0] == "set")
        self.assertEqual(len(events[:first_set]), 4)
        self.assertEqual(events[first_set:][-2:], [
            ("set", soak.EXPOSURE_ABSOLUTE, 78), ("set", soak.GAIN, 96)])

    def test_restore_requests_automatic_fixed_rate(self):
        from virtualglove import camera_controls as controls
        ioctl, events = self.ioctl()
        self.assertTrue(soak.restore_automatic(7, ioctl))
        self.assertEqual(events[-2:], [
            ("set", controls.EXPOSURE_AUTO, 3),
            ("set", controls.EXPOSURE_AUTO_PRIORITY, 0),
        ])

    def test_rejected_setting_is_reported_without_exception(self):
        ioctl, _events = self.ioctl(reject=(soak.GAIN, 96))
        report = soak.control_set(7, "manual", 78, 96, ioctl)
        self.assertFalse(report["applied"])
        self.assertEqual(report["reason"], "rejected")

    def test_percentile_handles_empty_and_nearest_rank(self):
        self.assertIsNone(soak.percentile([], .95))
        self.assertEqual(soak.percentile([1, 2, 100], .95), 100)


if __name__ == "__main__":
    unittest.main()
