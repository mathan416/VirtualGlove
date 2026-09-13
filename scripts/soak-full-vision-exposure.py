#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/soak-full-vision-exposure.py
# Purpose: Repeatedly exercise manual exposure through the complete vision pipeline.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Added the output-disabled full-pipeline exposure soak.
# Full history: docs/CHANGELOG.md and Git history.

"""Run finite output-disabled Vision lifecycles and emit aggregate JSON only."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request


def worker_command(args):
    """Build the deliberately isolated controller-disabled worker command."""
    return [
        sys.executable, "-m", "powerglove_vision.vision_app",
        "--receiver", "127.0.0.1", "--port", "55999",
        "--token", "0123456789abcdef", "--profile",
        "off" if getattr(args, "transition_profile", None) else "practice",
        "--camera", args.device, "--camera-format", "MJPG",
        "--tracker-backend", "legacy", "--web-host", "127.0.0.1",
        "--web-port", str(args.web_port), "--profile-listen", "127.0.0.1",
        "--profile-port", str(args.profile_port), "--no-matrix",
        "--tracker-graph", "full", "--inference-threads", "4",
        "--tracking-confidence", "0.35", "--tracking-roi-scale", "2.25",
        "--fps", "30", "--capture-backend", "direct-v4l2",
        "--camera-exposure", "auto", "--camera-buffers", "2",
        "--native-xy-mode", "latest", "--model", str(args.model),
        "--camera-manual-exposure-test", str(args.exposure),
        "--camera-manual-gain-test", str(args.gain),
    ]


def status(url, timeout=.5):
    """Read one private worker snapshot."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def automatic_state(device):
    """Read the two standard exposure controls after the worker has closed."""
    from powerglove_vision import camera_controls as controls
    fd = os.open(device, os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
    try:
        result = {}
        for name, identifier in (("auto_exposure", controls.EXPOSURE_AUTO),
                                 ("dynamic_framerate", controls.EXPOSURE_AUTO_PRIORITY)):
            control = controls._query(fd, identifier, fcntl.ioctl)
            if control is None:
                result[name] = None
                continue
            data = bytearray(struct.pack("Ii", identifier, 0))
            fcntl.ioctl(fd, controls.VIDIOC_G_CTRL, data)
            result[name] = struct.unpack("Ii", data)[1]
        return result
    finally:
        os.close(fd)


def stop_worker(process):
    """Prefer normal cleanup, with bounded escalation for a blocked driver."""
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def run_cycle(args, index):
    """Run one full camera, MediaPipe, status, and cleanup lifecycle."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(args.module_root)
    log = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    process = subprocess.Popen(
        worker_command(args), env=environment, stdout=log,
        stderr=subprocess.STDOUT, text=True,
    )
    endpoint = "http://127.0.0.1:{}/status".format(args.web_port)
    snapshots = []
    idle_after = False
    error = None
    try:
        if args.transition_profile:
            deadline = time.monotonic() + args.startup_timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    error = "worker exited before idle profile listener became ready"
                    break
                try:
                    if status(endpoint).get("vision_state") == "idle":
                        break
                except Exception:
                    pass
                time.sleep(.2)
            else:
                error = "idle profile listener did not become ready"
            if error is None:
                from powerglove_vision.profile_control import send_request
                send_request(
                    "127.0.0.1", args.profile_port, "0123456789abcdef",
                    args.transition_profile, "nes", "Super Glove Ball (USA).nes", 1.0,
                    session_id="exposuretest0001", lease_seconds=15.0,
                )
        deadline = time.monotonic() + args.startup_timeout
        while error is None and time.monotonic() < deadline:
            if process.poll() is not None:
                error = "worker exited before becoming active"
                break
            try:
                current = status(endpoint)
                if current.get("vision_state") == "active" and current.get("camera_available"):
                    snapshots.append(current)
                    break
            except Exception:
                pass
            time.sleep(.2)
        if not snapshots and error is None:
            error = "worker did not become active before timeout"
        if error is None:
            until = time.monotonic() + args.seconds
            renew_at = time.monotonic() + 7
            while time.monotonic() < until:
                time.sleep(.5)
                snapshots.append(status(endpoint))
                if args.transition_profile and time.monotonic() >= renew_at:
                    from powerglove_vision.profile_control import send_request
                    send_request(
                        "127.0.0.1", args.profile_port, "0123456789abcdef",
                        args.transition_profile, "nes", "Super Glove Ball (USA).nes", 1.0,
                        session_id="exposuretest0001", lease_seconds=15.0,
                    )
                    renew_at = time.monotonic() + 7
            if args.transition_profile:
                from powerglove_vision.profile_control import send_request
                send_request(
                    "127.0.0.1", args.profile_port, "0123456789abcdef",
                    None, "nes", "", 1.0,
                )
                deadline = time.monotonic() + args.startup_timeout
                while time.monotonic() < deadline:
                    if status(endpoint).get("vision_state") == "idle":
                        idle_after = True
                        break
                    time.sleep(.2)
                if not idle_after:
                    error = "profile returned Off but camera did not become idle"
    except Exception as exc:
        error = str(exc)
    finally:
        stop_worker(process)
        log.flush()
        log.seek(0)
        output = log.read()
        log.close()
    sequences = [int(item.get("sequence", 0)) for item in snapshots]
    restored = automatic_state(args.device)
    report = {
        "cycle": index, "active_snapshots": len(snapshots),
        "sequence_first": sequences[0] if sequences else None,
        "sequence_last": sequences[-1] if sequences else None,
        "sequence_advanced": bool(sequences and sequences[-1] > sequences[0]),
        "camera_available_throughout": bool(snapshots) and all(
            item.get("camera_available") for item in snapshots
        ),
        "vision_active_throughout": bool(snapshots) and all(
            item.get("vision_state") == "active" for item in snapshots
        ),
        "worker_exit": process.returncode,
        "traceback": "Traceback" in output,
        "automatic_state": restored,
        "error": error,
        "transition_profile": args.transition_profile,
        "idle_after_transition": idle_after if args.transition_profile else None,
    }
    report["passed"] = (
        error is None and report["sequence_advanced"]
        and report["camera_available_throughout"]
        and report["vision_active_throughout"] and process.returncode == 0
        and not report["traceback"]
        and restored == {"auto_exposure": 3, "dynamic_framerate": 0}
        and (not args.transition_profile or idle_after)
    )
    if not report["passed"]:
        report["log_tail"] = output.splitlines()[-30:]
    return report


def main():
    """Run finite full-worker cycles and emit only aggregate JSON results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--module-root", type=Path, required=True)
    parser.add_argument("--cycles", type=int, choices=range(1, 21), default=3)
    parser.add_argument("--seconds", type=int, choices=range(5, 301), default=20)
    parser.add_argument("--startup-timeout", type=int, default=15)
    parser.add_argument("--exposure", type=int, default=78)
    parser.add_argument("--gain", type=int, default=96)
    parser.add_argument("--web-port", type=int, default=8189)
    parser.add_argument("--profile-port", type=int, default=55456)
    parser.add_argument("--transition-profile", choices=("super_glove_ball",),
                        default=None)
    parser.add_argument("--acknowledge-exclusive-camera", action="store_true", required=True)
    args = parser.parse_args()
    report = {
        "format": "virtualglove-full-vision-exposure-soak/1",
        "stores_images": False, "controller_output": False,
        "exposure": args.exposure, "gain": args.gain, "cycles": [],
    }
    for index in range(1, args.cycles + 1):
        cycle = run_cycle(args, index)
        report["cycles"].append(cycle)
        if not cycle["passed"]:
            break
        time.sleep(1)
    report["complete"] = (
        len(report["cycles"]) == args.cycles
        and all(item["passed"] for item in report["cycles"])
    )
    print(json.dumps(report, allow_nan=False))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
