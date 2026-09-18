#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-staggered-trackers.py
# Purpose: Compare one proven MediaPipe graph with two staggered graphs without controller output.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-07 - Added matched four-thread baseline and two-by-two staggered comparison.
#   2026-09-07 - Added isolated dual-graph newest-sequence measurements.
# Full history: docs/CHANGELOG.md and Git history.

"""Measure newest-sequence arbitration for staggered MediaPipe Hands trackers."""

import argparse
import json
import math
import queue
import threading
import time
from pathlib import Path


def percentile(values, fraction):
    """Return one nearest-rank percentile from a numeric sequence."""
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(len(values) * fraction) - 1)] if values else None


def frame_schedule(clip, fallback_fps):
    """Use captured monotonic offsets when the guided sidecar is available."""
    sidecar = clip.with_suffix(clip.suffix + ".json")
    if not sidecar.is_file():
        return None
    raw = json.loads(sidecar.read_text()).get("frame_times_seconds")
    if not isinstance(raw, list) or not raw:
        raise ValueError("guided benchmark sidecar has no frame timestamps")
    values = [float(value) for value in raw]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("guided benchmark frame timestamps must be finite and non-negative")
    if any(second <= first for first, second in zip(values, values[1:])):
        raise ValueError("guided benchmark frame timestamps must increase")
    origin = values[0]
    return [value - origin for value in values]


class Worker:
    """Own one independent MediaPipe tracker with no pending-frame queue."""

    def __init__(self, tracker_class, results, threads, tracking_confidence):
        self.tracker = tracker_class(
            inference_threads=threads,
            tracking_confidence=tracking_confidence,
        )
        self.tracker.preview_enabled = self.tracker.diagnostics_enabled = False
        self.results = results
        self.jobs = queue.Queue(maxsize=1)
        self.lock = threading.Lock()
        self.busy = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def submit(self, job):
        """Accept one frame only when this graph is idle."""
        with self.lock:
            if self.busy:
                return False
            self.busy = True
        self.jobs.put_nowait(job)
        return True

    def run(self):
        """Process submitted frames until the explicit sentinel arrives."""
        while True:
            job = self.jobs.get()
            if job is None:
                return
            sequence, captured_at, frame, submitted_at = job
            try:
                result = self.tracker.process(frame, captured_at)
                observation = result.observation
                self.results.put((
                    time.monotonic(), sequence, captured_at, submitted_at,
                    observation.detected,
                    observation.palm_x if observation.detected else None,
                    observation.palm_y if observation.detected else None,
                ))
            finally:
                with self.lock:
                    self.busy = False

    def close(self):
        """Finish in-flight work and release this graph."""
        self.jobs.put(None)
        self.thread.join()
        self.tracker.close()


def _summarize(rows, started, submitted, busy_drops, worker_count, threads):
    """Arbitrate completed results and summarize only newest ordered samples."""
    rows.sort()
    newest = 0
    accepted = []
    stale = 0
    for row in rows:
        if row[1] <= newest:
            stale += 1
            continue
        newest = row[1]
        accepted.append(row)

    source_age = [(row[0] - row[2]) * 1000 for row in accepted]
    work = [(row[0] - row[3]) * 1000 for row in accepted]
    intervals = [(second[0] - first[0]) * 1000
                 for first, second in zip(accepted, accepted[1:])]
    coordinate_steps = []
    losses = recoveries = 0
    previous_detected = None
    previous_point = None
    for row in accepted:
        detected, x, y = row[4], row[5], row[6]
        if previous_detected is True and not detected:
            losses += 1
        if previous_detected is False and detected:
            recoveries += 1
        if detected and previous_detected and previous_point is not None:
            coordinate_steps.append(math.hypot(x - previous_point[0], y - previous_point[1]))
        previous_point = (x, y) if detected else None
        previous_detected = detected
    elapsed = max(.001, rows[-1][0] - started) if rows else .001
    return {
        "workers": worker_count,
        "threads_per_worker": threads,
        "submitted": submitted,
        "busy_drops": busy_drops,
        "completed": len(rows),
        "accepted": len(accepted),
        "stale_results": stale,
        "accepted_hz": len(accepted) / elapsed,
        "detection_percent": (
            sum(row[4] for row in accepted) / len(accepted) * 100
            if accepted else 0
        ),
        "tracking_losses": losses,
        "tracking_recoveries": recoveries,
        "source_age_ms": {
            "p50": percentile(source_age, .50),
            "p95": percentile(source_age, .95),
        },
        "inference_work_ms": {
            "p50": percentile(work, .50),
            "p95": percentile(work, .95),
        },
        "accepted_interval_ms": {
            "p50": percentile(intervals, .50),
            "p95": percentile(intervals, .95),
        },
        "coordinate_step": {
            "p50": percentile(coordinate_steps, .50),
            "p95": percentile(coordinate_steps, .95),
            "max": max(coordinate_steps) if coordinate_steps else None,
        },
    }


