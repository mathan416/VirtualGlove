#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-vision-replay.py
# Purpose: Compare repeatable tracker configurations using one local camera clip.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Allowed a replay-only three-thread scheduling comparison.
#   2026-09-09 - Described direction-aware search as standard outside replay comparisons.
#   2026-09-09 - Summarized native palm and landmark calculator timings.
#   2026-09-09 - Added exact directional-search candidate tuples for focused sweeps.
#   2026-09-09 - Added presence-score, native-inference, and recovery-cause summaries.
#   2026-09-09 - Compared immediate search reset with one-frame reacquisition carry.
#   2026-09-09 - Reported capture-time tracking loss and recovery timing.
#   2026-09-08 - Added fused-colour and fixed search-region comparison lanes.
#   2026-09-07 - Retained temporary palm-anchor candidates for aggregate comparison.
#   2026-09-05 - Kept aggregate means compatible with Python 3.7.
#   2026-09-05 - Added repeatable MediaPipe backend, thread, size, and preview comparisons.
# Full history: docs/CHANGELOG.md and Git history.

"""Replay one local clip through proven and experimental vision configurations."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import sys
import tempfile
import time
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virtualglove.tracker import (  # noqa: E402
    MediaPipeTracker,
    TRACKING_EVIDENCE_OUTPUTS,
)
from virtualglove.gesture import GestureEngine  # noqa: E402


def percentile(values: list[float], fraction: float) -> float | None:
    """Return a nearest-rank percentile rounded for the aggregate report."""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, ceil(len(ordered) * fraction) - 1)], 2)


def parse_roi_shift(value: str) -> tuple[float, float]:
    """Parse one bounded replay-only X,Y next-frame ROI shift."""
    try:
        parts = value.split(",")
        if len(parts) != 2:
            raise ValueError
        shift = (float(parts[0]), float(parts[1]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ROI shift must be X,Y") from exc
    if any(not math.isfinite(item) or not -.25 <= item <= .25 for item in shift):
        raise argparse.ArgumentTypeError(
            "ROI shift values must be finite and between -0.25 and 0.25"
        )
    return shift


def parse_directional_search_candidate(value: str) -> tuple[float, float, float, int]:
    """Parse one exact gain,min-speed,max-offset,recovery-frames candidate."""
    try:
        parts = value.split(",")
        if len(parts) != 4:
            raise ValueError
        gain, min_speed, max_offset = map(float, parts[:3])
        recovery_frames = int(parts[3])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "directional-search candidate must be gain,min-speed,max-offset,recovery-frames"
        ) from exc
    if (not math.isfinite(gain) or not 0.0 <= gain <= 1.0
            or not math.isfinite(min_speed) or not 0.0 <= min_speed <= 4.0
            or not math.isfinite(max_offset) or not 0.0 <= max_offset <= .15
            or recovery_frames not in (0, 1)):
        raise argparse.ArgumentTypeError(
            "directional-search candidate values are outside their safe bounds"
        )
    return gain, min_speed, max_offset, recovery_frames


def roi_shift_lane_label(shift_x: float, shift_y: float) -> str:
    """Make the production baseline unmistakable from fixed-shift research."""
    if shift_x == 0.0 and shift_y == 0.0:
        return "production-zero-shift"
    return f"replay-research-fixed-shift-x{shift_x:+.2f}-y{shift_y:+.2f}"


def tracking_path_summary(samples: list[dict]) -> dict:
    """Summarize detector cost and consecutive missing results per replay lane."""
    counts = Counter(sample["path"] for sample in samples)
    cause_counts = Counter(
        sample.get("observation_cause", "unavailable") for sample in samples
    )
    native_loss_causes = Counter(
        sample["native_loss_cause"] for sample in samples
        if sample.get("native_loss_cause")
    )
    timing = {}
    for path in sorted(counts):
        values = [sample["ms"] for sample in samples if sample["path"] == path]
        timing[path] = {
            "count": len(values),
            "p50": percentile(values, .50),
            "p95": percentile(values, .95),
        }
    missing_runs = []
    missing_run_details = []
    current_run = 0
    current_detail = None
    for index, sample in enumerate(samples, start=1):
        if not sample["detected"]:
            current_run += 1
            if current_detail is None:
                current_detail = {
                    "start_frame": sample.get("frame", index),
                    "end_frame": sample.get("frame", index),
                    "start_elapsed": sample.get("elapsed"),
                    "end_elapsed": sample.get("elapsed"),
                    "cues": [],
                    "causes": [],
                }
            current_detail["end_frame"] = sample.get("frame", index)
            current_detail["end_elapsed"] = sample.get("elapsed")
            cue = sample.get("cue")
            if cue is not None and cue not in current_detail["cues"]:
                current_detail["cues"].append(cue)
            cause = sample.get("observation_cause", "unavailable")
            if cause not in current_detail["causes"]:
                current_detail["causes"].append(cause)
            native_cause = sample.get("native_loss_cause")
            if native_cause:
                current_detail.setdefault("native_causes", [])
                if native_cause not in current_detail["native_causes"]:
                    current_detail["native_causes"].append(native_cause)
        elif current_run:
            missing_runs.append(current_run)
            current_detail["frames"] = current_run
            missing_run_details.append(current_detail)
            current_run = 0
            current_detail = None
    if current_run:
        missing_runs.append(current_run)
        current_detail["frames"] = current_run
        missing_run_details.append(current_detail)
    recovery_gaps = [sample["recovery_gap_ms"] for sample in samples
                     if sample.get("recovery_gap_ms") is not None]
    recovery_missing_spans = [sample["recovery_missing_span_ms"] for sample in samples
                              if sample.get("recovery_missing_span_ms") is not None]
    recovery_inference = [sample["recovery_inference_ms"] for sample in samples
                          if sample.get("recovery_inference_ms") is not None]
    native_palm_samples = [
        sample for sample in samples if sample.get("native_palm_inference") is True
    ]
    native_landmark_samples = [
        sample for sample in samples if sample.get("native_landmark_inference") is True
    ]
    presence_detected = [sample["hand_presence_score"] for sample in samples
                         if sample.get("detected")
                         and sample.get("hand_presence_score") is not None]
    presence_missing = [sample["hand_presence_score"] for sample in samples
                        if not sample.get("detected")
                        and sample.get("hand_presence_score") is not None]
    return {
        "paths": timing,
        "observation_causes": dict(sorted(cause_counts.items())),
        "native_loss_causes": dict(sorted(native_loss_causes.items())),
        "hand_presence_score": {
            "detected_p50": percentile(presence_detected, .50),
            "detected_p05": percentile(presence_detected, .05),
            "missing_p50": percentile(presence_missing, .50),
            "missing_p95": percentile(presence_missing, .95),
        },
        "native_inference_attribution": {
            "available": any("native_palm_inference" in sample for sample in samples),
            "palm_frames": len(native_palm_samples),
            "palm_frames_missing": sum(not sample["detected"]
                                       for sample in native_palm_samples),
            "palm_frames_detected": sum(sample["detected"]
                                        for sample in native_palm_samples),
            "landmark_frames": len(native_landmark_samples),
            "landmark_frames_missing": sum(not sample["detected"]
                                           for sample in native_landmark_samples),
        },
        "missing_runs": missing_runs,
        "missing_run_details": missing_run_details,
        "short_missing_runs": [length for length in missing_runs if length <= 3],
        "long_missing_runs": [length for length in missing_runs if length > 3],
        "recovery_gap_ms": {
            "count": len(recovery_gaps),
            "p50": percentile(recovery_gaps, .50),
            "p95": percentile(recovery_gaps, .95),
        },
        "recovery_missing_span_ms": {
            "count": len(recovery_missing_spans),
            "p50": percentile(recovery_missing_spans, .50),
            "p95": percentile(recovery_missing_spans, .95),
        },
        "recovery_inference_ms": {
            "count": len(recovery_inference),
            "p50": percentile(recovery_inference, .50),
            "p95": percentile(recovery_inference, .95),
        },
    }


def _enable_native_profile(tracker, folder: str) -> None:
    """Rebuild one replay tracker with MediaPipe's finite native profiler."""
    from google.protobuf import text_format
    from mediapipe.framework import calculator_pb2
    from mediapipe.python.solution_base import SolutionBase

    graph = calculator_pb2.CalculatorGraphConfig()
    text_format.Parse(tracker.hands._graph.text_config, graph)
    tracker.hands.close()
    profiler = graph.profiler_config
    profiler.enable_profiler = profiler.trace_enabled = True
    # A 30-second full graph replay can exceed the historical 131072-event
    # buffer. Keep this finite but large enough to avoid silently losing the
    # inference events needed for frame attribution.
    profiler.trace_log_capacity = 524288
    profiler.trace_log_interval_usec = -1
    profiler.trace_log_margin_usec = 0
    profiler.trace_log_path = folder + "/"
    outputs = (["multi_hand_landmarks"] if tracker.graph_mode == "lean-image" else [
        "multi_hand_landmarks", "multi_hand_world_landmarks", "multi_handedness",
    ]) + list(TRACKING_EVIDENCE_OUTPUTS)
    tracker.hands = SolutionBase(
        graph_config=graph,
        side_inputs={
            "model_complexity": tracker.model_complexity,
            "num_hands": 1,
            "use_prev_landmarks": tracker.use_previous_landmarks,
        },
        outputs=outputs,
    )


