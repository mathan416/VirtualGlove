# Project: VirtualGlove
# File: tests/test_windows_input.py
# Purpose: Verify transition-safe Windows Player 1 keyboard output.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added Windows keyboard transition and focus-safety tests.
# Full history: docs/CHANGELOG.md and Git history.

"""Tests for the LaunchBox Windows input publisher."""

import unittest

from powerglove_vision import windows_input


class WindowsKeyboardTests(unittest.TestCase):
    def test_emits_only_transitions_and_releases_owned_keys(self):
        events = []
        device = windows_input.WindowsKeyboardDevice(
            sender=lambda key, pressed: events.append((key, pressed))
        )
        state = {"dpad": {"left": True}, "buttons": {"a": True, "start": True}}
        device.write_state(state)
        device.write_state(state)
        device.write_state({"buttons": {"a": True}})
        device.close()

        self.assertEqual(events, [
            (windows_input.VK_RETURN, True),
            (windows_input.VK_LEFT, True),
            (windows_input.VK_X, True),
            (windows_input.VK_RETURN, False),
            (windows_input.VK_LEFT, False),
            (windows_input.VK_X, False),
        ])
        with self.assertRaisesRegex(RuntimeError, "closed"):
            device.write_state(state)

    def test_real_backend_is_rejected_outside_windows(self):
        if windows_input.os.name != "nt":
            with self.assertRaisesRegex(RuntimeError, "only on Windows"):
                windows_input.WindowsKeyboardDevice()

    def test_focus_loss_releases_keys_and_blocks_other_windows(self):
        events = []
        focused = [True]
        device = windows_input.WindowsKeyboardDevice(
            sender=lambda key, pressed: events.append((key, pressed)),
            active_window=lambda: focused[0],
        )
        state = {"buttons": {"a": True}}
        device.write_state(state)
        focused[0] = False
        device.write_state(state)
        device.write_state(state)
        focused[0] = True
        device.write_state(state)
        device.close()
        self.assertEqual(events, [
            (windows_input.VK_X, True),
            (windows_input.VK_X, False),
            (windows_input.VK_X, True),
            (windows_input.VK_X, False),
        ])


if __name__ == "__main__":
    unittest.main()
