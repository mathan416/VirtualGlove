# Project: VirtualGlove
# File: src/powerglove_vision/game_registry.py
# Purpose: Validate and atomically manage the installed game registry over paired requests.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added bounded, authenticated game registry administration.
# Full history: docs/CHANGELOG.md and Git history.

"""Fixed-purpose game registry service and its paired UNO client."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .gesture import SUPPORTED_PROFILES
from .profile_control import _registry_entry, read_token, sign_message, verify_message

PROTOCOL = "powerglove-games/1"
MAX_DOCUMENT = 65536
MAX_REQUEST = 524288
PORT = 55358


def _unique(pairs):
    """Reject duplicate JSON keys before a parser can silently overwrite them."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def validate_document(text: str) -> dict:
    """Preserve the existing games-object format while rejecting ambiguous mappings."""
    if not isinstance(text, str) or len(text.encode()) > MAX_DOCUMENT:
        raise ValueError("Game registry must be text smaller than 64 KiB.")
    data = json.loads(text, object_pairs_hook=_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Invalid number")))
    if not isinstance(data, dict) or not isinstance(data.get("games"), dict):
        raise ValueError("The JSON must contain a games object.")
    seen = set()
    for name, profile in data["games"].items():
        if not name or not Path(name).name or any(ord(c) < 32 for c in name):
            raise ValueError("ROM filenames must be nonempty and contain no control characters.")
        key = Path(name).name.casefold()
        if key in seen:
            raise ValueError("Conflicting ROM filename: " + name)
        seen.add(key)
        try:
            _registry_entry(profile)
        except ValueError as exc:
            raise ValueError("Unknown or invalid profile settings for " + name) from exc
    return data


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    """Replace a file only after its complete contents have reached disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RegistryStore:
    """Serialize revision-checked changes to one administrator-configured registry."""
    def __init__(self, path):
        self.path = Path(path)
        self.backup = self.path.with_name(self.path.name + ".previous")
        self.lock = threading.Lock()

    def snapshot(self) -> dict:
        """Read a bounded document and its exact-content revision."""
        with self.path.open("rb") as stream:
            raw = stream.read(MAX_DOCUMENT + 1)
        text = raw.decode("utf-8")
        validate_document(text)
        return {"document": text, "revision": hashlib.sha256(raw).hexdigest(),
                "has_backup": self.backup.is_file(), "profiles": list(SUPPORTED_PROFILES)}

    def operate(self, operation: str, payload: dict) -> dict:
        """Read, save, or swap the previous valid save without accepting a path."""
        with self.lock:
            current = self.snapshot()
            if operation == "read":
                return current
            if operation not in ("save", "restore"):
                raise ValueError("Unsupported registry operation.")
            if payload.get("revision") != current["revision"]:
                raise ValueError("The registry changed elsewhere. Reload before saving.")
            if operation == "restore":
                with self.backup.open("rb") as stream:
                    document = stream.read(MAX_DOCUMENT + 1).decode("utf-8")
            else:
                document = payload.get("document")
            validate_document(document)
            mode = self.path.stat().st_mode & 0o777
            atomic_write(self.backup, current["document"], mode)
            atomic_write(self.path, document, mode)
            result = self.snapshot()
            if result["document"] != document:
                raise OSError("Saved registry could not be verified. Reload to check it.")
            return result


class RegistryService:
    """Issue bounded one-use challenges and authenticate both request and response."""
    def __init__(self, store, token_file, clock=time.monotonic):
        self.store, self.token_file, self.clock = store, token_file, clock
        self.challenges = {}

    def exchange(self, request: dict) -> dict:
        """Process one protocol envelope; never return a secret or filesystem path."""
        if not isinstance(request, dict) or request.get("protocol") != PROTOCOL:
            raise ValueError("Unsupported games service protocol.")
        token = read_token(None, self.token_file)
        now = self.clock()
        self.challenges = {key: expires for key, expires in self.challenges.items() if expires > now}
        if request.get("operation") == "challenge":
            if len(self.challenges) >= 64:
                raise ValueError("Games service is busy. Retry shortly.")
            challenge = secrets.token_hex(32)
            self.challenges[challenge] = now + 15
            return sign_message({"protocol": PROTOCOL, "challenge": challenge,
                                 "request_id": request.get("request_id"), "ok": True}, token)
        if not verify_message(request, token):
            raise ValueError("Pairing authentication failed.")
        challenge = request.get("challenge")
        if not isinstance(challenge, str) or self.challenges.pop(challenge, 0) <= now:
            raise ValueError("Expired or already used request. Retry the operation.")
        response = {"protocol": PROTOCOL, "request_id": request.get("request_id"), "challenge": challenge}
        try:
            response.update(ok=True, result=self.store.operate(request.get("operation"), request))
        except ValueError as exc:
            response.update(ok=False, error=str(exc))
        except (OSError, UnicodeError):
            response.update(ok=False, error="Cannot access the registry or its previous save. Check RetroPie setup.")
        return sign_message(response, token)


def make_registry_handler(service):
    """Expose only a bounded JSON exchange endpoint, with no browser CORS access."""
    class Handler(BaseHTTPRequestHandler):
        """Handle the one fixed-purpose endpoint with bounded request lifetimes."""
        def log_message(self, *args):
            pass

        def setup(self):
            """Set the socket deadline before reading headers or a request body."""
            super().setup()
            self.connection.settimeout(3)

        def do_POST(self):
            try:
                if self.path != "/registry" or self.headers.get("Origin"):
                    raise ValueError("Use the paired UNO Games page.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST:
                    raise ValueError("Invalid request size.")
                request = json.loads(self.rfile.read(length), object_pairs_hook=_unique)
                body = json.dumps(service.exchange(request)).encode()
                status = 200
            except (ValueError, TypeError, OSError):
                status, body = 400, b'{"error":"Games request rejected. Check pairing or retry."}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
    return Handler


def registry_request(settings: dict, operation: str, payload: dict | None = None, port: int = PORT) -> dict:
    """Proxy to the paired console and verify replies before exposing their contents."""
    from .resolver import resolve_ipv4
    token = settings.get("token", "")
    host = settings.get("receiver", "")
    if not host or len(token) < 16:
        raise ValueError("Configure and pair your RetroPie before opening Games.")
    url = "http://%s:%d/registry" % (resolve_ipv4(host), port)
    request_id = secrets.token_hex(16)

    def exchange(data):
        """Send a bounded request and authenticate the correlated response."""
        request = urllib.request.Request(url, data=json.dumps(data).encode(),
                                         headers={"Content-Type": "application/json"})
        # Ignore environment proxy settings for this fixed paired LAN endpoint.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=4) as response:
                body = response.read(MAX_REQUEST + 1)
            if len(body) > MAX_REQUEST:
                raise ValueError("Games service response is too large.")
            result = json.loads(body)
        except (OSError, ValueError) as exc:
            raise ValueError("Cannot reach the paired Games service. Check the console is online and update RetroPie setup.") from exc
        if (not isinstance(result, dict) or result.get("protocol") != PROTOCOL
                or result.get("request_id") != request_id or not verify_message(result, token)):
            raise ValueError("Games service authentication failed. Check pairing.")
        return result

    challenge = exchange({"protocol": PROTOCOL, "operation": "challenge", "request_id": request_id})["challenge"]
    data = dict(payload or {})
    data.update(protocol=PROTOCOL, operation=operation, request_id=request_id, challenge=challenge)
    response = exchange(sign_message(data, token))
    if response.get("challenge") != challenge:
        raise ValueError("Games service returned the wrong challenge.")
    if not response.get("ok"):
        raise ValueError(response.get("error", "Registry operation failed."))
    return response["result"]


def main() -> int:
    """Run the serial, timeout-bounded administration service from installed settings."""
    parser = argparse.ArgumentParser(description="Serve paired VirtualGlove game registry editing")
    parser.add_argument("--settings", type=Path, default=Path("/etc/powerglove/launcher.json"))
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text())
    store = RegistryStore(settings.get("registry", "/etc/powerglove/games.json"))
    service = RegistryService(store, Path(settings["token_file"]))
    HTTPServer((args.listen, args.port), make_registry_handler(service)).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
