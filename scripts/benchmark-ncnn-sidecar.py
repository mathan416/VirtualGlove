#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-ncnn-sidecar.py
# Purpose: Compare an isolated ncnn CPU hand-tracking sidecar with MediaPipe.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added exact-model palm, ROI, landmark, and replay comparison.
# Full history: docs/CHANGELOG.md and Git history.

"""Run the experimental ncnn CPU sidecar against a retained camera clip.

This tool never sends controller data and never changes the configured tracker.
It implements MediaPipe 0.10.18's documented single-hand palm-to-ROI flow in
Python while a persistent native process performs only the two ncnn inferences.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import time
from typing import Iterable


REQUEST = struct.Struct("<III")
RESPONSE = struct.Struct("<IIIII")
REQUEST_MAGIC = 0x50474E43
RESPONSE_MAGIC = 0x50474E52
PALM = 1
LANDMARK = 2
PALM_FLOATS = 2016 + 2016 * 18
LANDMARK_FLOATS = 63 + 1 + 1 + 63
PARTIAL_LANDMARKS = (0, 1, 2, 3, 5, 6, 9, 10, 13, 14, 17, 18)


@dataclasses.dataclass(frozen=True)
class Rect:
    """Rotated normalized image rectangle."""

    x: float
    y: float
    width: float
    height: float
    rotation: float


class NcnnWorker:
    """Exchange compact RGB images with one persistent native worker."""

    def __init__(self, executable: Path, models: Path, threads: int) -> None:
        self.process = subprocess.Popen(
            [str(executable), str(models), str(threads)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
        )

    @staticmethod
    def _read_exact(stream, count: int) -> bytes:
        """Read exactly one bounded sidecar record or report early closure."""
        chunks = bytearray()
        while len(chunks) < count:
            block = stream.read(count - len(chunks))
            if not block:
                raise RuntimeError("ncnn sidecar closed its output")
            chunks.extend(block)
        return bytes(chunks)

    def infer(self, operation: int, tensor):
        """Send one RGB tensor and return model output plus timing."""
        import numpy as np

        values = np.ascontiguousarray(tensor, dtype=np.uint8).reshape(-1)
        assert self.process.stdin is not None and self.process.stdout is not None
        started = time.monotonic_ns()
        self.process.stdin.write(REQUEST.pack(REQUEST_MAGIC, operation, values.size))
        self.process.stdin.write(values.tobytes())
        self.process.stdin.flush()
        response = RESPONSE.unpack(self._read_exact(self.process.stdout, RESPONSE.size))
        magic, returned_operation, status, count, inference_us = response
        if magic != RESPONSE_MAGIC or returned_operation != operation or status:
            raise RuntimeError(f"ncnn sidecar response failed: {response}")
        payload = self._read_exact(self.process.stdout, count * 4)
        roundtrip_ms = (time.monotonic_ns() - started) / 1e6
        return (np.frombuffer(payload, dtype="<f4").copy(),
                inference_us / 1000.0, roundtrip_ms)

    def close(self) -> None:
        """Stop the sidecar cleanly and surface native-process failures."""
        if self.process.poll() is None and self.process.stdin is not None:
            try:
                self.process.stdin.write(REQUEST.pack(REQUEST_MAGIC, 0, 0))
                self.process.stdin.flush()
            except BrokenPipeError:
                pass
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=3)
        if self.process.returncode:
            message = b"" if self.process.stderr is None else self.process.stderr.read()
            raise RuntimeError(
                f"ncnn sidecar exited {self.process.returncode}: "
                f"{message.decode(errors='replace')}"
            )


def _anchors():
    """Generate the 2,016 anchors used by the lite palm detector."""
    result = []
    strides = (8, 16, 16, 16)
    layer = 0
    while layer < len(strides):
        last = layer
        ratios = []
        while last < len(strides) and strides[last] == strides[layer]:
            ratios.extend((1.0, 1.0))
            last += 1
        size = math.ceil(192 / strides[layer])
        for y in range(size):
            for x in range(size):
                for _ in ratios:
                    result.append(((x + .5) / size, (y + .5) / size))
        layer = last
    if len(result) != 2016:
        raise RuntimeError(f"unexpected palm anchor count: {len(result)}")
    return result


ANCHORS = _anchors()


def palm_tensor(rgb, cv2, np):
    """Create the model's compact 192-square RGB image and letterbox metadata."""
    height, width = rgb.shape[:2]
    scale = min(192 / width, 192 / height)
    resized_width = max(1, int(width * scale))
    resized_height = max(1, int(height * scale))
    resized = cv2.resize(rgb, (resized_width, resized_height),
                         interpolation=cv2.INTER_LINEAR)
    left = (192 - resized_width) // 2
    top = (192 - resized_height) // 2
    image = np.zeros((192, 192, 3), dtype=np.uint8)
    image[top:top + resized_height, left:left + resized_width] = resized
    padding = (left / 192, top / 192,
               (192 - left - resized_width) / 192,
               (192 - top - resized_height) / 192)
    return image, padding


