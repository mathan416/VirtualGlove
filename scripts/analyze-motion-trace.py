#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/analyze-motion-trace.py
# Purpose: Analyse finite per-frame native-motion traces without replaying input.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Added trace freshness, error, class, and settling analysis.
# Full history: docs/CHANGELOG.md and Git history.

"""Analyse per-frame motion trace coordinates without replaying controller input."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics


SMALL_DELTA = 0.010
MEDIUM_DELTA = 0.040
SETTLE_FRACTION = 0.05


def percentile(values, fraction):
    """Return the bounded percentile used by trace reports."""
    values = sorted(values)
    if not values:
        return None
    return values[min(len(values) - 1, int((len(values) - 1) * fraction))]


def summary(values):
    """Summarize finite numeric values for a stable JSON report."""
    values = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return {"samples": len(values),
            "median": round(statistics.median(values), 4) if values else None,
            "p95": round(percentile(values, .95), 4) if values else None,
            "max": round(max(values), 4) if values else None}


def classify(delta):
    """Classify one normalized coordinate delta by movement size."""
    if delta < SMALL_DELTA:
        return "small"
    if delta < MEDIUM_DELTA:
        return "medium"
    return "large"


def analyze(path):
    """Analyse one saved motion trace without modifying or replaying it."""
    report = json.loads(Path(path).read_text())
    events = [e for e in report.get("events", []) if e.get("event") == "vision"]

    def selected_xy(event):
        """Return the live or historical selected coordinate for one event."""
        motion = event.get("motion") or {}
        return motion.get("selected_xy") or event.get("observed_xy")

    valid = [e for e in events if e.get("observation_detected", e.get("detected"))
             and selected_xy(e) and e.get("filtered_xy")]
    changes = []
    for index, (previous, current) in enumerate(zip(valid, valid[1:]), 1):
        old = selected_xy(previous)
        new = selected_xy(current)
        delta = math.hypot(new[0] - old[0], new[1] - old[1])
        if delta == 0:
            continue
        target = new
        settled = None
        for later in valid[index:]:
            selected = selected_xy(later)
            filtered = later["filtered_xy"]
            if math.hypot(selected[0] - target[0], selected[1] - target[1]) > delta * .25:
                break
            if math.hypot(filtered[0] - target[0], filtered[1] - target[1]) <= delta * SETTLE_FRACTION:
                settled = (later["capture_ns"] - current["capture_ns"]) / 1e6
                break
        changes.append({"class": classify(delta), "delta": delta, "settled_ms": settled})

    error_x = [abs(selected_xy(e)[0] - e["filtered_xy"][0]) for e in valid]
    error_y = [abs(selected_xy(e)[1] - e["filtered_xy"][1]) for e in valid]
    source_ages = []
    for e in events:
        motion = e.get("motion") or {}
        source = motion.get("recognized_capture_ns")
        if source is not None:
            source_ages.append(max(0.0, (e["capture_ns"] - source) / 1e6))
    fallback = Counter((e.get("motion") or {}).get("fallback_reason") for e in events)
    losses = sum(bool(a.get("detected")) and not bool(b.get("detected"))
                 for a, b in zip(events, events[1:]))
    observation_losses = sum(
        bool(a.get("observation_detected", a.get("detected")))
        and not bool(b.get("observation_detected", b.get("detected")))
        for a, b in zip(events, events[1:])
    )
    recovery_holds = sum(
        bool(event.get("observation_detected"))
        and bool(event.get("latest_confirmation_pending"))
        for event in events
    )
    classes = {}
    for name in ("small", "medium", "large"):
        rows = [r for r in changes if r["class"] == name]
        classes[name] = {"changes": len(rows),
                         "delta": summary([r["delta"] for r in rows]),
                         "settling_ms": summary([r["settled_ms"] for r in rows])}
    return {"path": str(path), "trace_dropped": report.get("dropped", 0),
            "vision_events": len(events), "valid_events": len(valid),
            "valid_percent": round(100 * len(valid) / len(events), 2) if events else None,
            "tracking_losses": losses, "observation_losses": observation_losses,
            "latest_recovery_holds": recovery_holds,
            "fallback_reasons": dict(fallback),
            "recognition_source_age_ms": summary(source_ages),
            "selected_filtered_error_x": summary(error_x),
            "selected_filtered_error_y": summary(error_y),
            "movement_classes": classes,
            "thresholds": {"small_below": SMALL_DELTA, "medium_below": MEDIUM_DELTA,
                           "settle_fraction": SETTLE_FRACTION},
            "limitations": [
                "Coordinate traces contain software samples, not camera images or display frames.",
                "Movement classes are normalized-coordinate thresholds, not physical distances.",
                "Settling requires the selected target to remain near its new value; interrupted moves are excluded.",
                "Recognition age uses worker monotonic timestamps and must not be compared with phone clocks."]}


def main():
    """Parse arguments and print or create one trace report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.trace)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(text)
    else:
        print(text, end="")
    for name, values in result["movement_classes"].items():
        print("%s: %d changes, settling p95=%s ms" %
              (name, values["changes"], values["settling_ms"]["p95"]))


if __name__ == "__main__":
    main()
