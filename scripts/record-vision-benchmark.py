#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/record-vision-benchmark.py
# Purpose: Record a short, local-only, repeatable vision benchmark clip.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Added the local gameplay-recognition benchmark recorder.
# Full history: docs/CHANGELOG.md and Git history.

"""Record the fixed 30-second camera sequence used for tracker comparisons."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from powerglove_vision.camera import camera_candidates  # noqa: E402


CUES = (
    (0, 3, "neutral_near", "Sit near the camera; relaxed open hand at center"),
    (3, 5, "slow_xy", "Slow full-field left/right sweep"),
    (5, 7, "fast_xy", "Fast full-field left/right and up/down sweep"),
    (7, 9, "short_directions", "Short left, right, up, and down movements"),
    (9, 10.5, "a", "Curl index finger for A"),
    (10.5, 12, "b", "Curl thumb for B"),
    (12, 13.5, "roll_left", "Roll wrist left"),
    (13.5, 15, "roll_right", "Roll wrist right"),
    (15, 16.5, "closed_hand", "Close hand"),
    (16.5, 18.5, "push", "Glove Zap: move hand deliberately toward camera"),
    (18.5, 20.5, "pull", "Pull Back: move hand deliberately away from camera"),
    (20.5, 23, "tracking_recovery", "Remove hand, then return it to center"),
    (23, 26, "neutral_far", "Stand farther away; relaxed open hand at center"),
    (26, 28, "a_b_far", "At the farther position, curl index then thumb"),
    (28, 30, "neutral_finish", "Relaxed open hand; remain still"),
)


def parser() -> argparse.ArgumentParser:
    """Build the fixed-duration camera recorder command-line interface."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--camera", default="auto")
    result.add_argument("--output", type=Path,
                        default=Path("/tmp/virtualglove-vision-benchmark.avi"))
    result.add_argument("--width", type=int, default=640)
    result.add_argument("--height", type=int, default=480)
    result.add_argument("--fps", type=float, default=30)
    return result


def main() -> int:
    """Record the fixed cue sequence and its local timing sidecar."""
    args = parser().parse_args()
    import cv2

    capture = None
    for device in camera_candidates(args.camera):
        candidate = cv2.VideoCapture(device, cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY)
        candidate.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        candidate.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        candidate.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        candidate.set(cv2.CAP_PROP_FPS, args.fps)
        candidate.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if candidate.isOpened():
            capture = candidate
            break
        candidate.release()
    if capture is None:
        raise RuntimeError("No selected camera could be opened")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(args.output), cv2.VideoWriter_fourcc(*"MJPG"), args.fps,
        (args.width, args.height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Could not create benchmark clip")
    sidecar = args.output.with_suffix(args.output.suffix + ".json")
    print("This clip stays local and is not training data. Recording begins in 3 seconds.", flush=True)
    for remaining in (3, 2, 1):
        print(remaining, flush=True)
        time.sleep(1)
    started = time.monotonic()
    cue_index = -1
    frames = 0
    frame_times = []
    try:
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= CUES[-1][1]:
                break
            next_index = next(index for index, cue in enumerate(CUES) if cue[0] <= elapsed < cue[1])
            if next_index != cue_index:
                cue_index = next_index
                print(f"{CUES[cue_index][2]}: {CUES[cue_index][3]}", flush=True)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("Camera stopped during benchmark recording")
            if frame.shape[1] != args.width or frame.shape[0] != args.height:
                frame = cv2.resize(frame, (args.width, args.height))
            writer.write(frame)
            frames += 1
            frame_times.append(round(time.monotonic() - started, 6))
    finally:
        writer.release()
        capture.release()
    sidecar.write_text(json.dumps({
        "version": 2, "clip": str(args.output), "local_only": True,
        "width": args.width, "height": args.height, "fps": args.fps,
        "frames": frames, "duration_seconds": CUES[-1][1],
        "effective_fps": round(frames / CUES[-1][1], 6),
        "frame_times_seconds": frame_times,
        "cues": [dict(start=start, end=end, label=label, instruction=instruction)
                 for start, end, label, instruction in CUES],
    }, indent=2) + "\n")
    print(f"Recorded {frames} frames to {args.output}")
    print(f"Cue metadata: {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