def run_lane(clip, tracker_class, worker_count, threads, tracking_confidence):
    """Pace a clip through one lane while retaining no queued old frame."""
    import cv2

    capture = cv2.VideoCapture(str(clip))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    schedule = frame_schedule(clip, fps)
    results = queue.Queue()
    workers = [
        Worker(tracker_class, results, threads, tracking_confidence)
        for _ in range(worker_count)
    ]
    submitted = busy_drops = frame_index = next_worker = 0
    started = time.monotonic()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if schedule is not None and frame_index >= len(schedule):
                raise ValueError("guided benchmark has fewer timestamps than video frames")
            offset = schedule[frame_index] if schedule is not None else frame_index / fps
            captured_at = started + offset
            delay = captured_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            submitted_at = time.monotonic()
            accepted = False
            for offset in range(worker_count):
                index = (next_worker + offset) % worker_count
                if workers[index].submit(
                        (frame_index + 1, captured_at, frame, submitted_at)):
                    next_worker = (index + 1) % worker_count
                    accepted = True
                    submitted += 1
                    break
            if not accepted:
                busy_drops += 1
            frame_index += 1
    finally:
        capture.release()
        for worker in workers:
            worker.close()
    if schedule is not None and frame_index != len(schedule):
        raise ValueError("guided benchmark frame and timestamp counts differ")
    rows = []
    while not results.empty():
        rows.append(results.get())
    lane = _summarize(
        rows, started, submitted, busy_drops, worker_count, threads
    )
    lane["clip_frames"] = frame_index
    lane["capture_timestamps_used"] = schedule is not None
    return lane


def evaluate(baseline, candidate):
    """Apply performance gates without claiming unmeasured gesture equivalence."""
    baseline_p95 = baseline["source_age_ms"]["p95"]
    candidate_p95 = candidate["source_age_ms"]["p95"]
    gates = {
        "source_age_p95_improves_20_percent": bool(
            baseline_p95 and candidate_p95 <= baseline_p95 * .80
        ),
        "accepted_rate_improves": (
            candidate["accepted_hz"] > baseline["accepted_hz"]
        ),
        "detection_within_one_point": (
            candidate["detection_percent"] >= baseline["detection_percent"] - 1
        ),
        "coordinate_p95_not_larger": (
            candidate["coordinate_step"]["p95"]
            <= baseline["coordinate_step"]["p95"]
        ),
    }
    return {
        "measured_gates": gates,
        "passes_measured_gates": all(gates.values()),
        "eligible_for_live_output_paused_test": all(gates.values()),
        "still_required": [
            "gesture equivalence on labeled cues",
            "ten-minute thermal stability",
            "live newest-sequence ordering",
            "neutral jitter and false-gesture comparison",
        ],
    }


def main():
    """Write a matched baseline/candidate report without enabling output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", type=Path)
    parser.add_argument("--source-root", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tracking-confidence", type=float, default=.45)
    args = parser.parse_args()
    if not args.clip.is_file():
        parser.error("The clip must already exist locally")
    if args.output.exists():
        parser.error("The output path must not already exist")
    import sys
    sys.path.insert(0, str(args.source_root / "src"))
    from virtualglove.tracker import MediaPipeTracker

    baseline = run_lane(args.clip, MediaPipeTracker, 1, 4,
                        args.tracking_confidence)
    candidate = run_lane(args.clip, MediaPipeTracker, 2, 2,
                         args.tracking_confidence)
    report = {
        "version": 2,
        "controller_output": False,
        "newest_sequence_arbitration": True,
        "no_frame_queue": True,
        "tracking_confidence": args.tracking_confidence,
        "baseline": baseline,
        "candidate": candidate,
        "selection": evaluate(baseline, candidate),
    }
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({
        "output": str(args.output),
        "baseline_hz": baseline["accepted_hz"],
        "candidate_hz": candidate["accepted_hz"],
        "passes_measured_gates": report["selection"]["passes_measured_gates"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
