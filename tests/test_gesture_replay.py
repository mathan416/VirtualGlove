# Project: VirtualGlove
# File: tests/test_gesture_replay.py
# Purpose: Verify privacy-safe gesture recordings replay deterministically.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT

"""Exercise bounded gesture regression capture and replay."""

import json
import unittest

from powerglove_vision.gesture import GestureConfig, GestureEngine
from powerglove_vision.gesture_replay import (
    GestureRegressionRecorder, load_recording, replay_recording,
)
from powerglove_vision.model import Calibration, HandObservation


class GestureReplayTests(unittest.TestCase):
    def recording(self):
        engine = GestureEngine(
            "program_1", GestureConfig(joystick_deadzone=0.6),
            calibration=Calibration(0.5, 0.5, 0.2, 0.0),
            rapid_a=False, rapid_b=True,
        )
        recorder = GestureRegressionRecorder()
        recorder.begin(engine)
        recorder.record(HandObservation(10.0, True, 1.0, palm_x=0.5, palm_y=0.5,
                                        palm_scale=0.2, confidence_source="handedness"))
        recorder.record(HandObservation(10.1, True, 1.0, palm_x=0.9, palm_y=0.5,
                                        palm_scale=0.2, thumb_curl=0.8,
                                        confidence_source="handedness"))
        recorder.record(HandObservation(10.3, False))
        recorder.stop()
        return recorder

    def test_recording_contains_only_derived_inputs_and_replays(self):
        recorder = self.recording()
        document = recorder.document()
        self.assertNotIn(b"image", document.lower())
        self.assertNotIn(b"game", document.lower())
        data = load_recording(document)
        self.assertEqual(data["profile"], "program_1")
        self.assertEqual([frame["at_ms"] for frame in data["frames"]], [0.0, 100.0, 300.0])
        self.assertEqual(replay_recording(document)["mismatch_count"], 0)

    def test_replay_reports_changed_controller_output(self):
        data = json.loads(self.recording().document())
        data["frames"][1]["expected"]["dpad"]["right"] = False
        report = replay_recording(json.dumps(data))
        self.assertFalse(report["passed"])
        self.assertEqual(report["mismatches"][0]["frame"], 1)

    def test_unknown_fields_and_unready_download_are_rejected(self):
        recorder = GestureRegressionRecorder()
        with self.assertRaisesRegex(ValueError, "Stop a non-empty"):
            recorder.document()
        data = json.loads(self.recording().document())
        data["camera_image"] = "not allowed"
        with self.assertRaisesRegex(ValueError, "unknown or missing"):
            load_recording(json.dumps(data))


if __name__ == "__main__":
    unittest.main()
