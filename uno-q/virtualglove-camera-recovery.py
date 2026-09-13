#!/usr/bin/env python3
# Project: VirtualGlove
# File: uno-q/virtualglove-camera-recovery.py
# Purpose: Recover the single UVC camera through its most recently observed parent USB hub.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-10 - Refuse whole-hub recovery when the enrolled hub carries networking.
#   2026-09-09 - Added capability-gated per-port power cycling and explicit USB-action results.
#   2026-09-08 - Reset an enrolled hub when UVC streaming fails despite USB enumeration.
#   2026-09-05 - Added guarded camera USB recovery and autosuspend prevention.
#   2026-09-05 - Added first-use camera enrollment and automatic parent-hub updates.
# Full history: docs/CHANGELOG.md and Git history.

"""Consume one camera recovery request without granting the app general root access."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


APP_DATA = Path("/home/arduino/ArduinoApps/virtualglove/data")
REQUEST = APP_DATA / "camera-recovery-request"
RESULT = APP_DATA / "camera-recovery-result"
USB_DEVICES = Path("/sys/bus/usb/devices")
VIDEO_CLASS = Path("/sys/class/video4linux")
USB_DRIVER = Path("/sys/bus/usb/drivers/usb")
CONFIG = Path("/etc/virtualglove-camera-recovery.json")
LOCK = Path("/run/virtualglove-camera-recovery.lock")
STAMP = Path("/run/virtualglove-camera-recovery.stamp")
COOLDOWN_SECONDS = 60.0
USB_NAME = re.compile(r"^[0-9]+-[0-9]+(?:\.[0-9]+)*$")
USB_PORT = re.compile(r"^[1-9][0-9]*$")


def _read(path: Path, default: str = "") -> str:
    """Read and trim one sysfs value, returning a safe default on failure."""
    try:
        return path.read_text().strip()
    except OSError:
        return default


def _identity(device: Path) -> tuple[str, str] | None:
    """Return a lowercase USB vendor/product identity when both are present."""
    vendor = _read(device / "idVendor").lower()
    product = _read(device / "idProduct").lower()
    return (vendor, product) if vendor and product else None


def _usb_device_for(path: Path) -> Path | None:
    """Walk upward from a video node to its first identified USB device."""
    try:
        current = path.resolve()
    except OSError:
        return None
    for candidate in (current, *current.parents):
        if _identity(candidate):
            return candidate
    return None


def _parent_hub(camera: Path) -> Path | None:
    """Locate the camera's nearest identified USB hub ancestor."""
    for candidate in camera.parents:
        if (
            USB_NAME.fullmatch(candidate.name)
            and _identity(candidate)
            and _read(candidate / "bDeviceClass").lower() == "09"
        ):
            return candidate
    return None


def _discover_cameras() -> list[dict[str, object]]:
    """Discover primary UVC video nodes with resettable parent USB hubs."""
    cameras: dict[str, dict[str, object]] = {}
    if not VIDEO_CLASS.exists():
        return []
    for video in sorted(VIDEO_CLASS.glob("video*")):
        if _read(video / "index") not in ("", "0"):
            continue
        camera = _usb_device_for(video / "device")
        if camera is None:
            continue
        hub = _parent_hub(camera)
        if hub is None:
            continue
        camera_id = _identity(camera)
        hub_id = _identity(hub)
        if camera_id is None or hub_id is None:
            continue
        key = str(camera.resolve())
        cameras[key] = {
            "camera": {
                "vendor_id": camera_id[0],
                "product_id": camera_id[1],
                "name": _read(video / "name", _read(camera / "product", "USB camera")),
            },
            "hub": {
                "vendor_id": hub_id[0],
                "product_id": hub_id[1],
                "name": _read(hub / "product", "USB hub"),
                "sysfs_name": hub.name,
            },
            "camera_path": camera,
            "hub_path": hub,
        }
    return list(cameras.values())


