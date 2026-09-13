# Project: VirtualGlove
# File: src/powerglove_vision/debug_server.py
# Purpose: Expose live worker status, camera frames, calibration, and controller state to the supervisor.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-07 - Added an expiring demand signal for optional Dashboard telemetry.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Add complete hand-setup backups and explicit calibration restoration.
#   2026-09-06 - Expose bounded player operations and enforce fresh centering.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Added runtime profile requests and camera-free status updates.
#   2026-09-03 - Added expiring browser practice leases for the Learn page.

"""Expose live worker status, camera frames, calibration, and controller state to the supervisor."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .gesture import SUPPORTED_PROFILES


PRACTICE_LEASE_SECONDS = 6.0


PAGE = b"""<!doctype html>
<html><head><meta name=viewport content='width=device-width,initial-scale=1'>
<title>VirtualGlove</title>
<style>body{font:16px system-ui;background:#10131a;color:#eef;margin:24px auto;padding:0 18px;max-width:1000px}
img{width:100%;background:#000;border-radius:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:14px 0}
.card{background:#1b2130;padding:13px;border-radius:9px}.label{color:#9ca9c7;font-size:12px;text-transform:uppercase}.value{font-size:19px;margin-top:3px}
button{font-size:18px;padding:12px 20px;border:0;border-radius:8px;background:#287cff;color:white}</style></head>
<body><h1>VirtualGlove</h1><div class=grid>
<div class=card><div class=label>Game</div><div class=value id=game>Waiting...</div></div>
<div class=card><div class=label>Gesture profile</div><div class=value id=profile>Waiting...</div></div>
<div class=card><div class=label>Hand tracking</div><div class=value id=tracking>Waiting...</div></div>
<div class=card><div class=label>Selected by</div><div class=value id=source>Waiting...</div></div>
</div><img src=/stream><p><button onclick="fetch('/calibrate',{method:'POST'})">Center hand</button></p>
<script>
const names={bad_street_brawler:'Bad Street Brawler',super_glove_ball:'Super Glove Ball',off:'Off'};
function profileName(p){if(names[p])return names[p];if(p&&p.startsWith('program_'))return 'Program '+p.slice(-1).toUpperCase();return p||'Off'}
setInterval(async()=>{try{const s=await(await fetch('/status')).json();
game.textContent=s.game||'No game';profile.textContent=profileName(s.active_profile);
tracking.textContent=s.calibrating?'Centering - hold still':(s.detected?'Ready and tracking':'Show your hand');
source.textContent=s.profile_source||'Startup';}catch(e){}},250)</script></body></html>"""


class SharedDebugState:
    """Share the latest frame, diagnostics, and one-shot operator requests across threads."""
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jpeg: bytes | None = None
        self.status: dict = {}
        self.stream_clients = 0
        self.calibrate_requested = False
        self.controller_request: bool | None = None
        self.game_controller_event = None
        self.profile_request: tuple[str | None, str, str] | None = None
        self.practice_sessions: dict[str, float] = {}
        self.invalidated_practice_sessions: dict[str, float] = {}
        self.tuning = None
        self.practice_active = False
        self.practice_request: bool | None = None
        self.statistics_until = 0.0

    def request_statistics(self, seconds: float = 1.0) -> None:
        """Keep detailed worker telemetry active only for a watching browser."""
        with self.lock:
            self.statistics_until = max(self.statistics_until, time.monotonic() + seconds)

    def statistics_requested(self) -> bool:
        """Return whether optional Dashboard statistics currently have a reader."""
        with self.lock:
            return time.monotonic() < self.statistics_until

    def update(self, jpeg: bytes, status: dict) -> None:
        """Atomically replace the current JPEG frame and worker status."""
        with self.lock:
            self.jpeg = jpeg
            self.status = status

    def update_frame(self, jpeg: bytes) -> None:
        """Replace only the preview image without restoring an older status snapshot."""
        with self.lock:
            self.jpeg = jpeg

    def update_status(self, status: dict, *, clear_frame: bool = False) -> None:
        """Publish diagnostics without requiring a camera frame."""
        with self.lock:
            if clear_frame:
                self.jpeg = None
            self.status = status

    def stream_opened(self) -> None:
        """Record one active camera-preview consumer."""
        with self.lock:
            self.stream_clients += 1

    def stream_closed(self) -> None:
        """Release one active camera-preview consumer."""
        with self.lock:
            self.stream_clients = max(0, self.stream_clients - 1)

    def has_stream_clients(self) -> bool:
        """Return whether drawing and encoding a preview frame is useful."""
        with self.lock:
            return self.stream_clients > 0

    def request_calibration(self) -> None:
        """Queue one hand-centering request."""
        with self.lock:
            self.calibrate_requested = True

    def take_calibration_request(self) -> bool:
        """Consume and clear the pending calibration request."""
        with self.lock:
            requested = self.calibrate_requested
            self.calibrate_requested = False
            return requested

    def game_controller_transition(self, session, enabled, eligible=True):
        """Publish only the newest game lifecycle intent to the local supervisor."""
        with self.lock:
            self.game_controller_event = {"session": session, "enabled": enabled,
                                          "eligible": eligible, "at": time.monotonic()}

    def request_controller(self, enabled: bool) -> None:
        """Queue the requested controller transmission state."""
        with self.lock:
            self.controller_request = enabled

    def take_controller_request(self) -> bool | None:
        """Consume and clear a pending controller state change."""
        with self.lock:
            requested = self.controller_request
            self.controller_request = None
            return requested

    def request_profile(self, profile: str | None, source: str = "Dashboard", game: str = "Manual selection") -> None:
        """Queue a runtime profile change without changing the saved startup profile."""
        with self.lock:
            self.profile_request = (profile, source, game)

    def take_profile_request(self) -> tuple[str | None, str, str] | None:
        """Consume and clear a pending runtime profile change."""
        with self.lock:
            requested = self.profile_request
            self.profile_request = None
            return requested

    def _refresh_practice_locked(self, now: float) -> None:
        """Expire abandoned browser leases and queue only real mode changes."""
        self.practice_sessions = {
            session: refreshed
            for session, refreshed in self.practice_sessions.items()
            if now - refreshed < PRACTICE_LEASE_SECONDS
        }
        self.invalidated_practice_sessions = {
            session: refreshed
            for session, refreshed in self.invalidated_practice_sessions.items()
            if now - refreshed < PRACTICE_LEASE_SECONDS
        }
        active = bool(self.practice_sessions) or bool(self.tuning and self.tuning.active())
        if active != self.practice_active:
            self.practice_active = active
            self.practice_request = active

    def request_practice(self, session: str, enabled: bool, *, reset: bool = False) -> bool:
        """Create, refresh, release, or reset an expiring Learn-page camera lease."""
        now = time.monotonic()
        with self.lock:
            self._refresh_practice_locked(now)
            if reset:
                self.invalidated_practice_sessions.update(
                    dict.fromkeys(self.practice_sessions, now)
                )
                self.practice_sessions.clear()
            elif enabled:
                if session in self.invalidated_practice_sessions:
                    self.invalidated_practice_sessions[session] = now
                else:
                    self.practice_sessions[session] = now
            else:
                self.practice_sessions.pop(session, None)
                self.invalidated_practice_sessions.pop(session, None)
            self._refresh_practice_locked(now)
            return self.practice_active

    def practice_status(self, session: str) -> dict:
        """Report this lease separately from practice held by other browser tabs."""
        with self.lock:
            self._refresh_practice_locked(time.monotonic())
            return {"practice_mode": self.practice_active,
                    "session_active": session in self.practice_sessions}

    def take_practice_request(self) -> bool | None:
        """Consume a practice transition, including one caused by lease expiry."""
        with self.lock:
            self._refresh_practice_locked(time.monotonic())
            requested = self.practice_request
            self.practice_request = None
            return requested


def make_handler(shared: SharedDebugState) -> type[BaseHTTPRequestHandler]:
    """Build a local diagnostics handler bound to the supplied shared state."""
    class Handler(BaseHTTPRequestHandler):
        """Serve the worker status, MJPEG stream, and one-shot control requests."""
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:
            if self.path == "/tuning" and shared.tuning is not None:
                body = json.dumps(shared.tuning.snapshot()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/":
                self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(PAGE)
            elif self.path.split("?", 1)[0] == "/status":
                query = self.path.split("?", 1)[1] if "?" in self.path else ""
                if "statistics=1" in query.split("&"):
                    shared.request_statistics()
                with shared.lock:
                    status = dict(shared.status)
                    status["preview_clients"] = shared.stream_clients
                    status["_game_controller_event"] = shared.game_controller_event
                if shared.tuning is not None:
                    status["tuning"] = shared.tuning.snapshot()
                    status["player"] = shared.tuning.player_snapshot()
                body = json.dumps(status, indent=2).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
            elif self.path == "/stream":
                shared.stream_opened()
                try:
                    self.send_response(200); self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame"); self.end_headers()
                    while True:
                        with shared.lock:
                            jpeg = shared.jpeg
                        if jpeg:
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                        threading.Event().wait(0.05)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    shared.stream_closed()
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            if self.path in ("/tuning", "/players") and shared.tuning is not None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 8192:
                        raise ValueError("Invalid tuning request size")
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError("Expected a tuning operation")
                    result = shared.tuning.player_command(data) if self.path == "/players" else shared.tuning.command(data)
                    if (shared.tuning.active() or shared.tuning.needs_center() or
                            (self.path == "/players" and data.get("action") in ("create", "select", "delete", "restore", "reuse_calibration"))):
                        shared.request_controller(False)
                    body, code = json.dumps(result).encode(), 200
                except (ValueError, OSError) as exc:
                    body, code = json.dumps({"error": str(exc)}).encode(), 400
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/calibrate":
                if shared.tuning is not None:
                    shared.tuning.invalidate()
                shared.request_calibration()
                self.send_response(204); self.end_headers()
            elif self.path == "/controller":
                try:
                    length = min(int(self.headers.get("Content-Length", "0")), 1024)
                    body = json.loads(self.rfile.read(length) or b"{}")
                    enabled = body.get("enabled")
                    if not isinstance(enabled, bool):
                        raise ValueError("enabled must be true or false")
                    if enabled and shared.tuning is not None and shared.tuning.needs_center():
                        raise ValueError("Set your center in Glove Academy before starting controls for this player.")
                    shared.request_controller(enabled)
                    response = json.dumps({"controller_enabled": enabled}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                except (ValueError, json.JSONDecodeError) as exc:
                    response = json.dumps({"error": str(exc)}).encode()
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
            elif self.path == "/profile":
                try:
                    length = min(int(self.headers.get("Content-Length", "0")), 1024)
                    body = json.loads(self.rfile.read(length) or b"{}")
                    profile = body.get("profile")
                    if profile == "off":
                        profile = None
                    if profile is not None and profile not in SUPPORTED_PROFILES:
                        raise ValueError("choose a supported gesture profile")
                    shared.request_profile(profile)
                    response = json.dumps({"active_profile": profile or "off"}).encode()
                    self.send_response(202)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                except (ValueError, json.JSONDecodeError) as exc:
                    response = json.dumps({"error": str(exc)}).encode()
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
            elif self.path == "/practice":
                try:
                    length = min(int(self.headers.get("Content-Length", "0")), 1024)
                    body = json.loads(self.rfile.read(length) or b"{}")
                    enabled = body.get("enabled")
                    reset = body.get("reset") is True
                    session = str(body.get("session", ""))
                    if not isinstance(enabled, bool):
                        raise ValueError("enabled must be true or false")
                    if not reset and (
                        not 8 <= len(session) <= 128
                        or not all(character.isalnum() or character in "-_" for character in session)
                    ):
                        raise ValueError("session must be an opaque browser identifier")
                    shared.request_practice(session, enabled, reset=reset)
                    response = json.dumps(shared.practice_status(session)).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                except (ValueError, json.JSONDecodeError) as exc:
                    response = json.dumps({"error": str(exc)}).encode()
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
            else:
                self.send_error(404)
    return Handler


def start_debug_server(shared: SharedDebugState, host: str, port: int) -> ThreadingHTTPServer:
    """Start the worker diagnostics server in a daemon thread."""
    server = ThreadingHTTPServer((host, port), make_handler(shared))
    threading.Thread(target=server.serve_forever, name="debug-web", daemon=True).start()
    return server
