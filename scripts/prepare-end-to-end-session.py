#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/prepare-end-to-end-session.py
# Purpose: Record a privacy-safe, read-only manifest before latency measurement.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-21 - Added read-only Batocera and Recalbox FCEUmm preflight.
#   2026-09-08 - Added two-device latency-session preflight and acceptance gates.
# Full history: docs/CHANGELOG.md and Git history.

"""Inspect the checkout, Controller, and console without changing them."""

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
elif role == "retropie":
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
elif role in ("recalbox", "batocera"):
    base = (Path("/recalbox/share/system/virtualglove") if role == "recalbox"
            else Path("/userdata/system/virtualglove"))
    # These systems keep their read-only OS root separate from writable user
    # storage. Trace preparation must check the partition that holds evidence.
    result["disk_free_bytes"] = shutil.disk_usage(
        base if base.exists() else base.parent).free
    result["disk_checked"] = "writable_platform_data"
    result["installation_present"] = base.is_dir()
    version_path = (Path("/recalbox/recalbox.version") if role == "recalbox"
                    else Path("/usr/share/batocera/batocera.version"))
    result["platform_version"] = (text(version_path, 128) or "").strip() or None
    service = (base / "recalbox/virtualglove-service" if role == "recalbox"
               else Path("/userdata/system/services/VirtualGlove"))
    config_paths = (
        (Path("/recalbox/share/roms/.retroarch.cfg"),
         Path("/recalbox/share/system/recalbox.conf"),
         Path("/recalbox/share/system/configs/retroarch/retroarchcustom.cfg"),
         Path("/recalbox/share/system/configs/retroarch/nes.cfg"),
         Path("/recalbox/share/system/configs/retroarch/config/FCEUmm/FCEUmm.cfg"))
        if role == "recalbox" else
        (Path("/userdata/system/batocera.conf"),
         Path("/userdata/system/configs/retroarch/retroarchcustom.cfg"),
         Path("/userdata/system/configs/retroarch/nes.cfg"),
         Path("/userdata/system/configs/retroarch/config/FCEUmm/FCEUmm.cfg"))
    )
    result["services"] = {"virtualglove": command("sh", str(service), "status")}
    result["files"] = {
        "receiver_sha256": digest(base / "src/virtualglove/receiver.py"),
        "router_sha256": digest(base / "src/virtualglove/controller_router.py"),
        "fceumm_sha256": digest("/usr/lib/libretro/fceumm_libretro.so"),
        "router_config_sha256": digest(base / "data/controller-router.json"),
    }
    router = text(base / "data/controller-router.json")
    try:
        routed = json.loads(router) if router else {}
        slots = routed.get("players", {})
        result["router"] = {
            "platform": routed.get("platform"),
            "configured_player_slots": len(slots) if isinstance(slots, (dict, list)) else None,
            "virtualglove_player": routed.get("virtualglove_player"),
        }
    except ValueError:
        result["router"] = {"invalid": True}
    try:
        checked = subprocess.run(
            ("sh", str(base / "scripts/virtualglove-controller-router"), "check"),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
        if checked.returncode or len(checked.stdout) > 262144:
            raise ValueError("router check unavailable")
        state = json.loads(checked.stdout)
        inventory = state.get("inventory", [])
        result["router_check"] = {
            "safe": state.get("safe") is True,
            "enabled_players": state.get("enabled_players", []),
            "missing_source_count": len(state.get("missing_sources", [])),
            "configured_source_count": sum(len(item.get("sources", [])) for item in
                                           state.get("config", {}).get("players", [])),
            "connected_source_count": sum(item.get("connected") is True for item in inventory),
        }
    except (OSError, ValueError, subprocess.SubprocessError, TypeError):
        result["router_check"] = {"unavailable": True}
    result["merged_input_devices"] = (text("/proc/bus/input/devices") or "").count(
        'Name="VirtualGlove Merged Player ')
    result["retroarch_running"] = False
    result["active_core"] = None
    for process in Path("/proc").glob("[0-9]*"):
        if not (text(process / "comm") or "").strip().casefold().startswith("retroarch"):
            continue
        result["retroarch_running"] = True
        arguments = text(process / "cmdline", 32768) or ""
        for core in ("fceumm_libretro.so", "nestopia_powerglove_libretro.so",
                     "nestopia_libretro.so"):
            if core in arguments:
                result["active_core"] = core
                break
        if result["active_core"] is None:
            try:
                with (process / "maps").open(errors="replace") as mappings:
                    for line in mappings:
                        for core in ("fceumm_libretro.so", "nestopia_powerglove_libretro.so",
                                     "nestopia_libretro.so"):
                            if core in line:
                                result["active_core"] = core
                                break
                        if result["active_core"] is not None:
                            break
            except OSError:
                pass
        break
    keys = ("video_threaded", "video_driver", "video_vsync", "video_frame_delay",
            "video_frame_delay_auto",
            "video_max_swapchain_images", "video_refresh_rate", "run_ahead_enabled",
            "input_poll_type_behavior", "input_player1_joypad_index")
    configs = {}
    for path in config_paths:
        body = text(path)
        if body is None:
            continue
        selected = {}
        for line in body.splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            prefixed = (key.removeprefix("global.retroarch.")
                        if key.startswith("global.retroarch.") else
                        key.removeprefix("nes.retroarch.")
                        if key.startswith("nes.retroarch.") else None)
            if key in keys or prefixed in keys or key in ("global.videomode", "nes.videomode"):
                selected[key] = value.strip('"')
        configs[str(path)] = {"sha256": digest(path), "selected": selected}
    result["retroarch_configuration"] = configs
    if role == "batocera" and shutil.which("iw"):
        devices = command("iw", "dev")
        wifi = []
        for line in devices.get("output", "").splitlines():
            parts = line.strip().split()
            if len(parts) != 2 or parts[0] != "Interface":
                continue
            interface = parts[1]
            link = command("iw", "dev", interface, "link")
            if not link.get("output", "").startswith("Connected to "):
                continue
            power = command("iw", "dev", interface, "get", "power_save")
            wifi.append({"interface": interface,
                         "power_save": power.get("output", "").strip()})
        result["connected_wifi"] = wifi
else:
    raise SystemExit("unsupported inspection role")

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


def evaluate_merged_console(status: dict, controller: dict, console: dict,
                            source: dict, require_gameplay: bool = False) -> list[dict]:
    """Check FCEUmm comparison readiness without assuming RetroPie's native ABI."""
    checks = []
    def add(name, passed, severity="error", detail=None):
        """Append one privacy-safe readiness result."""
        checks.append({"name": name, "passed": bool(passed), "severity": severity,
                       "detail": detail})
    add("source checkout is clean", not source["dirty"], "warning")
    add("Controller worker is running", status.get("worker_running") is True)
    add("camera is available", status.get("camera_available") is True,
        "error" if require_gameplay else "warning")
    add("player calibration is available", status.get("calibrated") is True or
        (not require_gameplay and controller.get("files", {}).get("calibration_present")),
        "error" if require_gameplay else "warning")
    add("Controller has at least 1 GiB free", controller.get("disk_free_bytes", 0) >= 2**30)
    add("console has at least 1 GiB free", console.get("disk_free_bytes", 0) >= 2**30)
    add("VirtualGlove console installation is present",
        console.get("installation_present") is True)
    add("FCEUmm is installed", bool(console.get("files", {}).get("fceumm_sha256")))
    add("Controller Router is installed", bool(console.get("files", {}).get("router_sha256")))
    add("Controller Router configuration is valid for this platform",
        console.get("router", {}).get("platform") == console.get("role"))
    router_check = console.get("router_check", {})
    add("Controller Router live check is available",
        router_check.get("unavailable") is not True and bool(router_check))
    add("configured physical controllers are available",
        router_check.get("safe") is True, "warning",
        {"missing_source_count": router_check.get("missing_source_count")})
    add("merged input device is present", console.get("merged_input_devices", 0) >= 1)
    service_output = console.get("services", {}).get("virtualglove", {}).get("output", "")
    add("Controller Router process is running", "RUNNING controller_router" in service_output)
    add("receiver process is running", "RUNNING receiver" in service_output,
        "error" if require_gameplay else "warning")
    if console.get("role") == "batocera":
        for wifi in console.get("connected_wifi", []):
            add("Batocera connected Wi-Fi power saving is off",
                wifi.get("power_save") == "Power save: off", "warning",
                {"interface": wifi.get("interface"), "state": wifi.get("power_save")})
    add("deployed Controller commit matches checkout",
        (status.get("build") or {}).get("commit") == source.get("commit"),
        "warning", "A different checkout may be intentional; record the deployed build")
    if require_gameplay:
        add("RetroArch is running", console.get("retroarch_running") is True)
        add("FCEUmm is the active core", console.get("active_core") == "fceumm_libretro.so")
    else:
        add("RetroArch is closed for baseline preparation",
            console.get("retroarch_running") is False, "warning",
            "Close the game before changing settings; read-only preflight is still safe")
    return checks


def main() -> int:
    """Write one new private readiness report and fail record-phase errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-status", required=True,
                        help="Controller public status URL, normally ending in /status?statistics=1")
    parser.add_argument("--controller-ssh", required=True, help="SSH target, for example arduino@host")
    parser.add_argument("--console-platform", choices=("retropie", "recalbox", "batocera"),
                        default="retropie", help="Console integration being measured")
    parser.add_argument("--console-ssh", help="SSH target for the selected console")
    parser.add_argument("--retropie-ssh", help="Legacy alias for --console-ssh with RetroPie")
    parser.add_argument("--controller-identity", type=Path)
    parser.add_argument("--retropie-identity", type=Path)
    parser.add_argument("--console-identity", type=Path)
    parser.add_argument("--controller-host-key-alias")
    parser.add_argument("--retropie-host-key-alias")
    parser.add_argument("--console-host-key-alias")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("prepare", "record"), default="prepare",
                        help="record requires a running game and the selected platform's input checks")
    args = parser.parse_args()
    if args.console_ssh and args.retropie_ssh:
        parser.error("Use --console-ssh or --retropie-ssh, not both")
    if args.console_platform != "retropie" and args.retropie_ssh:
        parser.error("--retropie-ssh is only valid for RetroPie")
    target = args.console_ssh or args.retropie_ssh
    if not target:
        parser.error("--console-ssh is required")
    if args.console_identity and args.retropie_identity:
        parser.error("Use one console identity option")
    if args.console_host_key_alias and args.retropie_host_key_alias:
        parser.error("Use one console host-key alias option")
    status = fetch_status(args.controller_status)
    source = git_identity()
    controller = inspect_remote(args.controller_ssh, args.controller_identity, "controller",
                                args.controller_host_key_alias)
    console = inspect_remote(target, args.console_identity or args.retropie_identity,
                             args.console_platform,
                             args.console_host_key_alias or args.retropie_host_key_alias)
    checks = (evaluate(status, controller, console, source, args.phase == "record")
              if args.console_platform == "retropie" else
              evaluate_merged_console(status, controller, console, source,
                                      args.phase == "record"))
    report = {
        "format": "virtualglove-end-to-end-preflight/2",
        "session_id": uuid.uuid4().hex,
        "phase": args.phase,
        "console_platform": args.console_platform,
        "created_unix": time.time(),
        "source": source,
        "controller_status": status,
        "controller_host": controller,
        "console_host": console,
        "checks": checks,
        "acceptance": {
            "physical_hand_to_display_ms": {"historical_goal_p50": 150,
                                            "historical_goal_p95": 200},
            "comparison": "Use matched physical joypad and VirtualGlove trials; do not declare parity from this preflight",
            "core_consumption": "not established by this preflight",
            "tracking": "no continuity or stationary-stability regression",
            "trace_drops": 0,
            "movement_math_frozen_until_dominant_stage_identified": True,
        },
        "privacy": "No token, pairing credential, player name, image, landmark, or raw coordinate is recorded.",
    }
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
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
