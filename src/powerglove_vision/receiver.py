# Project: VirtualGlove
# File: src/powerglove_vision/receiver.py
# Purpose: Validate controller datagrams and publish them through the selected local input backend.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-07 - Publish native Super Glove Ball state before virtual-gamepad output.
#   2026-09-06 - Add opt-in correlated latency diagnostics without changing input formats.
#   2026-09-06 - Implement signed controller sessions and separate maintained web modules.
#   2026-09-06 - Address Setup review reliability and private configuration findings.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.

"""Validate controller datagrams and publish them through a local input backend."""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

from .diagnostic_trace import DiagnosticTrace, session_key
from .native_state import DEFAULT_PATH as DEFAULT_NATIVE_STATE_PATH, NativeStateWriter
from .transport import MAX_PACKET_BYTES
from .controller_protocol import ReceiverSessions


class DryRunDevice:
    """Print received state changes without creating a kernel input device."""
    def write_state(self, state: dict) -> None:
        """Print the meaningful controls in one accepted packet."""
        print(
            f"seq={state.get('sequence')} detected={state.get('detected')} "
            f"dpad={state.get('dpad')} buttons={state.get('buttons')} axes={state.get('axes')}",
            flush=True,
        )

    def release(self) -> None:
        """Report a timeout-driven neutral-controller release."""
        print("released", flush=True)

    def close(self) -> None:
        """Complete the no-resource dry-run device interface."""
        pass


class UInputDevice:
    """Expose authenticated VirtualGlove state as a standard Linux gamepad."""
    def __init__(self) -> None:
        try:
            from evdev import AbsInfo, UInput, ecodes
        except ImportError as exc:
            raise RuntimeError("install receiver dependencies with: pip install -e '.[receiver]'") from exc
        self.ecodes = ecodes
        absolute = AbsInfo(value=0, min=-32767, max=32767, fuzz=256, flat=2048, resolution=0)
        capabilities = {
            ecodes.EV_KEY: [
                ecodes.BTN_SOUTH, ecodes.BTN_EAST, ecodes.BTN_START,
                ecodes.BTN_SELECT, ecodes.BTN_TR2,
                ecodes.BTN_DPAD_UP, ecodes.BTN_DPAD_DOWN,
                ecodes.BTN_DPAD_LEFT, ecodes.BTN_DPAD_RIGHT,
            ],
            ecodes.EV_ABS: [
                (ecodes.ABS_X, absolute), (ecodes.ABS_Y, absolute),
                (ecodes.ABS_RX, absolute), (ecodes.ABS_RY, absolute),
            ],
        }
        self.device = UInput(capabilities, name="VirtualGlove", version=0x0100)

    def write_state(self, state: dict) -> None:
        """Write all buttons and axes, then synchronize the uinput frame."""
        e = self.ecodes
        dpad = state.get("dpad", {})
        buttons = state.get("buttons", {})
        axes = state.get("axes", {})
        for code, value in (
            (e.BTN_DPAD_UP, dpad.get("up", False)),
            (e.BTN_DPAD_DOWN, dpad.get("down", False)),
            (e.BTN_DPAD_LEFT, dpad.get("left", False)),
            (e.BTN_DPAD_RIGHT, dpad.get("right", False)),
            (e.BTN_SOUTH, buttons.get("a", False)),
            (e.BTN_EAST, buttons.get("b", False)),
            (e.BTN_START, buttons.get("start", False)),
            (e.BTN_SELECT, buttons.get("select", False)),
            (e.BTN_TR2, buttons.get("glove_zap", False)),
        ):
            self.device.write(e.EV_KEY, code, int(bool(value)))
        for code, name in ((e.ABS_X, "x"), (e.ABS_Y, "y"), (e.ABS_RX, "roll"), (e.ABS_RY, "z")):
            self.device.write(e.EV_ABS, code, int(axes.get(name, 0)))
        self.device.syn()

    def release(self) -> None:
        """Emit a neutral frame so no control remains held after loss or shutdown."""
        self.write_state({"dpad": {}, "buttons": {}, "axes": {}})

    def close(self) -> None:
        """Close and remove the virtual input device."""
        self.device.close()


def build_parser() -> argparse.ArgumentParser:
    """Create the virtual-controller receiver command-line parser."""
    parser = argparse.ArgumentParser(description="Receive VirtualGlove as a local input device")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=55355)
    tokens = parser.add_mutually_exclusive_group(required=True)
    tokens.add_argument("--token")
    tokens.add_argument("--token-file", type=Path)
    parser.add_argument("--timeout-ms", type=int, default=250)
    parser.add_argument("--native-state", type=Path, default=DEFAULT_NATIVE_STATE_PATH,
                        help="latest validated sample for the custom Nestopia core")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-device", choices=("gamepad", "keyboard", "windows-keyboard"),
                        default="gamepad",
                        help="publish a gamepad or merge keys beside physical Player 1")
    return parser


