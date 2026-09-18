#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/prepare-end-to-end-session.py
# Purpose: Record a privacy-safe, read-only manifest before latency measurement.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Added two-device latency-session preflight and acceptance gates.
# Full history: docs/CHANGELOG.md and Git history.

"""Inspect the development checkout, Controller, and RetroPie without changing them."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_FIELDS = (
    "version", "build", "firmware", "worker_running", "camera_available",
    "detected", "calibrated", "profile", "controller_delivery",
    "capture_backend_requested", "capture_backend", "capture_backend_fallback",
    "camera_format", "camera_width", "camera_height", "camera_fps_requested",
    "camera_fps", "camera_buffers", "camera_exposure_mode",
    "camera_exposure_supported", "camera_exposure_applied",
    "camera_exposure_fixed_rate", "camera_hdr_off_command_sent",
    "camera_driver_timestamp", "tracker_backend", "tracker_backend_label",
    "tracker_graph", "inference_threads", "tracking_confidence", "tracking_roi_scale",
    "inference_hz",
    "native_xy_source", "controller_enabled",
    "reach", "app_started_at",
)

REMOTE_INSPECTOR = r'''
import hashlib, json, os, platform, shutil, stat, subprocess, sys
from pathlib import Path

role = sys.argv[1]

def text(path, maximum=262144):
    try:
        data = Path(path).read_text(errors="replace")
        return data[:maximum]
    except OSError:
        return None

def digest(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None

def command(*args):
    try:
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=5)
        return {"returncode": result.returncode, "output": result.stdout.strip()[:4096]}
    except (OSError, subprocess.SubprocessError) as error:
        return {"returncode": None, "error": type(error).__name__}

boot = text("/proc/sys/kernel/random/boot_id")
load = text("/proc/loadavg")
disk = shutil.disk_usage("/")
thermal = []
for item in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
    value = text(item)
    try:
        thermal.append(round(int(value.strip()) / 1000, 1))
    except (AttributeError, ValueError):
        pass

result = {
    "role": role,
    "boot_id_sha256": hashlib.sha256(boot.strip().encode()).hexdigest() if boot else None,
    "platform": platform.platform(),
    "machine": platform.machine(),
    "python": platform.python_version(),
    "load_average": load.strip().split()[:3] if load else [],
    "disk_free_bytes": disk.free,
    "thermal_celsius": thermal,
}

if role == "controller":
    base = Path("/home/arduino/ArduinoApps/virtualglove")
    build = text(base / "src/virtualglove/_build_info.json")
    try:
        result["build"] = json.loads(build) if build else None
    except ValueError:
        result["build"] = None
    result["services"] = {
        name: command("systemctl", "is-active", name)
        for name in ("virtualglove-camera-recovery.path", "virtualglove-wifi-status.timer")
    }
    result["files"] = {
        "vision_app_sha256": digest(base / "src/virtualglove/vision_app.py"),
        "v4l2_capture_sha256": digest(base / "src/virtualglove/v4l2_capture.py"),
        "calibration_present": (base / "data/calibration.json").is_file(),
    }
    device = text(base / "data/device.json")
    try:
        source = json.loads(device) if device else {}
    except ValueError:
        source = {}
    allowed = ("camera_backend", "camera_exposure", "camera_format", "camera_width",
               "camera_height", "camera_fps", "camera_buffers", "recognizer_backend",
               "tracker_graph", "inference_threads", "tracking_confidence",
               "tracking_roi_scale",
               )
    result["device_settings"] = {key: source.get(key) for key in allowed if key in source}
else:
    core = Path("/opt/retropie/libretrocores/lr-nestopia-powerglove/nestopia_powerglove_libretro.so")
    native = Path("/run/virtualglove/native-state")
    result["services"] = {
        name: command("systemctl", "is-active", name)
        for name in ("virtualglove-receiver.service", "virtualglove-receiver.timer", "virtualglove-games.service")
    }
    result["files"] = {
        "core_path": str(core), "core_sha256": digest(core),
        "receiver_sha256": digest("/opt/virtualglove-src/src/virtualglove/receiver.py"),
        "retroarch_sha256": digest("/opt/retropie/emulators/retroarch/bin/retroarch"),
    }
    try:
        info = native.stat()
        result["native_state"] = {
            "present": True, "size": info.st_size,
            "mode": stat.filemode(info.st_mode), "owner_uid": info.st_uid,
        }
    except OSError:
        result["native_state"] = {"present": False}
    result["retroarch_running"] = any(
        (text(path / "comm") or "").strip().casefold().startswith("retroarch")
        for path in Path("/proc").glob("[0-9]*")
    )
    keys = ("video_threaded", "video_driver", "video_vsync", "video_frame_delay",
            "video_max_swapchain_images", "video_refresh_rate", "run_ahead_enabled",
            "input_poll_type_behavior")
    configs = {}
    for path in (Path("/opt/retropie/configs/all/retroarch.cfg"),
                 Path("/opt/retropie/configs/nes/retroarch.cfg"),
                 Path("/opt/retropie/configs/all/retroarch-core-options.cfg")):
        body = text(path)
        if body is None:
            continue
        selected = {}
        for line in body.splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            if key in keys or key.startswith("nestopia_"):
                selected[key] = value.strip('"')
        configs[str(path)] = {"sha256": digest(path), "selected": selected}
    result["retroarch_configuration"] = configs
    result["throttling"] = command("vcgencmd", "get_throttled") if shutil.which("vcgencmd") else None

print(json.dumps(result, allow_nan=False))
'''


def fetch_status(url: str) -> dict:
    """Read public status and retain only measurement-relevant, non-secret fields."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError("Controller status returned HTTP %d" % response.status)
        source = json.loads(response.read(1024 * 1024))
    return {key: source.get(key) for key in STATUS_FIELDS if key in source}


