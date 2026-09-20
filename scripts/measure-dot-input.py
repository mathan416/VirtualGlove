#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/measure-dot-input.py
# Purpose: Measure read-only native-state validity and range for the dot core.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Added bounded cabinet-side dot-input measurement.
# Full history: docs/CHANGELOG.md and Git history.
"""Read-only cabinet-side observations of the installed dot core's input record."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from virtualglove.native_state import (
    DEFAULT_PATH, PROFILE_SUPER_GLOVE_BALL, decode_record, monotonic_ns,
)


def inspect(payload, now_ns):
    """Match dot validity and coordinates; never reuse a previous valid position."""
    try:
        state = decode_record(payload)
    except ValueError:
        return "invalid_record", None
    if state["profile"] != PROFILE_SUPER_GLOVE_BALL:
        return "wrong_profile", None
    if not state["detected"]:
        return "undetected", None
    if not state["calibrated"]:
        return "uncalibrated", None
    age = now_ns - state["arrived_ns"]
    if age < 0:
        return "future", None
    if not now_ns or age > 250_000_000:
        return "stale", None
    x, y = state["axes"]["x"], state["axes"]["y"]
    state["dot"] = {"x": max(16, min(239, 16 + ((x + 32767) * 223 // 65534))),
                    "y": max(24, min(207, 24 + ((y + 32767) * 183 // 65534)))}
    state["publication_age_ms"] = age / 1_000_000
    return "tracking", state


class Window:
    """Accumulate bounded native-state observations for one diagnostic window."""
    def __init__(self):
        self.counts = Counter()
        self.previous_valid = None
        self.losses = self.recoveries = self.publications = 0
        self.last_identity = None
        self.ranges = {key: None for key in ("x", "y", "dot_x", "dot_y")}
        self.max_age = None

    def observe(self, reason, state):
        """Add one classified native-state observation to this window."""
        self.counts[reason] += 1
        valid = state is not None
        self.losses += int(self.previous_valid is True and not valid)
        self.recoveries += int(self.previous_valid is False and valid)
        self.previous_valid = valid
        if not valid:
            return
        age = state["publication_age_ms"]
        self.max_age = age if self.max_age is None else max(self.max_age, age)
        identity = (state["sequence"], state["guard"], state["arrived_ns"])
        if identity == self.last_identity:
            return
        self.last_identity = identity
        self.publications += 1
        for key, value in dict(state["axes"], dot_x=state["dot"]["x"], dot_y=state["dot"]["y"]).items():
            if key in self.ranges:
                old = self.ranges[key]
                self.ranges[key] = [value, value] if old is None else [min(old[0], value), max(old[1], value)]

    def report(self):
        """Return aggregate validity, recovery, publication, and range evidence."""
        return {"polls_by_state": dict(self.counts), "observed_input_losses": self.losses,
                "observed_recoveries": self.recoveries,
                "observed_valid_publications": self.publications,
                "valid_ranges": self.ranges, "max_publication_age_ms": self.max_age}


def main():
    """Collect a bounded observation window and create a new JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--interval", type=float, default=1 / 60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600 or not .005 <= args.interval <= 1:
        parser.error("Use 1-600 seconds and 0.005-1 second interval")
    if sys.platform != "linux":
        parser.error("Run on the RetroPie cabinet: freshness uses its CLOCK_MONOTONIC")
    # Reserve the report before observing; do not overwrite prior evidence.
    with args.output.open("x") as output:
        window = Window()
        started = time.monotonic()
        deadline = started + args.seconds
        while time.monotonic() < deadline:
            before = time.monotonic()
            try:
                with args.state.open("rb") as stream:
                    payload = stream.read(65)
                reason, state = inspect(payload, monotonic_ns())
            except FileNotFoundError:
                reason, state = "missing", None
            except OSError:
                reason, state = "unreadable", None
            window.observe(reason, state)
            time.sleep(max(0, min(args.interval - (time.monotonic() - before), deadline - time.monotonic())))
        report = dict(window.report(), format=1, test="uno-q-dot",
                      elapsed_seconds=time.monotonic() - started, state_path=str(args.state),
                      boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                      limitations=["Read-only polling samples receiver publications, not RetroArch frames.",
                                   "Counts can miss short losses and overwritten publications; they are not transport loss rates.",
                                   "Coordinates predict the dot mapping, not physical screen presentation.",
                                   "Publication age excludes camera, processing and network delay.",
                                   "Do not subtract clocks from different computers."])
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps(report, indent=2))
    return 0 if window.publications else 2


if __name__ == "__main__":
    raise SystemExit(main())
