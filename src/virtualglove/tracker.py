# Project: VirtualGlove
# File: src/virtualglove/tracker.py
# Purpose: Convert MediaPipe or Arduino hand landmarks into normalized observations and annotated frames.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Made validated 0.10.35 the sole shipped XNNPACK graph runtime.
#   2026-09-09 - Recorded landmark-presence loss causes and native profiling evidence.
#   2026-09-09 - Added a replay-selectable one-frame directional reacquisition lane.
#   2026-09-09 - Measured tracking-loss gaps and recovery inference separately.
#   2026-09-09 - Kept Dashboard preview out of MediaPipe frame preparation.
#   2026-09-08 - Added replay-only conditional search and precise tracking-path evidence.
#   2026-09-07 - Added an isolated image-landmark-only graph experiment.
#   2026-09-07 - Added geometry validation and benchmarkable pose-stable palm anchors.
# Full history: docs/CHANGELOG.md and Git history.

"""Convert MediaPipe or Arduino hand landmarks into normalized observations and annotated frames."""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import HandObservation


TRACKER_BACKEND_LABELS = {
    "legacy": "MediaPipe Hands",
    "tasks-video": "MediaPipe Tasks Video (experimental)",
}
# Existing calibration centres and reach spans were recorded from this anchor.
# Benchmark alternatives without silently changing that coordinate contract.
PALM_ANCHOR = "five_point_average"
HAND_PRESENCE_SCORE_OUTPUT = "handlandmarkcpu__hand_presence_score"
TRACKING_EVIDENCE_OUTPUTS = ("palm_detections", HAND_PRESENCE_SCORE_OUTPUT)


def log_startup_stage(label: str, started: float) -> None:
    """Record startup durations without camera imagery or configuration secrets."""
    print(f"Vision startup: {label}: {time.monotonic() - started:.3f}s",
          file=sys.stderr, flush=True)


CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)


def _distance(a: Any, b: Any) -> float:
    """Return the two-dimensional Euclidean distance between landmarks."""
    return math.hypot(a.x - b.x, a.y - b.y)


def _angle(a: Any, b: Any, c: Any, use_depth: bool = False) -> float:
    """Return the stable interior angle formed by three landmarks."""
    ab = (a.x - b.x, a.y - b.y, (a.z - b.z) if use_depth else 0.0)
    cb = (c.x - b.x, c.y - b.y, (c.z - b.z) if use_depth else 0.0)
    denominator = math.sqrt(sum(v*v for v in ab) * sum(v*v for v in cb))
    if denominator < 1e-8:
        return math.pi
    cosine = max(-1.0, min(1.0, sum(x*y for x, y in zip(ab, cb)) / denominator))
    return math.acos(cosine)


def _curl(a: Any, b: Any, c: Any, use_depth: bool = False) -> float:
    # Straight is approximately pi radians; tightly bent is near pi/3.
    """Convert two finger-joint angles into a normalized curl amount."""
    return max(0.0, min(1.0, (math.pi - _angle(a, b, c, use_depth)) / (2 * math.pi / 3)))


@dataclass
class TrackingResult:
    """Bundle one normalized observation with its annotated video frame."""
    observation: HandObservation
    frame: Any
    diagnostics: dict = field(default_factory=dict)
    palm_points: list = field(default_factory=list)
    palm_anchors: dict = field(default_factory=dict)
    preview_overlay: dict = field(default_factory=dict)


@dataclass
class _Point:
    """Provide a minimal normalized landmark representation for Arduino bridge data."""
    x: float
    y: float
    z: float = 0.0


