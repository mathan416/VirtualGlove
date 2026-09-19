# Project: VirtualGlove
# File: tests/test_control_server.py
# Purpose: Verify dashboard configuration, pairing safeguards, controller state, and guarded shutdown behavior.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Require a transparent Controller-web logo.
#   2026-09-11 - Covered the HTTPS-only public Controller-authority download.
#   2026-09-11 - Verify privacy-safe system reports omit secrets and personal data.
#   2026-09-06 - Address Setup review reliability and private configuration findings.
#   2026-09-06 - Verified Help discovery for Rock Paper Scissors and native validation.
#   2026-09-05 - Verified persistent armed state and clearer delivery status.
#   2026-09-05 - Kept mocked forwarding assertions compatible with Python 3.7.
#   2026-09-05 - Verified atomic Academy controls and fresh-frame navigation gates.
#   2026-09-05 - Verified the Academy completion trophy artwork.
#   2026-09-05 - Verified Academy camera recovery and public calibration forwarding.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Verified atomic publication of host shutdown requests.
#   2026-09-03 - Verified the bundled Help library, Markdown reader, and assets.
#   2026-09-03 - Verified dynamic UNO Q and RetroPie cabinet details.
#   2026-09-03 - Verified public PDF links, routes, and allowlisting.
#   2026-09-03 - Verified Dashboard profile switching and healthy idle status.
#   2026-09-03 - Verified Learn-page practice leases and Dashboard restoration.
#   2026-09-03 - Verified shared profile labels and Python 3.7-compatible mocks.

"""Verify dashboard configuration, pairing safeguards, controller state, and guarded shutdown behavior."""

import json
import http.client
import io
import os
import socket
import ssl
import tempfile
import time
import unittest
from zipfile import ZipFile
from pathlib import Path
from unittest import mock

from virtualglove.control_server import (
    CAMERA_PROFILE_MEASURE_SECONDS, CAMERA_PROFILE_READY_SECONDS,
    CAMERA_PROFILE_STAGES, DASHBOARD, LEARN, LOGO_PATH, PLAY, SETUP,
    ControlState, help_document_page, help_index_page, start_control_server,
)
from virtualglove.debug_server import SharedDebugState
from virtualglove.help_content import (
    enclosure_asset, guide_pdf, help_asset, help_document_content, render_markdown,
)
from virtualglove.help_content import cabinet_reference_content, request_browser_address
from virtualglove.vision_app import (
    _base_status, _effective_profile, _requested_rapid_fire,
)
from virtualglove.profile_control import ProfileRequest


