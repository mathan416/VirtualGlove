# Project: VirtualGlove
# File: src/powerglove_vision/windows_input.py
# Purpose: Merge authenticated VirtualGlove controls into a Windows Player 1 keyboard map.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added foreground-bound Windows Player 1 keyboard output.
# Full history: docs/CHANGELOG.md and Git history.

"""Dependency-free Windows keyboard injection for LaunchBox and RetroArch."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Callable


KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

VK_RETURN = 0x0D
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_X = 0x58
VK_Z = 0x5A
VK_RSHIFT = 0xA1


class _KEYBDINPUT(ctypes.Structure):
    """Describe one Win32 keyboard input event."""

    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class _INPUTUNION(ctypes.Union):
    """Hold the keyboard member of a Win32 INPUT value."""

    _fields_ = (("ki", _KEYBDINPUT),)


class _INPUT(ctypes.Structure):
    """Describe the Win32 INPUT wrapper passed to SendInput."""

    _anonymous_ = ("data",)
    _fields_ = (("type", wintypes.DWORD), ("data", _INPUTUNION))


def _send_input(virtual_key: int, pressed: bool) -> None:
    """Send one keyboard transition through the interactive Windows desktop."""
    event = _INPUT(
        type=INPUT_KEYBOARD,
        data=_INPUTUNION(
            ki=_KEYBDINPUT(
                wVk=virtual_key,
                wScan=0,
                dwFlags=0 if pressed else KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    send_input = ctypes.windll.user32.SendInput
    send_input.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
    send_input.restype = wintypes.UINT
    sent = send_input(1, ctypes.byref(event), ctypes.sizeof(_INPUT))
    if sent != 1:
        raise OSError("Windows rejected a VirtualGlove keyboard event")


def _retroarch_is_foreground() -> bool:
    """Limit synthetic gameplay keys to the installed RetroArch window."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
    )
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    window = user32.GetForegroundWindow()
    if not window:
        return False
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    process = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value
    )
    if not process:
        return False
    try:
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if not kernel32.QueryFullProcessImageNameW(
                process, 0, path, ctypes.byref(length)):
            return False
        return path.value.rsplit("\\", 1)[-1].casefold() == "retroarch.exe"
    finally:
        kernel32.CloseHandle(process)


class WindowsKeyboardDevice:
    """Publish controls as Player 1 keys without replacing an XInput joypad."""

    KEY_MAP = (
        (VK_UP, "dpad", "up"),
        (VK_DOWN, "dpad", "down"),
        (VK_LEFT, "dpad", "left"),
        (VK_RIGHT, "dpad", "right"),
        (VK_X, "buttons", "a"),
        (VK_Z, "buttons", "b"),
        (VK_RETURN, "buttons", "start"),
        (VK_RSHIFT, "buttons", "select"),
    )

    def __init__(
        self,
        sender: Callable[[int, bool], None] | None = None,
        active_window: Callable[[], bool] | None = None,
    ) -> None:
        if sender is None and os.name != "nt":
            raise RuntimeError("Windows keyboard output is available only on Windows")
        self._sender = sender or _send_input
        self._active_window = active_window or (
            _retroarch_is_foreground if sender is None else lambda: True
        )
        self._pressed: set[int] = set()
        self.closed = False

    def write_state(self, state: dict) -> None:
        """Emit only changed keys so held controls remain stable in RetroArch."""
        if self.closed:
            raise RuntimeError("Windows keyboard output is closed")
        desired = {
            code for code, group, name in self.KEY_MAP
            if bool(state.get(group, {}).get(name, False))
        } if self._active_window() else set()
        for code in sorted(self._pressed - desired):
            self._sender(code, False)
        for code in sorted(desired - self._pressed):
            self._sender(code, True)
        self._pressed = desired

    def release(self) -> None:
        """Release every key currently owned by VirtualGlove."""
        self.write_state({})

    def close(self) -> None:
        """Release controls and make subsequent writes fail closed."""
        if self.closed:
            return
        self.release()
        self.closed = True