class _DirectionalSearchState:
    """Lead only the model input during sustained, aligned fast movement."""

    def __init__(self, gain: float = .5, min_speed: float = .45,
                 alignment: float = .82, max_offset: float = .08,
                 recovery_frames: int = 0) -> None:
        self.gain = gain
        self.min_speed = min_speed
        self.alignment = alignment
        self.max_offset = max_offset
        self.recovery_frames = recovery_frames
        self.history: list[tuple[float, float, float]] = []
        self.offset = (0.0, 0.0)
        self.active = False
        self.recovery_frames_remaining = 0
        self.phase = "inactive"

    def reset(self) -> None:
        """Discard search history so recovery starts from the full frame."""
        self.history.clear()
        self.offset = (0.0, 0.0)
        self.active = False
        self.recovery_frames_remaining = 0
        self.phase = "inactive"

    def observe_missing(self) -> None:
        """Carry a proven fast-search offset into one reacquisition frame."""
        if self.phase == "recovery":
            self.reset()
            return
        if (self.recovery_frames and self.active
                and self.offset != (0.0, 0.0)):
            self.recovery_frames_remaining = self.recovery_frames
            self.phase = "recovery"
            return
        self.reset()

    def next_offset(self, timestamp: float) -> tuple[float, float]:
        """Return an input-only offset after two aligned fast observations."""
        if self.recovery_frames_remaining:
            self.recovery_frames_remaining -= 1
            self.active = True
            self.phase = "recovery"
            return self.offset
        self.active = False
        self.phase = "inactive"
        if len(self.history) < 3:
            return self.offset
        first, second, latest = self.history[-3:]
        dt1 = second[2] - first[2]
        dt2 = latest[2] - second[2]
        next_dt = timestamp - latest[2]
        if min(dt1, dt2, next_dt) <= 0.0:
            return self.offset
        velocity1 = ((second[0] - first[0]) / dt1,
                     (second[1] - first[1]) / dt1)
        velocity2 = ((latest[0] - second[0]) / dt2,
                     (latest[1] - second[1]) / dt2)
        speed1 = math.hypot(*velocity1)
        speed2 = math.hypot(*velocity2)
        cosine = (
            (velocity1[0] * velocity2[0] + velocity1[1] * velocity2[1])
            / (speed1 * speed2)
        ) if speed1 > 0.0 and speed2 > 0.0 else -1.0
        outward_at_edge = (
            (latest[0] <= .04 and velocity2[0] < 0.0)
            or (latest[0] >= .96 and velocity2[0] > 0.0)
            or (latest[1] <= .04 and velocity2[1] < 0.0)
            or (latest[1] >= .96 and velocity2[1] > 0.0)
        )
        if (speed1 < self.min_speed or speed2 < self.min_speed
                or cosine < self.alignment or outward_at_edge):
            self.offset = (0.0, 0.0)
            return self.offset
        # Offset the image opposite the hand's projected movement. The graph's
        # previous ROI therefore sees a smaller displacement. Output landmarks
        # are translated back before VirtualGlove coordinates are calculated.
        dt = min(next_dt, .067)
        x = self.offset[0] - self.gain * velocity2[0] * dt
        y = self.offset[1] - self.gain * velocity2[1] * dt
        magnitude = math.hypot(x, y)
        if magnitude > self.max_offset:
            scale = self.max_offset / magnitude
            x *= scale
            y *= scale
        self.offset = (x, y)
        self.active = True
        self.phase = "lead"
        return self.offset

    def observe(self, x: float, y: float, timestamp: float) -> None:
        """Retain only enough unshifted coordinate history to prove direction."""
        self.recovery_frames_remaining = 0
        self.history.append((x, y, timestamp))
        del self.history[:-3]


