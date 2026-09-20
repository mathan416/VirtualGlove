# Project: VirtualGlove
# File: tests/test_vision_benchmark_tools.py
# Purpose: Verify fixed and guided vision benchmark schedules and lifecycle.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Covered production-matched fast sweeps and malformed-frame retry.
#   2026-09-05 - Kept development-script loading compatible with Python 3.7.
#   2026-09-05 - Added coverage for user-paced guided benchmark capture.
# Full history: docs/CHANGELOG.md and Git history.

"""Tests for the temporary local vision benchmark tools."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    """Load a hyphenated development script as a test module."""
    path = ROOT / "scripts" / name
    module_name = name[:-3] if name.endswith(".py") else name
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VisionBenchmarkToolTests(unittest.TestCase):
    """Verify schedule compatibility and safe guided-capture completion."""

    def test_guided_schedules_cover_recognition_and_tracking_evidence(self) -> None:
        """The supported recorder must label recognition and tracking evidence."""
        guided = load_script("guided-vision-benchmark.py")
        self.assertEqual(
            [cue[0] for cue in guided.CUES],
            [
                "neutral_near", "slow_xy", "fast_xy", "short_directions",
                "a", "b", "roll_left", "roll_right", "closed_hand", "push",
                "pull", "tracking_recovery", "neutral_far", "a_b_far",
                "neutral_finish",
            ],
        )
        self.assertEqual(sum(cue[3] for cue in guided.CUES), 52)
        self.assertEqual(
            [cue[0] for cue in guided.TRACKING_CUES],
            ["neutral_near", "slow_xy", "fast_xy", "tracking_recovery", "neutral_finish"],
        )
        self.assertIn("Live camera preview", guided.PAGE)
        self.assertIn("Record this step", guided.PAGE)
        self.assertEqual(
            [cue[0] for cue in guided.FAST_SWEEP_CUES],
            ["neutral_start", "fast_xy", "neutral_finish"],
        )
        self.assertEqual(sum(cue[3] for cue in guided.FAST_SWEEP_CUES), 12)

    def test_guided_capture_releases_camera_when_final_step_finishes(self) -> None:
        """Completing capture must not leave the camera owned by the helper."""
        guided = load_script("guided-vision-benchmark.py")
        custom_cues = (("neutral", "Neutral", "Hold still", 0.01),)

        class Frame:
            shape = (480, 640, 3)

            def copy(self):
                return self

        class Camera:
            released = False

            def __init__(self):
                self.reads = 0

            def read(self):
                self.reads += 1
                if self.reads == 1:
                    raise RuntimeError("camera marked the direct MJPEG frame invalid")
                return True, Frame()

            def release(self):
                self.released = True

        class Writer:
            released = False

            def write(self, _frame):
                pass

            def release(self):
                self.released = True

        class Cv2:
            FONT_HERSHEY_SIMPLEX = 0
            LINE_AA = 0
            IMWRITE_JPEG_QUALITY = 1

            @staticmethod
            def putText(*_args):
                pass

            @staticmethod
            def imencode(*_args):
                return False, None

        with tempfile.TemporaryDirectory() as directory:
            capture = guided.GuidedCapture.__new__(guided.GuidedCapture)
            capture.cv2 = Cv2()
            capture.output = Path(directory) / "guided.avi"
            capture.width, capture.height, capture.fps = 640, 480, 30.0
            capture.cues = custom_cues
            capture.lock = threading.Lock()
            capture.release_lock = threading.Lock()
            capture.condition = threading.Condition(capture.lock)
            capture.index = 0
            capture.phase = "recording"
            capture.phase_started = time.monotonic() - 0.02
            capture.latest_jpeg = None
            capture.frames = 0
            capture.frame_times = []
            capture.cue_records = []
            capture.timeline = 0.0
            capture.complete = False
            capture.closed = False
            capture.camera_released = False
            capture.capture = Camera()
            capture.writer = Writer()

            capture._camera_loop()

            self.assertTrue(capture.complete)
            self.assertTrue(capture.capture.released)
            self.assertGreaterEqual(capture.capture.reads, 2)
            capture._release_camera()
            self.assertTrue(capture.camera_released)
            self.assertIsNone(capture.writer)
            sidecar = Path(directory) / "guided.avi.json"
            self.assertTrue(sidecar.is_file())
            self.assertEqual(json.loads(sidecar.read_text())["duration_seconds"], .01)

    def test_staggered_tracker_gate_requires_latency_continuity_and_precision(self) -> None:
        """A faster result rate alone must not promote the experimental lane."""
        staggered = load_script("benchmark-staggered-trackers.py")
        baseline = {
            "source_age_ms": {"p95": 100.0}, "accepted_hz": 16.0,
            "detection_percent": 99.0, "coordinate_step": {"p95": .04},
        }
        candidate = {
            "source_age_ms": {"p95": 75.0}, "accepted_hz": 22.0,
            "detection_percent": 98.5, "coordinate_step": {"p95": .04},
        }
        self.assertTrue(staggered.evaluate(baseline, candidate)["passes_measured_gates"])
        candidate["coordinate_step"]["p95"] = .05
        result = staggered.evaluate(baseline, candidate)
        self.assertFalse(result["passes_measured_gates"])
        self.assertIn("gesture equivalence on labeled cues", result["still_required"])

    def test_staggered_tracker_uses_guided_capture_timestamps(self) -> None:
        """Irregular camera delivery must not be replayed at the AVI nominal rate."""
        staggered = load_script("benchmark-staggered-trackers.py")
        with tempfile.TemporaryDirectory() as directory:
            clip = Path(directory) / "guided.avi"
            clip.touch()
            clip.with_suffix(".avi.json").write_text(json.dumps({
                "frame_times_seconds": [3.2, 3.25, 3.34],
            }))
            schedule = staggered.frame_schedule(clip, 30.0)
            self.assertEqual(len(schedule), 3)
            self.assertAlmostEqual(schedule[0], 0.0)
            self.assertAlmostEqual(schedule[1], 0.05)
            self.assertAlmostEqual(schedule[2], 0.14)


if __name__ == "__main__":
    unittest.main()