def _remove_letterbox(value: float, before: float, after: float) -> float:
    """Map one padded normalized coordinate back into source-image space."""
    return (value - before) / (1.0 - before - after)


def transform_rect(rect: Rect, image_size: tuple[int, int],
                   scale: float, shift_y: float) -> Rect:
    """Apply MediaPipe RectTransformationCalculator's square-long transform."""
    width_pixels = rect.width * image_size[0]
    height_pixels = rect.height * image_size[1]
    x_shift = (-height_pixels * shift_y * math.sin(rect.rotation)) / image_size[0]
    y_shift = (height_pixels * shift_y * math.cos(rect.rotation)) / image_size[1]
    long_side = max(width_pixels, height_pixels)
    return Rect(rect.x + x_shift, rect.y + y_shift,
                long_side * scale / image_size[0],
                long_side * scale / image_size[1], rect.rotation)


def palm_rect(scores, boxes, padding, image_size: tuple[int, int], threshold: float):
    """Decode the strongest palm and produce MediaPipe's landmark-input ROI."""
    import numpy as np

    probabilities = 1.0 / (1.0 + np.exp(-np.clip(scores, -80, 80)))
    index = int(np.argmax(probabilities))
    confidence = float(probabilities[index])
    if confidence < threshold:
        return None, confidence
    anchor_x, anchor_y = ANCHORS[index]
    values = boxes[index]
    center_x = values[0] / 192 + anchor_x
    center_y = values[1] / 192 + anchor_y
    box_width = values[2] / 192
    box_height = values[3] / 192
    points = []
    for point in range(7):
        points.append((values[4 + point * 2] / 192 + anchor_x,
                       values[5 + point * 2] / 192 + anchor_y))
    left, top, right, bottom = padding
    center_x = _remove_letterbox(center_x, left, right)
    center_y = _remove_letterbox(center_y, top, bottom)
    box_width /= 1.0 - left - right
    box_height /= 1.0 - top - bottom
    points = [(_remove_letterbox(x, left, right),
               _remove_letterbox(y, top, bottom)) for x, y in points]
    x0, y0 = points[0]
    x1, y1 = points[2]
    width, height = image_size
    rotation = normalize_angle(math.pi / 2 - math.atan2(
        -(y1 - y0) * height, (x1 - x0) * width))
    return transform_rect(
        Rect(center_x, center_y, box_width, box_height, rotation),
        image_size, 2.6, -.5,
    ), confidence


def normalize_angle(value: float) -> float:
    """Wrap an angle into MediaPipe's -pi..pi interval."""
    return value - 2 * math.pi * math.floor((value + math.pi) / (2 * math.pi))


def _roi_points(rect: Rect, image_size: tuple[int, int]):
    """Return three source points defining a rotated landmark crop."""
    width, height = image_size
    cx, cy = rect.x * width, rect.y * height
    rw, rh = rect.width * width, rect.height * height
    cosine, sine = math.cos(rect.rotation), math.sin(rect.rotation)
    result = []
    for u, v in ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)):
        dx, dy = (u - .5) * rw, (v - .5) * rh
        result.append((cx + cosine * dx - sine * dy,
                       cy + sine * dx + cosine * dy))
    return result