def main() -> int:
    """Authenticate sequenced datagrams, drive uinput, and release controls on timeout."""
    args = build_parser().parse_args()
    token = args.token if args.token is not None else args.token_file.read_text().strip()
    if len(token) < 16:
        raise ValueError("receiver token must contain at least 16 characters")
    # Keep an idle virtual controller out of frontend startup. Create the real
    # uinput device only after an authenticated controller packet arrives.
    device = DryRunDevice() if args.dry_run else None
    native = None
    try:
        native = NativeStateWriter(args.native_state)
    except OSError as exc:
        # The standard uinput path remains usable on systems without the optional core.
        print(f"Native VirtualGlove state unavailable: {exc}", flush=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.listen, args.port))
    packet_info = sys.platform.startswith("linux")
    if packet_info:
        # Linux in_pktinfo preserves the receiving address/interface for replies.
        # This matters when Ethernet and Wi-Fi share a subnet behind container NAT.
        sock.setsockopt(socket.IPPROTO_IP, 8, 1)  # IP_PKTINFO (Linux ABI)
    if args.timeout_ms <= 0:
        sock.close()
        raise ValueError("receiver timeout must be positive")
    timeout = args.timeout_ms / 1000
    sock.settimeout(timeout)
    last_valid_at = None
    released = True
    last_sequence = -1
    sessions = ReceiverSessions(token)
    trace = DiagnosticTrace.from_environment("receiver")
    try:
        while True:
            now = time.monotonic()
            if last_valid_at is not None and not released and now - last_valid_at >= timeout:
                device.release()
                if native is not None:
                    native.release(last_sequence + 1)
                released = True
            remaining = timeout if released or last_valid_at is None else timeout - (now - last_valid_at)
            sock.settimeout(max(0.001, remaining))
            try:
                reply_info = []
                if packet_info:
                    payload, ancillary, _flags, _peer = sock.recvmsg(MAX_PACKET_BYTES + 1, socket.CMSG_SPACE(12))
                    reply_info = [(level, kind, data[:12]) for level, kind, data in ancillary
                                  if level == socket.IPPROTO_IP and kind == 8 and len(data) >= 12]
                else:
                    payload, _peer = sock.recvfrom(MAX_PACKET_BYTES + 1)
                received_ns = time.monotonic_ns() if trace and trace.enabled else 0
                try:
                    state, reply = sessions.receive(payload, _peer)
                except (ValueError, UnicodeError, RecursionError):
                    continue
                if reply is not None:
                    try:
                        if reply_info:
                            sock.sendmsg([reply], reply_info, 0, _peer)
                        else:
                            sock.sendto(reply, _peer)
                    except OSError:
                        pass
                if state is None:
                    continue
                validated_ns = time.monotonic_ns() if received_ns else 0
                sequence = state["sequence"]
                last_sequence = sequence
                publication_started_ns = time.monotonic_ns() if received_ns else 0
                native_first = native is not None and state.get("profile") == "super_glove_ball"
                native_started_ns = native_completed_ns = 0
                if native_first:
                    native_started_ns = time.monotonic_ns() if received_ns else 0
                    native.write(state)
                    native_completed_ns = time.monotonic_ns() if received_ns else 0
                if device is None:
                    if args.output_device == "windows-keyboard":
                        from .windows_input import WindowsKeyboardDevice
                        device = WindowsKeyboardDevice()
                    else:
                        from .linux_uinput import UInputKeyboardDevice
                        device = (UInputKeyboardDevice() if args.output_device == "keyboard"
                                  else UInputDevice())
                device.write_state(state)
                if native is not None and not native_first:
                    native_started_ns = time.monotonic_ns() if received_ns else 0
                    native.write(state)
                    native_completed_ns = time.monotonic_ns() if received_ns else 0
                released = False
                last_valid_at = time.monotonic()
                if received_ns:
                    completed_ns = time.monotonic_ns()
                    identity = sessions.active[0][0]
                    trace.record(dict(event="receive", session=session_key(identity),
                        sequence=sequence, received_ns=received_ns, validated_ns=validated_ns,
                        publication_start_ns=publication_started_ns, end_ns=completed_ns,
                        native_start_ns=native_started_ns or None,
                        native_end_ns=native_completed_ns or None,
                        published_ns=native.published_ns if native else None,
                        guard=native.guard if native else None))
            except socket.timeout:
                if device is not None and not released:
                    device.release()
                    if native is not None:
                        native.release(last_sequence + 1)
                    released = True
    except KeyboardInterrupt:
        return 0
    finally:
        if device is not None:
            device.release()
            device.close()
        if native is not None:
            native.close()
        sock.close()
        if trace:
            trace.close()


if __name__ == "__main__":
    raise SystemExit(main())
