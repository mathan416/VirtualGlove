# Project: VirtualGlove
# File: tests/test_camera_recovery.py
# Purpose: Verify guarded camera USB recovery requests without touching host devices.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Required a post-reset worker frame before recovery confirmation.
#   2026-09-08 - Verify classified enrollment and stream-recovery requests.
#   2026-09-05 - Added sustained-outage, single-request, idle, and recovery tests.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify unprivileged recovery requests without operating real USB devices."""

import tempfile
import unittest
from pathlib import Path

from virtualglove.camera import CameraRecoveryRequester


class CameraRecoveryRequesterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = 100.0
        self.marker = self.root / ".enabled"
        self.request = self.root / "request"
        self.monitor = CameraRecoveryRequester(
            self.marker, self.request, delay=15.0, retry_delay=65.0,
            clock=lambda: self.now
        )

    @staticmethod
    def missing():
        return {
            "camera_available": False,
            "vision_state": "error",
            "vision_error": "camera 'auto' is unavailable; waiting for a USB camera",
        }

    def test_requests_once_after_sustained_camera_outage(self):
        self.marker.touch()
        self.assertFalse(self.monitor.observe(self.missing()))
        self.now += 14.9
        self.assertFalse(self.monitor.observe(self.missing()))
        self.now += 0.1
        self.assertTrue(self.monitor.observe(self.missing()))
        self.assertTrue(self.request.exists())
        self.assertEqual(self.request.read_text(), "recover\n")
        self.request.unlink()
        self.now += 64.9
        self.assertFalse(self.monitor.observe(self.missing()))
        self.assertFalse(self.request.exists())
        self.now += 0.1
        self.assertTrue(self.monitor.observe(self.missing()))
        self.assertEqual(self.request.read_text(), "recover\n")

    def test_host_completion_result_is_consumed(self):
        self.monitor.result.write_text(
            '{"schema":2,"status":"usb-action-complete","method":"port-power-cycle"}\n'
        )
        self.assertTrue(self.monitor.wait_for_recovery(timeout=0.1))
        self.assertFalse(self.monitor.result.exists())
        self.assertIsNone(self.monitor.consume_verified_recovery())
        self.monitor.observe({"camera_available": False, "vision_state": "error"})
        self.assertIsNone(self.monitor.consume_verified_recovery())
        self.monitor.observe({"camera_available": True, "vision_state": "active"})
        self.assertEqual(self.monitor.consume_verified_recovery(), "port-power-cycle")
        self.assertIsNone(self.monitor.consume_verified_recovery())

    def test_host_failure_result_is_consumed(self):
        self.monitor.result.write_text('{"schema":1,"status":"failed"}\n')
        self.assertFalse(self.monitor.wait_for_recovery(timeout=0.1))
        self.assertFalse(self.monitor.result.exists())

    def test_usb_action_is_not_verified_after_frame_deadline(self):
        self.monitor.result.write_text(
            '{"schema":2,"status":"usb-action-complete","method":"hub-driver-rebind"}\n'
        )
        self.assertTrue(self.monitor.wait_for_recovery(timeout=0.1))
        self.now += 65.0
        self.monitor.observe({"camera_available": True, "vision_state": "active"})
        self.assertIsNone(self.monitor.consume_verified_recovery())

    def test_never_requests_without_installed_host_helper(self):
        self.monitor.observe(self.missing())
        self.now += 20
        self.assertFalse(self.monitor.observe(self.missing()))
        self.assertFalse(self.request.exists())

    def test_camera_recovery_rearms_next_outage(self):
        self.marker.touch()
        self.monitor.observe(self.missing())
        self.now += 15
        self.assertTrue(self.monitor.observe(self.missing()))
        self.request.unlink()
        self.assertTrue(self.monitor.observe({"camera_available": True, "vision_state": "active"}))
        self.request.unlink()
        self.now += 1
        self.monitor.observe(self.missing())
        self.now += 15
        self.assertTrue(self.monitor.observe(self.missing()))

    def test_first_healthy_camera_requests_autosuspend_prevention_once(self):
        self.marker.touch()
        healthy = {"camera_available": True, "vision_state": "active"}
        self.assertTrue(self.monitor.observe(healthy))
        self.assertTrue(self.request.exists())
        self.assertEqual(self.request.read_text(), "enroll\n")
        self.request.unlink()
        self.assertFalse(self.monitor.observe(healthy))
        self.assertFalse(self.request.exists())

    def test_camera_return_requests_fresh_hub_enrollment(self):
        self.marker.touch()
        healthy = {"camera_available": True, "vision_state": "active"}
        self.assertTrue(self.monitor.observe(healthy))
        self.request.unlink()
        self.assertFalse(self.monitor.observe(self.missing()))
        self.assertTrue(self.monitor.observe(healthy))
        self.assertTrue(self.request.exists())
        self.assertEqual(self.request.read_text(), "enroll\n")

    def test_idle_resets_outage_timer(self):
        self.marker.touch()
        self.monitor.observe(self.missing())
        self.now += 14
        self.monitor.observe({"camera_available": False, "vision_state": "idle"})
        self.now += 10
        self.assertFalse(self.monitor.observe(self.missing()))
        self.now += 15
        self.assertTrue(self.monitor.observe(self.missing()))

    def test_non_camera_errors_do_not_request_recovery(self):
        self.marker.touch()
        status = {"camera_available": False, "vision_state": "error", "vision_error": "model unavailable"}
        self.assertFalse(self.monitor.observe(status))
        self.now += 30
        self.assertFalse(self.monitor.observe(status))