def landmark_tensor(rgb, rect: Rect, cv2, np):
    """Warp the selected rotated ROI to a compact 224-square RGB image."""
    source = np.asarray(_roi_points(rect, (rgb.shape[1], rgb.shape[0])), np.float32)
    destination = np.asarray(((0, 0), (224, 0), (0, 224)), np.float32)
    matrix = cv2.getAffineTransform(source, destination)
    crop = cv2.warpAffine(rgb, matrix, (224, 224), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return crop


def project_landmarks(raw, rect: Rect, image_size: tuple[int, int]):
    """Decode and project 21 model landmarks into normalized image space."""
    import numpy as np

    local = np.asarray(raw, dtype=np.float32).reshape(21, 3).copy()
    local[:, 0] /= 224.0
    local[:, 1] /= 224.0
    local[:, 2] /= 224.0 * .4
    width, height = image_size
    cosine, sine = math.cos(rect.rotation), math.sin(rect.rotation)
    output = np.empty_like(local)
    dx = (local[:, 0] - .5) * rect.width * width
    dy = (local[:, 1] - .5) * rect.height * height
    output[:, 0] = (rect.x * width + cosine * dx - sine * dy) / width
    output[:, 1] = (rect.y * height + sine * dx + cosine * dy) / height
    output[:, 2] = local[:, 2] * rect.width
    return output


def tracked_rect(landmarks, image_size: tuple[int, int], scale: float) -> Rect:
    """Reproduce HandLandmarksToRect plus the configured next-frame expansion."""
    import numpy as np

    points = np.asarray(landmarks, dtype=np.float64)[list(PARTIAL_LANDMARKS), :2]
    width, height = image_size
    wrist = points[0] * (width, height)
    finger_center = ((points[4] + points[8]) / 2 + points[6]) / 2 * (width, height)
    rotation = normalize_angle(math.pi / 2 - math.atan2(
        -(finger_center[1] - wrist[1]), finger_center[0] - wrist[0]))
    axis_center = (points.max(axis=0) + points.min(axis=0)) / 2
    centered = (points - axis_center) * (width, height)
    cosine, sine = math.cos(-rotation), math.sin(-rotation)
    rotated = np.column_stack((
        centered[:, 0] * cosine - centered[:, 1] * sine,
        centered[:, 0] * sine + centered[:, 1] * cosine,
    ))
    minimum, maximum = rotated.min(axis=0), rotated.max(axis=0)
    projected_center = (maximum + minimum) / 2
    cosine, sine = math.cos(rotation), math.sin(rotation)
    center_pixels = (
        projected_center[0] * cosine - projected_center[1] * sine
        + axis_center[0] * width,
        projected_center[0] * sine + projected_center[1] * cosine
        + axis_center[1] * height,
    )
    rect = Rect(center_pixels[0] / width, center_pixels[1] / height,
                (maximum[0] - minimum[0]) / width,
                (maximum[1] - minimum[1]) / height, rotation)
    return transform_rect(rect, image_size, scale, -.1)


class NcnnTracker:
    """Single-hand ncnn tracker matching the production graph's control flow."""

    def __init__(self, worker: NcnnWorker, cv2, np,
                 detection_threshold: float = .55,
                 presence_threshold: float = .35,
                 tracking_roi_scale: float = 2.25) -> None:
        self.worker, self.cv2, self.np = worker, cv2, np
        self.detection_threshold = detection_threshold
        self.presence_threshold = presence_threshold
        self.tracking_roi_scale = tracking_roi_scale
        self.rect = None
        self.palm_runs = 0

    def process(self, bgr):
        """Process one BGR frame through palm detection and landmark tracking."""
        started = time.monotonic_ns()
        rgb = self.cv2.cvtColor(self.cv2.flip(bgr, 1), self.cv2.COLOR_BGR2RGB)
        image_size = (rgb.shape[1], rgb.shape[0])
        palm_ms = 0.0
        landmark_ms = 0.0
        roundtrip_ms = 0.0
        palm_invoked = self.rect is None
        if palm_invoked:
            tensor, padding = palm_tensor(rgb, self.cv2, self.np)
            output, palm_ms, palm_roundtrip_ms = self.worker.infer(PALM, tensor)
            roundtrip_ms += palm_roundtrip_ms
            self.palm_runs += 1
            scores, boxes = output[:2016], output[2016:].reshape(2016, 18)
            self.rect, palm_score = palm_rect(
                scores, boxes, padding, image_size, self.detection_threshold)
            if self.rect is None:
                return None, dict(total_ms=(time.monotonic_ns() - started) / 1e6,
                                  model_ms=palm_ms, palm_ms=palm_ms,
                                  landmark_ms=0.0, roundtrip_ms=roundtrip_ms,
                                  palm_invoked=True,
                                  palm_score=palm_score)
        tensor = landmark_tensor(rgb, self.rect, self.cv2, self.np)
        output, landmark_ms, landmark_roundtrip_ms = self.worker.infer(LANDMARK, tensor)
        roundtrip_ms += landmark_roundtrip_ms
        landmarks = output[:63]
        presence = float(output[63])
        handedness = float(output[64])
        world = output[65:128].reshape(21, 3)
        if presence < self.presence_threshold or not self.np.isfinite(landmarks).all():
            self.rect = None
            return None, dict(total_ms=(time.monotonic_ns() - started) / 1e6,
                              model_ms=palm_ms + landmark_ms, palm_ms=palm_ms,
                              landmark_ms=landmark_ms, roundtrip_ms=roundtrip_ms,
                              palm_invoked=palm_invoked,
                              palm_score=None, presence=presence)
        projected = project_landmarks(landmarks, self.rect, image_size)
        self.rect = tracked_rect(projected, image_size, self.tracking_roi_scale)
        return projected, dict(total_ms=(time.monotonic_ns() - started) / 1e6,
                               model_ms=palm_ms + landmark_ms, palm_ms=palm_ms,
                               landmark_ms=landmark_ms, roundtrip_ms=roundtrip_ms,
                               palm_invoked=palm_invoked,
                               palm_score=None, presence=presence,
                               handedness=handedness, world_finite=bool(
                                   self.np.isfinite(world).all()))


def percentile(values: Iterable[float], fraction: float):
    """Return the nearest-rank percentile, or None for an empty lane."""
    values = sorted(values)
    if not values:
        return None
    return values[max(0, math.ceil(len(values) * fraction) - 1)]


def summarize(rows: list[dict]) -> dict:
    """Summarize a replay lane after its first ten warm-up frames."""
    rows = rows[10:]
    detected = [row for row in rows if row["detected"]]
    result = {
        "frames": len(rows),
        "detected_frames": len(detected),
        "continuity_percent": 100 * len(detected) / len(rows) if rows else 0,
    }
    for field in ("total_ms", "model_ms", "roundtrip_ms", "palm_ms", "landmark_ms"):
        values = [row[field] for row in rows if row.get(field) is not None]
        result[field] = {
            "p50": percentile(values, .5), "p95": percentile(values, .95),
            "mean": statistics.fmean(values) if values else None,
        }
    result["palm_invocations"] = sum(bool(row.get("palm_invoked")) for row in rows)
    return result


def replay_ncnn(path: Path, tracker: NcnnTracker, max_frames: int):
    """Replay a bounded clip and retain aggregate-ready research records."""
    capture = tracker.cv2.VideoCapture(str(path))
    rows = []
    try:
        while len(rows) < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            landmarks, timing = tracker.process(frame)
            anchor = None
            if landmarks is not None:
                palm = landmarks[[0, 5, 9, 13, 17], :2].mean(axis=0)
                anchor = [float(palm[0]), float(palm[1])]
            rows.append({"detected": landmarks is not None,
                         "anchor": anchor, **timing})
    finally:
        capture.release()
    return rows


def main() -> None:
    """Parse an output-paused ncnn comparison and write its new report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--threads", type=int, choices=(1, 2, 4), default=4)
    parser.add_argument("--max-frames", type=int, default=600)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must name a new file")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    import cv2
    import numpy as np

    worker = NcnnWorker(args.sidecar, args.models, args.threads)
    try:
        tracker = NcnnTracker(worker, cv2, np)
        rows = replay_ncnn(args.clip, tracker, args.max_frames)
        report = {
            "format": "virtualglove-ncnn-sidecar-benchmark/1",
            "clip": str(args.clip),
            "threads": args.threads,
            "detection_threshold": tracker.detection_threshold,
            "presence_threshold": tracker.presence_threshold,
            "tracking_roi_scale": tracker.tracking_roi_scale,
            "summary": summarize(rows),
            "rows": rows,
            "limitations": [
                "Research-only replay; controller output is never armed.",
                "This first report measures ncnn alone; paired MediaPipe replay follows only after geometric continuity passes.",
                "The sidecar sends compact RGB images through a persistent pipe; shared-memory transport is deferred.",
            ],
        }
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps(report["summary"], indent=2, allow_nan=False))
    finally:
        worker.close()


if __name__ == "__main__":
    main()
