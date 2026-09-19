# Project: VirtualGlove
# File: src/virtualglove/control_server.py
# Purpose: Serve the UNO Q dashboard, local play, setup, pairing, controller controls, and guarded shutdown request.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Serve a transparent logo tailored to the dark Controller pages.
#   2026-09-11 - Use the installer-recorded host identity for the HTTPS certificate.
#   2026-09-11 - Served the public Controller trust certificate only over HTTPS.
#   2026-09-11 - Kept camera-profile marker cleanup compatible with Python 3.7.
#   2026-09-11 - Add a privacy-safe downloadable system report.
#   2026-09-10 - Added Pixel Pal's safe camera-settings profiler.
#   2026-09-09 - Exposed direction-aware tracking as an independent experimental setting.
#   2026-09-08 - Listed discovered cameras in Setup while preserving Automatic selection.
#   2026-09-08 - Added portable automatic/manual exposure and gain settings.
#   2026-09-07 - Added portable camera backend and exposure settings.
#   2026-09-06 - Separate maintained browser pages from HTTP routing.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Address Setup review reliability and private configuration findings.
#   2026-09-06 - Add a persistent idle attract setting without restarting vision.
#   2026-09-06 - Add player controls, exact version details, and responsive layouts.
#   2026-09-06 - Replace the completed lesson panel with the Glove Master award.
#   2026-09-06 - Added the camera-controlled Rock Paper Scissors page.
#   2026-09-05 - Persisted the player's armed controller choice across app restarts.
#   2026-09-05 - Displayed fresh-frame and controller-transition latency.
#   2026-09-05 - Made every Academy lesson and completion control transition atomic.
#   2026-09-05 - Added Pixel Pal's trophy artwork to Academy completion.
#   2026-09-05 - Forwarded Dashboard and Academy calibration requests to the worker.
#   2026-09-05 - Replaced broken Academy camera images with a retrying status panel.
#   2026-09-05 - Displayed plain-language tracker backend names.
#   2026-09-05 - Made Academy lesson navigation atomic against recognition polls.
#   2026-09-05 - Added live capture and inference performance diagnostics.

"""Serve the UNO Q dashboard, local play, setup, pairing, and controller controls."""

from __future__ import annotations

import copy
import json
import hashlib
import math
import os
import re
import secrets
import socket
import ssl
import subprocess
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from .game_registry import registry_request, validate_document, MAX_REQUEST
from .controller_router import router_request
from .play_game import PLAY_CONTENT, PLAY_SCRIPT
from .setup_web import SETUP_CONTENT, SETUP_SCRIPT
from .games_web import GAMES_CONTENT, GAMES_SCRIPT
from .statistics_web import STATISTICS_CONTENT, STATISTICS_SCRIPT
from .web_common import _page, _profile_options, VISION_STARTUP_SCRIPT
from .gesture import SUPPORTED_PROFILES
from .dashboard_web import DASHBOARD
from .academy_web import LEARN
from . import __version__
from .versioning import current_identity
from .resolver import resolve_ipv4
from .camera import camera_device_identity, camera_device_options
from .camera_profile import (
    PROFILE_FIELDS as CAMERA_PROFILE_FIELDS,
    candidates as camera_profile_candidates,
    display_name as camera_profile_display_name,
    recommend as recommend_camera_profile,
    summarize as summarize_camera_profile,
)

from .help_content import (
    cabinet_reference_content, enclosure_asset, help_asset, help_document_content,
    help_index_content, guide_markdown, guide_pdf,
)
from .pairing import (
    CONSOLE_PLATFORMS,
    PAIRING_PORT,
    certificate_fingerprint,
    certificate_identity,
    ensure_controller_authority,
    pair_over_ssh,
    pair_with_code,
)


WORKER_URL = "http://127.0.0.1:8089"


def controller_tls_hostname(config_path: Path) -> str:
    """Return the stable UNO Q hostname instead of a transient container name."""
    identity = config_path.parent / "controller-hostname"
    try:
        value = identity.read_text().strip().lower()
    except OSError:
        value = ""
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value):
        value = socket.gethostname().split(".", 1)[0].lower()
    return value + ".local"
HTTPS_PORT = 8443
CAMERA_PROFILE_READY_SECONDS = 3.0
CAMERA_PROFILE_STAGES = (
    ("centre", 5.0, "Hold your open hand comfortably near the centre."),
    ("sweep", 9.0, "Sweep your hand smoothly between opposite corners."),
    ("edge", 6.0, "Touch an edge, then return to the centre."),
)
CAMERA_PROFILE_MEASURE_SECONDS = sum(stage[1] for stage in CAMERA_PROFILE_STAGES)
LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "virtualglove-logo-web.png"
PROFILES = {*SUPPORTED_PROFILES, "off"}


def _camera_fps(value: Any, *, strict: bool = False) -> str | int:
    """Normalize the portable camera-rate preference without accepting booleans."""
    if value == "auto":
        return "auto"
    if type(value) is int and value in (30, 60):
        return value
    if isinstance(value, str) and value in ("30", "60"):
        return int(value)
    if strict:
        raise ValueError("Choose Automatic, 30 fps, or 60 fps for the camera rate.")
    return "auto"


def _camera_buffers(value: Any, *, strict: bool = False) -> int:
    """Normalize the supported one- or two-buffer camera capture policy."""
    if type(value) is int and value in (1, 2):
        return value
    if isinstance(value, str) and value in ("1", "2"):
        return int(value)
    if strict:
        raise ValueError("Choose one or two camera buffers.")
    return 1


def _choice(value: Any, choices: tuple[str, ...], fallback: str, message: str,
            *, strict: bool = False) -> str:
    """Normalize one public fixed-choice setting."""
    if isinstance(value, str) and value in choices:
        return value
    if strict:
        raise ValueError(message)
    return fallback


def _manual_camera_value(value: Any, *, gain: bool = False,
                         strict: bool = False) -> int:
    """Normalize a saved manual control before the camera checks exact limits."""
    fallback = 96 if gain else 78
    try:
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError
        result = int(value)
    except (TypeError, ValueError):
        if strict:
            raise ValueError("Manual camera values must be whole numbers.") from None
        return fallback
    minimum = 0 if gain else 1
    if not minimum <= result <= 10_000:
        if strict:
            label = "gain" if gain else "exposure"
            raise ValueError(f"Manual {label} is outside the safe configuration range.")
        return fallback
    return result


class ForbiddenActionError(Exception):
    """Raised when a sensitive browser action lacks its CSRF safeguard."""


PLAY = _page(
    "Rock Paper Scissors",
    PLAY_CONTENT,
    VISION_STARTUP_SCRIPT + PLAY_SCRIPT,
)


SETUP = _page("Setup", SETUP_CONTENT.replace("{{PROFILE_OPTIONS}}", _profile_options()), SETUP_SCRIPT)

SETUP = SETUP.replace(b'</main>', (GAMES_CONTENT + STATISTICS_CONTENT).encode() + b'</main>', 1)
SETUP = SETUP.replace(b'</body>', b'<script>' + (GAMES_SCRIPT + '\n' + STATISTICS_SCRIPT).encode() + b'</script></body>', 1)


def help_index_page() -> bytes:
    """Build the Help library page from the bundled public-guide registry."""
    return _page("Help", help_index_content(), "")


def help_document_page(slug: str) -> bytes | None:
    """Build one styled Help reading page or return None for an unknown guide."""
    document = help_document_content(slug)
    if document is None:
        return None
    content, title = document
    return _page(title, content, "")


def cabinet_reference_page(host_header: str, state: "ControlState") -> bytes:
    """Build the live, non-secret cabinet reference for the address used by this browser."""
    content, title = cabinet_reference_content(host_header, state.public_config())
    return _page(title, content, "")