def _public_config(discovery: dict[str, object]) -> dict[str, object]:
    """Discard transient paths and retain only the validated enrollment record."""
    camera = dict(discovery["camera"])
    camera["hub_port"] = _camera_hub_port(
        discovery["camera_path"], discovery["hub_path"],
    )
    return {"schema": 2, "camera": camera, "hub": discovery["hub"]}


def _camera_hub_port(camera: Path, hub: Path) -> str:
    """Return the camera's direct port number on its nearest parent hub."""
    prefix = hub.name + "."
    if not camera.name.startswith(prefix):
        raise RuntimeError("camera path is not below its enrolled parent hub")
    port = camera.name[len(prefix):].split(".", 1)[0]
    if not USB_PORT.fullmatch(port):
        raise RuntimeError("camera has an unsafe parent-hub port")
    return port


def _validate_section(section: object, fields: tuple[str, ...]) -> dict[str, str]:
    """Validate one camera or hub configuration section and USB identifiers."""
    if not isinstance(section, dict):
        raise RuntimeError("camera recovery configuration is malformed")
    result = {}
    for field in fields:
        value = section.get(field)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"camera recovery configuration is missing {field}")
        result[field] = value
    for field in ("vendor_id", "product_id"):
        if not re.fullmatch(r"[0-9a-f]{4}", result[field].lower()):
            raise RuntimeError(f"camera recovery configuration has an invalid {field}")
        result[field] = result[field].lower()
    return result


def _config_is_secure() -> bool:
    """Require the enrollment file to be root-owned and not broadly writable."""
    try:
        status = CONFIG.stat()
    except OSError:
        return False
    return status.st_uid == 0 and status.st_mode & 0o022 == 0