def inspect_remote(target: str, identity: Path | None, role: str,
                   host_key_alias: str | None = None) -> dict:
    """Run the fixed read-only inspector over SSH; do not interpolate shell input."""
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if identity:
        command += ["-i", str(identity)]
    if host_key_alias:
        command += ["-o", "HostKeyAlias=" + host_key_alias]
    command += [target, "python3", "-", role]
    result = subprocess.run(command, input=REMOTE_INSPECTOR, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if result.returncode:
        raise RuntimeError("%s inspection failed: %s" % (role, result.stderr.strip()[:400]))
    return json.loads(result.stdout)


def git_identity() -> dict:
    """Identify the source checkout without changing it."""
    def git(*args):
        """Run one read-only Git query in the project checkout."""
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL, timeout=5).strip()
    commit = git("rev-parse", "HEAD")
    return {
        "commit": commit,
        "branch": git("branch", "--show-current"),
        "dirty": bool(git("status", "--porcelain")),
    }


def evaluate(status: dict, controller: dict, retropie: dict, source: dict,
             require_gameplay: bool = False) -> list[dict]:
    """Apply fixed readiness checks while keeping warnings distinct from failures."""
    checks = []
    def add(name, passed, severity="error", detail=None):
        """Append one normalized readiness result to the manifest."""
        checks.append({"name": name, "passed": bool(passed), "severity": severity,
                       "detail": detail})
    add("source checkout is clean", not source["dirty"],
        severity="warning",
        detail="Local analysis or documentation changes do not alter deployed gameplay")
    add("Controller worker is running", status.get("worker_running") is True)
    settings = controller.get("device_settings", {})
    add("camera is available", status.get("camera_available") is True,
        severity="error" if require_gameplay else "warning",
        detail="Camera may be intentionally closed during advance preparation")
    calibration = status.get("calibrated") is True
    if not require_gameplay:
        calibration = calibration or controller.get("files", {}).get("calibration_present")
    add("player calibration is available", calibration,
        severity="error" if require_gameplay else "warning")
    backend = status.get("tracker_backend") or settings.get("recognizer_backend", "legacy")
    graph = status.get("tracker_graph") or settings.get("tracker_graph", "full")
    add("MediaPipe Hands is selected", backend == "legacy")
    add("complete MediaPipe graph is selected", graph == "full")
    width = status.get("camera_width") or settings.get("camera_width", 640)
    height = status.get("camera_height") or settings.get("camera_height", 480)
    camera_format = status.get("camera_format") or settings.get("camera_format", "MJPG")
    fps = status.get("camera_fps") or settings.get("camera_fps")
    add("camera is configured for 640x480 MJPEG",
        width == 640 and height == 480 and camera_format == "MJPG")
    add("camera is configured for 30 fps", abs(float(fps or 0) - 30) < 1)
    add("native core is installed", bool(retropie.get("files", {}).get("core_sha256")))
    native = retropie.get("native_state", {})
    add("native state ABI is present", native.get("present") and native.get("size") == 64,
        severity="error" if require_gameplay else "warning", detail=native)
    build = status.get("build") or {}
    add("deployed Controller commit matches checkout",
        build.get("commit") == source.get("commit"),
        severity="error" if require_gameplay else "warning",
        detail={"deployed": build.get("commit"), "checkout": source.get("commit")})
    if require_gameplay:
        add("RetroArch is running for a gameplay trace",
            retropie.get("retroarch_running") is True)
    else:
        add("RetroArch is closed before trace setup",
            retropie.get("retroarch_running") is False,
            detail="Tracing must restart the receiver before the custom core opens native state")
    add("Controller has at least 1 GiB free", controller.get("disk_free_bytes", 0) >= 2**30)
    add("RetroPie has at least 1 GiB free", retropie.get("disk_free_bytes", 0) >= 2**30)
    return checks


