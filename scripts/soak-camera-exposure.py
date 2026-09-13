#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/soak-camera-exposure.py
# Purpose: Reliability-test temporary camera exposure settings outside gameplay.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Added the output-free camera exposure reliability soak.
# Full history: docs/CHANGELOG.md and Git history.

"""Run an output-free, aggregate-only V4L2 exposure soak.

The normal vision worker must be idle. The tool never sends controller data and
stores no images. Manual controls are applied only after the first valid frame,
through the already-streaming camera descriptor, and automatic exposure is
restored before every close.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import signal
import sys
import time

# Kept as public diagnostic constants for the dependency-free test harness.
EXPOSURE_ABSOLUTE = 0x009A0902
GAIN = 0x00980913


def percentile(values, fraction):
    """Return one nearest-rank percentile without external statistics tools."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def control_set(fd, mode, exposure, gain, ioctl=None):
    """Apply a fully capability-checked lane to an active stream descriptor."""
    from powerglove_vision import camera_controls as controls
    if mode == "manual":
        return controls.configure_manual_on_fd(fd, exposure, gain, ioctl)
    restored = controls.restore_automatic_on_fd(fd, ioctl)
    return {"applied": restored, "mode": mode, "exposure": None, "gain": None}


def restore_automatic(fd, ioctl=None):
    """Return the active camera to automatic, fixed-rate exposure."""
    from powerglove_vision import camera_controls as controls
    return controls.restore_automatic_on_fd(fd, ioctl)


def raw_camera_class(root):
    """Reuse the bounded, newest-buffer camera used by the existing benchmark."""
    source = root / "scripts" / "benchmark-camera-pipeline.py"
    spec = importlib.util.spec_from_file_location("camera_pipeline_soak", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RawCamera


def negotiate_camera(device, cv2):
    """Establish the same finite MJPEG mode used before direct capture."""
    camera = cv2.VideoCapture(device, cv2.CAP_V4L2)
    try:
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, 30)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        deadline = time.monotonic() + 5
        while camera.isOpened() and time.monotonic() < deadline:
            ok, _frame = camera.read()
            if ok:
                return
        raise RuntimeError("camera did not negotiate a first MJPEG frame")
    finally:
        camera.release()


def run_cycle(factory, device, seconds, mode, exposure, gain, cv2, np, stopped):
    """Open, warm, apply, measure, restore, and close one camera lifecycle."""
    camera = factory(device, 1, cv2, np)
    report = {"mode": mode, "frames": 0, "failed_reads": 0,
              "driver_sequence_gaps": 0, "restored_automatic": False}
    intervals, luma, sharpness = [], [], []
    previous_at = previous_sequence = None
    try:
        first = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not stopped():
            ok, payload = camera.read()
            if ok:
                first = payload
                break
        if first is None:
            report["error"] = "no first frame"
            return report
        setting = control_set(camera.fd, mode, exposure, gain)
        report["control"] = setting
        if not setting.get("applied"):
            report["error"] = "exposure controls were not fully applied"
            return report
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not stopped():
            ok, payload = camera.read()
            if not ok:
                report["failed_reads"] += 1
                continue
            frame, row = payload
            report["frames"] += 1
            at = row["dequeued_ns"]
            sequence = int(row["driver_sequence"])
            if previous_at is not None:
                intervals.append((at - previous_at) / 1e6)
                report["driver_sequence_gaps"] += max(0, sequence - previous_sequence - 1)
            previous_at, previous_sequence = at, sequence
            if report["frames"] % 10 == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                luma.append(float(gray.mean()))
                sharpness.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
        report.update({
            "interval_ms_p50": percentile(intervals, .5),
            "interval_ms_p95": percentile(intervals, .95),
            "interval_ms_max": max(intervals) if intervals else None,
            "luma_mean": sum(luma) / len(luma) if luma else None,
            "sharpness_mean": sum(sharpness) / len(sharpness) if sharpness else None,
        })
        return report
    finally:
        report["restored_automatic"] = restore_automatic(camera.fd)
        camera.close()


def main():
    """Run finite camera lifecycles and emit one image-free JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--mode", choices=("auto", "manual"), required=True)
    parser.add_argument("--cycles", type=int, choices=range(1, 21), default=3)
    parser.add_argument("--seconds", type=int, choices=range(5, 301), default=30)
    parser.add_argument("--exposure", type=int, default=78)
    parser.add_argument("--gain", type=int, default=96)
    parser.add_argument("--source-root", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--acknowledge-exclusive-camera", action="store_true",
                        required=True)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("the exposure soak requires Linux V4L2")
    sys.path.insert(0, str(args.source_root / "src"))
    import cv2
    import numpy as np
    from powerglove_vision.kiyo_camera import configure_kiyo
    if not configure_kiyo(args.device):
        raise SystemExit("refusing exposure test: camera is not the enrolled Kiyo Pro")
    stopped = False
    def request_stop(_signum, _frame):
        """Ask the active finite soak cycle to stop cleanly."""
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    factory = raw_camera_class(args.source_root)
    report = {"format": "virtualglove-camera-exposure-soak/1",
              "mode": args.mode, "exposure": args.exposure,
              "gain": args.gain, "cycles": [], "stores_images": False}
    try:
        for index in range(args.cycles):
            negotiate_camera(args.device, cv2)
            cycle = run_cycle(factory, args.device, args.seconds, args.mode,
                              args.exposure, args.gain, cv2, np, lambda: stopped)
            cycle["cycle"] = index + 1
            report["cycles"].append(cycle)
            if stopped or cycle.get("error") or not cycle["restored_automatic"]:
                break
            time.sleep(.5)
    finally:
        report["complete"] = (not stopped and len(report["cycles"]) == args.cycles and
                              all(not item.get("error") and item["restored_automatic"]
                                  for item in report["cycles"]))
        print(json.dumps(report, allow_nan=False), flush=True)
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