class ControlState:
    """Synchronize persistent settings, supervisor health, worker status, and pairing authorization."""
    def __init__(self, config_path: Path, pairing_display: Callable[[str, str], None] | None = None,
                 pairing_finished: Callable[[], None] | None = None) -> None:
        self.config_path = config_path
        self.lock = threading.Lock()
        self.config_lock = threading.RLock()
        self._controller_flush_lock = threading.Lock()
        self._controller_pending = None
        self._controller_revision = 0
        self._controller_retry_at = 0.0
        self._last_controller_choice = 0.0
        self._last_game_event = None
        self._game_session_marker = config_path.with_name("controller-last-game")
        self._last_auto_session = None
        if self._game_session_marker.is_file() and not self._game_session_marker.is_symlink():
            previous = self._game_session_marker.read_text().strip()
            if len(previous) == 64 and all(c in "0123456789abcdef" for c in previous):
                self._last_auto_session = previous
        self._auto_start_error = None
        self.revision = 0
        self.worker_status: dict[str, Any] = {}
        self._worker_status_at = None
        self._ready_marker = config_path.with_name("ready-guide-inhibit")
        self._ready_game_session = None
        self.camera_available = False
        self.worker_running = False
        self.last_error: str | None = None
        self._controller_marker = config_path.with_name("controller-armed")
        self._controller_enabled = (
            self._controller_marker.is_file() and not self._controller_marker.is_symlink()
            and not (self._ready_marker.exists() or self._ready_marker.is_symlink())
        )
        self._pairing_display = pairing_display
        self._pairing_finished = pairing_finished
        self._pairing_identity = ""
        self._controller_authority_pem = ""
        self._pairing_session: dict[str, Any] | None = None
        self._pairing_locked_until = 0.0
        self._shutdown_scheduled = False
        self.started_at = time.time()
        self.build_identity = current_identity()
        self.firmware_identity = None
        self.connection_probe = None
        self._statistics_until = 0.0
        self._camera_profile_marker = config_path.with_name("camera-profile-restore.json")
        self._camera_profile_cancel = threading.Event()
        self._camera_profile_thread: threading.Thread | None = None
        self._camera_profile = {
            "active": False, "phase": "idle", "candidate": 0, "total": 0,
            "instruction": "", "results": [], "recommendation": None,
            "error": None, "cue": None, "cue_remaining": 0,
            "candidate_remaining": 0, "candidate_progress": 0.0,
        }
        self._restore_interrupted_camera_profile()
        self._config = json.loads(self.config_path.read_text())
        self._camera_inventory = None
        self._camera_inventory_at = 0.0
        self._wifi_status = None
        self._wifi_status_at = 0.0

    def request_statistics(self, seconds: float = 1.0) -> None:
        """Lease detailed worker telemetry while a visible Dashboard requests it."""
        with self.lock:
            self._statistics_until = max(self._statistics_until, time.monotonic() + seconds)

    def statistics_requested(self) -> bool:
        """Return whether the supervisor should request detailed worker status."""
        with self.lock:
            return time.monotonic() < self._statistics_until

    def configure_pairing_identity(self, identity: str) -> None:
        """Publish the current certificate identity used for physical verification."""
        self._pairing_identity = identity

    def configure_controller_authority(self, pem: str) -> None:
        """Publish only the public Controller authority used by the trust download."""
        ssl.PEM_cert_to_DER_cert(pem)
        self._controller_authority_pem = pem

    def controller_authority(self) -> tuple[bytes, str]:
        """Return the public DER certificate and its complete fingerprint."""
        if not self._controller_authority_pem:
            raise ValueError("Controller trust certificate is unavailable.")
        return (ssl.PEM_cert_to_DER_cert(self._controller_authority_pem),
                certificate_fingerprint(self._controller_authority_pem))

    def begin_pairing(self, host: str, method: str, platform: str) -> dict[str, Any]:
        """Create a short-lived physical authorization PIN for one host and pairing method."""
        config = self.load_config()
        if method == "ssh" and platform == "launchbox":
            raise ValueError("LaunchBox pairing uses the one-time-code method")
        if (platform not in CONSOLE_PLATFORMS
                or platform != str(config.get("platform", ""))):
            raise ValueError("save the console platform before pairing")
        if (not host or len(host) > 253 or any(character.isspace() for character in host)
                or host != str(config.get("receiver", "")).strip()):
            raise ValueError("pairing requires the saved console hostname or IP address")
        if method not in {"ssh", "code"}:
            raise ValueError("choose a supported pairing method")
        now = time.monotonic()
        with self.lock:
            if now < self._pairing_locked_until:
                raise ValueError("pairing is temporarily locked; wait for the current window to expire")
            if self._pairing_session and now < self._pairing_session["expires"]:
                session = self._pairing_session
                if (session["host"] != host or session["method"] != method
                        or session["platform"] != platform):
                    raise ValueError("another pairing window is already active")
            else:
                pin = f"{secrets.randbelow(1_000_000):06d}"
                session = {
                    "host": host, "method": method, "platform": platform, "pin": pin,
                    "expires": now + 120, "attempts": 0,
                }
                self._pairing_session = session
        if self._pairing_display is not None:
            displayed = self._pairing_display(self._pairing_identity, str(session["pin"]))
            if displayed is False:
                with self.lock:
                    self._pairing_session = None
                raise ValueError("the UNO Q matrix is unavailable; physical pairing confirmation is required")
        else:
            with self.lock:
                self._pairing_session = None
            raise ValueError("the UNO Q matrix is unavailable; physical pairing confirmation is required")
        return {"certificate_id": self._pairing_identity, "expires_in": max(0, round(session["expires"] - now))}

    def authorize_pairing(self, host: str, method: str, platform: str, pin: str) -> None:
        """Consume a matching one-time physical PIN or reject the pairing attempt."""
        now = time.monotonic()
        with self.lock:
            session = self._pairing_session
            if session is None or now >= session["expires"]:
                self._pairing_session = None
                raise ValueError("pairing window expired; prepare pairing again")
            if (session["host"] != host or session["method"] != method
                    or session["platform"] != platform):
                raise ValueError("pairing request does not match the prepared device and method")
            session["attempts"] += 1
            if not secrets.compare_digest(str(session["pin"]), pin):
                if session["attempts"] >= 5:
                    self._pairing_session = None
                    self._pairing_locked_until = session["expires"]
                raise ValueError("UNO Q approval PIN was rejected")
            self._pairing_session = None

    def finish_pairing_display(self) -> None:
        """Release the consumed PIN display without interrupting a newer confirmation."""
        with self.lock:
            if self._pairing_session is None and self._pairing_finished is not None:
                self._pairing_finished()

    def controller_enabled(self) -> bool:
        """Return the operator-selected controller transmission state."""
        with self.lock:
            return self._controller_enabled

    def set_controller_enabled(self, enabled: bool) -> None:
        """Serialize persisted controller intent with device configuration writes."""
        with self.config_lock:
            self._set_controller_enabled(enabled)

    def _set_controller_enabled(self, enabled: bool, *, automatic: bool = False) -> None:
        """Queue a controller start or stop request for the vision worker."""
        if not automatic:
            self._last_controller_choice = time.monotonic()
            self._auto_start_error = None
        if enabled:
            if self._ready_marker.exists() or self._ready_marker.is_symlink():
                raise ValueError("Finish or leave Get ready to play before starting controller output.")
            with self.lock:
                if self.worker_status.get("player", {}).get("needs_center"):
                    raise ValueError("Select Center hand on Dashboard or in Glove Academy before starting controls for this player.")
            config = self.load_config()
            if not str(config.get("receiver", "")).strip() or not config.get("token"):
                raise ValueError("Configure your game console and pairing in Connection before starting controls.")
        self._persist_controller_enabled(enabled)
        with self.lock:
            self._controller_enabled = enabled
            self._controller_revision += 1
            self._controller_pending = (self._controller_revision, enabled)
            self._controller_retry_at = 0.0

    def flush_controller_request(self) -> bool:
        """Serialize delivery attempts while retaining any newer intent."""
        if not self._controller_flush_lock.acquire(blocking=False):
            return False
        try:
            return self._flush_controller_request()
        finally:
            self._controller_flush_lock.release()

    def _flush_controller_request(self) -> bool:
        """Retry only the newest explicit Start/Stop intent until the worker acknowledges it."""
        with self.lock:
            pending = self._controller_pending
            if pending is None:
                return True
            if time.monotonic() < self._controller_retry_at:
                return False
            self._controller_retry_at = time.monotonic() + 1.0
        _, enabled = pending
        request = urllib.request.Request(
            WORKER_URL + "/controller", method="POST",
            data=json.dumps({"enabled": enabled}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=1) as response:
                result = json.load(response)
            if not isinstance(result, dict) or result.get("controller_enabled") is not enabled:
                return False
        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                return False
            with self.config_lock:
                with self.lock:
                    current = self._controller_pending == pending
                if enabled and current:
                    self.set_controller_enabled(False)
            raise ValueError("The worker rejected the controller request. Check centering and try again.") from exc
        except (OSError, ValueError, RecursionError):
            return False
        with self.lock:
            if self._controller_pending == pending:
                self._controller_pending = None
                return True
        return False

    def _persist_controller_enabled(self, enabled: bool) -> None:
        """Atomically retain the explicit Start/Stop choice without storing it in settings."""
        path = self._controller_marker
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Controller state path is not a regular file.")
        if not enabled:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        temporary = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(str(temporary), flags, 0o600)
        try:
            with os.fdopen(descriptor, "w") as marker:
                marker.write("armed\n")
                marker.flush()
                os.fsync(marker.fileno())
            os.replace(str(temporary), str(path))
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def schedule_system_shutdown(self, delay_seconds: float = 2.0) -> None:
        """Ask the root-owned host helper to power off after the HTTP reply."""
        data_directory = self.config_path.parent
        if not (data_directory / ".shutdown-enabled").is_file():
            raise FileNotFoundError("System shutdown helper is not installed on this UNO Q.")
        with self.lock:
            if self._shutdown_scheduled:
                return
            self._shutdown_scheduled = True

        def trigger() -> None:
            """Publish a complete fixed request after allowing the HTTP response to finish."""
            path = data_directory / "shutdown-request"
            temporary = data_directory / f".shutdown-request.{secrets.token_hex(8)}.tmp"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(temporary, flags, 0o600)
                with os.fdopen(descriptor, "w") as request:
                    request.write("shutdown\n")
                    request.flush()
                    os.fsync(request.fileno())
                os.replace(temporary, path)
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

        timer = threading.Timer(delay_seconds, trigger)
        timer.daemon = True
        timer.start()

    def load_config(self) -> dict[str, Any]:
        """Return an independent copy of the cached private device configuration."""
        with self.config_lock:
            return copy.deepcopy(self._config)

    def _store_config(self, config: dict[str, Any], *, restart: bool) -> None:
        """Atomically persist and publish one validated configuration document."""
        from .game_registry import atomic_write
        with self.config_lock:
            atomic_write(self.config_path, json.dumps(config, indent=2) + "\n")
            self._config = copy.deepcopy(config)
            self._camera_inventory = None
            self._camera_inventory_at = 0.0
            if restart:
                with self.lock:
                    self.worker_status = {}
                    self.revision += 1

    def _camera_details(self, selection: str) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
        """Refresh physical camera inventory only for configuration consumers."""
        with self.config_lock:
            now = time.monotonic()
            if (self._camera_inventory is None
                    or now - self._camera_inventory_at >= 5.0):
                self._camera_inventory = {
                    "selection": selection,
                    "identity": camera_device_identity(selection),
                    "options": camera_device_options(),
                }
                self._camera_inventory_at = now
            elif self._camera_inventory["selection"] != selection:
                self._camera_inventory = {
                    "selection": selection,
                    "identity": camera_device_identity(selection),
                    "options": self._camera_inventory["options"],
                }
            return (copy.deepcopy(self._camera_inventory["identity"]),
                    copy.deepcopy(self._camera_inventory["options"]))

    def _cached_wifi_status(self) -> dict[str, Any]:
        """Read the independently updated host report at most once per second."""
        from .wifi_status import read_wifi_status
        with self.config_lock:
            now = time.monotonic()
            if self._wifi_status is None or now - self._wifi_status_at >= 1.0:
                self._wifi_status = read_wifi_status()
                self._wifi_status_at = now
            return copy.deepcopy(self._wifi_status)

    def public_config(self) -> dict[str, Any]:
        """Return browser-safe settings with all secrets removed."""
        config = self.load_config()
        identity, camera_options = self._camera_details(
            str(config.get("camera", "auto"))
        )
        camera_profiles = config.get("camera_profiles", {})
        saved_camera_profile = (
            camera_profiles.get(identity["key"])
            if identity and isinstance(camera_profiles, dict) else None
        )
        return {
            "receiver": config.get("receiver", ""),
            "platform": config.get("platform", ""),
            "port": int(config.get("port", 55355)),
            "profile": config.get("profile", "off"),
            "glove_color": config.get("glove_color", "none"),
            "camera": str(config.get("camera", "auto")),
            "camera_options": camera_options,
            "camera_fps": _camera_fps(config.get("camera_fps", "auto")),
            "camera_buffers": _camera_buffers(config.get("camera_buffers", 1)),
            "camera_backend": _choice(
                config.get("camera_backend", "opencv"),
                ("opencv", "direct-v4l2"), "opencv", "Choose a camera reader.",
            ),
            "camera_exposure": _choice(
                "kiyo-low-latency" if config.get("kiyo_hdr_off") is True else
                    config.get("camera_exposure", "auto"),
                ("auto", "low-latency", "kiyo-low-latency", "manual"), "auto",
                "Choose an exposure mode.",
            ),
            "camera_manual_exposure": _manual_camera_value(
                config.get("camera_manual_exposure", 78)
            ),
            "camera_manual_gain": _manual_camera_value(
                config.get("camera_manual_gain", 96), gain=True
            ),
            "matrix_attract": config.get("matrix_attract", "on"),
            "paired": bool(config.get("receiver") and config.get("token")),
            "connection_configured": bool(str(config.get("receiver", "")).strip() and config.get("token")),
            "pairing_configured": bool(str(config.get("receiver", "")).strip()
                                       and config.get("token")
                                       and config.get("platform") in CONSOLE_PLATFORMS),
            "controller_enabled": self.controller_enabled(),
            "camera_identity": identity,
            "saved_camera_profile": saved_camera_profile,
        }

    def _restore_interrupted_camera_profile(self) -> None:
        """Restore camera fields after a restart during a temporary comparison."""
        marker = self._camera_profile_marker
        if not marker.is_file() or marker.is_symlink():
            return
        try:
            document = json.loads(marker.read_text())
            original = document.get("original")
            if not isinstance(original, dict):
                raise ValueError
            from .game_registry import atomic_write
            atomic_write(self.config_path, json.dumps(original, indent=2) + "\n")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Never guess at private settings from a malformed restore marker.
            return
        try:
            marker.unlink()
        except FileNotFoundError:
            pass

    def camera_profile_snapshot(self) -> dict[str, Any]:
        """Return image-free progress for Pixel Pal's camera wizard."""
        with self.lock:
            return json.loads(json.dumps(self._camera_profile))

    def _set_camera_profile_state(self, **changes: Any) -> None:
        """Publish an atomic image-free camera wizard progress update."""
        with self.lock:
            self._camera_profile.update(changes)

    def _write_camera_profile_fields(self, fields: dict[str, Any]) -> None:
        """Apply temporary fields and restart vision without touching player data."""
        with self.config_lock:
            current = self.load_config()
            current.update(fields)
            self._store_config(current, restart=True)

    def _restore_camera_profile_config(self, original: dict[str, Any]) -> None:
        """Restore the exact pre-test document after blocking concurrent saves."""
        with self.config_lock:
            self._store_config(original, restart=True)

    def begin_camera_profile(self) -> dict[str, Any]:
        """Start one guarded, reversible comparison for the attached camera."""
        with self.config_lock:
            with self.lock:
                if self._camera_profile.get("active"):
                    raise ValueError("Camera profiling is already running.")
            config = self.load_config()
            identity = camera_device_identity(str(config.get("camera", "auto")))
            if identity is None:
                raise ValueError("Connect a camera before starting the test.")
            original = dict(config)
            marker = {"schema": 1, "camera_key": identity["key"], "original": original}
            from .game_registry import atomic_write
            atomic_write(
                self._camera_profile_marker,
                json.dumps(marker, indent=2) + "\n",
                mode=0o600,
            )
            self._set_controller_enabled(False)
            lanes = camera_profile_candidates(identity, config)
            self._camera_profile_cancel.clear()
            self._camera_profile = {
                "active": True, "phase": "starting", "candidate": 0,
                "total": len(lanes), "instruction": "Show Pixel Pal one open hand.",
                "results": [], "recommendation": None, "error": None,
                "camera": identity, "cue": None, "cue_remaining": 0,
                "candidate_remaining": 0, "candidate_progress": 0.0,
            }
            thread = threading.Thread(
                target=self._run_camera_profile,
                args=(lanes, original),
                name="camera-profile", daemon=True,
            )
            self._camera_profile_thread = thread
            thread.start()
        return self.camera_profile_snapshot()

    def stop_camera_profile(self) -> dict[str, Any]:
        """Stop a comparison or reset an already-restored failed comparison."""
        with self.lock:
            if self._camera_profile.get("active"):
                self._camera_profile_cancel.set()
                self._camera_profile["phase"] = "restoring"
                self._camera_profile["instruction"] = "Restoring your camera settings…"
                return json.loads(json.dumps(self._camera_profile))

        # A failed lane restores the saved document in the profiler's finally
        # block before publishing its error.  Restart the ordinary worker once
        # more after the operator reconnects the camera, then clear the failed
        # wizard state so a new test can start deterministically.
        with self.config_lock:
            marker = self._camera_profile_marker
            if marker.exists():
                if marker.is_symlink() or not marker.is_file():
                    raise ValueError("The camera restore record is not a regular file.")
                try:
                    document = json.loads(marker.read_text())
                    original = document.get("original")
                    if not isinstance(original, dict):
                        raise ValueError
                except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        "The original camera settings could not be verified; restart the Controller before testing again."
                    ) from exc
                self._restore_camera_profile_config(original)
                try:
                    marker.unlink()
                except FileNotFoundError:
                    pass
            else:
                with self.lock:
                    self.worker_status = {}
                    self.revision += 1
            with self.lock:
                self._camera_profile.update({
                    "active": False,
                    "phase": "cancelled",
                    "candidate": 0,
                    "instruction": "Your original camera settings are restored. You can start a new test.",
                    "results": [],
                    "recommendation": None,
                    "error": None,
                    "cue": None,
                    "cue_remaining": 0,
                    "candidate_remaining": 0,
                    "candidate_progress": 0.0,
                })
        return self.camera_profile_snapshot()

    def _candidate_ready(self, lane: dict[str, Any]) -> bool:
        """Confirm the requested lane started, including a measurable safe fallback."""
        with self.lock:
            status = dict(self.worker_status)
        return bool(
            status.get("camera_available")
            and status.get("capture_backend_requested") == lane["camera_backend"]
            and status.get("capture_isolation") == lane["capture_isolation"]
            and status.get("camera_fps_requested") == lane["camera_fps"]
            and status.get("camera_buffers_requested") == lane["camera_buffers"]
            and status.get("camera_exposure_mode") == lane["camera_exposure"]
        )

    def _run_camera_profile(self, lanes: list[dict[str, Any]],
                            original: dict[str, Any]) -> None:
        """Compare candidates from newest status only and restore configuration."""
        results = []
        error = None
        try:
            for index, lane in enumerate(lanes, 1):
                if self._camera_profile_cancel.is_set():
                    break
                self._set_camera_profile_state(
                    phase="starting", candidate=index,
                    instruction=f"Preparing test {index} of {len(lanes)}…",
                    cue=None, cue_remaining=0,
                    candidate_remaining=0, candidate_progress=0.0,
                )
                temporary = dict(lane)
                temporary["profile"] = "bad_street_brawler"
                self._write_camera_profile_fields(temporary)
                deadline = time.monotonic() + 15
                ready = False
                while time.monotonic() < deadline and not self._camera_profile_cancel.is_set():
                    if self._candidate_ready(lane):
                        ready = True
                        break
                    time.sleep(.1)
                if self._camera_profile_cancel.is_set():
                    break
                if not ready:
                    result = summarize_camera_profile(lane, [], .001)
                    result["name"] = camera_profile_display_name(lane)
                    result["error"] = "This camera setting did not start."
                    results.append(result)
                    self._set_camera_profile_state(results=list(results))
                    with self.lock:
                        camera_present = bool(self.worker_status.get("camera_available"))
                    if not camera_present:
                        raise ValueError("The camera disconnected during the test. Reconnect it and try again.")
                    continue
                ready_started = time.monotonic()
                while (time.monotonic() - ready_started < CAMERA_PROFILE_READY_SECONDS
                       and not self._camera_profile_cancel.is_set()):
                    remaining = max(
                        1,
                        math.ceil(
                            CAMERA_PROFILE_READY_SECONDS
                            - (time.monotonic() - ready_started)
                        ),
                    )
                    self._set_camera_profile_state(
                        phase="countdown", cue="ready",
                        instruction="Get ready with one open hand in the camera view.",
                        cue_remaining=remaining,
                        candidate_remaining=math.ceil(CAMERA_PROFILE_MEASURE_SECONDS),
                        candidate_progress=0.0,
                    )
                    time.sleep(.1)
                if self._camera_profile_cancel.is_set():
                    break
                samples = []
                started = time.monotonic()
                while (time.monotonic() - started < CAMERA_PROFILE_MEASURE_SECONDS
                       and not self._camera_profile_cancel.is_set()):
                    elapsed = time.monotonic() - started
                    stage_started = 0.0
                    cue, duration, instruction = CAMERA_PROFILE_STAGES[-1]
                    for candidate_cue, candidate_duration, candidate_instruction in CAMERA_PROFILE_STAGES:
                        if elapsed < stage_started + candidate_duration:
                            cue, duration, instruction = (
                                candidate_cue, candidate_duration,
                                candidate_instruction,
                            )
                            break
                        stage_started += candidate_duration
                    cue_remaining = max(1, math.ceil(duration - (elapsed - stage_started)))
                    with self.lock:
                        sample = dict(self.worker_status)
                    if not sample.get("detected"):
                        instruction = "Pixel Pal cannot see your whole hand. Move it into the camera frame."
                    self._set_camera_profile_state(
                        phase="measuring", instruction=instruction, cue=cue,
                        cue_remaining=cue_remaining,
                        candidate_remaining=max(
                            1, math.ceil(CAMERA_PROFILE_MEASURE_SECONDS - elapsed)
                        ),
                        candidate_progress=min(
                            1.0, elapsed / CAMERA_PROFILE_MEASURE_SECONDS
                        ),
                    )
                    self.request_statistics(1)
                    samples.append(sample)
                    time.sleep(.1)
                result = summarize_camera_profile(
                    lane, samples, max(.001, time.monotonic() - started)
                )
                result["name"] = camera_profile_display_name(lane)
                results.append(result)
                self._set_camera_profile_state(
                    results=list(results), cue=None, cue_remaining=0,
                    candidate_remaining=0, candidate_progress=1.0,
                )
        except Exception as exc:
            error = str(exc)
        finally:
            self._set_camera_profile_state(
                phase="restoring", instruction="Restoring your camera settings…",
                cue=None, cue_remaining=0, candidate_remaining=0,
                candidate_progress=1.0,
            )
            try:
                self._restore_camera_profile_config(original)
                try:
                    self._camera_profile_marker.unlink()
                except FileNotFoundError:
                    pass
            except Exception as exc:
                error = error or f"Camera settings could not be restored: {exc}"
            recommendation = recommend_camera_profile(results)
            if recommendation is not None:
                recommendation = dict(recommendation)
                recommendation["name"] = camera_profile_display_name(
                    recommendation["settings"]
                )
            cancelled = self._camera_profile_cancel.is_set()
            self._set_camera_profile_state(
                active=False,
                phase="cancelled" if cancelled else ("error" if error else "complete"),
                instruction=(
                    "Your original camera settings are restored."
                    if cancelled else
                    "Pixel Pal found the best measured settings for this camera."
                    if recommendation else
                    "No safe recommendation was available. Your settings are unchanged."
                ),
                results=results, recommendation=recommendation, error=error,
                cue=None, cue_remaining=0, candidate_remaining=0,
                candidate_progress=1.0,
            )

    def apply_camera_profile(self) -> dict[str, Any]:
        """Save only the explicit recommendation for the same attached camera."""
        with self.config_lock:
            snapshot = self.camera_profile_snapshot()
            if snapshot.get("active") or snapshot.get("phase") != "complete":
                raise ValueError("Finish the camera test before saving its recommendation.")
            recommendation = snapshot.get("recommendation")
            camera = snapshot.get("camera")
            if not isinstance(recommendation, dict) or not isinstance(camera, dict):
                raise ValueError("No camera recommendation is available.")
            current = self.load_config()
            identity = camera_device_identity(str(current.get("camera", "auto")))
            if identity is None or identity.get("key") != camera.get("key"):
                raise ValueError("The connected camera changed; run the test again.")
            settings = recommendation.get("settings")
            if not isinstance(settings, dict):
                raise ValueError("The camera recommendation is incomplete.")
            for field in CAMERA_PROFILE_FIELDS:
                current[field] = settings[field]
            profiles = current.get("camera_profiles")
            profiles = dict(profiles) if isinstance(profiles, dict) else {}
            profiles[identity["key"]] = {
                "label": identity["label"],
                **{field: settings[field] for field in CAMERA_PROFILE_FIELDS},
            }
            current["camera_profiles"] = profiles
            self._store_config(current, restart=True)
        return self.public_config()

    def save_attract(self, incoming):
        """Serialize preference updates with connection saves."""
        with self.config_lock:
            return self._save_attract(incoming)

    def _save_attract(self, incoming):
        """Persist an idle display preference without restarting or arming the worker."""
        with self.lock:
            if self._camera_profile.get("active"):
                raise ValueError("Wait for the camera test to finish before saving settings.")
        mode = incoming.get("mode")
        if mode not in ("on", "dim", "off"):
            raise ValueError("Choose On, Dim, or Off for attract mode.")
        current = self.load_config()
        current["matrix_attract"] = mode
        self._store_config(current, restart=False)
        return {"mode": mode}

    def save_config(self, incoming: dict[str, Any]) -> dict[str, Any]:
        """Serialize full configuration writes with display preference changes."""
        with self.config_lock:
            return self._save_config(incoming)

    def _save_config(self, incoming: dict[str, Any]) -> dict[str, Any]:
        """Validate and persist browser-submitted non-secret device settings."""
        with self.lock:
            if self._camera_profile.get("active"):
                raise ValueError("Wait for the camera test to finish before saving settings.")
        receiver = str(incoming.get("receiver", "")).strip()
        if len(receiver) > 253 or any(ch.isspace() for ch in receiver):
            raise ValueError("Enter a valid console hostname or IP address.")
        platform = str(incoming.get("platform", "")).strip()
        if platform not in ("",) + CONSOLE_PLATFORMS:
            raise ValueError("Choose a supported console platform.")
        if receiver and not platform:
            raise ValueError("Choose the console platform before saving its address.")
        try:
            raw_port = incoming.get("port", 55355)
            if isinstance(raw_port, bool) or isinstance(raw_port, float):
                raise ValueError("Controller port must be a whole number.")
            port = int(raw_port)
        except (TypeError, ValueError) as exc:
            raise ValueError("Controller port must be a number.") from exc
        if not 1 <= port <= 65535:
            raise ValueError("Controller port must be between 1 and 65535.")
        profile = str(incoming.get("profile", ""))
        if profile not in PROFILES:
            raise ValueError("Choose a supported gesture profile.")
        glove_color = str(incoming.get("glove_color", "none"))
        if glove_color not in {"none", "white", "black"}:
            raise ValueError("Choose bare hand, white glove, or black glove.")
        camera = str(incoming.get("camera", "auto")).strip().lower()
        if camera != "auto" and (not camera.isdigit() or int(camera) > 99):
            raise ValueError("Camera must be 'auto' or a camera number.")
        current = self.load_config()
        camera_fps = _camera_fps(
            incoming.get("camera_fps", current.get("camera_fps", "auto")),
            strict=True,
        )
        camera_buffers = _camera_buffers(
            incoming.get("camera_buffers", current.get("camera_buffers", 1)),
            strict=True,
        )
        camera_backend = _choice(
            incoming.get("camera_backend", current.get("camera_backend", "opencv")),
            ("opencv", "direct-v4l2"), "opencv",
            "Choose OpenCV or Direct V4L2 for camera reading.", strict=True,
        )
        camera_exposure = _choice(
            incoming.get("camera_exposure", current.get("camera_exposure", "auto")),
            ("auto", "low-latency", "kiyo-low-latency", "manual"), "auto",
            "Choose Automatic, Low latency, Kiyo Pro tested, or Manual exposure.", strict=True,
        )
        manual_exposure = _manual_camera_value(
            incoming.get("camera_manual_exposure",
                         current.get("camera_manual_exposure", 78)), strict=True,
        )
        manual_gain = _manual_camera_value(
            incoming.get("camera_manual_gain", current.get("camera_manual_gain", 96)),
            gain=True, strict=True,
        )
        if camera_exposure == "manual" and camera_backend != "direct-v4l2":
            raise ValueError("Manual exposure requires the Direct V4L2 camera reader.")
        token = current.get("token")
        if not token:
            token = secrets.token_urlsafe(24)
        saved = dict(current)
        saved.update({
            "receiver": receiver, "platform": platform, "port": port, "token": token,
            "profile": profile, "glove_color": glove_color,
            "camera": camera, "camera_fps": camera_fps,
            "camera_buffers": camera_buffers,
            "camera_backend": camera_backend, "camera_exposure": camera_exposure,
            "camera_manual_exposure": manual_exposure,
            "camera_manual_gain": manual_gain,
            "matrix_attract": current.get("matrix_attract", "on"),
        })
        saved.pop("kiyo_hdr_off", None)
        self._store_config(saved, restart=True)
        if not receiver:
            self.set_controller_enabled(False)
        return self.public_config()

    def snapshot(self) -> dict[str, Any]:
        """Return a thread-safe dashboard snapshot of configuration and runtime health."""
        with self.lock:
            status = dict(self.worker_status)
            status["worker_controller_enabled"] = status.get("controller_enabled")
            status["worker_status_age_seconds"] = None if self._worker_status_at is None else round(time.monotonic() - self._worker_status_at, 3)
            if self._auto_start_error and not self._controller_enabled:
                status["receiver_error"] = self._auto_start_error
            status.update({
                "camera_available": self.camera_available,
                "worker_running": self.worker_running,
                "last_error": self.last_error,
                "controller_enabled": self._controller_enabled,
                "controller_request_pending": self._controller_pending is not None,
                "uptime_seconds": round(time.time() - self.started_at),
                "app_started_at": self.started_at,
                "version": __version__,
                "build": dict(self.build_identity),
                "firmware": {"running": self.firmware_identity,
                    "expected": self.build_identity.get("firmware_expected"),
                    "state": "unavailable" if not self.firmware_identity else
                        "matched" if self.firmware_identity == self.build_identity.get("firmware_expected") else "different"},
            })
        config = self.load_config()
        status["wifi_status"] = self._cached_wifi_status()
        status["connection_configured"] = bool(
            str(config.get("receiver", "")).strip() and config.get("token")
        )
        status.setdefault("configured_profile", config.get("profile", "off"))
        return status

    def connection_status(self):
        """Return the same cached checks used by the four idle matrix pixels."""
        if self.connection_probe is not None:
            return self.connection_probe(self.load_config(), refresh=True)
        from .wifi_status import read_wifi_status, read_network_status
        return {"app": True, "console_configured": bool(self.load_config().get("receiver")),
                "console_service": None, "console_authenticated": None,
                "wifi": read_wifi_status(), "networking": read_network_status(), "checked_seconds_ago": None}

    def ready_request(self, incoming):
        """Own a durable output inhibit; stale tabs cannot release another visit's guard."""
        from .game_registry import atomic_write
        from .ready_guide import essential_complete, game_gate
        session, action = incoming.get("session"), incoming.get("action")
        if not isinstance(session, str) or not 16 <= len(session) <= 80 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in session):
            raise ValueError("Invalid ready-guide session.")
        with self.config_lock:
            if self._ready_marker.is_symlink():
                raise ValueError("Ready-guide state path is not a regular file.")
            if action == "begin":
                atomic_write(self._ready_marker, session)
                self._ready_game_session = None
                self._set_controller_enabled(False)
                self.flush_controller_request()
                return {"guarded": True}
            owner = self._ready_marker.read_text() if self._ready_marker.is_file() else None
            if action == "status":
                return {"guarded": owner == session, "game_stage": self._ready_game_session == session}
            if action in ("release", "cancel"):
                if owner != session or incoming.get("confirmed") is not True:
                    raise ValueError("This guide visit is no longer active. Reload the guide.")
                request = urllib.request.Request(WORKER_URL + "/practice", method="POST",
                    data=json.dumps({"session": session, "enabled": False}).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=1) as response:
                    practice = json.load(response)
                status = self.snapshot()
                if practice.get("practice_mode") is not False or status.get("practice_mode") is not False:
                    return {"released": False, "message": "Waiting for practice to stop. Close other Academy or tuning sessions."}
                if action == "release":
                    player = self._ready_player(incoming)
                    if not essential_complete(player):
                        raise ValueError("Complete the essential checks before launching a game.")
                self._set_controller_enabled(False)
                self._ready_marker.unlink()
                self._ready_game_session = session if action == "release" else None
                return {"released": True}
            if action == "arm":
                if owner is not None or self._ready_game_session != session:
                    raise ValueError("End guide practice explicitly before enabling game controls.")
                player = self._ready_player(incoming)
                if not essential_complete(player):
                    raise ValueError("Complete the essential checks first.")
                status = self.snapshot()
                if (status.get("player", {}).get("active") != incoming.get("player")
                        or status.get("player", {}).get("generation") != incoming.get("generation")):
                    raise ValueError("Waiting for tracker status for the selected player.")
                reason = game_gate(status, require_link=False)
                if reason:
                    raise ValueError(reason)
                connection = self.connection_status()
                age = connection.get("checked_seconds_ago")
                if (type(age) not in (int, float) or not 0 <= age < 30
                        or connection.get("console_service") is not True
                        or connection.get("console_authenticated") is not True):
                    raise ValueError("Recheck console connectivity and authenticated pairing in Setup.")
                self._set_controller_enabled(True)
                return {"armed": True, "pending": not self.flush_controller_request()}
            raise ValueError("Unknown ready-guide action.")

    def _ready_player(self, incoming):
        """Validate fresh player identity immediately before release or guide arming."""
        request = urllib.request.Request(WORKER_URL + "/players", method="POST",
            data=b'{"action":"read"}', headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=1) as response:
            player = json.load(response)
        if (player.get("active") != incoming.get("player") or type(incoming.get("generation")) is not int
                or player.get("generation") != incoming["generation"] or player.get("needs_center")):
            raise ValueError("Player or calibration changed. Return to the player step.")
        return player

    def support_report(self) -> dict[str, Any]:
        """Return useful installation health without secrets or personal hand data."""
        status = self.snapshot()
        connection = self.connection_status()
        config = self.public_config()
        build = status.get("build", {}) if isinstance(status.get("build"), dict) else {}
        firmware = status.get("firmware", {}) if isinstance(status.get("firmware"), dict) else {}
        active_link = bool(status.get("receiver_available"))
        context_active = bool(status.get("controller_context_active"))
        return {
            "format": "virtualglove-system-report",
            "version": 1,
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "privacy": {
                "contains_frames": False,
                "contains_pairing_key": False,
                "contains_player_or_calibration_data": False,
                "contains_rom_name": False,
                "contains_network_addresses": False,
            },
            "software": {
                "version": status.get("version"),
                "release": build.get("release"),
                "commit": build.get("commit"),
                "modified_source": bool(build.get("dirty")),
                "uptime_seconds": status.get("uptime_seconds"),
                "firmware_state": firmware.get("state"),
            },
            "camera": {
                "selection": "automatic" if config.get("camera") == "auto" else "named",
                "available": bool(status.get("camera_available")),
                "vision_state": status.get("vision_state"),
                "worker_running": bool(status.get("worker_running")),
                "reader": status.get("capture_backend"),
                "reader_fallback": bool(status.get("capture_backend_fallback")),
                "requested_fps": status.get("camera_fps_requested"),
                "delivered_fps": status.get("camera_fps"),
                "requested_buffers": status.get("camera_buffers_requested"),
                "exposure_mode": status.get("camera_exposure_mode"),
                "exposure_applied": bool(status.get("camera_exposure_applied")),
            },
            "controller": {
                "armed": bool(status.get("controller_enabled")),
                "request_pending": bool(status.get("controller_request_pending")),
                "game_context_active": context_active,
                "active_profile": status.get("active_profile", status.get("profile", "off")),
                "emulator": status.get("emulator") or "unknown",
                "input_mode": status.get("input_mode") or "inactive",
                "authenticated_input_link": active_link,
                "input_link_check": (
                    "passed" if active_link else
                    "waiting" if status.get("controller_enabled") and not context_active else
                    "not-run"
                ),
            },
            "connection": {
                "saved_destination_configured": bool(connection.get("console_configured")),
                "console_service_reachable": connection.get("console_service"),
                "console_registry_authenticated": connection.get("console_authenticated"),
                "physical_network": connection.get("networking"),
                "console_check_age_seconds": connection.get("checked_seconds_ago"),
            },
        }

    def update_firmware(self, identity):
        """Publish only the identity read from the running sketch."""
        with self.lock:
            self.firmware_identity = identity

    def update_supervisor(self, *, camera: bool, running: bool, error: str | None = None) -> None:
        """Publish camera, worker, and supervisor-error state for the dashboard."""
        with self.lock:
            self.camera_available = camera
            self.worker_running = running
            self.last_error = error
            if not running:
                self.worker_status = {}

    def update_worker(self, status: dict[str, Any]) -> None:
        """Merge the latest worker diagnostics into shared dashboard state."""
        status.pop("token", None)
        game_event = status.pop("_game_controller_event", None)
        with self.lock:
            if (self._worker_status_at is None or
                    any(status.get(key) != self.worker_status.get(key)
                        for key in ("timestamp", "sequence", "vision_state", "controller_enabled"))):
                self._worker_status_at = time.monotonic()
            self.worker_status = status
            self.worker_running = True
            self.camera_available = bool(status.get("camera_available", False))
            self.last_error = None
        self._apply_game_controller_event(game_event, status)

    def _apply_game_controller_event(self, event, status):
        """Consume a private worker launch once, with explicit operator choices winning."""
        if not isinstance(event, dict):
            return
        with self.config_lock:
            identity = (event.get("session"), event.get("enabled"), event.get("at"))
            if identity == self._last_game_event:
                return
            self._last_game_event = identity
            enabled = event.get("enabled")
            if type(enabled) is not bool:
                return
            if enabled:
                raw_session = event.get("session")
                if not isinstance(raw_session, str) or not raw_session:
                    return
                session = hashlib.sha256(raw_session.encode()).hexdigest()
                if session == self._last_auto_session:
                    return
                if self._game_session_marker.is_symlink():
                    return
                from .game_registry import atomic_write
                atomic_write(self._game_session_marker, session + "\n")
                self._last_auto_session = session
            if event.get("at", 0) <= self._last_controller_choice:
                return
            if enabled and (not event.get("eligible") or status.get("practice_mode")
                            or status.get("tuning", {}).get("active")):
                return
            try:
                self._set_controller_enabled(enabled, automatic=True)
                self._auto_start_error = None
            except ValueError as error:
                self._auto_start_error = str(error)


