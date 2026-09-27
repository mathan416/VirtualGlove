# Project: VirtualGlove
# File: src/virtualglove/controller_router.py
# Purpose: VirtualGlove integration and compatibility facade for the shared Router.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-27 - Kept product protocol separate from the shared Router core.
# Full history: docs/CHANGELOG.md and Git history.
"""Keep VirtualGlove's signed console protocol outside the reusable Router core."""

from __future__ import annotations

import json
import secrets
import time
import urllib.request
from pathlib import Path
from typing import Any

from .profile_control import read_token, sign_message, verify_message
from router_shared import controller_router as _core

# Existing command-line and Python callers use this module path. Export the
# shared engine's API while keeping only VirtualGlove transport here.
for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

PROTOCOL = "virtualglove-inputs/1"

class RouterService:
    """Authenticate bounded Controller Router operations with the paired key."""
    def __init__(self, store: RouterStore, token_file: Path, clock=time.monotonic) -> None:
        self.store, self.token_file, self.clock = store, Path(token_file), clock
        self.challenges: dict[str, float] = {}

    def exchange(self, request: dict[str, Any]) -> dict[str, Any]:
        """Authenticate one challenge or signed Router operation."""
        if not isinstance(request, dict) or request.get("protocol") != PROTOCOL:
            raise ValueError("Unsupported Controller Router protocol.")
        token, now = read_token(None, self.token_file), self.clock()
        self.challenges = {key: expiry for key, expiry in self.challenges.items() if expiry > now}
        if request.get("operation") == "challenge":
            if len(self.challenges) >= 64:
                raise ValueError("Controller Router is busy. Retry shortly.")
            challenge = secrets.token_hex(32)
            self.challenges[challenge] = now + 15
            return sign_message({"protocol": PROTOCOL, "challenge": challenge,
                                 "request_id": request.get("request_id"), "ok": True}, token)
        if not verify_message(request, token):
            raise ValueError("Pairing authentication failed.")
        challenge = request.get("challenge")
        if not isinstance(challenge, str) or self.challenges.pop(challenge, 0) <= now:
            raise ValueError("Expired or already used request. Retry the operation.")
        response = {"protocol": PROTOCOL, "request_id": request.get("request_id"),
                    "challenge": challenge}
        try:
            response.update(ok=True, result=self.store.operate(request.get("operation", ""), request))
        except ValueError as exc:
            response.update(ok=False, error=str(exc))
        except (OSError, UnicodeError, json.JSONDecodeError):
            response.update(ok=False, error="Cannot inspect or save Controller Router settings.")
        return sign_message(response, token)


def router_request(settings: dict[str, Any], operation: str,
                   payload: dict[str, Any] | None = None, port: int = 55358) -> dict[str, Any]:
    """Call the paired console's fixed-purpose Controller Router endpoint."""
    from .resolver import resolve_ipv4
    token, host = settings.get("token", ""), settings.get("receiver", "")
    if not host or len(token) < 16:
        raise ValueError("Configure and pair your console before opening Controller Router.")
    url = "http://%s:%d/inputs" % (resolve_ipv4(host), port)
    request_id = secrets.token_hex(16)

    def exchange(data: dict[str, Any]) -> dict[str, Any]:
        """Send and authenticate one correlated protocol message."""
        request = urllib.request.Request(url, data=json.dumps(data).encode(),
                                         headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            wait_seconds = 4
            if operation == "check":
                wait_seconds = min(
                    15, max(4, int((payload or {}).get("watch_ms", 0)) / 1000 + 2))
            with opener.open(request, timeout=wait_seconds) as response:
                body = response.read(MAX_REQUEST + 1)
            if len(body) > MAX_REQUEST:
                raise ValueError("Controller Router response is too large.")
            result = json.loads(body)
        except (OSError, ValueError) as exc:
            raise ValueError("Cannot reach Controller Router. Check the paired console and its VirtualGlove installation.") from exc
        if (not isinstance(result, dict) or result.get("protocol") != PROTOCOL
                or result.get("request_id") != request_id or not verify_message(result, token)):
            raise ValueError("Controller Router authentication failed. Check pairing.")
        return result

    challenge = exchange({"protocol": PROTOCOL, "operation": "challenge",
                          "request_id": request_id})["challenge"]
    data = dict(payload or {})
    data.update(protocol=PROTOCOL, operation=operation, request_id=request_id, challenge=challenge)
    response = exchange(sign_message(data, token))
    if response.get("challenge") != challenge:
        raise ValueError("Controller Router returned the wrong challenge.")
    if not response.get("ok"):
        raise ValueError(response.get("error", "Controller Router operation failed."))
    return response["result"]



if __name__ == "__main__":
    raise SystemExit(_core.main())
