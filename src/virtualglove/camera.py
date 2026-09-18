# Project: VirtualGlove
# File: src/virtualglove/camera.py
# Purpose: Discover usable Linux camera capture devices while excluding codec-only video nodes.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-10 - Added privacy-safe physical-camera identity for saved recommendations.
#   2026-09-09 - Required a real worker frame before confirming USB camera recovery.
#   2026-09-08 - Added browser-safe labels for selectable camera devices.
#   2026-09-08 - Distinguish healthy enrollment from present-but-wedged stream recovery.
#   2026-09-05 - Added guarded host USB-recovery requests for sustained camera outages.
#   2026-09-05 - Re-enroll the camera after each unavailable-to-healthy transition.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
# Full history: docs/CHANGELOG.md and Git history.

"""Linux camera discovery helpers for VirtualGlove."""

from __future__ import annotations

import json
import hashlib
import time
from pathlib import Path
from typing import Callable, Mapping


_NON_CAMERA_MARKERS = ("codec", "decoder", "encoder", "m2m", "venus")


class CameraUnavailableError(RuntimeError):
    """Raised when a configured camera cannot provide video frames."""


class CameraRecoveryRequester:
    """Request at most one host USB reset during each continuous camera outage."""

    def __init__(
        self,
        marker: Path,
        request: Path,
        *,
        delay: float = 15.0,
        retry_delay: float = 65.0,
        result: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.marker = marker
        self.request = request
        self.delay = max(0.0, float(delay))
        self.retry_delay = max(self.delay, float(retry_delay))
        self.result = result or request.with_name("camera-recovery-result")
        self.clock = clock
        self._missing_since: float | None = None
        self._requested = False
        self._was_available = False
        self._last_request_at: float | None = None
        self._awaiting_test_frame = False
        self._verification_started_at: float | None = None
        self._host_recovery_method: str | None = None
        self._verified_recovery_method: str | None = None
        self.last_action: str | None = None

    def _create_request(self, reason: str) -> None:
        """Atomically signal one narrowly classified host-side camera action."""
        self.request.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.result.unlink()
        except FileNotFoundError:
            pass
        temporary = self.request.with_name(self.request.name + ".tmp")
        temporary.write_text(reason + "\n")
        temporary.replace(self.request)
        self.last_action = reason

    def wait_for_recovery(self, timeout: float = 40.0) -> bool:
        """Wait for the host USB action; a later worker frame proves recovery."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline:
            try:
                result = json.loads(self.result.read_text())
                self.result.unlink()
                status = result.get("status")
                completed = status in ("usb-action-complete", "ready")
                if completed:
                    method = result.get("method", "legacy-host-action")
                    self._host_recovery_method = (
                        method if isinstance(method, str) and method else "unknown"
                    )
                    self._awaiting_test_frame = True
                    self._verification_started_at = self.clock()
                return completed
            except FileNotFoundError:
                time.sleep(0.1)
            except (OSError, ValueError, TypeError):
                return False
        return False

    def consume_verified_recovery(self) -> str | None:
        """Return a recovery method once, only after a worker received a frame."""
        method = self._verified_recovery_method
        self._verified_recovery_method = None
        return method

    def observe(self, status: Mapping[str, object]) -> bool:
        """Create one request after a sustained camera error; return when created."""
        if (
            self._awaiting_test_frame
            and self._verification_started_at is not None
            and self.clock() - self._verification_started_at >= self.retry_delay
        ):
            self._awaiting_test_frame = False
            self._verification_started_at = None
            self._host_recovery_method = None
        if bool(status.get("camera_available")):
            if self._awaiting_test_frame:
                self._awaiting_test_frame = False
                self._verification_started_at = None
                self._verified_recovery_method = self._host_recovery_method or "unknown"
                self._host_recovery_method = None
            self._missing_since = None
            self._requested = False
            self._last_request_at = None
            newly_available = not self._was_available
            self._was_available = True
            if self.marker.is_file() and newly_available:
                self._create_request("enroll")
                return True
            return False

        self._was_available = False

        state = str(status.get("vision_state", ""))
        error = str(status.get("vision_error", ""))
        if state == "idle":
            self._awaiting_test_frame = False
            self._verification_started_at = None
            self._host_recovery_method = None
            self._missing_since = None
            self._requested = False
            return False
        if state != "error" or "camera" not in error.lower():
            return False

        now = self.clock()
        if self._missing_since is None:
            self._missing_since = now
        if self._requested:
            if self._last_request_at is None or now - self._last_request_at < self.retry_delay:
                return False
            # The host may have restored USB enumeration without restoring a
            # usable video stream. Permit another guarded attempt after both
            # sides' cooldowns have elapsed.
            self._requested = False
        if now - self._missing_since < self.delay:
            return False
        if not self.marker.is_file():
            return False

        self._create_request("recover")
        self._requested = True
        self._last_request_at = now
        return True


def discover_camera_devices(
    dev_root: Path = Path("/dev"),
    sys_root: Path = Path("/sys/class/video4linux"),
) -> list[Path]:
    """Return likely capture devices, preferring stable USB-camera paths.

    Linux exposes hardware codecs as ``/dev/video*`` nodes too. Treating every
    such node as a camera made the UNO Q repeatedly probe its Qualcomm Venus
    encoder and decoder when no USB camera was attached.
    """
    devices: list[Path] = []
    resolved: set[Path] = set()

    for link in sorted((dev_root / "v4l" / "by-id").glob("*-video-index0")):
        try:
            target = link.resolve(strict=True)
        except OSError:
            continue
        devices.append(link)
        resolved.add(target)

    if not sys_root.exists():
        return devices

    for entry in sorted(sys_root.glob("video*")):
        node = dev_root / entry.name
        if not node.exists():
            continue
        try:
            name = (entry / "name").read_text().strip().lower()
        except OSError:
            continue
        if any(marker in name for marker in _NON_CAMERA_MARKERS):
            continue
        try:
            interface_index = (entry / "index").read_text().strip()
        except OSError:
            interface_index = "0"
        if interface_index != "0":
            continue
        target = node.resolve()
        if target not in resolved:
            devices.append(node)
            resolved.add(target)
    return devices


def camera_device_options(
    dev_root: Path = Path("/dev"),
    sys_root: Path = Path("/sys/class/video4linux"),
) -> list[dict[str, str]]:
    """Return browser-safe camera choices using the existing numeric setting format."""
    options = [{"value": "auto", "label": "Automatic — choose the connected camera"}]
    seen: set[str] = set()
    for device in discover_camera_devices(dev_root, sys_root):
        try:
            node = device.resolve(strict=True)
        except OSError:
            continue
        name = node.name
        if not name.startswith("video") or not name[5:].isdigit():
            continue
        value = name[5:]
        if value in seen or not 0 <= int(value) <= 99:
            continue
        seen.add(value)
        try:
            description = (sys_root / name / "name").read_text().strip()
        except OSError:
            description = "Camera"
        description = " ".join(description.split()) or "Camera"
        options.append({"value": value, "label": f"{description} — camera {value}"})
    return options


def camera_device_identity(
    selection: str,
    dev_root: Path = Path("/dev"),
    sys_root: Path = Path("/sys/class/video4linux"),
) -> dict[str, object] | None:
    """Return a stable, browser-safe identity for the selected physical camera."""
    choices = camera_candidates(selection, dev_root, sys_root)
    if not choices:
        return None
    choice = choices[0]
    node = dev_root / f"video{choice}" if isinstance(choice, int) else Path(choice)
    try:
        resolved = node.resolve(strict=True)
    except OSError:
        return None
    video = sys_root / resolved.name
    try:
        current = (video / "device").resolve(strict=True)
    except OSError:
        current = None
    usb = None
    if current is not None:
        for candidate in (current, *current.parents):
            if (candidate / "idVendor").is_file() and (candidate / "idProduct").is_file():
                usb = candidate
                break
    def read(path: Path, fallback: str = "") -> str:
        """Read and normalize one optional sysfs property."""
        try:
            return " ".join(path.read_text().split())
        except OSError:
            return fallback
    vendor = read(usb / "idVendor").lower() if usb else ""
    product = read(usb / "idProduct").lower() if usb else ""
    serial = read(usb / "serial") if usb else ""
    label = read(video / "name", "Camera")
    stable = f"{vendor}:{product}:{serial or label}"
    return {
        "key": hashlib.sha256(stable.encode()).hexdigest()[:24],
        "label": label,
        "vendor_id": vendor,
        "product_id": product,
        "has_serial": bool(serial),
        "direct_v4l2": resolved.name.startswith("video"),
    }


def camera_candidates(
    selection: str,
    dev_root: Path = Path("/dev"),
    sys_root: Path = Path("/sys/class/video4linux"),
) -> list[str | int]:
    """Resolve ``auto``, a numeric index, or an explicit device path."""
    value = str(selection).strip()
    if value.lower() == "auto":
        return [str(path) for path in discover_camera_devices(dev_root, sys_root)]
    try:
        return [int(value)]
    except ValueError:
        return [value]