def _translate_tracker_input(rgb: Any, offset: tuple[float, float],
                             cv2: Any, numpy: Any) -> Any:
    """Translate a research frame while keeping its size and colour unchanged."""
    if offset == (0.0, 0.0):
        return rgb
    height, width = rgb.shape[:2]
    translated = cv2.warpAffine(
        rgb,
        numpy.asarray(((1.0, 0.0, offset[0] * width),
                       (0.0, 1.0, offset[1] * height)), dtype=numpy.float32),
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    translated.flags.writeable = False
    return translated


class _TrackingTelemetry:
    """Classify graph tracking paths without retaining frames or landmarks."""

    def __init__(self) -> None:
        self.ever_detected = False
        self.hand_missing_streak = 0
        self.landmark_continuations_total = 0
        self.palm_detection_packets_total = 0
        self.palm_redetections_total = 0
        self.palm_reacquisitions_total = 0
        self.hand_missing_results_total = 0
        self.invalid_landmark_results_total = 0
        self.missing_cause_totals = {
            "invalid_landmark_geometry": 0,
            "palm_detection_without_valid_hand": 0,
            "landmark_presence_below_gate": 0,
            "graph_no_hand_unobservable": 0,
        }
        self.loss_start_cause: str | None = None
        self.last_recovery_loss_start_cause: str | None = None
        self.last_recovery_missing_causes: dict[str, int] = {}
        self.current_missing_causes: dict[str, int] = {}
        self.last_detected_timestamp: float | None = None
        self.loss_started_timestamp: float | None = None
        self.last_recovery_gap_ms: float | None = None
        self.last_recovery_missing_span_ms: float | None = None
        self.last_recovery_inference_ms: float | None = None
        self.longest_tracking_loss_ms = 0.0

    def observe(
        self,
        detected: bool,
        palm_detector_invoked: bool | None,
        palm_detection_count: int | None,
        *,
        invalid_landmarks: bool = False,
        timestamp: float | None = None,
        inference_ms: float | None = None,
        hand_presence_score: float | None = None,
        include_cause_details: bool = True,
    ) -> dict:
        """Record graph-path evidence and capture-time loss/recovery latency."""
        missing_before = self.hand_missing_streak
        if detected:
            observation_cause = "valid_landmarks"
        elif invalid_landmarks:
            observation_cause = "invalid_landmark_geometry"
        elif hand_presence_score is not None:
            observation_cause = "landmark_presence_below_gate"
        elif palm_detector_invoked is True:
            observation_cause = "palm_detection_without_valid_hand"
        else:
            # An empty MediaPipe stream does not reveal whether the palm branch
            # was skipped or ran without a detection. Keep that distinction
            # explicitly unknown until a native graph profile supplies it.
            observation_cause = "graph_no_hand_unobservable"
        tracking_recovered = bool(detected and self.ever_detected and missing_before)
        recovery_gap_ms = None
        recovery_missing_span_ms = None
        if tracking_recovered and timestamp is not None:
            if self.last_detected_timestamp is not None:
                recovery_gap_ms = max(
                    0.0, (timestamp - self.last_detected_timestamp) * 1000.0,
                )
                self.last_recovery_gap_ms = recovery_gap_ms
            if self.loss_started_timestamp is not None:
                recovery_missing_span_ms = max(
                    0.0, (timestamp - self.loss_started_timestamp) * 1000.0,
                )
                self.last_recovery_missing_span_ms = recovery_missing_span_ms
            self.last_recovery_inference_ms = inference_ms
        if tracking_recovered and include_cause_details:
            self.last_recovery_loss_start_cause = self.loss_start_cause
            self.last_recovery_missing_causes = dict(self.current_missing_causes)
        reacquired = False
        if palm_detector_invoked is True:
            self.palm_detection_packets_total += 1
            if detected:
                if self.ever_detected and self.hand_missing_streak:
                    path = "palm_reacquisition"
                    reacquired = True
                    self.palm_reacquisitions_total += 1
                elif self.ever_detected:
                    path = "palm_redetection"
                    self.palm_redetections_total += 1
                else:
                    path = "initial_palm_detection"
            else:
                path = "palm_detection_no_valid_hand"
        elif detected:
            # The graph gates palm detection when a previous landmark ROI can
            # produce this frame's valid landmarks, making this continuation
            # classification exact even though a skipped stream has no packet.
            path = "landmark_continuation"
            palm_detector_invoked = False
            self.landmark_continuations_total += 1
        else:
            # MediaPipe represents both a skipped detector stream and a
            # detector invocation with zero detections as no packet. A missing
            # hand therefore cannot be subdivided without native profiling.
            path = "hand_missing_path_unobservable"

        if detected:
            self.ever_detected = True
            self.hand_missing_streak = 0
            if timestamp is not None:
                self.last_detected_timestamp = timestamp
            self.loss_started_timestamp = None
            if include_cause_details:
                self.loss_start_cause = None
                self.current_missing_causes = {}
        else:
            self.hand_missing_results_total += 1
            self.hand_missing_streak += 1
            if include_cause_details:
                self.missing_cause_totals[observation_cause] += 1
                self.current_missing_causes[observation_cause] = (
                    self.current_missing_causes.get(observation_cause, 0) + 1
                )
            if self.loss_started_timestamp is None:
                self.loss_started_timestamp = timestamp
                if include_cause_details:
                    self.loss_start_cause = observation_cause
        if invalid_landmarks:
            self.invalid_landmark_results_total += 1

        current_loss_ms = None
        if (not detected and timestamp is not None
                and self.last_detected_timestamp is not None):
            current_loss_ms = max(
                0.0, (timestamp - self.last_detected_timestamp) * 1000.0,
            )
            self.longest_tracking_loss_ms = max(
                self.longest_tracking_loss_ms, current_loss_ms,
            )

        result = {
            "tracking_path": path,
            "tracking_observation_cause": observation_cause,
            "palm_detector_invoked": palm_detector_invoked,
            "palm_detection_count": palm_detection_count,
            "hand_presence_score": hand_presence_score,
            "palm_reacquired": reacquired,
            "hand_missing_streak": self.hand_missing_streak,
            "landmark_continuations_total": self.landmark_continuations_total,
            "palm_detection_packets_total": self.palm_detection_packets_total,
            "palm_redetections_total": self.palm_redetections_total,
            "palm_reacquisitions_total": self.palm_reacquisitions_total,
            "hand_missing_results_total": self.hand_missing_results_total,
            "invalid_landmark_results_total": self.invalid_landmark_results_total,
            "tracking_recovered": tracking_recovered,
            "tracking_inference_ms": inference_ms,
            "current_tracking_loss_ms": current_loss_ms,
            "recovery_gap_ms": recovery_gap_ms,
            "recovery_missing_span_ms": recovery_missing_span_ms,
            "last_recovery_gap_ms": self.last_recovery_gap_ms,
            "last_recovery_missing_span_ms": self.last_recovery_missing_span_ms,
            "last_recovery_inference_ms": self.last_recovery_inference_ms,
            "longest_tracking_loss_ms": self.longest_tracking_loss_ms,
        }
        if include_cause_details:
            result.update({
                "loss_start_cause": self.loss_start_cause,
                "current_missing_causes": dict(self.current_missing_causes),
                "last_recovery_loss_start_cause": self.last_recovery_loss_start_cause,
                "last_recovery_missing_causes": dict(self.last_recovery_missing_causes),
                "missing_cause_totals": dict(self.missing_cause_totals),
            })
        return result


def _palm_detector_evidence(result: Any) -> tuple[bool | None, int | None]:
    """Return direct graph evidence; ``None`` means the stream is unavailable."""
    if not hasattr(result, "palm_detections"):
        return None, None
    detections = result.palm_detections
    if detections is None:
        return None, None
    try:
        return True, len(detections)
    except TypeError:
        return True, None


def _hand_presence_score_evidence(result: Any) -> float | None:
    """Return the diagnostic landmark-presence score when explicitly exposed."""
    value = getattr(result, HAND_PRESENCE_SCORE_OUTPUT, None)
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) else None


