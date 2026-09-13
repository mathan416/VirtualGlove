# Project: VirtualGlove
# File: src/powerglove_vision/matrix.py
# Purpose: Drive UNO Q LED matrix status, pairing, and active-profile displays through Router Bridge.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Add idle-only brightness and bounded background connection indicators.
#   2026-09-06 - Read and cache the running matrix firmware source identity.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Added a gestures-idle state distinct from system shutdown.
#   2026-09-03 - Added a dedicated Learn-mode matrix state.

"""Drive UNO Q LED matrix status, pairing, and active-profile displays through Router Bridge."""

from __future__ import annotations

import time
import re
import threading
import socket
from enum import IntEnum
from typing import Any, Callable


class MatrixStatus(IntEnum):
    """Enumerate the display states understood by the UNO Q sketch."""
    OFF = 0
    LOADING = 1
    READY = 2
    TRACKING = 3
    ERROR = 4
    PAIRING = 5
    GESTURES_IDLE = 6
    LEARNING = 7
    TUNING = 8


def status_from_worker(status: dict) -> MatrixStatus:
    """Map a worker status snapshot to the physical matrix display state."""
    if status.get("tuning", {}).get("active"):
        return MatrixStatus.TUNING
    vision_state = status.get("vision_state")
    if status.get("practice_mode") and vision_state != "error":
        return MatrixStatus.LEARNING
    if status.get("practice_mode"):
        return MatrixStatus.ERROR
    active_profile = status.get("active_profile")
    if active_profile == "program_14" and vision_state == "idle":
        return MatrixStatus.READY
    if active_profile == "off" or vision_state == "idle":
        return MatrixStatus.GESTURES_IDLE
    if vision_state == "starting":
        return MatrixStatus.LOADING
    if vision_state == "error":
        return MatrixStatus.ERROR
    return (
        MatrixStatus.TRACKING
        if status.get("detected") and status.get("calibrated")
        else MatrixStatus.READY
    )


