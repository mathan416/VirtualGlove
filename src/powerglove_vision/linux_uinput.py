# Project: VirtualGlove
# File: src/powerglove_vision/linux_uinput.py
# Purpose: Publish portable Linux input devices without a third-party Python extension.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added dependency-free keyboard output for console ports.
# Full history: docs/CHANGELOG.md and Git history.

"""Small Linux uinput backend for console images without python-evdev."""

from __future__ import annotations

import fcntl
import os
import struct
from pathlib import Path


EV_SYN = 0
EV_KEY = 1
SYN_REPORT = 0
BUS_VIRTUAL = 0x06

KEY_ENTER = 28
KEY_Z = 44
KEY_X = 45
KEY_RIGHTSHIFT = 54
KEY_UP = 103
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_DOWN = 108


def _ioc(direction: int, kind: int, number: int, size: int) -> int:
    """Build a Linux ioctl request using the stable generic ABI layout."""
    return (direction << 30) | (size << 16) | (kind << 8) | number


def _iow(kind: int, number: int, size: int = 4) -> int:
    """Build a Linux write-direction ioctl request."""
    return _ioc(1, kind, number, size)


UI_SET_EVBIT = _iow(ord("U"), 100)
UI_SET_KEYBIT = _iow(ord("U"), 101)
UI_DEV_CREATE = _ioc(0, ord("U"), 1, 0)
UI_DEV_DESTROY = _ioc(0, ord("U"), 2, 0)


class UInputKeyboardDevice:
    """Expose VirtualGlove as Player 1 keyboard input beside a physical joypad."""

    KEY_MAP = (
        (KEY_UP, "dpad", "up"),
        (KEY_DOWN, "dpad", "down"),
        (KEY_LEFT, "dpad", "left"),
        (KEY_RIGHT, "dpad", "right"),
        (KEY_X, "buttons", "a"),
        (KEY_Z, "buttons", "b"),
        (KEY_ENTER, "buttons", "start"),
        (KEY_RIGHTSHIFT, "buttons", "select"),
    )

    def __init__(self, path: Path = Path("/dev/uinput")) -> None:
        if os.name != "posix":
            raise RuntimeError("uinput is available only on Linux consoles")
        self.descriptor = os.open(str(path), os.O_WRONLY | os.O_NONBLOCK)
        self.closed = False
        try:
            fcntl.ioctl(self.descriptor, UI_SET_EVBIT, EV_KEY)
            for code, _group, _name in self.KEY_MAP:
                fcntl.ioctl(self.descriptor, UI_SET_KEYBIT, code)
            # The legacy uinput_user_dev structure remains supported and avoids
            # depending on architecture-specific C headers or Python modules.
            identity = struct.pack("80sHHHHi", b"VirtualGlove Keyboard", BUS_VIRTUAL,
                                   1, 2, 0x0100, 0)
            axes = struct.pack("256i", *([0] * 256))
            os.write(self.descriptor, identity + axes)
            fcntl.ioctl(self.descriptor, UI_DEV_CREATE)
        except BaseException:
            os.close(self.descriptor)
            self.closed = True
            raise

    def _event(self, kind: int, code: int, value: int) -> None:
        """Write one native Linux input_event to the virtual keyboard."""
        os.write(self.descriptor, struct.pack("llHHi", 0, 0, kind, code, value))

    def write_state(self, state: dict) -> None:
        """Write a complete keyboard state and synchronize it atomically."""
        for code, group, name in self.KEY_MAP:
            self._event(EV_KEY, code, int(bool(state.get(group, {}).get(name, False))))
        self._event(EV_SYN, SYN_REPORT, 0)

    def release(self) -> None:
        """Release every VirtualGlove key."""
        self.write_state({})

    def close(self) -> None:
        """Remove the virtual device and close its kernel handle."""
        if self.closed:
            return
        try:
            fcntl.ioctl(self.descriptor, UI_DEV_DESTROY)
        finally:
            os.close(self.descriptor)
            self.closed = True