def _send(
    handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str,
    headers: dict[str, str] | None = None,
) -> None:
    """Send one HTTP response with explicit content type and length."""
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    for name, value in (headers or {}).items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(state: ControlState) -> type[BaseHTTPRequestHandler]:
    """Build the request handler bound to one shared control state."""
    class Handler(BaseHTTPRequestHandler):
        """Handle public diagnostics and protected local administration routes."""
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def json_body(self, require_json: bool = False) -> dict[str, Any]:
            """Read a size-bounded JSON request body and require an object value."""
            if require_json and self.headers.get_content_type() != "application/json":
                raise ValueError("Content-Type must be application/json")
            length = int(self.headers.get("Content-Length", "0"))
            limit = MAX_REQUEST if self.path in ("/api/games", "/api/controller-router") else 8192
            if not 0 <= length <= limit:
                raise ValueError("Request is too large.")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Request must be an object.")
            return data

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/debug"):
                self.send_response(302); self.send_header("Location", "/dashboard"); self.end_headers()
            elif path == "/dashboard":
                _send(self, 200, DASHBOARD, "text/html; charset=utf-8")
            elif path == "/play":
                _send(self, 200, PLAY, "text/html; charset=utf-8")
            elif path == "/games":
                self.send_response(302)
                self.send_header("Location", "/setup#games-section")
                self.end_headers()
            elif path == "/ready":
                from .ready_web import READY
                _send(self, 200, READY, "text/html; charset=utf-8")
            elif path == "/learn":
                _send(self, 200, LEARN, "text/html; charset=utf-8")
            elif path == "/setup":
                _send(self, 200, SETUP, "text/html; charset=utf-8")
            elif path == "/help":
                _send(self, 200, help_index_page(), "text/html; charset=utf-8")
            elif path == "/help/cabinet":
                _send(self, 200, cabinet_reference_page(self.headers.get("Host", ""), state), "text/html; charset=utf-8")
            elif path.startswith("/help/") and path.endswith(".md"):
                source = guide_markdown(path[len("/help/"):-len(".md")])
                if source is None:
                    self.send_error(404)
                else:
                    _send(self, 200, source, "text/markdown; charset=utf-8")
            elif path.startswith("/help-pdf/") and path.endswith(".pdf"):
                document = guide_pdf(path[len("/help-pdf/"):-len(".pdf")])
                if document is None:
                    self.send_error(404)
                else:
                    body, _filename = document
                    _send(self, 200, body, "application/pdf")
            elif path.startswith("/help/"):
                page = help_document_page(path[len("/help/"):])
                if page is None:
                    self.send_error(404)
                else:
                    _send(self, 200, page, "text/html; charset=utf-8")
            elif path.startswith("/help-assets/"):
                asset = help_asset(path[len("/help-assets/"):])
                if asset is None:
                    self.send_error(404)
                else:
                    body, content_type = asset
                    _send(self, 200, body, content_type)
            elif path.startswith("/help-enclosure/"):
                asset = enclosure_asset(path[len("/help-enclosure/"):])
                if asset is None:
                    self.send_error(404)
                else:
                    body, content_type, filename = asset
                    headers = None if content_type == "image/png" else {
                        "Content-Disposition": f'attachment; filename="{filename}"',
                    }
                    _send(self, 200, body, content_type, headers)
            elif path == "/favicon.ico":
                try:
                    _send(self, 200, (LOGO_PATH.parent / "favicon.ico").read_bytes(), "image/vnd.microsoft.icon")
                except OSError:
                    self.send_error(404)
            elif path in ("/assets/virtualglove-icon.png", "/assets/favicon-32.png", "/assets/apple-touch-icon.png"):
                try:
                    _send(self, 200, (LOGO_PATH.parent / path.rsplit("/", 1)[1]).read_bytes(), "image/png")
                except OSError:
                    self.send_error(404)
            elif path == "/assets/virtualglove-logo.png":
                try:
                    _send(self, 200, LOGO_PATH.read_bytes(), "image/png")
                except OSError:
                    self.send_error(404)
            elif path == "/status":
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                if query.get("statistics") == ["1"]:
                    state.request_statistics()
                _send(self, 200, json.dumps(state.snapshot()).encode(), "application/json")
            elif path == "/api/connection-status":
                _send(self, 200, json.dumps(state.connection_status()).encode(), "application/json")
            elif path == "/api/support-report":
                _send(self, 200, json.dumps(state.support_report(), indent=2).encode(), "application/json")
            elif path == "/api/config":
                _send(self, 200, json.dumps(state.public_config()).encode(), "application/json")
            elif path == "/api/camera-profile":
                _send(self, 200, json.dumps(state.camera_profile_snapshot()).encode(), "application/json")
            elif path == "/controller-ca.cer":
                if not isinstance(self.connection, ssl.SSLSocket):
                    _send(self, 426, b"Open secure Setup before downloading the trust certificate.\n",
                          "text/plain; charset=utf-8")
                else:
                    certificate, fingerprint = state.controller_authority()
                    _send(self, 200, certificate, "application/pkix-cert", {
                        "Content-Disposition": 'attachment; filename="virtualglove-controller-ca.cer"',
                        "X-VirtualGlove-CA-SHA256": fingerprint,
                    })
            elif path == "/stream":
                self.proxy_stream()
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            try:
                origin = self.headers.get("Origin")
                if (self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site" or
                        (origin and origin not in ("http://"+self.headers.get("Host", ""), "https://"+self.headers.get("Host", "")))):
                    raise ForbiddenActionError("Open this control from the Controller website.")
                if path in ("/api/games", "/api/controller-router", "/api/tuning", "/api/players", "/api/attract", "/api/camera-profile"):
                    expected = path.rsplit("/", 1)[-1]
                    origin = self.headers.get("Origin")
                    if (self.headers.get("X-VirtualGlove-Action") != expected
                            or self.headers.get("Sec-Fetch-Site", "") == "cross-site"
                            or (origin and origin not in ("http://" + self.headers.get("Host", ""), "https://" + self.headers.get("Host", "")))):
                        raise ForbiddenActionError("Open this control from the UNO website.")
                    incoming = self.json_body(require_json=True)
                    if path == "/api/attract":
                        result = state.save_attract(incoming)
                    elif path == "/api/camera-profile":
                        action = incoming.get("action")
                        if action == "begin":
                            result = state.begin_camera_profile()
                        elif action == "stop":
                            result = state.stop_camera_profile()
                        elif action == "apply":
                            result = state.apply_camera_profile()
                        else:
                            raise ValueError("Unknown camera test action.")
                    elif path == "/api/games":
                        action = incoming.get("action")
                        if action in ("validate", "format"):
                            data = validate_document(incoming.get("document"))
                            result = {"valid": True, "document": json.dumps(data, indent=2) + "\n"}
                        elif action in ("read", "save", "restore"):
                            result = registry_request(state.load_config(), action,
                                {"document": incoming.get("document"), "revision": incoming.get("revision")})
                        else:
                            raise ValueError("Unknown Games action.")
                    elif path == "/api/controller-router":
                        action = incoming.get("action")
                        if action not in ("inventory", "read", "save", "check", "rollback"):
                            raise ValueError("Unknown Controller Router action.")
                        result = router_request(state.load_config(), action, {
                            "config": incoming.get("config"),
                            "revision": incoming.get("revision"),
                            "watch_ms": incoming.get("watch_ms", 0),
                        })
                    else:
                        if path == "/api/players" and incoming.get("action") in ("create", "select", "delete", "restore", "reuse_calibration"):
                            # Persist stop before changing players, including across a supervisor restart.
                            state.set_controller_enabled(False)
                        request = urllib.request.Request(WORKER_URL + ("/players" if path == "/api/players" else "/tuning"), method="POST",
                            data=json.dumps(incoming).encode(), headers={"Content-Type": "application/json"})
                        try:
                            with urllib.request.urlopen(request, timeout=2) as response:
                                result = json.load(response)
                        except urllib.error.HTTPError as exc:
                            raise ValueError(json.loads(exc.read()).get("error", "Tuning request failed.")) from None
                        if incoming.get("action") == "begin":
                            state.set_controller_enabled(False)
                    _send(self, 200, json.dumps(result).encode(), "application/json")
                elif path == "/api/config":
                    result = state.save_config(self.json_body(require_json=True))
                    _send(self, 200, json.dumps(result).encode(), "application/json")
                elif path == "/api/test-connection":
                    receiver = str(self.json_body().get("receiver", "")).strip()
                    if not receiver:
                        raise ValueError("Enter your RetroPie hostname or IP address first.")
                    address = resolve_ipv4(receiver)
                    _send(self, 200, json.dumps({"ok": True, "receiver": receiver, "address": address}).encode(), "application/json")
                elif path == "/api/controller":
                    enabled = self.json_body().get("enabled")
                    if not isinstance(enabled, bool):
                        raise ValueError("enabled must be true or false")
                    state.set_controller_enabled(enabled)
                    delivered = state.flush_controller_request()
                    _send(self, 200 if delivered else 202, json.dumps({
                        "controller_enabled": enabled, "pending": not delivered}).encode(), "application/json")
                elif path == "/api/profile":
                    profile = str(self.json_body(require_json=True).get("profile", ""))
                    if profile not in PROFILES:
                        raise ValueError("Choose a supported gesture profile.")
                    request = urllib.request.Request(
                        WORKER_URL + "/profile",
                        method="POST",
                        data=json.dumps({"profile": profile}).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=1) as response:
                        result = response.read()
                    _send(self, 202, result, "application/json")
                elif path == "/api/rapid-fire":
                    if self.headers.get("X-VirtualGlove-Action") != "rapid-fire":
                        raise ForbiddenActionError(
                            "Rapid-fire request is missing its browser-action safeguard."
                        )
                    incoming = self.json_body(require_json=True)
                    request_id = incoming.get("request_id")
                    game = incoming.get("game")
                    rapid_a, rapid_b = incoming.get("rapid_a"), incoming.get("rapid_b")
                    if (not isinstance(request_id, str) or not 8 <= len(request_id) <= 64
                            or not all(c.isalnum() or c in "-_" for c in request_id)):
                        raise ValueError("request_id must be an opaque browser identifier.")
                    if not isinstance(game, str) or not game or len(game) > 512:
                        raise ValueError("A current registered game is required.")
                    if rapid_a is not None and type(rapid_a) is not bool:
                        raise ValueError("rapid_a must be Boolean or null.")
                    if rapid_b is not None and type(rapid_b) is not bool:
                        raise ValueError("rapid_b must be Boolean or null.")
                    request = urllib.request.Request(
                        WORKER_URL + "/rapid-fire", method="POST",
                        data=json.dumps({"request_id": request_id, "game": game, "rapid_a": rapid_a,
                                         "rapid_b": rapid_b}).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=1) as response:
                        result = response.read()
                    _send(self, 202, result, "application/json")
                elif path == "/api/ready":
                    if self.headers.get("X-VirtualGlove-Action") != "ready":
                        raise ForbiddenActionError("Ready guide request is missing its browser-action safeguard.")
                    result = state.ready_request(self.json_body(require_json=True))
                    _send(self, 200, json.dumps(result).encode(), "application/json")
                elif path == "/api/practice":
                    incoming = self.json_body(require_json=True)
                    enabled = incoming.get("enabled")
                    if not isinstance(enabled, bool):
                        raise ValueError("enabled must be true or false")
                    payload = {
                        "session": str(incoming.get("session", "")),
                        "enabled": enabled,
                        "reset": incoming.get("reset") is True,
                    }
                    request = urllib.request.Request(
                        WORKER_URL + "/practice",
                        method="POST",
                        data=json.dumps(payload).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=1) as response:
                        result = response.read()
                    _send(self, 200, result, "application/json")
                elif path == "/calibrate":
                    request = urllib.request.Request(
                        WORKER_URL + "/calibrate", method="POST"
                    )
                    with urllib.request.urlopen(request, timeout=1):
                        pass
                    _send(self, 204, b"", "application/json")
                elif path == "/api/system/shutdown":
                    incoming = self.json_body(require_json=True)
                    if self.headers.get("X-VirtualGlove-Action") != "shutdown":
                        raise ForbiddenActionError("Shutdown request is missing its browser-action safeguard.")
                    if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
                        raise ForbiddenActionError("Cross-site shutdown requests are not allowed.")
                    if incoming.get("confirm") != "SHUTDOWN":
                        raise ValueError("Confirm the system shutdown before continuing.")
                    state.schedule_system_shutdown()
                    state.set_controller_enabled(False)
                    request = urllib.request.Request(
                        WORKER_URL + "/controller", method="POST",
                        data=b'{"enabled":false}', headers={"Content-Type": "application/json"},
                    )
                    try:
                        with urllib.request.urlopen(request, timeout=1):
                            pass
                    except (OSError, urllib.error.URLError):
                        pass
                    _send(self, 202, b'{"shutting_down":true}', "application/json")
                elif path == "/api/pair/code":
                    self.require_secure_pairing()
                    incoming = self.json_body(require_json=True)
                    host = str(incoming.get("host", "")).strip()
                    platform = str(incoming.get("platform", "")).strip()
                    state.authorize_pairing(
                        host, "code", platform, str(incoming.get("device_code", "")))
                    try:
                        pair_with_code(
                            host, PAIRING_PORT,
                            str(incoming.get("code", "")), str(state.load_config()["token"]),
                            platform,
                        )
                    finally:
                        state.finish_pairing_display()
                    _send(self, 200, b'{"paired":true}', "application/json")
                elif path == "/api/pair/ssh":
                    self.require_secure_pairing()
                    incoming = self.json_body(require_json=True)
                    host = str(incoming.get("host", "")).strip()
                    platform = str(incoming.get("platform", "")).strip()
                    state.authorize_pairing(
                        host, "ssh", platform, str(incoming.get("device_code", "")))
                    password = str(incoming.get("password", ""))
                    try:
                        pair_over_ssh(
                            host,
                            str(incoming.get("username", "")).strip(), password,
                            str(state.load_config()["token"]),
                            state.config_path.parent / "ssh" / "known_hosts",
                            platform,
                        )
                    finally:
                        password = ""
                        incoming["password"] = ""
                        state.finish_pairing_display()
                    _send(self, 200, b'{"paired":true}', "application/json")
                elif path == "/api/pair/begin":
                    self.require_secure_pairing()
                    incoming = self.json_body(require_json=True)
                    result = state.begin_pairing(
                        str(incoming.get("host", "")).strip(),
                        str(incoming.get("method", "")),
                        str(incoming.get("platform", "")).strip(),
                    )
                    _send(self, 200, json.dumps(result).encode(), "application/json")
                else:
                    self.send_error(404)
            except (ValueError, json.JSONDecodeError, RecursionError) as exc:
                _send(self, 400, json.dumps({"error": str(exc)}).encode(), "application/json")
            except ForbiddenActionError as exc:
                _send(self, 403, json.dumps({"error": str(exc)}).encode(), "application/json")
            except PermissionError as exc:
                _send(self, 426, json.dumps({"error": str(exc)}).encode(), "application/json")
            except (OSError, urllib.error.URLError, subprocess.SubprocessError) as exc:
                _send(self, 503, json.dumps({"error": f"Not reachable: {exc}"}).encode(), "application/json")

        def require_secure_pairing(self) -> None:
            """Reject credential-bearing requests that did not arrive through HTTPS."""
            if not isinstance(self.connection, ssl.SSLSocket):
                raise PermissionError(f"Pairing credentials require HTTPS on port {HTTPS_PORT}.")

        def proxy_stream(self) -> None:
            """Relay the worker MJPEG stream while tolerating temporary worker loss."""
            try:
                with urllib.request.urlopen(WORKER_URL + "/stream", timeout=2) as response:
                    self.send_response(200)
                    self.send_header("Content-Type", response.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame"))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    while True:
                        chunk = response.read(16384)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (OSError, urllib.error.URLError, BrokenPipeError, ConnectionResetError):
                if not self.wfile.closed:
                    body = b"<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480'><rect width='100%' height='100%' fill='%23050608'/><text x='50%' y='50%' fill='%23a6aec5' font-family='monospace' font-size='24' text-anchor='middle'>CAMERA OFFLINE</text></svg>"
                    try:
                        _send(self, 503, body, "image/svg+xml")
                    except OSError:
                        pass
    return Handler


class ControlServerGroup:
    """Own the HTTP and HTTPS control servers as one shutdown unit."""
    def __init__(self, servers: list[ThreadingHTTPServer]) -> None:
        self.servers = servers

    def shutdown(self) -> None:
        """Stop and close every managed control server."""
        for server in self.servers:
            server.shutdown()
            server.server_close()


def start_control_server(
    config_path: Path,
    host: str = "0.0.0.0",
    port: int = 8088,
    https_port: int = HTTPS_PORT,
    pairing_display: Callable[[str, str], None] | None = None,
    pairing_finished: Callable[[], None] | None = None,
) -> tuple[ControlServerGroup, ControlState]:
    """Start public diagnostics and protected setup servers and return their shared state."""
    state = ControlState(config_path, pairing_display, pairing_finished)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    threading.Thread(target=server.serve_forever, name="control-web", daemon=True).start()
    servers = [server]
    try:
        tls_directory = config_path.parent / "tls"
        hostname = controller_tls_hostname(config_path)
        certificate, private_key, pem, authority_pem = ensure_controller_authority(
            tls_directory, hostname, [])
        state.configure_pairing_identity(certificate_identity(pem))
        state.configure_controller_authority(authority_pem)
        secure_server = ThreadingHTTPServer((host, https_port), make_handler(state))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, private_key)
        secure_server.socket = context.wrap_socket(secure_server.socket, server_side=True)
        threading.Thread(target=secure_server.serve_forever, name="control-https", daemon=True).start()
        servers.append(secure_server)
    except (OSError, ValueError, subprocess.CalledProcessError, ssl.SSLError) as exc:
        print(f"VirtualGlove: secure setup unavailable: {exc}", flush=True)
    return ControlServerGroup(servers), state
