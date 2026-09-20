#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-frame-preprocessing.py
# Purpose: Compare output-paused frame-preparation candidates without changing tracker semantics.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Documented isolated preparation closures for source checks.
#   2026-09-08 - Added fused and greyscale controls with streaming, frame-free reports.
#   2026-09-07 - Added an output-paused mirror and buffer-reuse benchmark.
# Full history: docs/CHANGELOG.md and Git history.

"""Compare frame preparation candidates on a local camera clip.

The benchmark never runs MediaPipe, never enables controller output, and retains
only aggregate timings. The fused NumPy lane is eligible for later live testing
only when it exactly matches the current mirrored RGB pixels. Greyscale and
no-mirror lanes are deliberately non-equivalent controls, not candidates.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float | None:
    """Return one nearest-rank percentile from a numeric sequence."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def summary(values: list[float]) -> dict:
    """Summarize preprocessing duration without retaining frame content."""
    return {
        "count": len(values),
        "p50_ms": round(statistics.median(values), 4) if values else None,
        "p95_ms": round(percentile(values, .95), 4) if values else None,
    }


def _timed(callable_):
    """Return a callable's result and elapsed wall time in milliseconds."""
    started = time.perf_counter_ns()
    result = callable_()
    return result, (time.perf_counter_ns() - started) / 1e6


def _gain(baseline: dict, candidate: dict) -> float:
    """Return p95 improvement relative to the current implementation."""
    if not baseline["p95_ms"]:
        return 0.0
    return 100 * (baseline["p95_ms"] - candidate["p95_ms"]) / baseline["p95_ms"]


def fused_mirror_channel_swap(frame, numpy):
    """Mirror X and reverse BGR channels in one contiguous array copy."""
    return numpy.ascontiguousarray(frame[:, ::-1, ::-1])


def build_report(lanes: dict, frames: int, equivalence: dict) -> dict:
    """Build a privacy-safe aggregate report from per-frame durations."""
    summaries = {name: summary(values) for name, values in lanes.items()}
    current = summaries["current_flip_and_convert"]
    reused = summaries["reused_flip_and_convert"]
    fused = summaries["fused_numpy_mirror_channel_swap"]
    reused_gain = _gain(current, reused)
    fused_gain = _gain(current, fused)
    reused_eligible = equivalence["reused"] and reused_gain > 0
    fused_eligible = equivalence["fused"] and fused_gain > 0
    return {
        "format": "powerglove-frame-preprocessing-benchmark-v2",
        "frames": frames,
        "controller_output": False,
        "mediapipe_inference_run": False,
        "frame_content_retained": False,
        "lanes": summaries,
        # Retain version-1 names for simple comparison with earlier reports.
        "current_flip_and_convert": current,
        "reused_flip_and_convert": reused,
        "reused_output_bit_exact": equivalence["reused"],
        "reused_p95_improvement_percent": round(reused_gain, 2),
        "reused_promotion_eligible": reused_eligible,
        "fused_output_bit_exact": equivalence["fused"],
        "fused_p95_improvement_percent": round(fused_gain, 2),
        "fused_promotion_eligible": fused_eligible,
        "no_mirror_cost_ceiling": summaries["no_mirror_convert_only"],
        "promotion_eligible": reused_eligible or fused_eligible,
        "no_mirror_promotion_eligible": False,
        "grayscale_promotion_eligible": False,
        "limitations": [
            "This isolates preparation cost; MediaPipe inference is not run or estimated.",
            "VideoCapture has already decoded each source frame to BGR before these lanes run.",
            "The greyscale transform control measures BGR-to-grey-to-RGB work, not camera MJPEG greyscale decoding.",
            "Synthetic JPEG controls re-encode each decoded frame outside the timed lanes and do not reproduce the camera's original MJPEG bytes.",
            "Greyscale and no-mirror outputs are not recognition-equivalent and cannot be promoted from this report.",
            "Any bit-exact faster candidate still requires repeated live latency, continuity, gesture, and thermal validation.",
        ],
    }


