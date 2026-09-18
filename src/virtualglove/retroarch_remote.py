# Project: VirtualGlove
# File: src/virtualglove/retroarch_remote.py
# Purpose: Publish authenticated controls to RetroArch's loopback Network RetroPad.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-18 - Added loopback-only LaunchBox RetroPad output.
# Full history: docs/CHANGELOG.md and Git history.

"""Send bounded Player 1 state to RetroArch's built-in Network RetroPad."""

from __future__ import annotations

import argparse
import socket
import struct
import threading
from typing import Callable


RETRO_DEVICE_JOYPAD = 1
PACKET = struct.Struct("<iiiiHxx")

# libretro RetroPad identifiers. These are core inputs, not RetroArch hotkeys.
CONTROL_IDS = (
    ("buttons", "b", 0),
    ("buttons", "select", 2),
    ("buttons", "start", 3),
    ("dpad", "up", 4),
    ("dpad", "down", 5),
    ("dpad", "left", 6),
    ("dpad", "right", 7),
    ("buttons", "a", 8),
)


def encode_button(control_id: int, pressed: bool) -> bytes:
    """Encode RetroArch's native remote_message layout for Player 1."""
    if control_id not in {item[2] for item in CONTROL_IDS}:
        raise ValueError("unsupported RetroPad control")
    return PACKET.pack(0, RETRO_DEVICE_JOYPAD, 0, control_id, int(bool(pressed)))


class RetroArchRemoteDevice:
    """Merge VirtualGlove into RetroArch Player 1 over a loopback-only socket."""

    def __init__(
        self,
        port: int,
        *,
        sender: Callable[[bytes, tuple[str, int]], object] | None = None,
        refresh_hz: float | None = 60.0,
    ) -> None:
        if not 49152 <= int(port) <= 65535:
            raise ValueError("RetroArch remote port must be in the dynamic range")
        self.port = int(port)
        self._socket = None
        if sender is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sender = self._socket.sendto
        self._sender = sender
        self._pressed: set[int] = set()
        self._refresh_index = 0
        self._condition = threading.Condition()
        self._refresh_interval = None if refresh_hz is None else 1.0 / float(refresh_hz)
        if self._refresh_interval is not None and not 0.005 <= self._refresh_interval <= 0.1:
            raise ValueError("RetroArch refresh rate is out of range")
        self._stopping = False
        self._refresh_thread = None
        self.closed = False
        # A supervised receiver may be replacing one that stopped while a
        # control was held. Clear all supported controls before accepting state.
        self._send_neutral()
        if self._refresh_interval is not None:
            self._refresh_thread = threading.Thread(
                target=self._refresh_loop,
                name="virtualglove-retroarch-refresh",
                daemon=True,
            )
            self._refresh_thread.start()

    def _send(self, control_id: int, pressed: bool) -> None:
        self._sender(encode_button(control_id, pressed), ("127.0.0.1", self.port))

    def _send_neutral(self) -> None:
        for _group, _name, control_id in CONTROL_IDS:
            self._send(control_id, False)
        self._pressed.clear()

    def _refresh_loop(self) -> None:
        """Keep one held control visible to affected Windows RetroArch builds."""
        assert self._refresh_interval is not None
        with self._condition:
            while not self._stopping:
                if not self._pressed:
                    self._condition.wait()
                    continue
                controls = sorted(self._pressed)
                control_id = controls[self._refresh_index % len(controls)]
                self._refresh_index += 1
                self._send(control_id, True)
                self._condition.wait(timeout=self._refresh_interval)

    def write_state(self, state: dict) -> None:
        """Send transitions and safely refresh holds for Windows RetroArch."""
        desired = {
            control_id
            for group, name, control_id in CONTROL_IDS
            if bool(state.get(group, {}).get(name, False))
        }
        with self._condition:
            if self.closed:
                raise RuntimeError("RetroArch remote output is closed")
            for control_id in sorted(self._pressed - desired):
                self._send(control_id, False)
            for control_id in sorted(desired - self._pressed):
                self._send(control_id, True)
            self._pressed = desired
            self._refresh_index = 0
            self._condition.notify_all()

    def release(self) -> None:
        """Release every control currently owned by this receiver."""
        with self._condition:
            if not self.closed:
                for control_id in sorted(self._pressed):
                    self._send(control_id, False)
                self._pressed.clear()
                self._refresh_index = 0
                self._condition.notify_all()

    def close(self) -> None:
        """Release controls and close the local datagram socket."""
        with self._condition:
            if self.closed:
                return
            for control_id in sorted(self._pressed):
                self._send(control_id, False)
            self._pressed.clear()
            self.closed = True
            self._stopping = True
            self._condition.notify_all()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=1.0)
        if self._socket is not None:
            self._socket.close()


def check_loopback(port: int) -> bool:
    """Prove the configured local port carries a correctly sized neutral packet."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.settimeout(1.0)
    try:
        listener.bind(("127.0.0.1", int(port)))
        device = RetroArchRemoteDevice(port)
        try:
            payload, peer = listener.recvfrom(PACKET.size + 1)
            return len(payload) == PACKET.size and peer[0] == "127.0.0.1"
        finally:
            device.close()
    except OSError:
        return False
    finally:
        listener.close()


def main() -> int:
    """Run the installer's bounded loopback transport check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-loopback", type=int, metavar="PORT", required=True)
    args = parser.parse_args()
    if not check_loopback(args.check_loopback):
        print("FAIL  RetroArch loopback input check failed")
        return 1
    print("PASS  RetroArch loopback input is available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