def native_profile_frames(folder: str, frame_count: int) -> dict:
    """Map palm/landmark inference calls to exact SolutionBase replay frames."""
    from mediapipe.framework import calculator_profile_pb2

    frames = {index: {} for index in range(1, frame_count + 1)}
    event_count = 0
    inference_nodes = Counter()
    out_of_range_timestamps = []
    for path in Path(folder).glob("*.binarypb"):
        report = calculator_profile_pb2.GraphProfile()
        report.ParseFromString(path.read_bytes())
        for trace in report.graph_trace:
            for event in trace.calculator_trace:
                if event.event_type != calculator_profile_pb2.GraphTrace.PROCESS:
                    continue
                if not (event.HasField("input_timestamp")
                        and event.HasField("start_time")
                        and event.HasField("finish_time")
                        and 0 <= event.node_id < len(trace.calculator_name)):
                    continue
                name = trace.calculator_name[event.node_id].lower()
                if "inferencecalculator" not in name:
                    continue
                inference_nodes[name] += 1
                if "palmdetection" in name:
                    lane = "palm"
                elif "handlandmark" in name:
                    lane = "landmark"
                else:
                    continue
                # GraphProfile stores this field as the zero-based packet index
                # in current MediaPipe builds. Accept the older simulated-us
                # representation as a conservative compatibility fallback.
                if 0 <= event.input_timestamp < frame_count:
                    frame = int(event.input_timestamp) + 1
                else:
                    frame = int(round(event.input_timestamp / 33333.0))
                if frame not in frames:
                    out_of_range_timestamps.append(event.input_timestamp)
                    continue
                frames[frame][lane + "_inference_ms"] = max(
                    0.0, (event.finish_time - event.start_time) / 1000.0,
                )
                event_count += 1
    palm_ms = [item["palm_inference_ms"] for item in frames.values()
               if "palm_inference_ms" in item]
    landmark_ms = [item["landmark_inference_ms"] for item in frames.values()
                   if "landmark_inference_ms" in item]

    def timing_summary(values: list[float]) -> dict:
        """Summarize one extracted graph-timing lane."""
        return {
            "count": len(values),
            "p50": percentile(values, .50),
            "p95": percentile(values, .95),
            "mean": round(sum(values) / len(values), 2) if values else None,
        }

    return {
        "events": event_count,
        "frames": frames,
        "palm_inference_frames": sum("palm_inference_ms" in item
                                     for item in frames.values()),
        "landmark_inference_frames": sum("landmark_inference_ms" in item
                                         for item in frames.values()),
        "inference_nodes": dict(sorted(inference_nodes.items())),
        "inference_ms": {
            "palm": timing_summary(palm_ms),
            "landmark": timing_summary(landmark_ms),
        },
        "out_of_range_timestamps": out_of_range_timestamps[:20],
    }


