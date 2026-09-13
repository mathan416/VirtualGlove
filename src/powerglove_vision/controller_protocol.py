# Project: VirtualGlove
# File: src/powerglove_vision/controller_protocol.py
# Purpose: Authenticate current controller input with receiver-issued session challenges.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Add signed controller sessions and bounded restart-safe admission.

"""Version-two message integrity and session admission; never retain input states."""

import hashlib
import hmac
import json
import secrets
import time

PROTOCOL = "virtualglove-vision/2"
MAX_PACKET_BYTES = 4096
DOMAIN = b"virtualglove-controller-v2\0"


def _canonical(value):
    """Use one deterministic encoding for HMAC; reject non-finite numbers."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def encode_message(kind, token, **fields):
    """Sign a bounded message without including its shared secret."""
    value = dict(fields, protocol=PROTOCOL, kind=kind)
    value["mac"] = hmac.new(token.encode(), DOMAIN + _canonical(value), hashlib.sha256).hexdigest()
    payload = _canonical(value)
    if len(payload) > MAX_PACKET_BYTES:
        raise ValueError("controller packet exceeds size limit")
    return payload


def _unique(pairs):
    """Reject ambiguous duplicate JSON keys, including in nested controller data."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate controller field")
        result[key] = value
    return result


def decode_message(payload, token):
    """Authenticate before using any routing, session, or input fields."""
    if len(payload) > MAX_PACKET_BYTES:
        raise ValueError("controller packet exceeds size limit")
    value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique)
    if not isinstance(value, dict) or value.get("protocol") != PROTOCOL:
        raise ValueError("unsupported controller protocol")
    mac = value.pop("mac", None)
    expected = hmac.new(token.encode(), DOMAIN + _canonical(value), hashlib.sha256).hexdigest()
    if not isinstance(mac, str) or len(mac) != 64 or not hmac.compare_digest(mac.encode(), expected.encode()):
        raise ValueError("controller authentication failed")
    kind = value.get("kind")
    keys = {"protocol", "kind", "session"}
    keys |= {"request"} if kind == "hello" else {"request", "challenge"} if kind == "challenge" else {"challenge", "state"} if kind == "state" else set()
    if kind not in ("hello", "challenge", "state") or set(value) != keys:
        raise ValueError("invalid controller message fields")
    for key in ("session", "request", "challenge"):
        if key in value and (not isinstance(value[key], str) or len(value[key]) != 32 or any(c not in "0123456789abcdef" for c in value[key])):
            raise ValueError("invalid controller " + key)
    return value


class ReceiverSessions:
    """Admit only increasing input for a live receiver-issued challenge.

    Pending handshakes are bounded and expire. Activating a session invalidates
    every older challenge, including pending challenges; reboot creates fresh
    randomness. No wall-clock synchronization or persistent secret state is needed.
    """
    def __init__(self, token, clock=time.monotonic):
        self.token, self.clock = token, clock
        self.active = None
        self.pending = {}

    def receive(self, payload, peer):
        """Return (accepted state, handshake reply), with at most one populated."""
        from .transport import decode_state
        value = decode_message(payload, self.token)
        now = self.clock()
        self.pending = {key:item for key,item in self.pending.items() if item[1] > now}
        key = (value["session"], peer)
        if value["kind"] == "hello":
            if self.active and self.active[0] == key:
                challenge = self.active[1]
            else:
                if key not in self.pending:
                    if len(self.pending) >= 8:
                        return None, None
                    self.pending[key] = (secrets.token_hex(16), now + 3.0)
                challenge = self.pending[key][0]
            return None, encode_message("challenge", self.token, session=value["session"],
                                        request=value["request"], challenge=challenge)
        if value["kind"] != "state":
            return None, None
        challenge = value["challenge"]
        current = bool(self.active and self.active[0] == key and self.active[1] == challenge)
        if not current and self.pending.get(key, (None,))[0] != challenge:
            return None, None
        raw = value["state"]
        if not isinstance(raw, dict) or "token" in raw or "protocol" in raw or "session" in raw:
            raise ValueError("invalid signed controller state")
        state = decode_state(_canonical(dict(raw, protocol="virtualglove-vision/1")))
        sequence = state["sequence"]
        if current and sequence <= self.active[2]:
            return None, None
        if not current:
            self.pending.clear()
        self.active = (key, challenge, sequence)
        return state, None