class AutomaticGameControllerTests(unittest.TestCase):
    """Check automatic launches without overriding explicit player actions."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = Path(self.directory.name) / "device.json"
        path.write_text(json.dumps({"receiver":"console.local", "token":"test-pairing-token"}))
        self.state = ControlState(path)

    def publish(self, session="game-one", enabled=True, **status):
        event = {"session":session,"enabled":enabled,"eligible":True,"at":time.monotonic()}
        self.state.update_worker(dict(_game_controller_event=event, **status))
        return event

    def test_launch_starts_once_and_heartbeat_keeps_stop(self):
        self.publish()
        self.assertTrue(self.state.controller_enabled())
        self.state.set_controller_enabled(False)
        self.publish()
        self.assertFalse(self.state.controller_enabled())
        self.publish("game-two")
        self.assertTrue(self.state.controller_enabled())
        self.assertNotIn("_game_controller_event",self.state.snapshot())

    def test_stop_after_launch_wins_over_delayed_status(self):
        event = {"session":"game-one","enabled":True,"eligible":True,"at":time.monotonic()}
        self.state.set_controller_enabled(False)
        self.state.update_worker({"_game_controller_event":event})
        self.assertFalse(self.state.controller_enabled())

    def test_exit_stops_and_same_session_recovery_does_not_restart(self):
        self.publish()
        self.publish(enabled=False)
        self.assertFalse(self.state.controller_enabled())
        self.publish()
        self.assertFalse(self.state.controller_enabled())

    def test_controller_restart_preserves_stop_for_current_game(self):
        self.publish()
        self.state.set_controller_enabled(False)
        self.state = ControlState(self.state.config_path)
        self.publish()
        self.assertFalse(self.state.controller_enabled())
        self.publish("new-game")
        self.assertTrue(self.state.controller_enabled())

    def test_practice_and_tuning_block_automatic_start(self):
        for index,status in enumerate(({"practice_mode":True},{"tuning":{"active":True}})):
            self.publish(str(index), **status)
            self.assertFalse(self.state.controller_enabled())
        self.publish("next-game")
        self.assertTrue(self.state.controller_enabled())

    def test_missing_center_reports_reason_without_starting(self):
        self.publish(player={"needs_center":True})
        self.assertFalse(self.state.controller_enabled())
        self.assertIn("Center hand",self.state.snapshot()["receiver_error"])

    def test_manual_profile_status_does_not_start(self):
        self.state.update_worker({"profile_source":"Dashboard","active_profile":"program_a"})
        self.assertFalse(self.state.controller_enabled())

    def test_practice_at_launch_stays_blocked_after_page_closes(self):
        event={"session":"game-one","enabled":True,"eligible":False,"at":time.monotonic()}
        self.state.update_worker({"_game_controller_event":event,"practice_mode":False})
        self.assertFalse(self.state.controller_enabled())


class ControlStateTests(unittest.TestCase):
    def test_players_route_requires_same_origin_and_action_header(self):
        servers, state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            for extra in ({}, {"X-VirtualGlove-Action":"players", "Sec-Fetch-Site":"cross-site"},
                          {"X-VirtualGlove-Action":"players", "Origin":"http://other.invalid"}):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                with mock.patch('virtualglove.control_server.urllib.request.urlopen') as forward:
                    connection.request("POST", "/api/players", json.dumps({"action":"read"}),
                                       dict({"Content-Type":"application/json"}, **extra))
                    response = connection.getresponse()
                    response.read()
                    self.assertEqual(response.status, 403)
                    forward.assert_not_called()
                connection.close()
        finally:
            servers.shutdown()

    def test_players_switch_stops_before_forwarding_and_requires_center(self):
        """A failed or interrupted switch cannot leave a persisted armed marker."""
        servers, state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            state.set_controller_enabled(True)
            def fail_forward(*args, **kwargs):
                self.assertFalse(state.controller_enabled())
                self.assertFalse(state._controller_marker.exists())
                raise ValueError("worker unavailable")
            connection = http.client.HTTPConnection("127.0.0.1", servers.servers[0].server_address[1], timeout=2)
            with mock.patch('virtualglove.control_server.urllib.request.urlopen', side_effect=fail_forward):
                connection.request("POST", "/api/players", json.dumps({"action":"select", "id":"other"}),
                                   {"Content-Type":"application/json", "X-VirtualGlove-Action":"players"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 400)
            connection.close()
            state.worker_status["player"] = {"needs_center": True}
            with self.assertRaisesRegex(ValueError, "Center hand"):
                state.set_controller_enabled(True)
        finally:
            servers.shutdown()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "device.json"
        self.path.write_text(json.dumps({
            "receiver": "retropieconsole.local", "platform": "retropie", "port": 55355,
            "token": "private-token", "profile": "bad_street_brawler",
            "glove_color": "none", "camera": "auto", "camera_fps": "auto",
            "camera_backend": "opencv", "camera_exposure": "auto",
            "camera_buffers": 2, "tracking_confidence": 0.45,
        }))
        self.state = ControlState(self.path)

    def test_first_run_config_is_blank_and_existing_config_is_preserved(self):
        """A fresh install has no destination; loading again never rewrites settings."""
        import runpy
        namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "python/main.py"))
        loader = namespace["load_device_config"]
        loader.__globals__["CONFIG_PATH"] = self.path
        before = self.path.read_bytes()
        self.assertEqual(loader()["receiver"], "retropieconsole.local")
        self.assertEqual(self.path.read_bytes(), before)
        self.path.unlink()
        fresh = loader()
        self.assertEqual(fresh["receiver"], "")
        self.assertEqual(fresh["platform"], "")
        self.assertEqual(fresh["profile"], "off")
        self.state = ControlState(self.path)
        self.assertFalse(self.state.public_config()["connection_configured"])
        self.assertFalse(self.state.public_config()["paired"])
        with self.assertRaisesRegex(ValueError, "Connection"):
            self.state.set_controller_enabled(True)
        self.assertFalse(self.state.controller_enabled())
        settings = self.state.public_config()
        settings["profile"] = "off"
        self.state.save_config(settings)
        self.assertEqual(self.state.public_config()["profile"], "off")
        self.assertEqual(self.state.load_config()["receiver"], "")

    def test_clearing_destination_stops_controller(self):
        """Removing the destination disables transmission without losing the token."""
        self.state.set_controller_enabled(True)
        settings = self.state.public_config()
        settings["receiver"] = ""
        self.state.save_config(settings)
        self.assertFalse(self.state.controller_enabled())
        self.assertEqual(self.state.load_config()["token"], "private-token")

    def test_explicit_controller_choice_survives_an_application_restart(self):
        self.state.set_controller_enabled(True)
        restarted = ControlState(self.path)
        self.assertTrue(restarted.controller_enabled())
        restarted.set_controller_enabled(False)
        self.assertFalse(ControlState(self.path).controller_enabled())

    def tearDown(self):
        self.temporary.cleanup()

    def test_public_config_never_contains_token(self):
        public = self.state.public_config()
        self.assertNotIn("token", public)
        self.assertTrue(public["paired"])
        self.assertEqual(public["platform"], "retropie")
        self.assertTrue(public["pairing_configured"])

    def test_existing_connection_runs_but_cannot_pair_until_platform_is_saved(self):
        existing = self.state.load_config()
        existing.pop("platform")
        self.path.write_text(json.dumps(existing))
        state = ControlState(self.path, pairing_display=lambda _identity, _pin: True)
        self.assertTrue(state.public_config()["connection_configured"])
        self.assertFalse(state.public_config()["pairing_configured"])
        state.set_controller_enabled(True)
        self.assertTrue(state.controller_enabled())
        with self.assertRaisesRegex(ValueError, "platform"):
            state.begin_pairing("retropieconsole.local", "code", "retropie")

    def test_pairing_is_bound_to_saved_platform_and_address(self):
        state = ControlState(self.path, pairing_display=lambda _identity, _pin: True)
        with self.assertRaisesRegex(ValueError, "platform"):
            state.begin_pairing("retropieconsole.local", "code", "recalbox")
        with self.assertRaisesRegex(ValueError, "saved console"):
            state.begin_pairing("other.local", "code", "retropie")

    def test_connection_save_requires_platform_with_an_address(self):
        settings = self.state.public_config()
        settings["platform"] = ""
        with self.assertRaisesRegex(ValueError, "platform"):
            self.state.save_config(settings)
        settings["platform"] = "unsupported"
        with self.assertRaisesRegex(ValueError, "supported console"):
            self.state.save_config(settings)

    def test_system_report_is_useful_without_private_configuration(self):
        self.state.connection_probe = lambda _settings, refresh: {
            "app": True, "console_configured": True,
            "console_service": True, "console_authenticated": True,
            "networking": "connected", "checked_seconds_ago": 2.0,
        }
        self.state.update_worker({
            "camera_available": True, "vision_state": "active",
            "capture_backend": "opencv", "camera_fps": 30.0,
            "controller_enabled": True, "controller_context_active": True,
            "receiver_available": True, "receiver_active_address": "10.0.2.44",
            "active_profile": "program_h", "emulator": "lr-fceumm",
            "input_mode": "joystick", "palm_position": {"x": 0.4, "y": 0.6},
            "game": "Private Game Name.nes",
        })
        report = self.state.support_report()
        serialized = json.dumps(report)
        self.assertEqual(report["format"], "virtualglove-system-report")
        self.assertTrue(report["controller"]["authenticated_input_link"])
        self.assertEqual(report["connection"]["console_registry_authenticated"], True)
        for private in ("private-token", "retropieconsole.local", "10.0.2.44",
                        "Private Game Name.nes", "palm_position"):
            self.assertNotIn(private, serialized)

    def test_setup_contains_guided_camera_profiler_with_unsaved_live_view(self):
        self.assertIn(b"Find the best camera settings", SETUP)
        self.assertIn(b"id=camera-profile-start", SETUP)
        self.assertIn(b"id=camera-profile-cancel hidden>Stop test", SETUP)
        self.assertIn(b"id=camera-profile-apply", SETUP)
        self.assertIn(b"No video or images are saved", SETUP)
        self.assertIn(b"id=camera-profile-frame data-src=/stream", SETUP)
        self.assertIn(b"id=camera-profile-cue", SETUP)
        self.assertIn(b"id=camera-profile-countdown", SETUP)
        self.assertIn(b"id=camera-profile-time", SETUP)
        self.assertIn(b"about three minutes", SETUP)
        self.assertIn(b"frame.removeAttribute('src')", SETUP)

    def test_camera_profile_gives_each_visible_cue_enough_time(self):
        self.assertEqual(CAMERA_PROFILE_READY_SECONDS, 3)
        self.assertEqual(
            [(cue, seconds) for cue, seconds, _instruction in CAMERA_PROFILE_STAGES],
            [("centre", 5), ("sweep", 9), ("edge", 6)],
        )
        self.assertEqual(CAMERA_PROFILE_MEASURE_SECONDS, 20)

    def test_camera_profile_apply_changes_only_recommended_fields(self):
        identity = {
            "key": "camera-key", "label": "Test Camera", "vendor_id": "1234",
            "product_id": "5678", "has_serial": False, "direct_v4l2": True,
        }
        settings = {
            "camera_backend": "direct-v4l2", "capture_isolation": "thread",
            "camera_fps": 30, "camera_buffers": 1, "camera_exposure": "auto",
        }
        before = self.state.load_config()
        self.state._camera_profile = {
            "active": False, "phase": "complete", "camera": identity,
            "recommendation": {"settings": settings}, "results": [],
        }
        with mock.patch("virtualglove.control_server.camera_device_identity", return_value=identity):
            self.state.apply_camera_profile()
        after = self.state.load_config()
        for key, value in before.items():
            if key not in settings:
                self.assertEqual(after[key], value)
        for key, value in settings.items():
            self.assertEqual(after[key], value)
        self.assertEqual(after["camera_profiles"]["camera-key"]["label"], "Test Camera")

    def test_camera_profile_crash_marker_restores_original_fields(self):
        original = self.state.load_config()
        marker = self.path.with_name("camera-profile-restore.json")
        marker.write_text(json.dumps({
            "schema": 1,
            "original": original,
        }))
        changed = dict(original, camera_backend="direct-v4l2", camera_fps=60,
                       camera_buffers=1, profile="super_glove_ball")
        self.path.write_text(json.dumps(changed))
        restored = ControlState(self.path).load_config()
        self.assertEqual(restored["camera_backend"], "opencv")
        self.assertEqual(restored["camera_fps"], "auto")
        self.assertEqual(restored["camera_buffers"], 2)
        self.assertEqual(restored["profile"], "bad_street_brawler")
        self.assertEqual(restored["token"], "private-token")
        self.assertFalse(marker.exists())

    def test_camera_profile_stop_after_disconnect_restarts_normal_worker(self):
        original = self.state.load_config()
        self.state.worker_status = {"vision_state": "error", "camera_available": False}
        self.state._camera_profile.update({
            "active": False,
            "phase": "error",
            "candidate": 2,
            "error": "The camera disconnected during the test.",
            "results": [{"name": "temporary"}],
        })
        revision = self.state.revision
        result = self.state.stop_camera_profile()
        self.assertEqual(result["phase"], "cancelled")
        self.assertIn("start a new test", result["instruction"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["results"], [])
        self.assertEqual(self.state.worker_status, {})
        self.assertEqual(self.state.revision, revision + 1)
        self.assertEqual(self.state.load_config(), original)

    def test_camera_profile_stop_during_lane_requests_safe_restore(self):
        self.state._camera_profile.update({"active": True, "phase": "measuring"})
        result = self.state.stop_camera_profile()
        self.assertTrue(self.state._camera_profile_cancel.is_set())
        self.assertTrue(result["active"])
        self.assertEqual(result["phase"], "restoring")

    def test_camera_profile_stop_retries_a_pending_exact_restore(self):
        original = self.state.load_config()
        marker = self.path.with_name("camera-profile-restore.json")
        marker.write_text(json.dumps({"schema": 1, "original": original}))
        self.path.write_text(json.dumps(dict(original, camera_fps=60)))
        self.state._camera_profile.update({"active": False, "phase": "error"})
        result = self.state.stop_camera_profile()
        self.assertEqual(result["phase"], "cancelled")
        self.assertEqual(self.state.load_config(), original)
        self.assertFalse(marker.exists())

    def test_camera_profile_route_requires_browser_action_header(self):
        servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request(
                "POST", "/api/camera-profile", json.dumps({"action": "cancel"}),
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 403)
            connection.close()
        finally:
            servers.shutdown()

    def test_attract_persists_without_restarting_or_changing_controls(self):
        self.state.set_controller_enabled(True)
        original = json.loads(self.path.read_text())
        self.assertEqual(self.state.public_config()['matrix_attract'],'on')
        for mode in ('off','dim','on'):
            self.state.save_attract({'mode':mode})
            self.assertEqual(json.loads(self.path.read_text()),dict(original,matrix_attract=mode))
            self.assertEqual(self.state.revision,0)
            self.assertTrue(self.state.controller_enabled())
        with self.assertRaises(ValueError):
            self.state.save_attract({'mode':'brightest'})
        self.state.save_attract({'mode':'dim'})
        self.state.save_config(original)
        self.assertEqual(self.state.public_config()['matrix_attract'],'dim')

    def test_retired_directional_search_setting_is_absent(self):
        self.assertNotIn("directional_search", self.state.public_config())
        self.assertNotIn("directional_search", self.state.load_config())

    def test_status_uses_cached_config_without_camera_enumeration(self):
        self.state.update_worker({"active_profile": "program_1"})
        with mock.patch.object(self.state, "public_config",
                               side_effect=AssertionError("slow config path")), \
                mock.patch("virtualglove.control_server.camera_device_identity") as identity, \
                mock.patch("virtualglove.control_server.camera_device_options") as options:
            for _ in range(100):
                status = self.state.snapshot()
                self.assertEqual(status["configured_profile"], "bad_street_brawler")
                self.assertTrue(status["connection_configured"])
        identity.assert_not_called()
        options.assert_not_called()

    def test_cached_config_returns_defensive_copies(self):
        first = self.state.load_config()
        first["receiver"] = "changed.invalid"
        self.assertEqual(
            self.state.load_config()["receiver"], "retropieconsole.local"
        )

    def test_camera_inventory_cache_expires_and_config_save_invalidates_it(self):
        identity = {"key": "camera:auto", "label": "Automatic"}
        options = [{"value": "auto", "label": "Automatic"}]
        with mock.patch(
            "virtualglove.control_server.camera_device_identity",
            return_value=identity,
        ) as identify, mock.patch(
            "virtualglove.control_server.camera_device_options",
            return_value=options,
        ) as enumerate_cameras, mock.patch(
            "virtualglove.control_server.time.monotonic",
            side_effect=[10.0, 12.0, 16.0, 17.0, 17.1],
        ):
            self.state.public_config()
            self.state.public_config()
            self.state.public_config()
            self.state.save_config(self.state.load_config())
            self.state.public_config()
        self.assertEqual(identify.call_count, 3)
        self.assertEqual(enumerate_cameras.call_count, 3)

    def test_wifi_status_cache_expires_and_returns_defensive_copies(self):
        report = {"state": "connected", "ssid": "Cabinet"}
        with mock.patch(
            "virtualglove.wifi_status.read_wifi_status",
            return_value=report,
        ) as read_status, mock.patch(
            "virtualglove.control_server.time.monotonic",
            side_effect=[10.0, 10.5, 11.1],
        ):
            first = self.state._cached_wifi_status()
            first["state"] = "changed"
            self.assertEqual(self.state._cached_wifi_status()["state"], "connected")
            self.assertEqual(self.state._cached_wifi_status()["state"], "connected")
        self.assertEqual(read_status.call_count, 2)

    def test_dashboard_uses_latest_native_xy_without_a_mode_control(self):
        self.assertNotIn(b"id=native-xy-mode", DASHBOARD)
        self.assertNotIn(b"Bounded speed curve", DASHBOARD)
        self.assertIn("MediaPipe — Latest coordinate".encode(), DASHBOARD)
        self.assertNotIn(b"/api/native-xy", DASHBOARD)
        self.assertNotIn(b"Optical flow (experimental)", DASHBOARD)

    def test_removed_native_xy_route_is_not_available(self):
        servers, state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("POST", "/api/native-xy",
                               json.dumps({"mode": "bounded"}),
                               {"Content-Type": "application/json",
                                "X-VirtualGlove-Action": "native-xy"})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 404)
            connection.close()
        finally:
            servers.shutdown()

    def test_save_preserves_token_and_updates_connection(self):
        self.assertIn(b'id=camera_fps', SETUP)
        self.assertIn(b'Automatic \xe2\x80\x94 prefer 30 fps', SETUP)
        self.assertIn(b'id=camera-rate-status', SETUP)
        self.assertIn(b'id=camera_buffers', SETUP)
        self.assertIn(b'id=camera_backend', SETUP)
        self.assertIn(b'<select id=camera name=camera>', SETUP)
        self.assertIn(b'Automatic \xe2\x80\x94 choose the connected camera', SETUP)
        self.assertIn(b'syncCameraOptions', SETUP)
        self.assertIn(b'id=camera_exposure', SETUP)
        self.assertIn(b'id=camera_manual_exposure', SETUP)
        self.assertIn(b'id=camera_manual_gain', SETUP)
        self.assertIn(b'Manual exposure and gain', SETUP)
        self.assertNotIn(b'id=experimental-tracking-section', SETUP)
        self.assertNotIn(b'id=directional-search', SETUP)
        self.state.save_config({
            "receiver": "arcade.local", "platform": "recalbox", "port": 55357,
            "profile": "program_i", "glove_color": "white", "camera": "2",
            "camera_fps": "60",
            "camera_buffers": "1",
            "camera_backend": "direct-v4l2",
            "camera_exposure": "low-latency",
        })
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["token"], "private-token")
        self.assertEqual(saved["receiver"], "arcade.local")
        self.assertEqual(saved["platform"], "recalbox")
        self.assertEqual(saved["camera_fps"], 60)
        self.assertEqual(saved["camera_backend"], "direct-v4l2")
        self.assertEqual(saved["camera_exposure"], "low-latency")
        self.assertEqual(saved["camera_manual_exposure"], 78)
        self.assertEqual(saved["camera_manual_gain"], 96)
        self.assertEqual(saved["camera_buffers"], 1)
        self.assertEqual(saved["tracking_confidence"], 0.45)
        self.assertEqual(self.state.revision, 1)

    def test_manual_camera_values_are_private_safe_and_require_direct_reader(self):
        settings=self.state.public_config()
        self.assertEqual(settings["camera_options"][0], {
            "value": "auto", "label": "Automatic — choose the connected camera",
        })
        settings.update({"camera_backend":"direct-v4l2","camera_exposure":"manual",
                         "camera_manual_exposure":78,"camera_manual_gain":96})
        saved=self.state.save_config(settings)
        self.assertEqual(saved["camera_exposure"],"manual")
        self.assertEqual(saved["camera_manual_exposure"],78)
        self.assertEqual(saved["camera_manual_gain"],96)
        before=self.path.read_bytes()
        for changes,message in (
            ({"camera_backend":"opencv"},"Direct V4L2"),
            ({"camera_manual_exposure":0},"exposure"),
            ({"camera_manual_gain":10001},"gain"),
            ({"camera_manual_exposure":78.5},"whole numbers"),
        ):
            invalid=dict(saved,**changes)
            with self.assertRaisesRegex(ValueError,message):
                self.state.save_config(invalid)
            self.assertEqual(self.path.read_bytes(),before)

    def test_invalid_camera_rate_is_rejected_without_changing_settings(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Automatic, 30 fps, or 60 fps"):
            self.state.save_config({
                "receiver": "arcade.local", "platform": "retropie", "port": 55355,
                "profile": "program_i", "glove_color": "none",
                "camera": "auto", "camera_fps": 24,
            })
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_camera_buffers_are_rejected_without_changing_settings(self):
        before = self.path.read_bytes()
        for value in (0, 3, True, 1.5, "auto"):
            settings = self.state.public_config()
            settings["camera_buffers"] = value
            with self.assertRaisesRegex(ValueError, "one or two camera buffers"):
                self.state.save_config(settings)
            self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "supported gesture profile"):
            self.state.save_config({
                "receiver": "arcade.local", "platform": "retropie", "port": 55355,
                "profile": "shell_command", "glove_color": "none", "camera": "auto",
            })

    def test_logo_is_available_to_both_web_pages(self):
        self.assertTrue(LOGO_PATH.is_file())
        logo = LOGO_PATH.read_bytes()
        self.assertEqual(logo[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIn(logo[25], (4, 6), "Controller logo must carry an alpha channel")
        logo_url = b"/assets/virtualglove-logo.png"
        self.assertIn(logo_url, DASHBOARD)
        self.assertIn(logo_url, LEARN)
        self.assertIn(logo_url, PLAY)
        self.assertIn(logo_url, SETUP)

    def test_help_is_in_the_primary_navigation(self):
        for page in (DASHBOARD, LEARN, PLAY, SETUP, help_index_page()):
            self.assertIn(b"href=/help>Help", page)

    def test_play_page_has_camera_controlled_rock_paper_scissors(self):
        self.assertIn(b"Rock Paper Scissors", PLAY)
        self.assertIn(b"data-src=/stream", PLAY)
        self.assertIn(b"/api/practice", PLAY)
        self.assertIn(b"recognition?.closed_hand", PLAY)
        self.assertIn(b"menu_gesture?.pose==='start'", PLAY)
        self.assertIn(b"First to three wins", PLAY)
        self.assertIn(b"pagehide", PLAY)
        self.assertIn(b"keepalive:true", PLAY)
        self.assertIn(b"Camera image unavailable. Reconnecting", PLAY)
        for page in (DASHBOARD, LEARN, PLAY, SETUP, help_index_page()):
            self.assertIn(b"href=/play>Play", page)

    def test_dashboard_exposes_realtime_performance_readings(self):
        self.assertIn(b'id=performance', DASHBOARD)
        self.assertIn(b'Inference p50 / p95', DASHBOARD)
        self.assertIn(b'Camera read \xe2\x86\x92 send p50 / p95', DASHBOARD)
        self.assertIn(b'Changed control \xe2\x86\x92 send p50 / p95', DASHBOARD)
        self.assertIn(b'Frame waiting before inference p50 / p95', DASHBOARD)
        self.assertIn(b'capture_skipped_total', DASHBOARD)
        self.assertIn(b'tracker_backend_label||s.tracker_backend', DASHBOARD)
        self.assertIn(b'Controller delivery', DASHBOARD)
        self.assertIn(b'id=game-session', DASHBOARD)
        self.assertIn(b'id=player-select', DASHBOARD)
        self.assertNotIn(b'<div class=label>RetroPie receiver</div>', DASHBOARD)

    def test_dashboard_replaces_a_failed_camera_stream_with_guidance(self):
        self.assertIn(b"Camera unavailable. Connect a USB camera to use gesture controls.", DASHBOARD)
        self.assertIn(b"s.vision_state==='error'||s.camera_available===false", DASHBOARD)
        self.assertIn(b"$('camera').removeAttribute('src')", DASHBOARD)

    def test_help_index_lists_the_public_guides(self):
        page = help_index_page()
        self.assertIn(b"Help, without leaving the glove", page)
        self.assertIn(b"/help/gameplay", page)
        self.assertIn(b"/help/installation", page)
        self.assertIn(b"/help/cabinet", page)
        self.assertIn(b"This console", page)
        self.assertIn(b"Rock Paper Scissors instructions", page)
        self.assertIn(b"Live-confirmed native game actions", page)
        self.assertNotIn(b"cheatsheet", page.lower())
        self.assertIn(b"/help-pdf/overview.pdf", page)
        technical = page.index(b"Technical documentation")
        overview = page.index(b"/help-pdf/overview.pdf", technical)
        architecture = page.index(b"/help/architecture", technical)
        configuration = page.index(b"/help/configuration", technical)
        input_audit = page.index(b"/help/input-audit", technical)
        self.assertLess(overview, architecture)
        self.assertLess(architecture, configuration)
        self.assertLess(configuration, input_audit)
        self.assertIsNone(help_document_page("field-guide"))

    def test_cabinet_reference_uses_request_address_and_public_config(self):
        body, title = cabinet_reference_content("10.0.2.105:8088", self.state.public_config())
        self.assertEqual(title, "This console")
        self.assertIn("http://10.0.2.105:8088/help", body)
        self.assertIn("http://10.0.2.105:8088/play", body)
        self.assertIn("https://10.0.2.105:8443/setup", body)
        self.assertIn("retropieconsole.local", body)
        self.assertIn("55355", body)
        self.assertNotIn("private-token", body)
        self.assertIn("Stopped", body)
        self.state.set_controller_enabled(True)
        body, _ = cabinet_reference_content("10.0.2.105:8088", self.state.public_config())
        self.assertIn("Armed", body)

    def test_cabinet_reference_preserves_local_names_and_rejects_bad_hosts(self):
        self.assertEqual(request_browser_address("arduiain.local:8088"), "arduiain.local")
        self.assertEqual(request_browser_address("bad host:8088"), "UNO-Q-NAME.local")

    def test_help_document_renders_markdown_with_contents_and_images(self):
        page = help_document_page("gameplay")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn(b"Play with VirtualGlove", page)
        self.assertIn(b"On this page", page)
        self.assertIn(b"/help-assets/gestures/actions/whole-hand-movement.png", page)
        self.assertIn(b"/help-assets/gestures/v2/v-sign.png", page)
        self.assertIn(b"/help-assets/gestures/v2/thumbs-up.png", page)
        self.assertGreaterEqual(page.count(b"<img loading=lazy"), 46)
        self.assertIn(b"<table class=program-starters>", page)
        self.assertIn(b"width='176'", page)
        self.assertIn(b"/help/gameplay.md", page)
        self.assertIn(b"/help-pdf/gameplay.pdf", page)
        self.assertIn(b"Pixel Pal&#x27;s Extra-Digit Hunt", page)
        self.assertIn(b"<details class=extra-digit-answer>", page)
        self.assertIn(b"<summary>Reveal Pixel Pal's answer</summary>", page)
        self.assertIn(b"Pixel Pal&#x27;s answer: 28 six-digit hands.", page)

        self.assertIsNone(help_document_page("programs"))

    def test_extra_digit_answer_is_collapsed_and_omitted_from_contents(self):
        rendered, headings = render_markdown(
            "# Hunt\n\n## Pixel Pal's Extra-Digit Hunt answer\n\n"
            "**Pixel Pal's answer: 1 six-digit hand.**"
        )
        self.assertIn("<details class=extra-digit-answer>", rendered)
        self.assertIn("<summary>Reveal Pixel Pal's answer</summary>", rendered)
        self.assertTrue(rendered.endswith("</details>"))
        self.assertNotIn("Pixel Pal's Extra-Digit Hunt answer", [title for _level, _anchor, title in headings])

    def test_help_guides_keep_only_the_shared_header_logo(self):
        for slug, width in (("gameplay", 680), ("installation", 680)):
            with self.subTest(slug=slug):
                page = help_document_page(slug)
                self.assertEqual(page.count(b"/assets/virtualglove-logo.png"), 1)
                rendered, _ = render_markdown('<img src="../assets/virtualglove-logo.png" alt="VirtualGlove" width="%s">' % width)
                self.assertIn("<img loading=lazy", rendered)
                self.assertNotIn(b"&lt;img", page)
        rendered, _ = render_markdown('<img src="../assets/private.png" alt="Unlisted" width="680">')
        self.assertNotIn("<img loading=lazy", rendered)

    def test_help_renderer_escapes_html_and_unsafe_links(self):
        rendered, _headings = render_markdown("# Safe\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))")
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertIn("href='#'", rendered)

        table, _headings = render_markdown(
            '| Name | Pose |\n| --- | --- |\n| Start | <img src="images/gestures/actions/v-sign.png" alt="V sign" width="72"> |'
        )
        self.assertIn("<img loading=lazy", table)
        self.assertIn("/help-assets/gestures/actions/v-sign.png", table)
        self.assertIn("<th class=art-column>", table)
        self.assertIn("<td class=art-cell>", table)

        mixed_table, _headings = render_markdown(
            '| State | See it |\n| --- | --- |\n| Pairing | — |\n'
            '| Ready | <img src="images/matrix/A.jpg" alt="A" width="104"> |'
        )
        self.assertEqual(mixed_table.count("<td class=art-cell>"), 2)

        unsafe_table, _headings = render_markdown(
            '| Name | Pose |\n| --- | --- |\n| Start | <img src="images/gestures/actions/v-sign.png" alt="V sign" width="72" onerror="alert(1)"> |'
        )
        self.assertNotIn("<img loading=lazy", unsafe_table)
        self.assertIn("&lt;img", unsafe_table)

    def test_help_renderer_keeps_wrapped_and_spaced_list_items_together(self):
        rendered, _headings = render_markdown(
            "- First item starts here\n"
            "  and wraps onto another source line.\n\n"
            "- Second item follows a blank line.\n\n"
            "1. First numbered item\n"
            "   also wraps.\n"
            "2. Second numbered item"
        )
        self.assertIn(
            "<ul><li>First item starts here and wraps onto another source line.</li>"
            "<li>Second item follows a blank line.</li></ul>",
            rendered,
        )
        self.assertIn(
            "<ol><li>First numbered item also wraps.</li><li>Second numbered item</li></ol>",
            rendered,
        )

    def test_help_assets_are_limited_to_documentation_images(self):
        asset = help_asset("gestures/directional-movement.png")
        self.assertIsNotNone(asset)
        assert asset is not None
        self.assertEqual(asset[1], "image/png")
        self.assertIsNone(help_asset("../../data/device.json"))

    def test_gesture_http_assets_use_compact_copies_without_changing_originals(self):
        root = Path(__file__).resolve().parents[1] / "docs/images"
        for name in ("v2/v-sign.png", "v2/thumbs-up.png", "actions/v-sign.png"):
            asset = help_asset("gestures/" + name)
            self.assertEqual(asset[1], "image/png")
            self.assertEqual(asset[0], (root / "web/gestures" / name).read_bytes())
            self.assertLess(len(asset[0]), 40000)
            self.assertLess(len(asset[0]), (root / "gestures" / name).stat().st_size // 4)
        for name in (
            "v2/pixel-pal-coach.png", "v2/pixel-pal-ready.png",
            "v2/pixel-pal-thinking.png", "v2/pixel-pal-safety.png",
            "v2/pixel-pal-success.png",
        ):
            asset = help_asset("gestures/" + name)
            self.assertEqual(asset[1], "image/png")
            self.assertEqual(asset[0], (root / "web/gestures" / name).read_bytes())
            self.assertLess(len(asset[0]), 180000)
            self.assertLess(len(asset[0]), (root / "gestures" / name).stat().st_size // 4)

    def test_help_pdfs_are_allowlisted_and_exclude_the_cabinet_reference(self):
        document = guide_pdf("gameplay")
        self.assertIsNotNone(document)
        assert document is not None
        self.assertTrue(document[0].startswith(b"%PDF-"))
        self.assertEqual(document[1], "VirtualGlove-Gameplay-Guide.pdf")
        self.assertEqual(
            guide_pdf("native-super-glove-ball")[1],
            "VirtualGlove-Super-Glove-Ball-Native.pdf",
        )
        self.assertEqual(
            guide_pdf("enclosure-quick-reference")[1],
            "VirtualGlove-Enclosure-Quick-Reference.pdf",
        )
        self.assertIsNone(guide_pdf("quick-reference"))
        self.assertIsNone(guide_pdf("../../data/device"))

    def test_enclosure_downloads_are_bounded_to_public_print_files(self):
        asset = enclosure_asset("stl/virtualglove-uno-base.stl")
        self.assertIsNotNone(asset)
        assert asset is not None
        self.assertEqual(asset[1:], ("model/stl", "virtualglove-uno-base.stl"))
        self.assertGreater(len(asset[0]), 1000)
        for stl_name in (
            "virtualglove-dock-v2-base.stl",
            "virtualglove-dock-v2-lid.stl",
            "virtualglove-dock-v2-lid-full-logo.stl",
            "virtualglove-uno-lid-full-logo.stl",
        ):
            with self.subTest(stl_name=stl_name):
                stl_asset = enclosure_asset(f"stl/{stl_name}")
                self.assertIsNotNone(stl_asset)
                assert stl_asset is not None
                self.assertEqual(stl_asset[1], "model/stl")
                self.assertGreater(len(stl_asset[0]), 1000)
        for model_name in (
            "virtualglove-lid-logo-multicolor.3mf",
            "virtualglove-compact-full-logo-multicolor.3mf",
        ):
            with self.subTest(model_name=model_name):
                model_asset = enclosure_asset(f"stl/{model_name}")
                self.assertIsNotNone(model_asset)
                assert model_asset is not None
                self.assertEqual(model_asset[1], "model/3mf")
                self.assertGreater(len(model_asset[0]), 1000)
        for preview_name in (
            "virtualglove-uno-case-exterior.png",
            "virtualglove-uno-case-back.png",
            "virtualglove-uno-case-left.png",
            "virtualglove-uno-case-right.png",
            "virtualglove-uno-case-exploded.png",
            "virtualglove-controller-dock-back.png",
            "virtualglove-controller-dock-left.png",
            "virtualglove-controller-dock-right.png",
            "virtualglove-controller-dock-exploded.png",
            "virtualglove-controller-dock-v2-exterior.png",
            "virtualglove-controller-dock-v2-back.png",
            "virtualglove-controller-dock-v2-left.png",
            "virtualglove-controller-dock-v2-right.png",
            "virtualglove-controller-dock-v2-exploded.png",
            "virtualglove-controller-dock-v2-port-access.png",
            "virtualglove-enclosure-quick-reference.png",
            "virtualglove-enclosure-quick-reference-parts.png",
            "virtualglove-enclosure-quick-reference-uno.png",
            "virtualglove-enclosure-quick-reference-dock-v1.png",
            "virtualglove-enclosure-quick-reference-dock-v1-finish.png",
            "virtualglove-enclosure-quick-reference-dock-v2.png",
            "virtualglove-enclosure-quick-reference-dock-v2-finish.png",
            "virtualglove-enclosure-quick-reference-finish.png",
            "virtualglove-lid-logo-options.png",
            "virtualglove-branding-insets.png",
        ):
            with self.subTest(preview_name=preview_name):
                self.assertEqual(
                    enclosure_asset(f"previews/{preview_name}")[1],
                    "image/png",
                )
        self.assertIsNone(enclosure_asset("../../data/device.json"))
        self.assertIsNone(enclosure_asset("stl/not-a-real-part.stl"))

    def test_enclosure_quick_reference_help_uses_all_visual_pages(self):
        document = help_document_content("enclosure-quick-reference")
        self.assertIsNotNone(document)
        assert document is not None
        page, _title = document
        self.assertIn(
            "/help-enclosure/previews/virtualglove-enclosure-quick-reference.png",
            page,
        )
        for suffix in (
            "parts", "uno", "dock-v1", "dock-v1-finish",
            "dock-v2", "dock-v2-finish", "finish",
        ):
            self.assertIn(
                f"/help-enclosure/previews/virtualglove-enclosure-quick-reference-{suffix}.png",
                page,
            )
        self.assertIn("Seat the four heat-set inserts square and flush", page)
        self.assertIn("Pixel Pal appears only where a warning", page)

    def test_enclosure_multicolor_3mf_preserves_brand_materials(self):
        asset = enclosure_asset("stl/virtualglove-lid-logo-multicolor.3mf")
        self.assertIsNotNone(asset)
        assert asset is not None
        with ZipFile(io.BytesIO(asset[0])) as archive:
            model = archive.read("3D/3dmodel.model").decode()
        self.assertIn("#111722FF", model)
        self.assertIn("#00D6EFFF", model)
        self.assertIn("#FF2145FF", model)
        self.assertIn('p1="1"', model)
        self.assertIn('p1="2"', model)
        self.assertIn('p1="3"', model)

    def test_help_routes_serve_html_markdown_and_images(self):
        servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            for path, expected_type in (
                ("/favicon.ico", "image/vnd.microsoft.icon"),
                ("/assets/favicon-32.png", "image/png"),
                ("/assets/virtualglove-icon.png", "image/png"),
                ("/assets/apple-touch-icon.png", "image/png"),
                ("/play", "text/html"),
                ("/help", "text/html"),
                ("/help/build-your-own", "text/html"),
                ("/help/native-emulation", "text/html"),
                ("/help/troubleshooting", "text/html"),
                ("/help/enclosure-quick-reference", "text/html"),
                ("/help-pdf/build-your-own.pdf", "application/pdf"),
                ("/help-pdf/native-emulation.pdf", "application/pdf"),
                ("/help-pdf/troubleshooting.pdf", "application/pdf"),
                ("/help-pdf/engineering-toolkit.pdf", "application/pdf"),
                ("/help-pdf/enclosure-quick-reference.pdf", "application/pdf"),
                ("/help/cabinet", "text/html"),
                ("/help/gameplay", "text/html"),
                ("/help/gameplay.md", "text/markdown"),
                ("/help-pdf/gameplay.pdf", "application/pdf"),
                ("/help-assets/gestures/directional-movement.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-uno-case-exterior.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-uno-case-back.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-uno-case-left.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-uno-case-right.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-uno-case-exploded.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-back.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-left.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-right.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-exploded.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-v2-exterior.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-v2-back.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-v2-left.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-v2-right.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-v2-exploded.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-controller-dock-v2-port-access.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-enclosure-quick-reference.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-enclosure-quick-reference-parts.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-enclosure-quick-reference-uno.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-enclosure-quick-reference-dock-v1.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-enclosure-quick-reference-dock-v1-finish.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-enclosure-quick-reference-dock-v2.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-enclosure-quick-reference-dock-v2-finish.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-enclosure-quick-reference-finish.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-lid-logo-options.png", "image/png"),
                ("/help-enclosure/previews/virtualglove-branding-insets.png", "image/png"),
                ("/help-enclosure/stl/virtualglove-uno-base.stl", "model/stl"),
                ("/help-enclosure/stl/virtualglove-dock-v2-base.stl", "model/stl"),
                ("/help-enclosure/stl/virtualglove-dock-v2-lid.stl", "model/stl"),
                ("/help-enclosure/stl/virtualglove-dock-v2-lid-full-logo.stl", "model/stl"),
                ("/help-enclosure/stl/virtualglove-lid-logo-multicolor.3mf", "model/3mf"),
            ):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("GET", path)
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 200, path)
                self.assertTrue(response.getheader("Content-Type").startswith(expected_type), path)
                connection.close()
        finally:
            servers.shutdown()

    def test_setup_direct_url_and_old_bookmarks_keep_shared_icon(self):
        servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            for path in ("/setup", "/setup?ui=2", "/setup?icon-check=1"):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("GET", path)
                response = connection.getresponse()
                body = response.read()
                self.assertEqual(response.status, 200)
                self.assertIsNone(response.getheader("Location"))
                self.assertIn(b"/favicon.ico?v=", body)
                self.assertNotIn(b"/setup?ui=", body)
                connection.close()
        finally:
            servers.shutdown()

    def test_learn_page_is_offline_practice_mode(self):
        self.assertIn(b"Practice gesture recognition without a console connection", LEARN)
        self.assertIn(b"Pixel Pal will guide you through 16 fun lessons", LEARN)
        self.assertNotIn(b"General controls: index curl is A", LEARN)
        self.assertIn(b"/api/practice", LEARN)
        self.assertIn(b"pagehide", LEARN)
        self.assertIn(b"keepalive:true", LEARN)
        self.assertIn(b"data-src=/stream", LEARN)
        self.assertIn(b"Camera unavailable. Check that it is connected", LEARN)
        self.assertIn(b"Camera image unavailable. Reconnecting", LEARN)
        self.assertIn(b"$('learn-camera').onerror", LEARN)
        self.assertIn(b"id=learn-camera-target", LEARN)
        self.assertIn(b"$('learn-camera-target').hidden=false", LEARN)
        self.assertIn(b"cameraRetryAt=Date.now()+1000", LEARN)
        self.assertNotIn(b"/api/controller", LEARN)
        self.assertIn(b"Lesson 1 of 16", LEARN)

    def test_live_camera_pages_share_the_center_target(self):
        self.assertIn(b"id=camera-centre-target", DASHBOARD)
        self.assertIn(b"id=learn-camera-target", LEARN)
        self.assertIn(b"id=rps-camera-target", PLAY)
        self.assertIn(b".camera-centre-target", DASHBOARD)
        self.assertIn(b"cameraImageReady", DASHBOARD)

    @mock.patch("virtualglove.control_server.urllib.request.urlopen")
    def test_calibration_request_is_forwarded_to_worker(self, open_worker):
        """Both web calibration buttons must reach the private vision worker."""
        open_worker.return_value.__enter__.return_value = mock.MagicMock()
        servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("POST", "/calibrate")
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 204)
            forwarded = open_worker.call_args[0][0]
            self.assertEqual(forwarded.full_url, "http://127.0.0.1:8089/calibrate")
            self.assertEqual(forwarded.method, "POST")
            connection.close()
        finally:
            servers.shutdown()

    def test_dashboard_load_clears_practice_and_restores_selected_mode(self):
        self.assertIn(b"/api/practice", DASHBOARD)
        self.assertIn(b"reset:true", DASHBOARD)

        shared = SharedDebugState()
        with mock.patch("virtualglove.debug_server.time.monotonic", return_value=10.0):
            self.assertTrue(shared.request_practice("existing-learn-tab", True))
            self.assertIs(shared.take_practice_request(), True)
            self.assertFalse(shared.request_practice("", False, reset=True))
            self.assertIs(shared.take_practice_request(), False)
            # A still-open tab cannot undo the Dashboard reset with its next heartbeat.
            self.assertFalse(shared.request_practice("existing-learn-tab", True))
            self.assertIsNone(shared.take_practice_request())
            # Reloading Learn creates a new browser session and starts normally.
            self.assertTrue(shared.request_practice("reloaded-learn-tab", True))
            self.assertIs(shared.take_practice_request(), True)

    def test_practice_leases_support_multiple_pages_and_clean_release(self):
        shared = SharedDebugState()
        with mock.patch("virtualglove.debug_server.time.monotonic", return_value=10.0):
            self.assertTrue(shared.request_practice("learn-page-one", True))
            self.assertIs(shared.take_practice_request(), True)
            self.assertTrue(shared.request_practice("learn-page-two", True))
            self.assertIsNone(shared.take_practice_request())
            self.assertTrue(shared.request_practice("learn-page-one", False))
            self.assertIsNone(shared.take_practice_request())
            self.assertFalse(shared.request_practice("learn-page-two", False))
            self.assertIs(shared.take_practice_request(), False)

    def test_abandoned_practice_lease_expires(self):
        shared = SharedDebugState()
        with mock.patch("virtualglove.debug_server.time.monotonic", return_value=10.0):
            shared.request_practice("abandoned-page", True)
            self.assertIs(shared.take_practice_request(), True)
        with mock.patch("virtualglove.debug_server.time.monotonic", return_value=17.0):
            self.assertIs(shared.take_practice_request(), False)

    def test_practice_uses_general_tracking_without_changing_selected_off_mode(self):
        self.assertEqual(_effective_profile(None, True), "practice")
        self.assertIsNone(_effective_profile(None, False))
        self.assertEqual(_effective_profile("bad_street_brawler", True), "practice")
        self.assertEqual(_effective_profile("bad_street_brawler", False), "bad_street_brawler")
        self.assertEqual(_effective_profile("program_14", True), "practice")
        self.assertIsNone(_effective_profile("program_14", False))
        status = _base_status(
            None, "Startup default", "startup", True, practice_mode=True,
        )
        self.assertEqual(status["active_profile"], "off")
        self.assertEqual(status["vision_profile"], "practice")
        self.assertTrue(status["practice_mode"])
        self.assertIn("Practice mode", status["receiver_error"])

    def test_practice_preserves_active_game_rapid_fire_switches(self):
        self.assertEqual(
            _requested_rapid_fire(None, None, False, (False, True)),
            (False, True),
        )
        request = ProfileRequest(
            "one", "program_1", "nes", "Example.nes", ("127.0.0.1", 1),
            rapid_a=True, rapid_b=False,
        )
        self.assertEqual(
            _requested_rapid_fire(request, None, False, (False, True)),
            (True, False),
        )
        self.assertEqual(
            _requested_rapid_fire(None, ("program_1", "Dashboard", "Manual"),
                                  False, (False, True)),
            (None, None),
        )

    def test_password_pairing_requires_certificate_comparison(self):
        self.assertIn(b"browser certificate fingerprint", SETUP)
        self.assertIn(b"type=password autocomplete=off disabled", SETUP)
        self.assertIn(b"verified').checked", SETUP)

    def test_setup_guides_one_time_controller_trust_without_private_keys(self):
        self.assertIn(b"Trust this Controller", SETUP)
        self.assertIn(b"href=/controller-ca.cer", SETUP)
        self.assertIn(b"Certificate Trust Settings", SETUP)
        self.assertNotIn(b"controller-ca-key.pem", SETUP)

    def test_pairing_methods_are_explicit(self):
        self.assertIn(b"SSH password", SETUP)
        self.assertIn(b"One-time code (recommended)", SETUP)

    def test_controller_connection_starts_disarmed_until_player_arms_it(self):
        self.assertFalse(self.state.controller_enabled())
        self.assertFalse(self.state.snapshot()["controller_enabled"])
        self.assertFalse(self.state.public_config()["controller_enabled"])

        self.state.set_controller_enabled(True)
        self.assertTrue(self.state.snapshot()["controller_enabled"])
        self.assertTrue(self.state.public_config()["controller_enabled"])

        restarted = ControlState(self.path)
        self.assertTrue(restarted.controller_enabled())

    def test_shutdown_controls_are_only_on_dashboard(self):
        self.assertNotIn(b"id=shutdown-system", SETUP)
        self.assertNotIn(b"/api/system/shutdown", SETUP)
        self.assertNotIn(b"id=controller-toggle", SETUP)
        for page in (DASHBOARD,):
            self.assertIn(b"id=shutdown-system", page)
            self.assertIn(b"/api/system/shutdown", page)
            self.assertIn(b"restart automatically", page.lower())
            self.assertIn(b"does not confirm it is safe to remove power", page.lower())

    def test_runtime_profile_selector_is_dashboard_only(self):
        self.assertIn(b"id=profile-selector", DASHBOARD)
        self.assertIn(b"Gestures off \xe2\x80\x94 no active profile", DASHBOARD)
        self.assertIn(b"14: Physical controller only", DASHBOARD)
        self.assertIn(b"/api/profile", DASHBOARD)
        self.assertNotIn(b"/api/profile", SETUP)

    def test_startup_feedback_is_shared_by_dashboard_and_learn(self):
        for page in (DASHBOARD, LEARN):
            self.assertIn(b"First startup can take longer.", page)
            self.assertIn(b"s.vision_started_at", page)
            self.assertIn(b"seconds}s elapsed", page)
            self.assertIn(b"updateCalibration(s)", page)
        self.assertLess(LEARN.index(b"startupMessage(s),starting="),
                        LEARN.index(b"sequence<=sequenceFloor"))

    def test_footer_version_and_application_start_metadata(self):
        from virtualglove import __version__
        for page in (DASHBOARD, LEARN, PLAY, SETUP):
            self.assertIn(("VirtualGlove v" + __version__).encode(), page)
        self.assertNotIn(b"id=app-started", DASHBOARD)
        self.assertNotIn(b"id=app-started", PLAY)
        for page in (LEARN, SETUP):
            self.assertIn(b"id=app-started", page)
        first = self.state.snapshot()
        second = self.state.snapshot()
        self.assertEqual(first["app_started_at"], self.state.started_at)
        self.assertEqual(first["app_started_at"], second["app_started_at"])
        self.assertEqual(first["version"], __version__)

    def test_pixel_pal_poses_match_each_page_purpose(self):
        self.assertIn(b"pixel-pal-web.png", DASHBOARD)
        self.assertIn(b"pixel-pal-ready.png", PLAY)
        self.assertIn(b"pixel-pal-coach.png", LEARN)
        self.assertIn(b"pixel-pal-thinking.png", SETUP)
        self.assertIn(b"pixel-pal-success.png", SETUP)
        self.assertIn(b"pixel-pal-web.png", help_index_page())

    def test_learn_has_gesture_images_and_accepts_held_menu_recognition(self):
        self.assertIn(b"id=lesson-image", LEARN)
        self.assertIn(b"/help-assets/gestures/actions/", LEARN)
        self.assertIn(b"image:'v-sign.png'", LEARN)
        self.assertIn(b"image:'thumbs-up.png'", LEARN)
        self.assertIn(b"image:'thumb-curl.png'", LEARN)
        self.assertIn(b"Glove Zap recognized!", LEARN)
        self.assertIn(b"image:'wrist-roll-left.png'", LEARN)
        self.assertIn(b"image:'wrist-roll-right.png'", LEARN)
        self.assertIn(b"image:'close-all-fingers.png'", LEARN)
        self.assertIn(b"image:'menu-guard.png'", LEARN)
        self.assertIn(b"pixel-pal-gold-cup.png", LEARN)
        self.assertIn(b"Pixel Pal holds a golden award cup", LEARN)
        self.assertIn(b"setInterval(update,75)", LEARN)
        self.assertIn(b"id=practice-actions", LEARN)
        self.assertIn(b"s.menu_gesture?.recognized", LEARN)
        self.assertIn(b"lessons[index].instant?0", LEARN)

    def test_learn_navigation_invalidates_stale_recognition_work(self):
        self.assertIn(b"function cancelLessonAdvance(){lessonRevision++", LEARN)
        self.assertIn(b"function beginTransition(){sequenceFloor=Math.max", LEARN)
        self.assertIn(b"if(requestRevision!==lessonRevision)return", LEARN)
        self.assertIn(b"sequence<=sequenceFloor", LEARN)
        self.assertIn(b"sequence<latestSequence", LEARN)
        self.assertIn(
            b"setTimeout(()=>finishLesson(advanceRevision),700)", LEARN
        )
        self.assertIn(b"$('restart-training').onclick=restartTraining", LEARN)
        self.assertIn(b"if(trainingComplete)return restartTraining()", LEARN)

    def test_profile_selectors_use_descriptive_names_and_stable_ids(self):
        expected = {
            **{f"program_{number}".encode(): f"{number}:".encode()
               for number in range(1, 15)},
            b"program_a": b"A: Pinball",
            b"program_b": b"B: Joust",
            b"program_c": b"C: Gyruss",
            b"program_d": b"D: Challenge",
            b"program_e": b"E: Defender II",
            b"program_f": b"F: Sesame Street",
            b"program_g": b"G: Gun Smoke",
            b"program_h": b"H: General",
            b"program_i": b"I: Knight Rider",
        }
        for page in (DASHBOARD, SETUP):
            for group in (
                b"Original programs 1\xe2\x80\x9314",
                b"Cartridge programs A\xe2\x80\x93I",
                b"Game-specific", b"Gestures off",
            ):
                self.assertIn(b"<optgroup label='" + group + b"'>", page)
            for profile, label in expected.items():
                self.assertIn(b"value=" + profile + b">" + label, page)
            self.assertIn(b"value=off>Gestures off</option>", page)
            self.assertNotIn(b"value=off>Gestures off \xe2\x80\x94", page)
            self.assertNotIn(b">Program A<", page)

    def test_runtime_profile_route_rejects_unknown_profiles(self):
        servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request(
                "POST", "/api/profile", json.dumps({"profile": "run-a-command"}),
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 400)
            connection.close()
        finally:
            servers.shutdown()

    def test_runtime_profile_route_forwards_valid_selection_to_worker(self):
        servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            reply = mock.MagicMock()
            reply.__enter__.return_value.read.return_value = b'{"active_profile":"program_h"}'
            with mock.patch("virtualglove.control_server.urllib.request.urlopen", return_value=reply) as open_worker:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request(
                    "POST", "/api/profile", json.dumps({"profile": "program_h"}),
                    {"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, 202)
                self.assertEqual(body["active_profile"], "program_h")
                forwarded = open_worker.call_args[0][0]
                self.assertEqual(forwarded.full_url, "http://127.0.0.1:8089/profile")
                self.assertEqual(json.loads(forwarded.data), {"profile": "program_h"})
                connection.close()
        finally:
            servers.shutdown()

    def test_practice_route_forwards_session_and_dashboard_reset(self):
        settings = self.state.public_config()
        settings["receiver"] = ""
        self.state.save_config(settings)
        servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            reply = mock.MagicMock()
            reply.__enter__.return_value.read.return_value = b'{"practice_mode":true}'
            with mock.patch(
                "virtualglove.control_server.urllib.request.urlopen",
                return_value=reply,
            ) as open_worker:
                for payload in (
                    {"session": "learn-session-1", "enabled": True},
                    {"enabled": False, "reset": True},
                ):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                    connection.request(
                        "POST", "/api/practice", json.dumps(payload),
                        {"Content-Type": "application/json"},
                    )
                    response = connection.getresponse()
                    response.read()
                    self.assertEqual(response.status, 200)
                    connection.close()

                first = open_worker.call_args_list[0][0][0]
                second = open_worker.call_args_list[1][0][0]
                self.assertEqual(first.full_url, "http://127.0.0.1:8089/practice")
                self.assertEqual(json.loads(first.data), {
                    "session": "learn-session-1", "enabled": True, "reset": False,
                })
                self.assertEqual(json.loads(second.data), {
                    "session": "", "enabled": False, "reset": True,
                })
        finally:
            servers.shutdown()

    def test_shutdown_uses_only_the_fixed_host_trigger(self):
        marker = self.path.parent / ".shutdown-enabled"
        marker.touch()
        with mock.patch("virtualglove.control_server.os.replace", wraps=os.replace) as replace:
            self.state.schedule_system_shutdown(delay_seconds=0)
            trigger = self.path.parent / "shutdown-request"
            for _attempt in range(50):
                if trigger.exists():
                    break
                time.sleep(0.01)
        replace.assert_called_once()
        self.assertEqual(Path(replace.call_args[0][1]), trigger)
        self.assertEqual(trigger.read_text(), "shutdown\n")
        self.assertEqual(trigger.stat().st_mode & 0o777, 0o600)

    def test_shutdown_requires_installed_host_helper(self):
        with self.assertRaisesRegex(FileNotFoundError, "helper is not installed"):
            self.state.schedule_system_shutdown(delay_seconds=0)

    def test_shutdown_route_requires_confirmation_header(self):
        servers, state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            with mock.patch.object(state, "schedule_system_shutdown") as schedule:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                body = json.dumps({"confirm": "SHUTDOWN"})
                connection.request("POST", "/api/system/shutdown", body, {"Content-Type": "application/json"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 403)
                schedule.assert_not_called()
                connection.close()

                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("POST", "/api/system/shutdown", body, {
                    "Content-Type": "application/json", "X-VirtualGlove-Action": "shutdown",
                    "Sec-Fetch-Site": "cross-site",
                })
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 403)
                schedule.assert_not_called()
                connection.close()

                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("POST", "/api/system/shutdown", body, {
                    "Content-Type": "application/json", "X-VirtualGlove-Action": "shutdown",
                })
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 202)
                schedule.assert_called_once_with()
                connection.close()
        finally:
            servers.shutdown()

    def test_worker_controller_request_is_consumed_once(self):
        shared = SharedDebugState()
        self.assertIsNone(shared.take_controller_request())
        shared.request_controller(True)
        self.assertTrue(shared.take_controller_request())
        self.assertIsNone(shared.take_controller_request())

    def test_preview_work_tracks_active_stream_consumers(self):
        shared = SharedDebugState()
        self.assertFalse(shared.has_stream_clients())
        shared.stream_opened()
        shared.stream_opened()
        self.assertTrue(shared.has_stream_clients())
        shared.stream_closed()
        self.assertTrue(shared.has_stream_clients())
        shared.stream_closed()
        shared.stream_closed()
        self.assertFalse(shared.has_stream_clients())

    def test_worker_profile_request_is_consumed_once_and_normalizes_off(self):
        shared = SharedDebugState()
        self.assertIsNone(shared.take_profile_request())
        shared.request_profile(None, "Dashboard", "Manual selection")
        self.assertEqual(shared.take_profile_request(), (None, "Dashboard", "Manual selection"))
        self.assertIsNone(shared.take_profile_request())

    def test_worker_rapid_fire_request_is_correlated_and_consumed_once(self):
        shared = SharedDebugState()
        shared.request_rapid_fire("rapid-test", "Example.nes", False, True)
        self.assertEqual(
            shared.take_rapid_fire_request(),
            ("rapid-test", "Example.nes", False, True),
        )
        self.assertIsNone(shared.take_rapid_fire_request())
        self.assertEqual(shared.rapid_fire_update["state"], "pending")
        shared.finish_rapid_fire("rapid-test")
        self.assertEqual(shared.rapid_fire_update, {
            "request_id": "rapid-test", "state": "applied",
            "message": "Applied to the running game.",
        })

    def test_gestures_off_reports_healthy_camera_idle_state(self):
        status = _base_status(None, "Manual selection", "dashboard", True)
        status["vision_state"] = "idle"
        self.assertEqual(status["active_profile"], "off")
        self.assertFalse(status["camera_available"])
        self.assertEqual(status["receiver_error"], "Gestures are paused")

    def test_program_14_retains_profile_while_camera_and_output_are_paused(self):
        status = _base_status("program_14", "Anticipation", "RetroPie launch hook", True)
        self.assertEqual(status["active_profile"], "program_14")
        self.assertEqual(status["vision_profile"], "off")
        self.assertFalse(status["camera_available"])
        self.assertEqual(status["receiver_error"], "Gestures are paused")
        self.assertEqual(status["rapid_fire"], {
            "a": False, "b": False, "default_a": False, "default_b": False,
            "override_a": False, "override_b": False,
        })
        overridden = _base_status(
            "program_14", "Anticipation", "RetroPie launch hook", True,
            rapid_a=True, rapid_b=True,
        )
        self.assertEqual(overridden["rapid_fire"], {
            "a": False, "b": False, "default_a": False, "default_b": False,
            "override_a": False, "override_b": False,
        })

    def test_status_reports_applied_rapid_fire_overrides_during_startup(self):
        status = _base_status(
            "program_1", "Blaster Master", "RetroPie launch hook", True,
            rapid_a=False, rapid_b=True,
        )
        self.assertEqual(status["rapid_fire"], {
            "a": False, "b": True, "default_a": False, "default_b": False,
            "override_a": False, "override_b": True,
        })

    def test_pairing_credentials_are_rejected_over_plain_http(self):
        servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            port = servers.servers[0].server_address[1]
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            body = json.dumps({"host": "retropie.local", "username": "pi", "password": "secret"})
            connection.request("POST", "/api/pair/ssh", body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 426)
            connection.close()
        finally:
            servers.shutdown()

    def test_controller_authority_download_requires_https(self):
        (self.path.parent / "controller-hostname").write_text("virtualglove\n")
        with mock.patch("virtualglove.control_server.socket.gethostname",
                        return_value="transient-container-id"):
            servers, _state = start_control_server(self.path, "127.0.0.1", 0, 0)
        try:
            plain_port = servers.servers[0].server_address[1]
            connection = http.client.HTTPConnection("127.0.0.1", plain_port, timeout=2)
            connection.request("GET", "/controller-ca.cer")
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 426)
            connection.close()

            secure_port = servers.servers[1].server_address[1]
            connection = http.client.HTTPSConnection(
                "127.0.0.1", secure_port, context=ssl._create_unverified_context())
            connection.request("GET", "/controller-ca.cer")
            response = connection.getresponse()
            body = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "application/pkix-cert")
            self.assertEqual(response.getheader("Content-Disposition"),
                             'attachment; filename="virtualglove-controller-ca.cer"')
            self.assertRegex(response.getheader("X-VirtualGlove-CA-SHA256"),
                             r"^(?:[0-9A-F]{2}:){31}[0-9A-F]{2}$")
            self.assertGreater(len(body), 500)
            connection.close()

            context = ssl.create_default_context(
                cafile=str(self.path.parent / "tls/controller-ca-cert.pem"))
            with socket.create_connection(("127.0.0.1", secure_port), timeout=2) as raw:
                with context.wrap_socket(raw, server_hostname="virtualglove.local") as trusted:
                    self.assertEqual(trusted.version()[:3], "TLS")
                    trusted.sendall(
                        b"GET /status HTTP/1.1\r\nHost: virtualglove.local\r\nConnection: close\r\n\r\n")
                    self.assertIn(b" 200 ", trusted.recv(4096).splitlines()[0])
        finally:
            servers.shutdown()

    def test_pairing_requires_a_physical_single_use_pin(self):
        displayed = []
        state = ControlState(self.path, lambda identity, pin: displayed.append((identity, pin)))
        state.configure_pairing_identity("1A2B3C4")
        result = state.begin_pairing("retropieconsole.local", "code", "retropie")
        self.assertEqual(result["certificate_id"], "1A2B3C4")
        self.assertEqual(displayed[0][0], "1A2B3C4")
        self.assertRegex(displayed[0][1], r"^\d{6}$")

        wrong_pin = "999999" if displayed[0][1] != "999999" else "000000"
        with self.assertRaisesRegex(ValueError, "rejected"):
            state.authorize_pairing("retropieconsole.local", "code", "retropie", wrong_pin)
        state.authorize_pairing("retropieconsole.local", "code", "retropie", displayed[0][1])
        with self.assertRaisesRegex(ValueError, "expired"):
            state.authorize_pairing("retropieconsole.local", "code", "retropie", displayed[0][1])

    def test_connection_status_has_unknown_fallback_and_uses_shared_probe(self):
        state = ControlState(self.path)
        health = state.connection_status()
        self.assertTrue(health['app'])
        self.assertIsNone(health['console_authenticated'])
        state.connection_probe = mock.Mock(return_value={'app': True, 'console_service': True})
        self.assertTrue(state.connection_status()['console_service'])
        self.assertTrue(state.connection_probe.call_args[1]['refresh'])

    def test_both_pairing_methods_require_their_own_controller_pin(self):
        displayed = []
        state = ControlState(self.path, pairing_display=lambda identity, pin: displayed.append(pin))
        state.configure_pairing_identity('0123456789abcdef')
        for method in ('code', 'ssh'):
            with self.assertRaises(ValueError):
                state.authorize_pairing('retropieconsole.local', method, 'retropie', '000000')
            state.begin_pairing('retropieconsole.local', method, 'retropie')
            pin = displayed[-1]
            with self.assertRaises(ValueError):
                state.authorize_pairing('retropieconsole.local', 'ssh' if method == 'code' else 'code', 'retropie', pin)
            state.authorize_pairing('retropieconsole.local', method, 'retropie', pin)

    def test_launchbox_allows_code_pairing_but_rejects_ssh(self):
        displayed = []
        state = ControlState(self.path, pairing_display=lambda identity, pin: displayed.append(pin))
        state.save_config({'platform': 'launchbox', 'receiver': 'launchbox.local', 'profile': 'off'})
        state.configure_pairing_identity('0123456789abcdef')
        state.begin_pairing('launchbox.local', 'code', 'launchbox')
        self.assertTrue(displayed)
        state.finish_pairing_display()
        with self.assertRaisesRegex(ValueError, 'one-time-code'):
            state.begin_pairing('launchbox.local', 'ssh', 'launchbox')

    def test_https_pairing_route_requires_matrix_pin_before_token_export(self):
        displayed = []
        servers, _state = start_control_server(
            self.path, "127.0.0.1", 0, 0,
            pairing_display=lambda identity, pin: displayed.append((identity, pin)),
        )
        try:
            secure_port = servers.servers[1].server_address[1]
            context = ssl._create_unverified_context()

            unauthorized = json.dumps({
                "host": "attacker.local", "code": "ABCDE-FGHIJ-23456-7ABCD",
                "device_code": "000000",
            })
            with mock.patch("virtualglove.control_server.pair_with_code") as send_token:
                connection = http.client.HTTPSConnection("127.0.0.1", secure_port, context=context)
                connection.request("POST", "/api/pair/code", unauthorized, {"Content-Type": "application/json"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 400)
                send_token.assert_not_called()
                connection.close()

            connection = http.client.HTTPSConnection("127.0.0.1", secure_port, context=context)
            begin = json.dumps({"host": "retropieconsole.local", "platform": "retropie", "method": "code"})
            connection.request("POST", "/api/pair/begin", begin, {"Content-Type": "application/json"})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 200)
            connection.close()

            payload = json.dumps({
                "host": "retropieconsole.local", "platform": "retropie", "code": "ABCDE-FGHIJ-23456-7ABCD",
                "device_code": displayed[0][1],
            })
            with mock.patch("virtualglove.control_server.pair_with_code") as send_token:
                connection = http.client.HTTPSConnection("127.0.0.1", secure_port, context=context)
                connection.request("POST", "/api/pair/code", payload, {"Content-Type": "application/json"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 200)
                send_token.assert_called_once_with(
                    "retropieconsole.local", 55357, "ABCDE-FGHIJ-23456-7ABCD", "private-token", "retropie"
                )
                connection.close()
        finally:
            servers.shutdown()

    def test_pairing_display_released_after_transport_success_or_failure(self):
        displayed = []
        finished = mock.Mock()
        servers, state = start_control_server(
            self.path, "127.0.0.1", 0, 0,
            pairing_display=lambda identity, pin: displayed.append(pin),
            pairing_finished=finished,
        )
        try:
            port = servers.servers[1].server_address[1]
            for method in ('code', 'ssh'):
                for failed in (False, True):
                    with self.subTest(method=method, failed=failed):
                        state.begin_pairing('retropieconsole.local', method, 'retropie')
                        finished.reset_mock()
                        def transport(*args):
                            finished.assert_not_called()
                            if failed:
                                raise OSError('test connection failure')
                        target = 'pair_with_code' if method == 'code' else 'pair_over_ssh'
                        with mock.patch('virtualglove.control_server.' + target, side_effect=transport):
                            connection = http.client.HTTPSConnection('127.0.0.1', port, context=ssl._create_unverified_context())
                            connection.request('POST', '/api/pair/' + method, json.dumps({
                                'host':'retropieconsole.local', 'platform':'retropie', 'device_code':displayed[-1],
                                'code':'ABCDE-FGHIJ-23456-7ABCD', 'username':'pi', 'password':'test-only',
                            }), {'Content-Type':'application/json'})
                            response = connection.getresponse()
                            response.read()
                            self.assertEqual(response.status, 503 if failed else 200)
                            finished.assert_called_once_with()
                            connection.close()
            state.begin_pairing('retropieconsole.local', 'code', 'retropie')
            finished.reset_mock()
            state.finish_pairing_display()
            finished.assert_not_called()  # An older request cannot clear a newer PIN.
        finally:
            servers.shutdown()


if __name__ == "__main__":
    unittest.main()
