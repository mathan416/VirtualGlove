# Project: VirtualGlove
# File: tests/test_linux_uinput.py
# Purpose: Verify the dependency-free Recalbox/Batocera keyboard device backend.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added dependency-free uinput keyboard coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Tests for the direct Linux uinput keyboard publisher."""

import struct
import unittest
from unittest.mock import patch

from powerglove_vision import linux_uinput


class UInputKeyboardTests(unittest.TestCase):
    def test_creates_keyboard_without_axes_and_maps_player_one_controls(self):
        writes = []
        ioctls = []
        with patch.object(linux_uinput.os, "open", return_value=17), \
                patch.object(linux_uinput.os, "write", side_effect=lambda _fd, data: writes.append(data)), \
                patch.object(linux_uinput.os, "close"), \
                patch.object(linux_uinput.fcntl, "ioctl", side_effect=lambda *args: ioctls.append(args)):
            device = linux_uinput.UInputKeyboardDevice()
            device.write_state({"dpad": {"left": True},
                                "buttons": {"a": True, "start": True}})
            device.release()
            device.close()

        self.assertEqual(len(writes[0]), 1116)
        self.assertIn((17, linux_uinput.UI_SET_EVBIT, linux_uinput.EV_KEY), ioctls)
        self.assertIn((17, linux_uinput.UI_SET_KEYBIT, linux_uinput.KEY_X), ioctls)
        self.assertNotIn(linux_uinput.EV_ABS if hasattr(linux_uinput, "EV_ABS") else 3,
                         [item[2] for item in ioctls if len(item) > 2])
        events = [struct.unpack("llHHi", item) for item in writes[1:]]
        self.assertIn((0, 0, linux_uinput.EV_KEY, linux_uinput.KEY_LEFT, 1), events)
        self.assertIn((0, 0, linux_uinput.EV_KEY, linux_uinput.KEY_X, 1), events)
        self.assertIn((0, 0, linux_uinput.EV_KEY, linux_uinput.KEY_ENTER, 1), events)
        self.assertEqual(events[-1], (0, 0, linux_uinput.EV_SYN,
                                      linux_uinput.SYN_REPORT, 0))

    def test_constructor_failure_closes_descriptor(self):
        with patch.object(linux_uinput.os, "open", return_value=19), \
                patch.object(linux_uinput.fcntl, "ioctl", side_effect=OSError("rejected")), \
                patch.object(linux_uinput.os, "close") as close:
            with self.assertRaises(OSError):
                linux_uinput.UInputKeyboardDevice()
        close.assert_called_once_with(19)


if __name__ == "__main__":
    unittest.main()
