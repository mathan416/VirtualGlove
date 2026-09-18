#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-native-motion-curve.py
# Purpose: Compare bounded native X/Y response curves from one vision replay.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-07 - Accept bounded stops that settle within the calibrated noise floor.
#   2026-09-07 - Added four-lane speed-curve comparison and candidate sweep.
# Full history: docs/CHANGELOG.md and Git history.

"""Compare native movement filters without replaying input to a game or mouse."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virtualglove.gesture import (  # noqa: E402
    GestureConfig, GestureEngine, _camera_coordinate, _field_coordinate,
    load_calibration,
)
from virtualglove.model import Calibration, HandObservation  # noqa: E402


def percentile(values, fraction):
    """Return a bounded percentile for finite values."""
    ordered = sorted(float(value) for value in values if value is not None and math.isfinite(value))
    if not ordered:
        return None
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def calibration_from(samples, cues):
    """Derive the same neutral center, scale, and p95 jitter used by gameplay."""
    neutral = next((cue for cue in cues if cue["label"] == "neutral_near"), None)
    rows = [row for row in samples if row.get("detected", True)
            and neutral
            and all(math.isfinite(row.get(name, float("nan")))
                    for name in ("x", "y", "scale"))
            and neutral["start"] <= row["elapsed"] < neutral["end"]]
    if len(rows) < 3:
        raise ValueError("The replay needs at least three detected neutral_near observations")
    x = statistics.mean(row["x"] for row in rows)
    y = statistics.mean(row["y"] for row in rows)
    scale = max(.01, statistics.mean(row["scale"] for row in rows))
    noise_x = percentile([abs(row["x"] - x) / scale for row in rows], .95)
    noise_y = percentile([abs(row["y"] - y) / scale for row in rows], .95)
    return Calibration(x, y, scale, 0.0, noise_x=noise_x, noise_y=noise_y)


def old_curve(samples, minimum, boost, cap):
    """Reproduce the prior error-driven native curve, including optional overshoot."""
    output = []
    previous = None
    previous_time = None
    for row in samples:
        if not row.get("detected", True):
            output.append(None)
            previous = previous_time = None
            continue
        values = (row["x"], row["y"])
        if previous is None:
            filtered = values
        else:
            dt = max(0.0, row["elapsed"] - previous_time)
            filtered_values = []
            for old, value in zip(previous, values):
                alpha = min(cap, max(minimum, minimum + abs(value - old) * boost))
                if alpha <= 1.0:
                    alpha = 1 - (1 - alpha) ** (min(dt, .25) / .09)
                filtered_values.append(old + alpha * (value - old))
            filtered = tuple(filtered_values)
        output.append(filtered)
        previous = filtered
        previous_time = row["elapsed"]
    return output


def speed_curve(samples, calibration, config):
    """Exercise the actual bounded speed-sensitive gameplay engine."""
    engine = GestureEngine("super_glove_ball", config=config, calibration=calibration)
    output = []
    for row in samples:
        x = .5 if row.get("x") is None else row["x"]
        y = .5 if row.get("y") is None else row["y"]
        scale = 0.0 if row.get("scale") is None else row["scale"]
        observation = HandObservation(
            row["elapsed"], row.get("detected", True), row.get("confidence", .95),
            x, y, scale,
        )
        state = engine.update_native_motion(
            observation, observation if observation.detected else None
        )
        output.append((engine._filtered_palm_x, engine._filtered_palm_y)
                      if state.detected else None)
    return output


def clamped_samples(samples, calibration, config):
    """Apply the same calibrated reach rectangle used before both live modes."""
    rows = []
    for source in samples:
        row = dict(source)
        if (row.get("detected", True) and row.get("x") is not None
                and row.get("y") is not None):
            for axis, negative, positive in (
                ("x", calibration.reach_left, calibration.reach_right),
                ("y", calibration.reach_up, calibration.reach_down),
            ):
                center = calibration.palm_x if axis == "x" else calibration.palm_y
                field = _field_coordinate(
                    row[axis], center, config.coordinate_edge_margin, negative, positive
                )
                row[axis] = _camera_coordinate(
                    field, center, config.coordinate_edge_margin, negative, positive
                )
        rows.append(row)
    return rows


def cue_for(elapsed, cues):
    """Return the label covering one replay timestamp."""
    return next((cue["label"] for cue in cues
                 if cue["start"] <= elapsed < cue["end"]), None)


def metrics(samples, outputs, cues, calibration, config,
            continuity=None, source_age=None):
    """Summarize jitter, tracking, lag, stops, reversals, and overshoot."""
    tagged = [(row, point, cue_for(row["elapsed"], cues))
              for row, point in zip(samples, outputs)
              if row.get("detected", True) and point is not None]
    neutral = [point for _row, point, cue in tagged if cue and cue.startswith("neutral")]
    jitter = {
        "x": max((p[0] for p in neutral), default=0) - min((p[0] for p in neutral), default=0),
        "y": max((p[1] for p in neutral), default=0) - min((p[1] for p in neutral), default=0),
    }
    error = [math.hypot(row["x"] - point[0], row["y"] - point[1])
             for row, point, _cue in tagged]
    overshoot = 0
    reversals = 0
    reversal_misses = 0
    large_changes = 0
    large_first_sample_misses = 0
    medium_settling = []
    stop_events = 0
    stop_misses = 0
    previous_direction = (0.0, 0.0)
    tracking_recoveries = 0
    recovery_misses = 0
    stale_recoveries = 0
    stale_recovery_misses = 0
    for index in range(1, len(samples)):
        stale_gap = samples[index]["elapsed"] - samples[index - 1]["elapsed"] > .25
        current_valid = samples[index].get("detected", True) and outputs[index] is not None
        previous_valid = (samples[index - 1].get("detected", True)
                          and outputs[index - 1] is not None)
        if not current_valid:
            previous_direction = (0.0, 0.0)
            continue
        if not previous_valid:
            tracking_recoveries += 1
            if math.hypot(outputs[index][0] - samples[index]["x"],
                          outputs[index][1] - samples[index]["y"]) > 1e-9:
                recovery_misses += 1
            previous_direction = (0.0, 0.0)
            continue
        if stale_gap:
            # Gameplay discards bounded-curve history after the receiver's
            # release interval, so the first new sample is a recovery rather
            # than a motion reversal or stop.
            stale_recoveries += 1
            if math.hypot(outputs[index][0] - samples[index]["x"],
                          outputs[index][1] - samples[index]["y"]) > 1e-9:
                stale_recovery_misses += 1
            previous_direction = (0.0, 0.0)
            continue
        delta_x = samples[index]["x"] - samples[index - 1]["x"]
        delta_y = samples[index]["y"] - samples[index - 1]["y"]
        raw_distance = math.hypot(delta_x, delta_y)
        scale_noise_x = 0.0 if calibration.noise_x >= 1.0 else calibration.noise_x
        scale_noise_y = 0.0 if calibration.noise_y >= 1.0 else calibration.noise_y
        noise_x = max(config.motion_noise_floor,
                      scale_noise_x * calibration.palm_scale * config.motion_noise_multiplier)
        noise_y = max(config.motion_noise_floor,
                      scale_noise_y * calibration.palm_scale * config.motion_noise_multiplier)
        delta_noise = math.hypot(delta_x / noise_x, delta_y / noise_y)
        reach_x = (calibration.reach_right if delta_x >= 0 else calibration.reach_left) or (
            1.0 - config.coordinate_edge_margin - calibration.palm_x
            if delta_x >= 0 else calibration.palm_x - config.coordinate_edge_margin
        )
        reach_y = (calibration.reach_down if delta_y >= 0 else calibration.reach_up) or (
            1.0 - config.coordinate_edge_margin - calibration.palm_y
            if delta_y >= 0 else calibration.palm_y - config.coordinate_edge_margin
        )
        direction = (delta_x / max(.05, reach_x), delta_y / max(.05, reach_y))
        direction_length = math.hypot(*direction)
        previous_length = math.hypot(*previous_direction)
        stopped = delta_noise <= 1.0
        reversal = (not stopped and direction_length > 0 and previous_length > 0
                    and direction[0] * previous_direction[0]
                    + direction[1] * previous_direction[1] < 0)
        dt = max(1 / 240, samples[index]["elapsed"] - samples[index - 1]["elapsed"])
        speed = direction_length / dt
        if stopped and previous_length > 0:
            stop_events += 1
            output_noise = math.hypot(
                (outputs[index][0] - samples[index]["x"]) / noise_x,
                (outputs[index][1] - samples[index]["y"]) / noise_y,
            )
            if output_noise > 1.000001:
                stop_misses += 1
        if not stopped and speed >= config.motion_full_speed:
            large_changes += 1
            if math.hypot(outputs[index][0] - samples[index]["x"],
                          outputs[index][1] - samples[index]["y"]) > 1e-9:
                large_first_sample_misses += 1
        elif raw_distance >= .01:
            target = (samples[index]["x"], samples[index]["y"])
            settled = None
            for later in range(index, len(samples)):
                if (not samples[later].get("detected", True)
                        or outputs[later] is None
                        or samples[later].get("x") is None
                        or samples[later].get("y") is None):
                    break
                selected = (samples[later]["x"], samples[later]["y"])
                if math.hypot(selected[0] - target[0], selected[1] - target[1]) > raw_distance * .25:
                    break
                if math.hypot(outputs[later][0] - target[0],
                              outputs[later][1] - target[1]) <= raw_distance * .10:
                    settled = (samples[later]["elapsed"] - samples[index]["elapsed"]) * 1000
                    break
            if settled is not None:
                medium_settling.append(settled)
        if reversal:
            reversals += 1
            if math.hypot(outputs[index][0] - samples[index]["x"],
                          outputs[index][1] - samples[index]["y"]) > 1e-9:
                reversal_misses += 1
        for axis in (0, 1):
            raw = samples[index]["x" if axis == 0 else "y"]
            low, high = sorted((outputs[index - 1][axis], raw))
            if outputs[index][axis] < low - 1e-12 or outputs[index][axis] > high + 1e-12:
                overshoot += 1
        previous_direction = (0.0, 0.0) if stopped else direction
    spans = {}
    for label in ("slow_xy", "fast_xy"):
        rows = [(row, point) for row, point, cue in tagged if cue == label]
        raw_span = max((row["x"] for row, _point in rows), default=0) - min(
            (row["x"] for row, _point in rows), default=0)
        output_span = max((point[0] for _row, point in rows), default=0) - min(
            (point[0] for _row, point in rows), default=0)
        spans[label] = {"raw_x": raw_span, "output_x": output_span,
                        "retained_fraction": output_span / raw_span if raw_span else None}
    return {
        "neutral_jitter_span": jitter,
        "selected_filtered_error": {"median": percentile(error, .5), "p95": percentile(error, .95)},
        "overshoot_count": overshoot,
        "reversals": reversals,
        "reversal_misses": reversal_misses,
        "large_changes": large_changes,
        "large_first_sample_misses": large_first_sample_misses,
        "stop_events": stop_events,
        "stop_misses": stop_misses,
        "tracking_recoveries": tracking_recoveries,
        "recovery_misses": recovery_misses,
        "stale_recoveries": stale_recoveries,
        "stale_recovery_misses": stale_recovery_misses,
        "medium_time_to_90_percent_ms": {
            "samples": len(medium_settling),
            "median": percentile(medium_settling, .5),
            "p95": percentile(medium_settling, .95),
        },
        "movement_span": spans,
        "detection_continuity_percent": continuity,
        "recognition_source_age_ms": source_age,
    }


def compare(document, lane_index=0, calibration=None):
    """Create four reference lanes and a deterministic bounded-curve sweep."""
    lanes = document.get("lanes", [])
    if not lanes or not 0 <= lane_index < len(lanes):
        raise ValueError("Replay report does not contain the requested lane")
    lane = lanes[lane_index]
    samples = lane.get("motion_samples") or lane.get("observation_samples", [])
    cues = document.get("cues", [])
    if not samples or "elapsed" not in samples[0] or not cues:
        raise ValueError("Run benchmark-vision-replay.py version 2 before this comparison")
    calibration = calibration or calibration_from(samples, cues)
    samples = clamped_samples(samples, calibration, GestureConfig())
    continuity = lane.get("detection_continuity_percent")
    source_age = lane.get("recognition_source_age_ms")
    configs = {
        "deployed_overshoot_reference": old_curve(samples, .70, 15.0, 1.30),
        "error_curve_capped": old_curve(samples, .70, 15.0, 1.00),
        "speed_curve": speed_curve(samples, calibration, GestureConfig()),
        "latest_coordinate": [((row["x"], row["y"])
                               if row.get("detected", True) else None) for row in samples],
    }
    default_config = GestureConfig()
    result_lanes = {name: metrics(samples, values, cues, calibration, default_config,
                                  continuity, source_age)
                    for name, values in configs.items()}
    candidates = []
    capped_jitter = result_lanes["error_curve_capped"]["neutral_jitter_span"]
    for noise in (1.0, 1.25, 1.5):
        for slow in (.55, .70, .85):
            for full in (1.0, 1.5, 2.0):
                config = replace(GestureConfig(), motion_noise_multiplier=noise,
                                 motion_slow_follow=slow, motion_full_speed=full)
                values = metrics(samples, speed_curve(samples, calibration, config), cues,
                                 calibration, config, continuity, source_age)
                slow_fraction = values["movement_span"]["slow_xy"]["retained_fraction"]
                medium_p95 = values["medium_time_to_90_percent_ms"]["p95"]
                accepted = (
                    values["overshoot_count"] == 0
                    and values["reversal_misses"] == 0
                    and values["stop_events"] > 0 and values["stop_misses"] == 0
                    and values["recovery_misses"] == 0
                    and values["stale_recovery_misses"] == 0
                    and values["large_first_sample_misses"] == 0
                    and medium_p95 is not None and medium_p95 <= 150
                    and values["neutral_jitter_span"]["x"] <= capped_jitter["x"] + 1e-12
                    and values["neutral_jitter_span"]["y"] <= capped_jitter["y"] + 1e-12
                    and (slow_fraction is None or slow_fraction >= .80)
                )
                candidates.append({"noise_multiplier": noise, "slow_follow": slow,
                                   "full_speed": full, "accepted": accepted, "metrics": values})
    accepted = [row for row in candidates if row["accepted"]]
    accepted.sort(key=lambda row: (
        row["metrics"]["neutral_jitter_span"]["x"]
        + row["metrics"]["neutral_jitter_span"]["y"],
        row["metrics"]["selected_filtered_error"]["p95"],
        -row["slow_follow"], row["full_speed"], row["noise_multiplier"],
    ))
    return {
        "version": 1,
        "source_replay": document.get("clip"),
        "source_lane": lane_index,
        "calibration": {"palm_x": calibration.palm_x, "palm_y": calibration.palm_y,
                        "palm_scale": calibration.palm_scale,
                        "noise_x": calibration.noise_x, "noise_y": calibration.noise_y},
        "lanes": result_lanes,
        "candidate_sweep": candidates,
        "selected_candidate": accepted[0] if accepted else None,
        "selection_note": ("Physical camera-to-display latency still requires synchronized live video. "
                           "A null selection keeps the capped existing curve."),
    }


def main():
    """Read one replay report and create the four-lane curve comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    parser.add_argument("--lane", type=int, default=0)
    parser.add_argument("--calibration", type=Path,
                        help="Active versioned calibration containing center, reach, and jitter")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    calibration = load_calibration(args.calibration) if args.calibration else None
    if args.calibration and calibration is None:
        parser.error("Calibration is missing or invalid")
    report = compare(json.loads(args.replay.read_text()), args.lane, calibration)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(args.output),
                      "selected_candidate": report["selected_candidate"]}, indent=2))


if __name__ == "__main__":
    main()