def run_lane(clip: Path, backend: str, threads: int, size: tuple[int, int],
             preview: bool, model: Path | None, cues: list[dict],
             tracking_confidence: float = .55,
             tracking_roi_scale: float = 2.0,
             tracking_roi_shift: tuple[float, float] = (0.0, 0.0),
             palm_detection_mode: str = "tracked",
             detection_confidence: float = .55,
             model_complexity: int = 0,
             fused_preprocessing: bool = True,
             palm_inference_threads: int | None = None,
             tracking_roi_scale_x: float | None = None,
             tracking_roi_scale_y: float | None = None,
             frame_times: list[float] | None = None,
             effective_fps: float | None = None,
             directional_search: bool = False,
             directional_search_gain: float = .275,
             directional_search_min_speed: float = .5,
             directional_search_max_offset: float = .04,
             directional_search_recovery_frames: int = 0,
             native_profile: bool = False) -> dict:
    """Replay one clip through a single tracker configuration and summarize it."""
    import cv2
    tracker = MediaPipeTracker(
        backend=backend, inference_threads=threads, model_path=model, mirror=True,
        tracking_confidence=tracking_confidence,
        tracking_roi_scale=tracking_roi_scale,
        tracking_roi_shift_x=tracking_roi_shift[0],
        tracking_roi_shift_y=tracking_roi_shift[1],
        use_previous_landmarks=palm_detection_mode == "tracked",
        detection_confidence=detection_confidence,
        model_complexity=model_complexity,
        fused_preprocessing=fused_preprocessing,
        palm_inference_threads=palm_inference_threads,
        tracking_roi_scale_x=tracking_roi_scale_x,
        tracking_roi_scale_y=tracking_roi_scale_y,
        directional_search=directional_search,
        directional_search_gain=directional_search_gain,
        directional_search_min_speed=directional_search_min_speed,
        directional_search_max_offset=directional_search_max_offset,
        directional_search_recovery_frames=directional_search_recovery_frames,
        tracking_evidence=True,
    )
    profile_folder = tempfile.TemporaryDirectory(
        prefix="pgv-replay-native-profile-"
    ) if native_profile else None
    if profile_folder is not None:
        _enable_native_profile(tracker, profile_folder.name)
    tracker.preview_enabled = preview
    tracker.diagnostics_enabled = preview
    capture = cv2.VideoCapture(str(clip))
    source_fps = effective_fps or capture.get(cv2.CAP_PROP_FPS) or 30.0
    inference = []
    detected = []
    observations = []
    motion_samples = []
    tracking_paths = []
    encoded_ms = []
    frame_index = 0
    engine = GestureEngine("practice")
    cue_stats = {
        cue["label"]: {"frames": 0, "detected": 0, "recognized": 0, "first_ms": None}
        for cue in cues
    }
    neutral_false_frames = 0
    neutral_axes = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_index += 1
            elapsed = (
                frame_times[frame_index - 1]
                if frame_times is not None and frame_index <= len(frame_times)
                else frame_index / source_fps
            )
            cue = next(
                (item for item in cues if item["start"] <= elapsed < item["end"]),
                None,
            )
            frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
            started = time.monotonic()
            result = tracker.process(frame, elapsed)
            finished = time.monotonic()
            inference.append((finished - started) * 1000)
            detected.append(result.observation.detected)
            tracking_paths.append({
                "path": result.diagnostics.get("tracking_path", "unavailable"),
                "observation_cause": result.diagnostics.get(
                    "tracking_observation_cause", "unavailable"
                ),
                "frame": frame_index,
                "elapsed": elapsed,
                "cue": None if cue is None else cue["label"],
                "ms": (finished - started) * 1000,
                "detected": result.observation.detected,
                "recovery_gap_ms": result.diagnostics.get("recovery_gap_ms"),
                "hand_presence_score": result.diagnostics.get("hand_presence_score"),
                "recovery_missing_span_ms": (
                    result.diagnostics.get("recovery_missing_span_ms")
                ),
                "recovery_inference_ms": (
                    result.diagnostics.get("last_recovery_inference_ms")
                    if result.diagnostics.get("tracking_recovered") else None
                ),
                "recovery_loss_start_cause": (
                    result.diagnostics.get("last_recovery_loss_start_cause")
                    if result.diagnostics.get("tracking_recovered") else None
                ),
                "recovery_missing_causes": (
                    result.diagnostics.get("last_recovery_missing_causes", {})
                    if result.diagnostics.get("tracking_recovered") else {}
                ),
                "directional_search_phase": result.diagnostics.get(
                    "directional_search_phase", "inactive"
                ),
            })
            state = engine.update(result.observation)
            item = result.observation
            motion_samples.append({
                "frame": frame_index, "elapsed": elapsed,
                "detected": item.detected, "confidence": item.confidence,
                "confidence_source": item.confidence_source,
                "x": item.palm_x if item.detected else None,
                "y": item.palm_y if item.detected else None,
                "scale": item.palm_scale if item.detected else None,
                "palm_anchors": result.palm_anchors if item.detected else {},
                "directional_search_active": bool(
                    result.diagnostics.get("directional_search_active", False)
                ),
                "directional_search_offset": result.diagnostics.get(
                    "directional_search_offset", (0.0, 0.0)
                ),
                "directional_search_phase": result.diagnostics.get(
                    "directional_search_phase", "inactive"
                ),
            })
            feedback = engine.recognition_feedback()
            curls = engine.curl_feedback(result.observation)
            push = engine.push_feedback(result.observation)["active"]
            pull = engine.pull_feedback(result.observation)["active"]
            recognized = {
                "short_directions": any(state.dpad.values()),
                "a": curls["index"], "b": curls["thumb"],
                "roll_left": feedback["roll_left"],
                "roll_right": feedback["roll_right"],
                "closed_hand": feedback["closed_hand"],
                "push": push, "pull": pull,
                "a_b_far": curls["index"] or curls["thumb"],
            }
            any_action = (
                any(state.dpad.values()) or any(curls.values()) or push or pull
                or feedback["roll_left"] or feedback["roll_right"]
                or feedback["closed_hand"] or feedback["menu_guard"]
            )
            if cue is not None:
                stat = cue_stats[cue["label"]]
                stat["frames"] += 1
                stat["detected"] += int(result.observation.detected)
                active = recognized.get(cue["label"], False)
                stat["recognized"] += int(active)
                if active and stat["first_ms"] is None:
                    stat["first_ms"] = round((elapsed - cue["start"]) * 1000)
                if cue["label"] in ("neutral_near", "neutral_far", "neutral_finish"):
                    neutral_false_frames += int(any_action)
                    if state.calibrated and state.detected:
                        neutral_axes.append((state.axes["x"], state.axes["y"]))
            if result.observation.detected:
                item = result.observation
                observations.append({
                    "frame": frame_index, "elapsed": elapsed,
                    "confidence": item.confidence,
                    "confidence_source": item.confidence_source,
                    "x": item.palm_x, "y": item.palm_y,
                    "scale": item.palm_scale, "roll": item.roll,
                    "thumb": item.thumb_curl, "index": item.index_curl,
                    "middle": item.middle_curl, "ring": item.ring_curl,
                    "pinky": item.pinky_curl,
                    "palm_anchors": result.palm_anchors,
                })
            if preview and frame_index % max(1, round(source_fps / 5)) == 0:
                encode_started = time.monotonic()
                cv2.imencode(".jpg", result.frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                encoded_ms.append((time.monotonic() - encode_started) * 1000)
    finally:
        capture.release()
        tracker.close()
    native_profile_summary = None
    if profile_folder is not None:
        native_profile_summary = native_profile_frames(
            profile_folder.name, frame_index,
        )
        for sample in tracking_paths:
            native = native_profile_summary["frames"].get(sample["frame"], {})
            sample.update(native)
            sample["native_palm_inference"] = "palm_inference_ms" in native
            sample["native_landmark_inference"] = "landmark_inference_ms" in native
            if not sample["detected"]:
                if sample["native_landmark_inference"]:
                    sample["native_loss_cause"] = (
                        "landmark_inference_without_valid_hand"
                    )
                elif sample["native_palm_inference"]:
                    sample["native_loss_cause"] = "palm_inference_without_valid_hand"
                else:
                    sample["native_loss_cause"] = "no_profiled_inference"
        detected_frames = sum(sample["detected"] for sample in tracking_paths)
        native_profile_summary["trace_complete_for_detected_frames"] = (
            native_profile_summary["landmark_inference_frames"] >= detected_frames
        )
        del native_profile_summary["frames"]
        profile_folder.cleanup()
    for stat in cue_stats.values():
        stat["detection_percent"] = round(
            stat["detected"] / stat["frames"] * 100, 2
        ) if stat["frames"] else 0
        stat["recognition_percent"] = round(
            stat["recognized"] / stat["frames"] * 100, 2
        ) if stat["frames"] else 0
    jitter_span = {
        axis: (max(values) - min(values) if values else None)
        for axis, values in (
            ("x", [value[0] for value in neutral_axes]),
            ("y", [value[1] for value in neutral_axes]),
        )
    }
    return {
        "backend": backend, "threads": threads,
        "palm_inference_threads": palm_inference_threads or threads,
        "tracking_confidence": tracking_confidence, "resize": list(size),
        "tracking_roi_scale": tracking_roi_scale,
        "tracking_roi_scale_x": tracking_roi_scale_x or tracking_roi_scale,
        "tracking_roi_scale_y": tracking_roi_scale_y or tracking_roi_scale,
        "tracking_roi_shift": {"x": tracking_roi_shift[0], "y": tracking_roi_shift[1]},
        "tracking_roi_lane": roi_shift_lane_label(*tracking_roi_shift),
        "tracking_roi_shift_research_only": tracking_roi_shift != (0.0, 0.0),
        "palm_detection_mode": palm_detection_mode,
        "detection_confidence": detection_confidence,
        "model_complexity": model_complexity,
        "frame_preparation": "fused" if fused_preprocessing else "current",
        "directional_search": directional_search,
        "directional_search_gain": directional_search_gain,
        "directional_search_min_speed": directional_search_min_speed,
        "directional_search_max_offset": directional_search_max_offset,
        "directional_search_recovery_frames": directional_search_recovery_frames,
        "preview": "open" if preview else "closed", "frames": frame_index,
        "inference_ms": {"p50": percentile(inference, .50),
                         "p95": percentile(inference, .95),
                         "mean": round(sum(inference) / len(inference), 2) if inference else None},
        "preview_encode_ms": {"p50": percentile(encoded_ms, .50),
                              "p95": percentile(encoded_ms, .95)},
        "detection_continuity_percent": round(sum(detected) / len(detected) * 100, 2) if detected else 0,
        "tracking_path_summary": tracking_path_summary(tracking_paths),
        "native_profile": native_profile_summary,
        "cue_results": cue_stats,
        "neutral_false_activation_frames": neutral_false_frames,
        "neutral_coordinate_jitter_span": jitter_span,
        "observation_samples": observations,
        "motion_samples": motion_samples,
    }


def parser() -> argparse.ArgumentParser:
    """Build the repeatable replay benchmark command-line interface."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("clip", type=Path)
    result.add_argument("--model", type=Path)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument(
        "--quick", action="store_true",
        help="Run only the proven 640x480, two-thread lane for clip validation",
    )
    result.add_argument("--threads", nargs="+", type=int, choices=(1, 2, 3, 4))
    result.add_argument(
        "--palm-threads", nargs="+", type=int, choices=(1, 2, 4),
        help="replay research only: palm-detector threads; landmark threads remain --threads",
    )
    result.add_argument("--tracking-confidences", nargs="+", type=float,
                        choices=(.10, .20, .25, .30, .35, .40, .45, .50, .55, .60))
    result.add_argument("--tracking-roi-scales", nargs="+", type=float,
                        choices=(2.0, 2.1, 2.15, 2.2, 2.25, 2.3, 2.35,
                                 2.4, 2.6, 2.8, 3.0))
    result.add_argument(
        "--tracking-roi-x-scales", nargs="+", type=float,
        choices=(2.0, 2.1, 2.15, 2.2, 2.25, 2.3, 2.35, 2.4, 2.45,
                 2.5, 2.6, 2.8, 3.0),
        help="replay research only: override horizontal next-frame ROI scale",
    )
    result.add_argument(
        "--tracking-roi-shift", action="append", type=parse_roi_shift,
        help=("replay research only: add one fixed ROI-local X,Y shift to the "
              "next-frame landmark region; repeat this option for multiple lanes"),
    )
    result.add_argument("--palm-detection-modes", nargs="+",
                        choices=("tracked", "every-frame"))
    result.add_argument("--detection-confidences", nargs="+", type=float,
                        choices=(.30, .35, .40, .45, .50, .55, .60))
    result.add_argument("--model-complexities", nargs="+", type=int,
                        choices=(0, 1))
    result.add_argument("--preview", choices=("closed", "open", "both"))
    result.add_argument(
        "--frame-preparations", nargs="+", choices=("current", "fused"),
        help="compare the current two-step transform with fused full-colour preparation",
    )
    result.add_argument(
        "--directional-search-modes", nargs="+", choices=("off", "on"),
        help="replay research only: compare conditional direction-aware input search",
    )
    result.add_argument("--directional-search-gains", nargs="+", type=float)
    result.add_argument("--directional-search-min-speeds", nargs="+", type=float)
    result.add_argument("--directional-search-max-offsets", nargs="+", type=float)
    result.add_argument(
        "--directional-search-recovery-frames", nargs="+", type=int,
        choices=(0, 1),
        help="replay research only: compare immediate reset with one-frame recovery carry",
    )
    result.add_argument(
        "--directional-search-candidate", action="append",
        type=parse_directional_search_candidate,
        help=("replay research only: run one exact on-lane as "
              "gain,min-speed,max-offset,recovery-frames; repeat for more lanes"),
    )
    result.add_argument(
        "--native-profile", action="store_true",
        help=("enable MediaPipe's finite native calculator trace for exact "
              "palm/landmark inference attribution; replay only"),
    )
    return result


def main() -> int:
    """Run every requested comparison lane and write one aggregate JSON report."""
    args = parser().parse_args()
    if not args.clip.is_file():
        raise FileNotFoundError(args.clip)
    sidecar = args.clip.with_suffix(args.clip.suffix + ".json")
    if not sidecar.is_file():
        raise FileNotFoundError(f"Benchmark cue sidecar is missing: {sidecar}")
    cue_document = json.loads(sidecar.read_text())
    cues = cue_document["cues"]
    frame_times = cue_document.get("frame_times_seconds")
    effective_fps = cue_document.get("effective_fps")
    lanes = []
    focused = bool(args.threads or args.palm_threads or args.tracking_confidences
                   or args.tracking_roi_scales or args.tracking_roi_x_scales
                   or args.tracking_roi_shift
                   or args.palm_detection_modes
                   or args.detection_confidences or args.model_complexities
                   or args.frame_preparations or args.directional_search_modes
                   or args.directional_search_gains
                   or args.directional_search_min_speeds
                   or args.directional_search_max_offsets
                   or args.directional_search_recovery_frames
                   or args.directional_search_candidate or args.preview
                   or args.native_profile)
    sizes = ((640, 480),) if args.quick or focused else ((640, 480), (512, 384))
    previews = ((False,) if args.preview in (None, "closed") else
                (True,) if args.preview == "open" else (False, True))
    if not args.quick and not focused:
        previews = (False, True)
    threads_to_test = tuple(args.threads or ((2,) if args.quick or focused else (1, 2, 4)))
    palm_threads_to_test = tuple(args.palm_threads or (None,))
    confidences = tuple(args.tracking_confidences or (.55,))
    roi_scales = tuple(args.tracking_roi_scales or (2.0,))
    roi_x_scales = tuple(args.tracking_roi_x_scales or (None,))
    roi_shifts = tuple(args.tracking_roi_shift or ((0.0, 0.0),))
    palm_modes = tuple(args.palm_detection_modes or ("tracked",))
    detection_confidences = tuple(args.detection_confidences or (.55,))
    model_complexities = tuple(args.model_complexities or (0,))
    frame_preparations = tuple(args.frame_preparations or ("fused",))
    directional_modes = tuple(args.directional_search_modes or ("off",))
    directional_gains = tuple(args.directional_search_gains or (.275,))
    directional_min_speeds = tuple(args.directional_search_min_speeds or (.5,))
    directional_max_offsets = tuple(args.directional_search_max_offsets or (.04,))
    directional_recovery_frames = tuple(
        args.directional_search_recovery_frames or (0,)
    )
    if args.directional_search_candidate:
        directional_candidates = tuple(
            ("on", gain, speed, offset, recovery)
            for gain, speed, offset, recovery in args.directional_search_candidate
        )
    else:
        directional_candidates = tuple(
            (mode, gain, speed, offset, recovery)
            for mode in directional_modes
            for gain in directional_gains
            for speed in directional_min_speeds
            for offset in directional_max_offsets
            for recovery in directional_recovery_frames
        )
    for size in sizes:
        for preview in previews:
            for threads in threads_to_test:
                for palm_threads in palm_threads_to_test:
                    for confidence in confidences:
                        for roi_scale in roi_scales:
                            for roi_x_scale in roi_x_scales:
                                for roi_shift in roi_shifts:
                                    for palm_mode in palm_modes:
                                        for detection_confidence in detection_confidences:
                                            for model_complexity in model_complexities:
                                                for preparation in frame_preparations:
                                                    for (directional_mode, directional_gain,
                                                         directional_speed, directional_offset,
                                                         recovery_frames) in directional_candidates:
                                                        lanes.append(run_lane(
                                                                        args.clip, "legacy", threads, size, preview,
                                                                        None, cues, confidence, roi_scale, roi_shift,
                                                                        palm_mode, detection_confidence, model_complexity,
                                                                        preparation == "fused", palm_threads,
                                                                        roi_x_scale, None,
                                                                        frame_times, effective_fps,
                                                                        directional_mode == "on", directional_gain,
                                                                        directional_speed, directional_offset,
                                                                        recovery_frames,
                                                                        args.native_profile,
                                                                        ))
            if args.model is not None and not args.quick:
                lanes.append(run_lane(
                    args.clip, "tasks-video", 1, size, preview, args.model, cues,
                    .55, 2.0, (0.0, 0.0), "tracked", .55, 0, True, None,
                    None, None,
                    frame_times, effective_fps,
                ))
    result = {
        "version": 3, "clip": str(args.clip), "full_frame_resize_only": True,
        "fixed_roi_shift_scope": "replay research only; production remains zero shift",
        "directional_search_scope": (
            "production standard; replay may explicitly compare an off lane"
        ),
        "cues": cues,
        "lanes": lanes,
        "note": ("Observation samples support cue-by-cue recognition review. Live Dashboard "
                 "telemetry remains authoritative for latest-frame age and camera-to-send latency."),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "lanes": len(lanes)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