class UnoQMatrix:
    """Optional bridge to the UNO Q's STM32-driven 8x13 LED matrix."""

    def __init__(
        self,
        enabled: bool = True,
        call: Callable[..., Any] | None = None,
    ) -> None:
        self.enabled = enabled
        self.last_status: MatrixStatus | None = None
        self.last_error: str | None = None
        self.last_profile: str | None = None
        self.pairing_until = 0.0
        self._status_retry_at = 0.0
        self._profile_retry_at = 0.0
        self._call = call
        self._firmware_checked_at = -60.0
        self._firmware_id = None
        self._attract_sent = None
        self._attract_retry = 0.0
        self._probe_lock = threading.Lock()
        self._probe_key = None
        self._probe_result = 0
        self._probe_at = -60.0
        self._probe_running = False
        if enabled and self._call is None:
            try:
                from arduino.app_utils import Bridge

                self._call = Bridge.call
            except ImportError:
                # Development computers and ordinary Debian installations do
                # not provide App Lab's Bridge. Matrix support is optional.
                self.enabled = False

    @property
    def available(self) -> bool:
        """Return whether Router Bridge matrix calls can currently be attempted."""
        return self.enabled and self._call is not None

    def firmware_identity(self):
        """Read the running sketch identity occasionally, outside the vision worker."""
        if time.monotonic() - self._firmware_checked_at < 30:
            return self._firmware_id
        self._firmware_checked_at = time.monotonic()
        self._firmware_id = None
        if self.available:
            try:
                result = self._call("get_virtualglove_firmware")
                if isinstance(result, str) and re.fullmatch(r"[0-9a-f]{64}", result):
                    self._firmware_id = result
            except Exception:
                # Older sketches do not expose the identity endpoint.
                pass
        return self._firmware_id

    def set_attract(self, settings, idle=False):
        """Update idle-only settings; check console health outside all frame loops."""
        mode = settings.get("matrix_attract", "on")
        if mode not in ("on", "dim", "off"):
            mode = "on"
        now = time.monotonic()
        health = self.connection_status(settings, refresh=idle and mode == "off")
        connections = (1 if health["console_service"] else 0) | (2 if health["console_authenticated"] else 0)
        if health["networking"] == "connected":
            connections |= 4
        value = (("on", "dim", "off").index(mode), connections)
        if value == self._attract_sent or now < self._attract_retry or not self.available:
            return
        try:
            self._call("set_virtualglove_attract", *value)
            self._attract_sent = value
        except Exception:
            # An older sketch keeps its existing animation until upgraded.
            self._attract_retry = now + 30

    def connection_status(self, settings, refresh=False):
        """Share cached matrix checks with Setup; network work stays in one background thread."""
        now = time.monotonic()
        key = (settings.get("receiver", ""), settings.get("token", ""))
        with self._probe_lock:
            if key != self._probe_key:
                self._probe_key, self._probe_result, self._probe_at = key, 0, -60.0
            if refresh and not self._probe_running and now - self._probe_at >= 10:
                self._probe_running = True
                threading.Thread(target=self._probe_console, args=(key,), daemon=True,
                                 name="matrix-connections").start()
            age = now - self._probe_at
            known = bool(key[0]) and 0 <= age < 30
            result = {
                "app": True,
                "console_configured": bool(key[0]),
                "console_service": bool(self._probe_result & 1) if known else None,
                "console_authenticated": bool(self._probe_result & 2) if known else None,
                "checked_seconds_ago": round(age, 1) if known else None,
            }
        from .wifi_status import read_wifi_status, read_network_status
        result["wifi"] = read_wifi_status()
        result["networking"] = read_network_status()
        return result

    def _probe_console(self, key):
        """Distinguish TCP reachability from an authenticated console response."""
        from .resolver import resolve_ipv4
        from .game_registry import registry_request, PORT
        bits = 0
        try:
            host, token = key
            if host:
                address = resolve_ipv4(host)
                with socket.create_connection((address, PORT), timeout=2):
                    bits = 1
                registry_request({"receiver": address, "token": token}, "read")
                bits = 3
        except (OSError, ValueError, KeyError, TypeError):
            pass
        finally:
            with self._probe_lock:
                if key == self._probe_key:
                    self._probe_result, self._probe_at = bits, time.monotonic()
                self._probe_running = False

    def set_status(self, status: MatrixStatus) -> bool:
        """Display a new status unless a temporary pairing display owns the matrix."""
        if status not in {MatrixStatus.OFF, MatrixStatus.PAIRING} and time.monotonic() < self.pairing_until:
            return self.available
        if status == self.last_status:
            return self.available
        if time.monotonic() < self._status_retry_at:
            return False
        if not self.available:
            return False
        try:
            assert self._call is not None
            self._call("set_virtualglove_status", int(status))
            self.last_status = status
            self._status_retry_at = 0.0
            self.last_error = None
            return True
        except Exception as exc:  # Bridge errors vary by App Lab release.
            self._status_retry_at = time.monotonic() + 1.0
            self.last_error = str(exc)
            return False

    def finish_pairing(self) -> None:
        """Let the next supervisor update restore the current normal display."""
        self.pairing_until = 0.0

    def show_pairing(self, certificate_id: str, pin: str, seconds: int = 120) -> bool:
        """Show a certificate prefix and one-time approval PIN on the physical matrix."""
        if len(certificate_id) != 7 or any(character not in "0123456789ABCDEF" for character in certificate_id):
            raise ValueError("invalid certificate identity")
        if len(pin) != 6 or not pin.isdigit():
            raise ValueError("invalid pairing PIN")
        if not self.available:
            return False
        try:
            assert self._call is not None
            self._call("set_virtualglove_pairing", int(certificate_id, 16), int(pin))
            self.pairing_until = time.monotonic() + seconds
            self.last_status = MatrixStatus.PAIRING
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def set_profile(self, profile: str | None) -> bool:
        """Display the compact numeric code for the active gesture profile."""
        codes = {
            **{f"program_{letter}": index for index, letter in enumerate("abcdefghi", 1)},
            "bad_street_brawler": 10,
            "super_glove_ball": 11,
            **{f"program_{number}": 11 + number for number in range(1, 15)},
        }
        if profile == self.last_profile:
            return self.available
        if time.monotonic() < self._profile_retry_at:
            return False
        if not self.available:
            return False
        try:
            assert self._call is not None
            self._call("set_virtualglove_profile", codes.get(profile, 0))
            self.last_profile = profile
            self._profile_retry_at = 0.0
            self.last_error = None
            return True
        except Exception as exc:
            self._profile_retry_at = time.monotonic() + 1.0
            self.last_error = str(exc)
            return False
