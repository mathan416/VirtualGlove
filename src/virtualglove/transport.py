# Project: VirtualGlove
# File: src/virtualglove/transport.py
# Purpose: Encode bounded controller packets and send them to RetroPie without blocking vision recovery.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Add paired-console liveness and authenticated LAN discovery.
#   2026-09-09 - Prioritized state packets and bounded handshake maintenance work.
#   2026-09-06 - Add opt-in correlated latency diagnostics without changing input formats.
#   2026-09-06 - Implement signed controller sessions and separate maintained web modules.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-05 - Carried native closed-hand and index-point recognition states.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Support an unconfigured first-run receiver without blocking local practice.

"""Encode bounded controller packets and send them to RetroPie without blocking vision recovery."""

from __future__ import annotations

import socket
import time
import uuid

from .diagnostic_trace import DiagnosticTrace, session_key
from .model import ControllerState
from .controller_protocol import encode_message, decode_message
from .wifi_status import read_discovery_addresses


MAX_PACKET_BYTES = 4096
DISCOVERY_ADDRESS = "255.255.255.255"
DISCOVERY_AFTER_SECONDS = 3.0
DISCOVERY_INTERVAL_SECONDS = 2.0


def validate_state(data: dict) -> dict:
    """Validate one controller state carried inside an authenticated v2 message."""
    if not isinstance(data, dict):
        raise ValueError("invalid controller state")
    if set(data) - {
        "sequence", "timestamp", "profile", "detected", "confidence",
        "calibrated", "axes", "dpad", "buttons", "fingers", "events",
    }:
        raise ValueError("invalid controller state fields")
    sequence = data.get("sequence")
    if type(sequence) is not int or not 0 <= sequence <= 2_147_483_647:
        raise ValueError("invalid controller sequence")
    for name, keys, maximum in (
        ("axes", {"x", "y", "z", "roll"}, 32767),
        ("dpad", {"up", "down", "left", "right"}, None),
        ("buttons", {
            "a", "b", "start", "select", "glove_zap", "menu_guard",
            "closed_hand", "index_point",
        }, None),
        ("fingers", {"thumb", "index", "middle", "ring", "pinky"}, 3),
    ):
        values = data.get(name, {})
        if not isinstance(values, dict) or set(values) - keys:
            raise ValueError("invalid controller " + name)
        for value in values.values():
            if maximum is None:
                valid = type(value) is bool
            else:
                valid = type(value) is int and (-maximum if name == "axes" else 0) <= value <= maximum
            if not valid:
                raise ValueError("invalid controller " + name)
    for name in ("timestamp", "confidence"):
        if name in data:
            value = data[name]
            if (type(value) not in (int, float)
                    or not 0 <= value <= (1 if name == "confidence" else 1e15)):
                raise ValueError("invalid controller " + name)
    for name in ("detected", "calibrated"):
        if name in data and type(data[name]) is not bool:
            raise ValueError("invalid controller " + name)
    profile = data.get("profile")
    if profile is not None and (not isinstance(profile, str) or not 1 <= len(profile) <= 64):
        raise ValueError("invalid controller profile")
    events = data.get("events", [])
    if (not isinstance(events, list) or len(events) > 32
            or any(not isinstance(value, str) or len(value) > 64 for value in events)):
        raise ValueError("invalid controller events")
    return data


from .resolver import BackgroundAddress, resolve_ipv4