def run(path: Path, maximum: int, jpeg_controls: bool = True) -> dict:
    """Stream at most ``maximum`` frames and retain aggregate durations only."""
    import cv2
    import numpy as np

    lane_names = (
        "current_flip_and_convert",
        "reused_flip_and_convert",
        "fused_numpy_mirror_channel_swap",
        "no_mirror_convert_only",
        "grayscale_transform_expand_control",
    )
    lanes = {name: [] for name in lane_names}
    if jpeg_controls:
        lanes.update({
            "synthetic_jpeg_color_decode_prepare": [],
            "synthetic_jpeg_grayscale_decode_expand": [],
        })
    equivalent = {"reused": True, "fused": True}
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"could not open clip: {path}")
    frames = 0
    mirror_buffer = rgb_buffer = None
    try:
        while frames < maximum:
            ok, frame = capture.read()
            if not ok:
                break
            if mirror_buffer is None:
                mirror_buffer = np.empty_like(frame)
                rgb_buffer = np.empty_like(frame)

            expected, elapsed = _timed(
                lambda: cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            )
            lanes["current_flip_and_convert"].append(elapsed)

            def reused_prepare():
                """Reuse caller-owned mirror and colour-conversion buffers."""
                cv2.flip(frame, 1, dst=mirror_buffer)
                cv2.cvtColor(mirror_buffer, cv2.COLOR_BGR2RGB, dst=rgb_buffer)
                return rgb_buffer

            reused, elapsed = _timed(reused_prepare)
            lanes["reused_flip_and_convert"].append(elapsed)
            equivalent["reused"] = equivalent["reused"] and bool(
                np.array_equal(expected, reused)
            )

            fused, elapsed = _timed(
                lambda: fused_mirror_channel_swap(frame, np)
            )
            lanes["fused_numpy_mirror_channel_swap"].append(elapsed)
            equivalent["fused"] = equivalent["fused"] and bool(
                np.array_equal(expected, fused)
            )

            _unused, elapsed = _timed(
                lambda: cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            )
            lanes["no_mirror_convert_only"].append(elapsed)

            def grayscale_prepare():
                """Build the greyscale comparison lane and expand it to RGB."""
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.flip(gray, 1)
                return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

            grayscale, elapsed = _timed(grayscale_prepare)
            lanes["grayscale_transform_expand_control"].append(elapsed)

            if jpeg_controls:
                encoded_ok, encoded = cv2.imencode(".jpg", frame)
                if not encoded_ok:
                    raise RuntimeError("could not create synthetic JPEG control")

                def color_decode_prepare():
                    """Decode the synthetic colour JPEG and prepare MediaPipe RGB."""
                    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                    if decoded is None:
                        raise RuntimeError("synthetic color JPEG decode failed")
                    return cv2.cvtColor(cv2.flip(decoded, 1), cv2.COLOR_BGR2RGB)

                _color, elapsed = _timed(color_decode_prepare)
                lanes["synthetic_jpeg_color_decode_prepare"].append(elapsed)

                def grayscale_decode_expand():
                    """Decode the greyscale JPEG control and expand it to RGB."""
                    gray = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
                    if gray is None:
                        raise RuntimeError("synthetic greyscale JPEG decode failed")
                    return cv2.cvtColor(cv2.flip(gray, 1), cv2.COLOR_GRAY2RGB)

                _gray, elapsed = _timed(grayscale_decode_expand)
                lanes["synthetic_jpeg_grayscale_decode_expand"].append(elapsed)

            # Drop all pixel arrays before requesting another source frame.
            del expected, reused, fused, grayscale, _unused
            if jpeg_controls:
                del encoded, _color, _gray
            frames += 1
    finally:
        capture.release()
    if not frames:
        raise RuntimeError("clip contains no readable frames")
    report = build_report(lanes, frames, equivalent)
    report["source"] = str(path)
    return report


def main() -> int:
    """Read one local clip and optionally create an aggregate report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("clip", type=Path)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--no-jpeg-controls", action="store_true",
        help="skip synthetic JPEG colour/greyscale decode controls",
    )
    args = parser.parse_args()
    report = run(args.clip, max(1, args.frames), not args.no_jpeg_controls)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