def _prepare_tracker_frame(frame: Any, mirror: bool, preview: bool,
                           fused: bool,
                           cv2: Any, numpy: Any) -> tuple[Any, Any, str]:
    """Prepare MediaPipe RGB input without making Dashboard work part of inference."""
    if mirror and fused:
        # Reverse screen X and BGR channel order in one contiguous allocation.
        # This is pixel-identical to flip followed by BGR-to-RGB conversion.
        # The preview worker mirrors its own display copy when one is requested.
        rgb = numpy.ascontiguousarray(frame[:, ::-1, ::-1])
        display_frame = frame
        preparation = "fused-mirror-bgr-to-rgb"
    else:
        display_frame = cv2.flip(frame, 1) if mirror else frame
        rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        preparation = "preview-compatible" if mirror else "bgr-to-rgb"
    rgb.flags.writeable = False
    return display_frame, rgb, preparation


def _camera_curl_points(result: Any, landmarks: list, tasks: bool,
                        width: int, height: int) -> list:
    """Prefer metric world geometry; correct image aspect ratio in the fallback."""
    worlds = getattr(result, "hand_world_landmarks" if tasks else "multi_hand_world_landmarks", None)
    if worlds:
        points = worlds[0] if tasks else worlds[0].landmark
        if len(points) == 21:
            return points
    # MediaPipe normalized z uses approximately the same scale as normalized x.
    return [_Point(p.x, p.y * height / width, p.z) for p in landmarks]


def _finger_spreads(points: list) -> dict:
    """Normalize adjacent fingertip gaps by the hand's knuckle width."""
    scale = max(_distance(points[5], points[17]), 1e-6)
    return {
        "index_middle_spread": _distance(points[8], points[12]) / scale,
        "middle_ring_spread": _distance(points[12], points[16]) / scale,
        "ring_pinky_spread": _distance(points[16], points[20]) / scale,
    }


def _landmarks_valid(landmarks: list) -> bool:
    """Reject malformed landmark sets without inventing a confidence score."""
    if len(landmarks) != 21:
        return False
    finite = all(
        math.isfinite(value)
        for point in landmarks
        for value in (point.x, point.y, point.z)
    )
    if not finite:
        return False
    # These two independent palm dimensions must have measurable area. This
    # rejects collapsed/corrupt results while allowing hands near image edges.
    return _distance(landmarks[0], landmarks[9]) > .005 \
        and _distance(landmarks[5], landmarks[17]) > .005


def _polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Return the area-weighted centre of a simple polygon, with a safe fallback."""
    twice_area = 0.0
    x_total = y_total = 0.0
    for first, second in zip(points, points[1:] + points[:1]):
        cross = first[0] * second[1] - second[0] * first[1]
        twice_area += cross
        x_total += (first[0] + second[0]) * cross
        y_total += (first[1] + second[1]) * cross
    if abs(twice_area) < 1e-9:
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    return x_total / (3.0 * twice_area), y_total / (3.0 * twice_area)


def _palm_anchor_candidates(landmarks: list) -> dict[str, tuple[float, float]]:
    """Calculate comparable palm anchors from one coherent landmark result."""
    ids = (0, 5, 9, 13, 17)
    points = [(float(landmarks[index].x), float(landmarks[index].y)) for index in ids]
    knuckles = points[1:]
    return {
        "five_point_average": (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        ),
        "four_knuckle_centroid": (
            sum(point[0] for point in knuckles) / len(knuckles),
            sum(point[1] for point in knuckles) / len(knuckles),
        ),
        "palm_polygon": _polygon_centroid(points),
        "weighted_wrist_knuckles": (
            (2 * points[0][0] + sum(point[0] for point in knuckles)) / 6,
            (2 * points[0][1] + sum(point[1] for point in knuckles)) / 6,
        ),
    }


def _finger_bends(points: list) -> dict:
    """Measure each joint separately so one deliberate bend is not averaged away."""
    result = {}
    for name, (a, b, c, d) in zip(
        ("thumb", "index", "middle", "ring", "pinky"),
        ((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12),
         (13, 14, 15, 16), (17, 18, 19, 20)),
    ):
        bends = [_curl(points[a], points[b], points[c], True),
                 _curl(points[b], points[c], points[d], True)]
        if name != "thumb":
            bends.insert(0, _curl(points[0], points[a], points[b], True))
        result[name] = bends
    return result


def _finger_curls_from_bends(bends: dict) -> dict:
    """Collapse already-measured joints without repeating angle calculations."""
    return {name + "_curl": max(values) for name, values in bends.items()}


def _start_curls_from_bends(bends: dict) -> dict:
    """Keep distal index/middle bends for a splayed V-sign menu pose."""
    return {
        name + "_tip_curl": max(bends[name][1:])
        for name in ("index", "middle")
    }


def _configure_tracking_roi(options: Any, scale: float,
                            shift_x: float, shift_y: float,
                            scale_x: float | None = None,
                            scale_y: float | None = None) -> None:
    """Apply one fixed graph ROI candidate without changing output coordinates."""
    options.scale_x = scale if scale_x is None else scale_x
    options.scale_y = scale if scale_y is None else scale_y
    options.shift_x = shift_x
    # MediaPipe Hands normally frames 10% above the calculated hand rectangle.
    # A research shift is additional to that proven built-in framing.
    options.shift_y = -0.1 + shift_y


def _inference_node_threads(node_name: str, landmark_threads: int,
                            palm_threads: int | None) -> int:
    """Choose threads independently for MediaPipe's two inference models."""
    normalized = node_name.lower()
    if "palmdetection" in normalized:
        return landmark_threads if palm_threads is None else palm_threads
    if "handlandmark" in normalized:
        return landmark_threads
    raise RuntimeError(f"unrecognized MediaPipe inference node: {node_name}")