def main() -> int:
    """Write one new private readiness report and fail record-phase errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-status", required=True,
                        help="Controller public status URL, normally ending in /status?statistics=1")
    parser.add_argument("--controller-ssh", required=True, help="SSH target, for example arduino@host")
    parser.add_argument("--retropie-ssh", required=True, help="SSH target, for example pi@host")
    parser.add_argument("--controller-identity", type=Path)
    parser.add_argument("--retropie-identity", type=Path)
    parser.add_argument("--controller-host-key-alias")
    parser.add_argument("--retropie-host-key-alias")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("prepare", "record"), default="prepare",
                        help="record makes live game/native-state checks mandatory")
    args = parser.parse_args()
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    status = fetch_status(args.controller_status)
    source = git_identity()
    controller = inspect_remote(args.controller_ssh, args.controller_identity, "controller",
                                args.controller_host_key_alias)
    retropie = inspect_remote(args.retropie_ssh, args.retropie_identity, "retropie",
                              args.retropie_host_key_alias)
    checks = evaluate(status, controller, retropie, source, args.phase == "record")
    report = {
        "format": "virtualglove-end-to-end-preflight/1",
        "session_id": uuid.uuid4().hex,
        "phase": args.phase,
        "created_unix": time.time(),
        "source": source,
        "controller_status": status,
        "controller_host": controller,
        "retropie_host": retropie,
        "checks": checks,
        "acceptance": {
            "physical_hand_to_display_ms": {"target_p50": 150, "target_p95": 200},
            "receiver_publication_p95_ms": 2,
            "core_consumption": "next emulated input frame",
            "tracking": "no continuity or stationary-stability regression",
            "trace_drops": 0,
            "movement_math_frozen_until_dominant_stage_identified": True,
        },
        "privacy": "No token, pairing credential, player name, image, landmark, or raw coordinate is recorded.",
    }
    destination = args.output_dir / "preflight.json"
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    os.chmod(destination, 0o600)
    errors = [item for item in checks if not item["passed"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["passed"] and item["severity"] == "warning"]
    print("Preflight written to %s" % destination)
    print("%d checks passed; %d errors; %d warnings" %
          (len(checks) - len(errors) - len(warnings), len(errors), len(warnings)))
    for item in errors + warnings:
        print("%s: %s" % (item["severity"].upper(), item["name"]))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
