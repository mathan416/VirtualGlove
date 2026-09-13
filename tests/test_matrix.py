# Project: VirtualGlove
# File: tests/test_matrix.py
# Purpose: Verify LED matrix status, profile, and physical pairing-display bridge calls.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Verified gestures idle remains distinct from system off.
#   2026-09-03 - Verified the dedicated Learn-mode matrix state.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify LED matrix status, profile, and physical pairing-display bridge calls."""

import unittest
from unittest.mock import patch

from powerglove_vision.matrix import MatrixStatus, UnoQMatrix, status_from_worker


class MatrixTests(unittest.TestCase):
    def test_attract_is_separate_cached_and_idle_probe_only(self):
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        with patch('powerglove_vision.matrix.threading.Thread') as thread:
            matrix.set_attract({'matrix_attract':'off'}, idle=False)
            matrix.set_status(MatrixStatus.TUNING)
            matrix.set_attract({'matrix_attract':'off'}, idle=False)
            thread.assert_not_called()
            self.assertEqual(calls, [('set_powerglove_attract',2,0), ('set_powerglove_status',8)])
            matrix.set_attract({'matrix_attract':'off'}, idle=True)
            thread.return_value.start.assert_called_once()
        matrix.set_attract({'matrix_attract':'dim'})
        self.assertEqual(calls[-1], ('set_powerglove_attract',1,0))
        self.assertEqual(matrix.last_status, MatrixStatus.TUNING)

    def test_setup_health_is_cached_shared_and_expires(self):
        matrix = UnoQMatrix(call=lambda *args: None)
        settings = {'receiver': 'cabinet.local', 'token': 'private-token'}
        with patch('powerglove_vision.matrix.time.monotonic', return_value=100), \
             patch('powerglove_vision.wifi_status.read_network_status', return_value='connected'), \
             patch('powerglove_vision.matrix.threading.Thread') as thread:
            initial = matrix.connection_status(settings, refresh=True)
            self.assertIsNone(initial['console_service'])
            self.assertEqual(initial['networking'], 'connected')
            matrix.connection_status(settings, refresh=True)
            thread.return_value.start.assert_called_once()
            matrix._probe_result, matrix._probe_at = 3, 95
            ready = matrix.connection_status(settings)
            self.assertTrue(ready['console_authenticated'])
            self.assertEqual(ready['checked_seconds_ago'], 5)
            self.assertNotIn('private-token', str(ready))
            matrix._probe_at = 69
            self.assertIsNone(matrix.connection_status(settings)['console_authenticated'])
            matrix._probe_at = 95
            changed = matrix.connection_status(dict(settings, receiver='other.local'))
            self.assertIsNone(changed['console_authenticated'])

    def test_failed_authentication_is_distinct_from_unreachable_and_wifi(self):
        matrix = UnoQMatrix(call=lambda *args: None)
        settings = {'receiver': 'cabinet.local', 'token': 'private-token'}
        matrix._probe_key = ('cabinet.local', 'private-token')
        matrix._probe_result, matrix._probe_at = 1, 100
        with patch('powerglove_vision.matrix.time.monotonic', return_value=101), \
             patch('powerglove_vision.wifi_status.read_network_status', return_value='disconnected'):
            health = matrix.connection_status(settings)
            self.assertTrue(health['console_service'])
            self.assertFalse(health['console_authenticated'])
            self.assertEqual(health['networking'], 'disconnected')

    def test_connection_pixels_require_reachable_and_authenticated_console(self):
        matrix = UnoQMatrix(call=lambda *args: None)
        key = ('cabinet.local','private-token')
        matrix._probe_key = key
        with patch('powerglove_vision.resolver.resolve_ipv4', return_value='10.0.0.2'), \
             patch('powerglove_vision.matrix.socket.create_connection'), \
             patch('powerglove_vision.game_registry.registry_request', return_value={}) as request:
            matrix._probe_console(key)
            self.assertEqual(matrix._probe_result,3)
            request.side_effect=ValueError('wrong token')
            matrix._probe_console(key)
            self.assertEqual(matrix._probe_result,1)
        with patch('powerglove_vision.resolver.resolve_ipv4', side_effect=OSError):
            matrix._probe_console(key)
            self.assertEqual(matrix._probe_result,0)

    def test_running_firmware_identity_is_cached_and_old_firmware_is_unknown(self):
        calls = []
        def identify(*args):
            calls.append(args)
            return 'a' * 64
        matrix = UnoQMatrix(call=identify)
        self.assertEqual(matrix.firmware_identity(), 'a' * 64)
        self.assertEqual(matrix.firmware_identity(), 'a' * 64)
        self.assertEqual(calls, [('get_powerglove_firmware',)])
        def old_firmware(*args):
            raise RuntimeError('Unknown endpoint')
        self.assertIsNone(UnoQMatrix(call=old_firmware).firmware_identity())

    def test_status_is_sent_over_bridge(self):
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        self.assertTrue(matrix.set_status(MatrixStatus.LOADING))
        self.assertTrue(matrix.set_status(MatrixStatus.READY))
        self.assertEqual(
            calls,
            [
                ("set_powerglove_status", int(MatrixStatus.LOADING)),
                ("set_powerglove_status", int(MatrixStatus.READY)),
            ],
        )

    def test_gestures_idle_is_distinct_from_system_off(self):
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        matrix.set_status(MatrixStatus.GESTURES_IDLE)
        matrix.set_status(MatrixStatus.OFF)
        self.assertEqual(calls, [
            ("set_powerglove_status", int(MatrixStatus.GESTURES_IDLE)),
            ("set_powerglove_status", int(MatrixStatus.OFF)),
        ])

    def test_learning_is_a_dedicated_matrix_state(self):
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        matrix.set_status(MatrixStatus.LEARNING)
        self.assertEqual(calls, [
            ("set_powerglove_status", int(MatrixStatus.LEARNING)),
        ])
        self.assertEqual(status_from_worker({
            "practice_mode": True,
            "active_profile": "off",
            "vision_state": "starting",
        }), MatrixStatus.LEARNING)
        self.assertEqual(status_from_worker({
            "practice_mode": True,
            "active_profile": "off",
            "vision_state": "active",
            "detected": True,
            "calibrated": True,
        }), MatrixStatus.LEARNING)
        self.assertEqual(status_from_worker({
            "practice_mode": True,
            "active_profile": "off",
            "vision_state": "error",
        }), MatrixStatus.ERROR)

    def test_tuning_has_its_own_matrix_state_even_before_camera_frames(self):
        for vision in ("starting", "active", "error", "idle"):
            self.assertEqual(status_from_worker({"vision_state": vision,
                "practice_mode": True, "tuning": {"active": True}}), MatrixStatus.TUNING)
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        matrix.set_status(MatrixStatus.TUNING)
        self.assertEqual(calls[-1], ("set_powerglove_status", 8))

    def test_duplicate_status_is_not_resent(self):
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        matrix.set_status(MatrixStatus.TRACKING)
        matrix.set_status(MatrixStatus.TRACKING)
        self.assertEqual(len(calls), 1)

    def test_bridge_failure_does_not_crash_vision(self):
        def fail(*_args):
            raise RuntimeError("not ready")

        matrix = UnoQMatrix(call=fail)
        self.assertFalse(matrix.set_status(MatrixStatus.LOADING))
        self.assertEqual(matrix.last_error, "not ready")

    def test_profile_codes_are_sent_over_bridge(self):
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        matrix.set_profile("program_c")
        matrix.set_profile("bad_street_brawler")
        matrix.set_profile("super_glove_ball")
        matrix.set_profile("program_1")
        matrix.set_profile("program_14")
        matrix.set_profile(None)
        self.assertEqual(calls, [
            ("set_powerglove_profile", 3),
            ("set_powerglove_profile", 10),
            ("set_powerglove_profile", 11),
            ("set_powerglove_profile", 12),
            ("set_powerglove_profile", 25),
            ("set_powerglove_profile", 0),
        ])

    def test_pairing_identity_and_pin_are_sent_to_physical_matrix(self):
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        self.assertTrue(matrix.show_pairing("1A2B3C4", "001234"))
        self.assertEqual(calls[-1], ("set_powerglove_pairing", 0x1A2B3C4, 1234))
        self.assertEqual(matrix.last_status, MatrixStatus.PAIRING)
        matrix.set_status(MatrixStatus.ERROR)
        self.assertEqual(len(calls), 1)

    def test_finished_pairing_restores_normal_status_before_timeout(self):
        calls = []
        matrix = UnoQMatrix(call=lambda *args: calls.append(args))
        matrix.show_pairing("1A2B3C4", "001234")
        matrix.set_status(MatrixStatus.GESTURES_IDLE)
        self.assertEqual(len(calls), 1)
        matrix.finish_pairing()
        matrix.set_status(MatrixStatus.GESTURES_IDLE)
        self.assertEqual(calls[-1], ("set_powerglove_status", int(MatrixStatus.GESTURES_IDLE)))
        matrix.set_status(MatrixStatus.TRACKING)
        self.assertEqual(matrix.last_status, MatrixStatus.TRACKING)


if __name__ == "__main__":
    unittest.main()