def _is_cpu_inference_calculator(calculator: str) -> bool:
    """Recognize supported legacy Hands CPU nodes across MediaPipe releases."""
    return calculator in (
        "InferenceCalculatorCpu",
        "InferenceCalculatorXnnpack",
    )


def _legacy_hands(mp, cpu_threads: int, tracking_confidence: float = .55,
                  detection_confidence: float = .55,
                  graph_mode: str = "full", tracking_roi_scale: float = 2.0,
                  tracking_roi_shift_x: float = 0.0,
                  tracking_roi_shift_y: float = 0.0,
                  use_previous_landmarks: bool = True,
                  model_complexity: int = 0,
                  palm_inference_threads: int | None = None,
                  tracking_roi_scale_x: float | None = None,
                  tracking_roi_scale_y: float | None = None,
                  tracking_evidence: bool = False):
    """Build the lite legacy graph, enabling safe CPU parallelism when supported."""
    settings = {
        "static_image_mode": False,
        "max_num_hands": 1,
        "model_complexity": model_complexity,
        "min_detection_confidence": detection_confidence,
        "min_tracking_confidence": tracking_confidence,
    }
    base = mp.solutions.hands.Hands(**settings)
    if (cpu_threads <= 1 and graph_mode == "full"
            and tracking_roi_scale == 2.0
            and tracking_roi_shift_x == 0.0
            and tracking_roi_shift_y == 0.0
            and tracking_roi_scale_x is None
            and tracking_roi_scale_y is None
            and use_previous_landmarks
            and not tracking_evidence):
        return base
    try:
        from google.protobuf import text_format
        from mediapipe.calculators.tensor import inference_calculator_pb2
        from mediapipe.calculators.util import rect_transformation_calculator_pb2
        from mediapipe.framework import calculator_pb2
        from mediapipe.python.solution_base import SolutionBase

        graph = calculator_pb2.CalculatorGraphConfig()
        text_format.Parse(base._graph.text_config, graph)
        modified = 0
        configured_inference_nodes = set()
        for node in graph.node:
            # MediaPipe 0.10.18 names the CPU wrapper generically; 0.10.35
            # exposes the selected XNNPACK implementation in the calculator
            # name. Both carry the same InferenceCalculatorOptions extension.
            if not _is_cpu_inference_calculator(node.calculator):
                continue
            node_threads = _inference_node_threads(
                node.name, cpu_threads, palm_inference_threads,
            )
            options = node.options.Extensions[
                inference_calculator_pb2.InferenceCalculatorOptions.ext
            ]
            options.cpu_num_thread = node_threads
            # XNNPACK uses its own thread pool, independent of the interpreter.
            if options.delegate.HasField("xnnpack"):
                options.delegate.xnnpack.num_threads = node_threads
            configured_inference_nodes.add(
                "palm" if "palmdetection" in node.name.lower() else "landmark"
            )
            modified += 1
        if modified != 2 or configured_inference_nodes != {"palm", "landmark"}:
            raise RuntimeError(
                "expected one palm and one landmark CPU inference node, "
                f"found {modified}: {sorted(configured_inference_nodes)}"
            )
        roi_modified = 0
        for node in graph.node:
            if (node.calculator != "RectTransformationCalculator" or
                    "handlandmarklandmarkstoroi" not in node.name):
                continue
            options = node.options.Extensions[
                rect_transformation_calculator_pb2.RectTransformationCalculatorOptions.ext
            ]
            _configure_tracking_roi(
                options, tracking_roi_scale,
                tracking_roi_shift_x, tracking_roi_shift_y,
                tracking_roi_scale_x, tracking_roi_scale_y,
            )
            roi_modified += 1
        if roi_modified != 1:
            raise RuntimeError(
                f"expected one next-frame hand region, found {roi_modified}"
            )
        if tracking_evidence and not any(
            HAND_PRESENCE_SCORE_OUTPUT in output for output in graph.output_stream
        ):
            graph.output_stream.append(
                "HAND_PRESENCE_SCORE:" + HAND_PRESENCE_SCORE_OUTPUT
            )
        threaded = SolutionBase(
            graph_config=graph,
            side_inputs={
                "model_complexity": model_complexity,
                "num_hands": 1,
                "use_prev_landmarks": use_previous_landmarks,
            },
            outputs=(
                (["multi_hand_landmarks"] if graph_mode == "lean-image" else [
                    "multi_hand_landmarks", "multi_hand_world_landmarks", "multi_handedness",
                ]) + list(TRACKING_EVIDENCE_OUTPUTS if tracking_evidence else ())
            ),
        )
    except Exception as exc:
        print(
            f"Vision startup: parallel MediaPipe inference unavailable: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return base
    base.close()
    return threaded


class MediaPipeTracker:
    """Run single-hand tracking and produce normalized controller observations."""
    def __init__(
        self,
        glove_color: str = "none",
        mirror: bool = True,
        model_path: Path | str | None = None,
        inference_threads: int = 4,
        tracking_confidence: float = .35,
        detection_confidence: float = .45,
        backend: str = "legacy",
        graph_mode: str = "full",
        tracking_roi_scale: float = 2.25,
        tracking_roi_shift_x: float = 0.0,
        tracking_roi_shift_y: float = 0.0,
        use_previous_landmarks: bool = True,
        model_complexity: int = 0,
        fused_preprocessing: bool = True,
        palm_inference_threads: int | None = None,
        tracking_roi_scale_x: float | None = None,
        tracking_roi_scale_y: float | None = None,
        directional_search: bool = True,
        directional_search_gain: float = .275,
        directional_search_min_speed: float = .5,
        directional_search_max_offset: float = .04,
        directional_search_recovery_frames: int = 0,
        tracking_evidence: bool = False,
    ) -> None:
        if type(directional_search) is not bool:
            raise ValueError("directional search must be a boolean")
        for label, value, lower, upper in (
            ("gain", directional_search_gain, 0.0, 1.0),
            ("minimum speed", directional_search_min_speed, 0.0, 4.0),
            ("maximum offset", directional_search_max_offset, 0.0, .15),
        ):
            if not math.isfinite(float(value)) or not lower <= float(value) <= upper:
                raise ValueError(
                    f"directional search {label} must be between {lower} and {upper}"
                )
        if (type(directional_search_recovery_frames) is not int
                or directional_search_recovery_frames not in (0, 1)):
            raise ValueError("directional search recovery frames must be 0 or 1")
        self.directional_search = directional_search
        self._directional_search = _DirectionalSearchState(
            float(directional_search_gain), float(directional_search_min_speed),
            max_offset=float(directional_search_max_offset),
            recovery_frames=directional_search_recovery_frames,
        )
        if type(tracking_evidence) is not bool:
            raise ValueError("tracking evidence must be a boolean")
        self.tracking_evidence = tracking_evidence
        self.tracking_roi_scale = float(tracking_roi_scale)
        if not 2.0 <= self.tracking_roi_scale <= 3.0:
            raise ValueError("tracking ROI scale must be between 2.0 and 3.0")
        for label, value in (("X", tracking_roi_scale_x),
                             ("Y", tracking_roi_scale_y)):
            if value is not None and (not math.isfinite(float(value))
                                      or not 2.0 <= float(value) <= 3.0):
                raise ValueError(
                    f"tracking ROI {label} scale must be between 2.0 and 3.0"
                )
        self.tracking_roi_scale_x = (
            None if tracking_roi_scale_x is None else float(tracking_roi_scale_x)
        )
        self.tracking_roi_scale_y = (
            None if tracking_roi_scale_y is None else float(tracking_roi_scale_y)
        )
        self.tracking_roi_shift_x = float(tracking_roi_shift_x)
        self.tracking_roi_shift_y = float(tracking_roi_shift_y)
        if (not math.isfinite(self.tracking_roi_shift_x)
                or not -.25 <= self.tracking_roi_shift_x <= .25
                or not math.isfinite(self.tracking_roi_shift_y)
                or not -.25 <= self.tracking_roi_shift_y <= .25):
            raise ValueError("tracking ROI shifts must be finite and between -0.25 and 0.25")
        if type(use_previous_landmarks) is not bool:
            raise ValueError("use_previous_landmarks must be a boolean")
        self.use_previous_landmarks = use_previous_landmarks
        self.detection_confidence = float(detection_confidence)
        if not 0.0 <= self.detection_confidence <= 1.0:
            raise ValueError("detection confidence must be between 0.0 and 1.0")
        if type(model_complexity) is not int or model_complexity not in (0, 1):
            raise ValueError("model complexity must be 0 or 1")
        self.model_complexity = model_complexity
        if type(fused_preprocessing) is not bool:
            raise ValueError("fused preprocessing must be a boolean")
        self.fused_preprocessing = fused_preprocessing
        if (palm_inference_threads is not None
                and (type(palm_inference_threads) is not int
                     or palm_inference_threads not in (1, 2, 4))):
            raise ValueError("palm inference threads must be 1, 2, 4, or omitted")
        self.palm_inference_threads = palm_inference_threads
        try:
            import cv2
            import numpy
            started = time.monotonic()
            import mediapipe as mp
            log_startup_stage("MediaPipe import", started)
            started = time.monotonic()
        except ImportError as exc:
            raise RuntimeError(
                "camera tracking requires the 'vision' dependencies; "
                "install with: pip install -e '.[vision]'"
            ) from exc
        self.cv2 = cv2
        self.numpy = numpy
        self.mp = mp
        self.glove_color = glove_color
        self.mirror = mirror
        self.preview_enabled = True
        self.diagnostics_enabled = True
        self.inference_threads = max(1, int(inference_threads))
        self.tracking_confidence = max(0.0, min(1.0, float(tracking_confidence)))
        if graph_mode not in ("full", "lean-image"):
            raise ValueError("unsupported MediaPipe graph mode")
        self.graph_mode = graph_mode
        self._last_timestamp_ms = -1
        self._tracking_telemetry = _TrackingTelemetry()
        if backend not in TRACKER_BACKEND_LABELS:
            raise ValueError(f"unsupported tracker backend: {backend}")
        if backend == "legacy" and not hasattr(mp, "solutions"):
            raise RuntimeError("this MediaPipe build does not provide the legacy Hands API")
        self.backend = backend
        self.backend_label = TRACKER_BACKEND_LABELS[backend]
        self._tasks = backend == "tasks-video"
        if self._tasks:
            if model_path is None:
                model_path = (
                    Path(__file__).resolve().parents[2]
                    / "data" / "models" / "hand_landmarker.task"
                )
            model_path = Path(model_path)
            if not model_path.is_file():
                raise RuntimeError(f"MediaPipe hand model not found: {model_path}")
            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.55,
                min_hand_presence_confidence=0.55,
                min_tracking_confidence=0.55,
            )
            self.hands = mp.tasks.vision.HandLandmarker.create_from_options(options)
        else:
            self.hands = _legacy_hands(
                mp, self.inference_threads, self.tracking_confidence,
                self.detection_confidence,
                self.graph_mode, self.tracking_roi_scale,
                self.tracking_roi_shift_x, self.tracking_roi_shift_y,
                self.use_previous_landmarks,
                self.model_complexity,
                self.palm_inference_threads,
                self.tracking_roi_scale_x,
                self.tracking_roi_scale_y,
                self.tracking_evidence,
            )

        log_startup_stage("tracker construction", started)

    def close(self) -> None:
        """Release the underlying MediaPipe hand tracker."""
        self.hands.close()

    def process(self, frame: Any, timestamp: float | None = None) -> TrackingResult:
        """Track and annotate one frame, returning a neutral observation when no hand is found."""
        cv2 = self.cv2
        annotate = self.preview_enabled
        now = time.monotonic() if timestamp is None else timestamp
        frame, rgb, frame_preparation = _prepare_tracker_frame(
            frame, self.mirror, annotate, self.fused_preprocessing,
            cv2, self.numpy,
        )
        search_offset = (
            self._directional_search.next_offset(now)
            if self.directional_search and not self._tasks else (0.0, 0.0)
        )
        if search_offset != (0.0, 0.0):
            rgb = _translate_tracker_input(rgb, search_offset, cv2, self.numpy)
        inference_started = time.monotonic()
        if self._tasks:
            timestamp_ms = max(self._last_timestamp_ms + 1, int(now * 1000))
            self._last_timestamp_ms = timestamp_ms
            image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
            result = self.hands.detect_for_video(image, timestamp_ms)
            detected = result.hand_landmarks
        else:
            result = self.hands.process(rgb)
            detected = result.multi_hand_landmarks
        tracking_inference_ms = (time.monotonic() - inference_started) * 1000.0
        palm_detector_invoked, palm_detection_count = _palm_detector_evidence(result)
        hand_presence_score = _hand_presence_score_evidence(result)
        if not detected:
            if self.directional_search:
                self._directional_search.observe_missing()
            diagnostics = self._tracking_telemetry.observe(
                False, palm_detector_invoked, palm_detection_count,
                timestamp=now, inference_ms=tracking_inference_ms,
                hand_presence_score=hand_presence_score,
                include_cause_details=self.tracking_evidence,
            )
            diagnostics["frame_preparation"] = frame_preparation
            diagnostics["directional_search_active"] = self._directional_search.active
            diagnostics["directional_search_offset"] = search_offset
            diagnostics["directional_search_phase"] = self._directional_search.phase
            if not annotate:
                return TrackingResult(HandObservation(now, False), frame, diagnostics)
            return TrackingResult(
                HandObservation(now, False), frame, diagnostics,
            )

        if self._tasks:
            landmarks = result.hand_landmarks[0]
            handedness = result.handedness[0][0]
            hand_label = handedness.category_name or "Hand"
            hand_score = float(handedness.score or 0.0)
        else:
            landmarks = result.multi_hand_landmarks[0].landmark
            if search_offset != (0.0, 0.0):
                for point in landmarks:
                    point.x -= search_offset[0]
                    point.y -= search_offset[1]
            handednesses = getattr(result, "multi_handedness", None)
            if handednesses:
                handedness = handednesses[0].classification[0]
                hand_label = handedness.label
                hand_score = float(handedness.score)
            else:
                hand_label = "Hand"
                hand_score = 1.0
        if not _landmarks_valid(landmarks):
            if self.directional_search:
                self._directional_search.observe_missing()
            diagnostics = self._tracking_telemetry.observe(
                False, palm_detector_invoked, palm_detection_count,
                invalid_landmarks=True,
                timestamp=now, inference_ms=tracking_inference_ms,
                hand_presence_score=hand_presence_score,
                include_cause_details=self.tracking_evidence,
            )
            diagnostics["frame_preparation"] = frame_preparation
            diagnostics["directional_search_active"] = self._directional_search.active
            diagnostics["directional_search_offset"] = search_offset
            diagnostics["directional_search_phase"] = self._directional_search.phase
            diagnostics["landmark_validation"] = "invalid"
            return TrackingResult(HandObservation(now, False), frame, diagnostics)
        palm_ids = (0, 5, 9, 13, 17)
        if self.diagnostics_enabled:
            palm_anchors = _palm_anchor_candidates(landmarks)
            palm_x, palm_y = palm_anchors[PALM_ANCHOR]
            palm_points = [(landmarks[i].x, landmarks[i].y) for i in palm_ids]
        else:
            # Gameplay needs only the calibration-compatible production anchor.
            # Avoid calculating three experimental alternatives on every frame.
            palm_x = sum(float(landmarks[i].x) for i in palm_ids) / len(palm_ids)
            palm_y = sum(float(landmarks[i].y) for i in palm_ids) / len(palm_ids)
            palm_anchors = {}
            palm_points = []
        if self.directional_search:
            self._directional_search.observe(palm_x, palm_y, now)
        palm_scale = (_distance(landmarks[0], landmarks[9]) + _distance(landmarks[5], landmarks[17])) / 2
        roll = math.atan2(
            landmarks[5].y - landmarks[17].y,
            landmarks[5].x - landmarks[17].x,
        )

        height, width = frame.shape[:2]
        curl_points = _camera_curl_points(result, landmarks, self._tasks, width, height)
        bends = _finger_bends(curl_points)
        curls = _finger_curls_from_bends(bends)
        observation = HandObservation(
            timestamp=now,
            detected=True,
            confidence=hand_score,
            confidence_source=(
                "landmark_presence" if self.graph_mode == "lean-image" else "handedness"
            ),
            palm_x=palm_x,
            palm_y=palm_y,
            palm_scale=palm_scale,
            roll=roll,
            **_finger_spreads(curl_points),
            **_start_curls_from_bends(bends),
            **curls,
        )
        preview_overlay = {}
        if annotate:
            preview_overlay = {
                "connections": CONNECTIONS,
                "landmarks": [(float(point.x), float(point.y)) for point in landmarks],
            }
        diagnostics = self._tracking_telemetry.observe(
            True, palm_detector_invoked, palm_detection_count,
            timestamp=now, inference_ms=tracking_inference_ms,
            hand_presence_score=hand_presence_score,
            include_cause_details=self.tracking_evidence,
        )
        diagnostics["frame_preparation"] = frame_preparation
        diagnostics["directional_search_active"] = self._directional_search.active
        diagnostics["directional_search_offset"] = search_offset
        diagnostics["directional_search_phase"] = self._directional_search.phase
        if self.diagnostics_enabled:
            diagnostics.update({
                "tracker_backend": self.backend,
                "tracker_backend_label": self.backend_label,
                "tracker_graph": self.graph_mode,
                "palm_anchor": PALM_ANCHOR,
                "confidence_source": observation.confidence_source,
                "finger_bends": bends,
                "hand_landmarks": [[p.x, p.y] for p in landmarks],
            })
        return TrackingResult(observation, frame, diagnostics,
                              palm_points=palm_points,
                              palm_anchors=palm_anchors,
                              preview_overlay=preview_overlay)