def _load_config(optional: bool = False) -> dict[str, object] | None:
    """Load and validate the root-owned camera/hub enrollment document."""
    if optional and not CONFIG.exists():
        return None
    if not _config_is_secure():
        raise RuntimeError(f"{CONFIG} must be root-owned and not be group/world writable")
    try:
        document = json.loads(CONFIG.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read camera recovery configuration: {error}") from error
    if not isinstance(document, dict) or document.get("schema") not in (1, 2):
        raise RuntimeError("unsupported camera recovery configuration schema")
    camera = _validate_section(document.get("camera"), ("vendor_id", "product_id", "name"))
    hub = _validate_section(document.get("hub"), ("vendor_id", "product_id", "name", "sysfs_name"))
    if not USB_NAME.fullmatch(hub["sysfs_name"]):
        raise RuntimeError("camera recovery configuration has an unsafe hub path")
    schema = document["schema"]
    if schema == 2:
        port = document["camera"].get("hub_port")
        if not isinstance(port, str) or not USB_PORT.fullmatch(port):
            raise RuntimeError("camera recovery configuration has an unsafe hub port")
        camera["hub_port"] = port
    return {"schema": schema, "camera": camera, "hub": hub}


def _write_config(discovery: dict[str, object]) -> None:
    """Atomically persist the last healthy camera and parent-hub identity."""
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_name(CONFIG.name + ".tmp")
    temporary.write_text(json.dumps(_public_config(discovery), indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o644)
    os.replace(temporary, CONFIG)


def _enroll_if_present(required: bool) -> int:
    """Enroll exactly one visible camera, optionally deferring when absent."""
    if os.geteuid() != 0:
        raise PermissionError("camera recovery configuration must run as root")
    cameras = _discover_cameras()
    if not cameras and not required:
        print("VirtualGlove camera recovery: no camera connected; enrollment deferred until first use")
        return 0
    if len(cameras) != 1:
        raise RuntimeError(
            f"expected exactly one UVC camera with a resettable parent hub; found {len(cameras)}"
        )
    discovery = cameras[0]
    _write_config(discovery)
    camera = discovery["camera"]
    hub = discovery["hub"]
    print(
        "VirtualGlove camera recovery enrolled:\n"
        f"  camera: {camera['name']} ({camera['vendor_id']}:{camera['product_id']})\n"
        f"  hub: {hub['name']} ({hub['vendor_id']}:{hub['product_id']}) at {hub['sysfs_name']}"
    )
    return 0


def _approved_hub(config: dict[str, object]) -> Path:
    """Resolve the allowlisted hub only when its current identity still matches."""
    hub_config = config["hub"]
    hub = USB_DEVICES / hub_config["sysfs_name"]
    expected = (hub_config["vendor_id"], hub_config["product_id"])
    if not hub.exists() or _identity(hub) != expected:
        raise RuntimeError("the last observed USB hub is absent or has changed identity")
    if _read(hub / "bDeviceClass").lower() != "09":
        raise RuntimeError("the last observed USB device is no longer a hub")
    return hub


def _matches_enrollment(discovery: dict[str, object], config: dict[str, object]) -> bool:
    """Require the returned camera and hub to match the allowlisted identities."""
    return (
        discovery["camera"]["vendor_id"] == config["camera"]["vendor_id"]
        and discovery["camera"]["product_id"] == config["camera"]["product_id"]
        and discovery["hub"]["vendor_id"] == config["hub"]["vendor_id"]
        and discovery["hub"]["product_id"] == config["hub"]["product_id"]
        and discovery["hub"]["sysfs_name"] == config["hub"]["sysfs_name"]
    )


def _keep_awake(device: Path) -> None:
    """Disable USB autosuspend for one enrolled device when supported."""
    control = device / "power" / "control"
    if control.exists():
        control.write_text("on")


def _consume_request() -> str | None:
    """Consume and validate one unprivileged, narrowly classified request."""
    try:
        reason = REQUEST.read_text().strip()
        REQUEST.unlink()
        # Empty files were written by versions before request classification.
        if reason == "":
            return "legacy"
        if reason not in ("enroll", "recover"):
            raise RuntimeError("camera recovery request has an unknown action")
        return reason
    except FileNotFoundError:
        return None


def _publish_result(status: str, method: str | None = None) -> None:
    """Atomically tell the unprivileged supervisor that the guarded action ended."""
    APP_DATA.mkdir(parents=True, exist_ok=True)
    temporary = RESULT.with_name(RESULT.name + "." + str(os.getpid()) + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(temporary), flags, 0o644)
    try:
        with os.fdopen(descriptor, "w") as stream:
            result = {"schema": 2, "status": status}
            if method is not None:
                result["method"] = method
            json.dump(result, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(RESULT))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _within_cooldown(now: float) -> bool:
    """Report whether a prior physical reset is still inside the cooldown."""
    try:
        return now - float(STAMP.read_text().strip()) < COOLDOWN_SECONDS
    except (OSError, ValueError):
        return False


def _uhubctl_supports_port(binary: str, hub_name: str, port: str) -> bool:
    """Ask uhubctl whether one exact hub location exposes switchable port power."""
    try:
        completed = subprocess.run(
            [binary, "-l", hub_name, "-p", port, "-e", "-N"],
            check=False, capture_output=True, text=True, timeout=8.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    output = completed.stdout + "\n" + completed.stderr
    return (
        completed.returncode == 0
        and re.search(
            r"(?:Current status for hub|Hub)\s+" + re.escape(hub_name) + r"(?:\s|\[|$)",
            output,
        ) is not None
    )


def _power_cycle_camera_port(config: dict[str, object], hub: Path) -> bool:
    """Power-cycle only the enrolled camera port when the hub proves support."""
    port = config["camera"].get("hub_port")
    if not isinstance(port, str) or not USB_PORT.fullmatch(port):
        return False
    binary = shutil.which("uhubctl")
    if binary is None or not _uhubctl_supports_port(binary, hub.name, port):
        return False
    try:
        completed = subprocess.run(
            [
                binary, "-l", hub.name, "-p", port, "-e", "-N",
                "-a", "cycle", "-d", "2",
            ],
            check=False, capture_output=True, text=True, timeout=15.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _rebind_hub(hub: Path) -> None:
    """Use the established identity-checked whole-hub driver fallback."""
    hub_name = hub.name
    unbound = False
    try:
        (USB_DRIVER / "unbind").write_text(hub_name)
        unbound = True
        time.sleep(2.0)
        (USB_DRIVER / "bind").write_text(hub_name)
        unbound = False
    finally:
        if unbound:
            (USB_DRIVER / "bind").write_text(hub_name)


def _hub_has_network_interface(hub: Path) -> bool:
    """Report whether any network interface is below the enrolled USB hub."""
    try:
        root = hub.resolve()
    except OSError:
        root = hub
    try:
        network_directories = root.rglob("net")
        for directory in network_directories:
            if not directory.is_dir():
                continue
            try:
                if any(directory.iterdir()):
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _recover() -> str:
    """Handle one request by enrolling a healthy camera or resetting its hub."""
    APP_DATA.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        reason = _consume_request()
        if reason is None:
            return 0
        if os.geteuid() != 0:
            raise PermissionError("camera recovery must run as root")

        # A healthy sighting is authoritative for enrollment. A stream-failure
        # request remains a recovery request even when sysfs/lsusb can still see
        # the device: UVC negotiation can wedge without USB disconnection.
        cameras = _discover_cameras()
        if len(cameras) > 1:
            raise RuntimeError(f"expected one UVC camera; found {len(cameras)}")
        if cameras:
            discovery = cameras[0]
            previous = _load_config(optional=True)
            current = _public_config(discovery)
            if previous != current:
                _write_config(discovery)
                print("VirtualGlove camera recovery: camera and parent hub enrollment updated")
            _keep_awake(discovery["camera_path"])
            _keep_awake(discovery["hub_path"])
            if reason != "recover":
                print("VirtualGlove camera recovery: camera present; autosuspend disabled")
                return "enrollment"

        config = _load_config(optional=True)
        if config is None:
            raise RuntimeError(
                "no camera has been enrolled yet; reconnect or power-cycle it once so it can be observed"
            )
        now = time.monotonic()
        if _within_cooldown(now):
            print("VirtualGlove camera recovery: request ignored during cooldown")
            return "cooldown"
        hub = _approved_hub(config)
        hub_name = hub.name
        _keep_awake(hub)
        STAMP.write_text(str(now))
        if _power_cycle_camera_port(config, hub):
            method = "port-power-cycle"
            print(
                "VirtualGlove camera recovery: power-cycled camera port "
                f"{config['camera']['hub_port']} on {hub_name}"
            )
        else:
            if _hub_has_network_interface(hub):
                raise RuntimeError(
                    "camera-port power cycling is unavailable; refusing a whole-hub "
                    "reset because the enrolled hub also carries a network interface"
                )
            method = "hub-driver-rebind"
            _rebind_hub(hub)

        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            cameras = _discover_cameras()
            if len(cameras) == 1:
                discovery = cameras[0]
                if not _matches_enrollment(discovery, config):
                    raise RuntimeError(
                        "a different camera or hub appeared after recovery; refusing enrollment"
                    )
                _write_config(discovery)
                _keep_awake(discovery["camera_path"])
                _keep_awake(discovery["hub_path"])
                print(
                    f"VirtualGlove camera recovery: {method} completed; camera enumerated"
                )
                return method
            if len(cameras) > 1:
                raise RuntimeError(f"hub reset returned {len(cameras)} UVC cameras; refusing enrollment")
            time.sleep(0.25)
        raise RuntimeError(f"reset {hub_name}, but the enrolled camera did not return")


def main(argv: list[str] | None = None) -> int:
    """Dispatch installation-time enrollment or one guarded recovery request."""
    arguments = sys.argv[1:] if argv is None else argv
    if arguments == ["--configure"]:
        return _enroll_if_present(required=True)
    if arguments == ["--configure-if-present"]:
        return _enroll_if_present(required=False)
    if arguments:
        raise SystemExit("usage: virtualglove-camera-recovery [--configure|--configure-if-present]")
    try:
        method = _recover()
    except Exception:
        _publish_result("failed")
        raise
    _publish_result("usb-action-complete", method)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