class UdpSender:
    """Send controller states in recoverable sessions over connectionless UDP."""
    def __init__(self, host: str, port: int, token: str | None) -> None:
        self.trace = DiagnosticTrace.from_environment("controller")
        self.destination = (host, port)
        self.token = token
        self.session = uuid.uuid4().hex
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.address = BackgroundAddress(host, resolve=resolve_ipv4)
        self.challenge = None
        self.request = None
        self._hello_at = 0.0
        self._peer = None
        self._last_reply_at = 0.0
        self._discovery_at = 0.0
        self._started_at = time.monotonic()
        self.discovery_addresses = read_discovery_addresses
        self.last_error: str | None = None
        self._retry_at = 0.0

    def send(self, state: ControllerState) -> bool:
        """Send a controller state without letting network loss stop vision.

        UDP has no persistent connection, and hostname resolution can briefly
        fail while Wi-Fi, mDNS, or the RetroPie console is starting. Throttle
        retries after an error so tracking and the dashboard remain responsive.
        """
        if not self.destination[0].strip():
            self.last_error = "Configure your console destination in Connection before starting controls."
            return False
        now = time.monotonic()
        if now < self._retry_at:
            return False
        if not self.token:
            self.last_error = "Pair with your console before starting controls."
            return False
        try:
            # Drain only a bounded number of small handshake replies; input itself
            # is never queued. Accept replies only for our newest hello request.
            for _ in range(2):
                try:
                    payload, source = self.socket.recvfrom(MAX_PACKET_BYTES + 1)
                except BlockingIOError:
                    break
                # A multi-homed receiver may reply from its preferred interface.
                # Its identity is the HMAC plus our fresh request/session, not IP.
                if source[1] != self.destination[1]:
                    continue
                try:
                    reply = decode_message(payload, self.token)
                except (ValueError, UnicodeError, RecursionError):
                    continue
                if (reply["kind"] == "challenge" and reply["session"] == self.session
                        and reply["request"] == self.request):
                    self.challenge = reply["challenge"]
                    self._peer = (source[0], self.destination[1])
                    self._last_reply_at = now

            address, error = self.address.current()
            configured_peer = (address, self.destination[1]) if address is not None else None
            if self._peer is None and configured_peer is not None:
                self._peer = configured_peer

            # A UDP send can succeed even when a saved literal address is stale.
            # Maintenance challenges therefore act as the receiver liveness signal.
            # If they stop, discard the unusable session and look for the holder of
            # the same pairing key on the local broadcast domain.
            reply_age = now - (self._last_reply_at or self._started_at)
            discovery_due = address is None or reply_age >= DISCOVERY_AFTER_SECONDS
            if self.challenge is not None and reply_age >= DISCOVERY_AFTER_SECONDS:
                self.challenge = None

            hello_due = now >= self._hello_at
            broadcast_due = discovery_due and now >= self._discovery_at
            if self.challenge is None and ((hello_due and self._peer is not None) or broadcast_due):
                self.request = uuid.uuid4().hex
                hello = encode_message("hello", self.token,
                    session=self.session, request=self.request)
                if hello_due and self._peer is not None:
                    self.socket.sendto(hello, self._peer)
                    self._hello_at = now + (0.25 if self.challenge is None else 1.0)
                if broadcast_due:
                    targets = self.discovery_addresses() or (DISCOVERY_ADDRESS,)
                    for target in targets:
                        self.socket.sendto(hello, (target, self.destination[1]))
                    self._discovery_at = now + DISCOVERY_INTERVAL_SECONDS
            if self.challenge is None:
                self.last_error = ("Looking for the paired RetroPie console on this network…"
                    if discovery_due else
                    "Waiting for the RetroPie controller handshake; update both computers if this persists.")
                return False
            send_started_ns = time.monotonic_ns() if self.trace and self.trace.enabled else 0
            data = state.to_transport_dict()
            self.socket.sendto(encode_message("state", self.token, session=self.session,
                challenge=self.challenge, state=data), self._peer)
            # Renew an established handshake after publishing the time-critical
            # gameplay sample. The receiver can reject the old challenge after
            # a restart, while this maintenance hello obtains its replacement.
            if now >= self._hello_at:
                self.request = uuid.uuid4().hex
                self.socket.sendto(encode_message("hello", self.token,
                    session=self.session, request=self.request), self._peer)
                self._hello_at = now + 1.0
            send_finished_ns = time.monotonic_ns() if send_started_ns else 0
            if send_started_ns:
                self.trace.record(dict(event="send", session=session_key(self.session),
                    sequence=state.sequence, start_ns=send_started_ns, end_ns=send_finished_ns))
        except OSError as exc:
            self.last_error = str(exc)
            self._retry_at = now + 2.0
            return False
        self.last_error = None
        self._retry_at = 0.0
        return True

    def new_session(self) -> None:
        """Allow sequence numbers to restart after an atomic profile change."""
        self.session = uuid.uuid4().hex
        self.challenge, self.request, self._hello_at = None, None, 0.0
        self._peer, self._last_reply_at, self._discovery_at = None, 0.0, 0.0
        self._started_at = time.monotonic()

    @property
    def active_address(self) -> str | None:
        """Return the current authenticated receiver address, never the pairing key."""
        return self._peer[0] if self.challenge is not None and self._peer is not None else None

    def close(self) -> None:
        """Close the sender socket."""
        if self.trace:
            self.trace.close()
        self.address.close()
        self.socket.close()
