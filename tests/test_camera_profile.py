# Project: VirtualGlove
# File: tests/test_camera_profile.py
# Purpose: Verify safe, image-free camera setting recommendations.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-10 - Added guided camera-profile recommendation coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify candidate selection and conservative camera profile scoring."""

import unittest

from virtualglove.camera_profile import candidates, recommend, summarize


def status(sequence, *, detected=True, age=70, inference=35, fps=30, **changes):
    row = {
        "sequence": sequence, "detected": detected,
        "sample_age_ms": age, "inference_ms": inference,
        "camera_fps": fps, "vision_state": "active",
        "capture_backend": "opencv", "camera_exposure_applied": True,
    }
    row.update(changes)
    return row


class CameraProfileTests(unittest.TestCase):
    def test_portable_candidates_add_only_detected_capabilities(self):
        generic = candidates({"direct_v4l2": False, "vendor_id": "1234", "product_id": "5678"})
        self.assertEqual(len(generic), 4)
        self.assertFalse(any(row["camera_backend"] == "direct-v4l2" for row in generic))
        kiyo = candidates({"direct_v4l2": True, "vendor_id": "1532", "product_id": "0e05"})
        self.assertEqual(len(kiyo), 6)
        self.assertTrue(any(row["camera_backend"] == "direct-v4l2" for row in kiyo))
        self.assertTrue(any(row["camera_exposure"] == "kiyo-low-latency" for row in kiyo))

    def test_current_supported_configuration_is_always_the_first_baseline(self):
        current = {
            "camera_backend": "direct-v4l2", "capture_isolation": "process",
            "camera_fps": 30, "camera_buffers": 2, "camera_exposure": "manual",
        }
        self.assertEqual(candidates({"direct_v4l2": True}, current)[0], current)

    def test_summary_uses_unique_fresh_sequences_and_keeps_no_frames(self):
        settings = candidates({"direct_v4l2": False})[0]
        result = summarize(settings, [status(1), status(1), status(2, detected=False)], 1)
        self.assertEqual(result["samples"], 2)
        self.assertEqual(result["continuity"], .5)
        self.assertNotIn("frame", result)
        self.assertTrue(result["valid"])

    def test_unsupported_rate_and_reader_fallback_are_not_recommended(self):
        fast = dict(candidates({"direct_v4l2": False})[2])
        unsupported = summarize(fast, [status(i, fps=30) for i in range(10)], 1)
        self.assertFalse(unsupported["valid"])
        direct = {
            "camera_backend": "direct-v4l2", "capture_isolation": "thread",
            "camera_fps": 30, "camera_buffers": 1, "camera_exposure": "auto",
        }
        fallback = summarize(direct, [status(i, capture_backend_fallback="unsupported") for i in range(10)], 1)
        self.assertFalse(fallback["valid"])

    def test_recommendation_protects_continuity_then_uses_lower_age(self):
        settings = candidates({"direct_v4l2": False})[0]
        slow = summarize(settings, [status(i, age=100) for i in range(100)], 10)
        quicker = summarize(settings, [status(i, age=65, detected=i != 0) for i in range(100)], 10)
        poor = summarize(settings, [status(i, age=20, detected=i < 70) for i in range(100)], 10)
        self.assertIs(recommend([slow, quicker, poor]), quicker)

    def test_visible_camera_without_a_visible_hand_is_not_recommended(self):
        settings = candidates({"direct_v4l2": False})[0]
        missing = summarize(
            settings, [status(i, detected=False) for i in range(20)], 2
        )
        self.assertTrue(missing["valid"])
        self.assertIsNone(recommend([missing]))


if __name__ == "__main__":
    unittest.main()
