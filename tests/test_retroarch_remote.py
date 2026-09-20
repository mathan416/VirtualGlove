# Project: VirtualGlove
# File: tests/test_retroarch_remote.py
# Purpose: Verify safe loopback RetroArch Network RetroPad output.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-18 - Added safe loopback Network RetroPad coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Tests for the LaunchBox Network RetroPad publisher."""

import struct
import threading
from unittest import mock
import unittest

from virtualglove import retroarch_remote


class RetroArchRemoteTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.device = retroarch_remote.RetroArchRemoteDevice(
            55001, sender=lambda payload, target: self.sent.append((payload, target)),
            refresh_hz=None,
        )

    def decoded(self):
        return [struct.unpack("<iiiiHxx", payload) for payload, _target in self.sent]

    def test_initialization_clears_every_supported_button_on_loopback(self):
        self.assertEqual(len(self.sent), 8)
        self.assertTrue(all(target == ("127.0.0.1", 55001)
                            for _payload, target in self.sent))
        self.assertEqual({item[3] for item in self.decoded()}, {0, 2, 3, 4, 5, 6, 7, 8})
        self.assertTrue(all(item[0:3] == (0, 1, 0) and item[4] == 0
                            for item in self.decoded()))

    def test_transitions_merge_directions_buttons_start_and_select(self):
        self.sent.clear()
        self.device.write_state({
            "dpad": {"left": True, "up": True},
            "buttons": {"a": True, "start": True, "select": True},
        })
        self.assertEqual({(item[3], item[4]) for item in self.decoded()},
                         {(6, 1), (4, 1), (8, 1), (3, 1), (2, 1)})
        self.sent.clear()
        self.device.write_state({
            "dpad": {"right": True}, "buttons": {"b": True},
        })
        self.assertEqual({(item[3], item[4]) for item in self.decoded()},
                         {(6, 0), (4, 0), (8, 0), (3, 0), (2, 0), (7, 1), (0, 1)})

    def test_repeated_state_is_quiet_and_release_clears_only_owned_inputs(self):
        state = {"dpad": {"down": True}, "buttons": {"b": True}}
        self.sent.clear()
        self.device.write_state(state)
        self.sent.clear()
        self.device.write_state(state)
        self.assertEqual(self.sent, [])
        self.device.release()
        self.assertEqual({(item[3], item[4]) for item in self.decoded()}, {(0, 0), (5, 0)})
        self.sent.clear()
        self.device.release()
        self.assertEqual(self.sent, [])

    def test_rejects_non_dynamic_ports_and_unknown_controls(self):
        with self.assertRaises(ValueError):
            retroarch_remote.RetroArchRemoteDevice(48000, sender=lambda *_args: None)
        with self.assertRaises(ValueError):
            retroarch_remote.encode_button(15, True)
        with self.assertRaises(ValueError):
            retroarch_remote.RetroArchRemoteDevice(
                55001, sender=lambda *_args: None, refresh_hz=1,
            )

    def test_held_control_is_refreshed_until_release(self):
        refreshed = threading.Event()
        sent = []

        def sender(payload, target):
            sent.append((payload, target))
            if len(sent) > 9:
                refreshed.set()

        device = retroarch_remote.RetroArchRemoteDevice(
            55002, sender=sender, refresh_hz=100,
        )
        try:
            device.write_state({"dpad": {"right": True}})
            self.assertTrue(refreshed.wait(0.5))
            decoded = [struct.unpack("<iiiiHxx", payload) for payload, _ in sent]
            self.assertGreaterEqual(decoded.count((0, 1, 0, 7, 1)), 2)
            device.release()
            self.assertEqual(struct.unpack("<iiiiHxx", sent[-1][0]), (0, 1, 0, 7, 0))
        finally:
            device.close()

    def test_close_releases_then_refuses_more_state(self):
        self.device.write_state({"buttons": {"a": True}})
        self.sent.clear()
        self.device.close()
        self.assertEqual([(item[3], item[4]) for item in self.decoded()], [(8, 0)])
        with self.assertRaises(RuntimeError):
            self.device.write_state({})

    def test_loopback_check_fails_closed_when_port_is_already_owned(self):
        listener = mock.Mock()
        listener.bind.side_effect = OSError("owned")
        with mock.patch.object(retroarch_remote.socket, "socket", return_value=listener):
            self.assertFalse(retroarch_remote.check_loopback(55001))
        listener.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
