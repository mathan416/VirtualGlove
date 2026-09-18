# Project: VirtualGlove
# File: src/virtualglove/camera_profile.py
# Purpose: Build and score safe, image-free camera setting comparisons.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-10 - Added the guided camera-settings profiler.
# Full history: docs/CHANGELOG.md and Git history.

"""Pure helpers for the Setup camera profiler; no frames or secrets are retained."""

from __future__ import annotations

import math
from typing import Any, Iterable


PROFILE_FIELDS = (
    "camera_backend", "capture_isolation", "camera_fps", "camera_buffers",
    "camera_exposure",
)


def candidates(camera: dict[str, Any], current: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return portable comparisons, adding model-specific controls only when safe."""
    choices = []
    if current is not None:
        backend = current.get("camera_backend", "opencv")
        isolation = current.get("capture_isolation", "thread")
        exposure = current.get("camera_exposure", "auto")
        rate = current.get("camera_fps", 30)
        rate = 30 if rate == "auto" else rate
        buffers = current.get("camera_buffers", 1)
        if (backend in {"opencv", "direct-v4l2"}
                and isolation in {"thread", "process"}
                and exposure in {"auto", "low-latency", "kiyo-low-latency", "manual"}
                and rate in {30, 60} and buffers in {1, 2}):
            choices.append({
                "camera_backend": backend, "capture_isolation": isolation,
                "camera_fps": rate, "camera_buffers": buffers,
                "camera_exposure": exposure,
            })
    choices.extend([
        {"camera_backend": "opencv", "capture_isolation": "thread",
         "camera_fps": 30, "camera_buffers": 1, "camera_exposure": "auto"},
        {"camera_backend": "opencv", "capture_isolation": "thread",
         "camera_fps": 30, "camera_buffers": 2, "camera_exposure": "auto"},
        {"camera_backend": "opencv", "capture_isolation": "thread",
         "camera_fps": 60, "camera_buffers": 1, "camera_exposure": "auto"},
        {"camera_backend": "opencv", "capture_isolation": "thread",
         "camera_fps": 30, "camera_buffers": 1,
         "camera_exposure": "low-latency"},
    ])
    if camera.get("direct_v4l2"):
        choices.append({
            "camera_backend": "direct-v4l2", "capture_isolation": "thread",
            "camera_fps": 30, "camera_buffers": 1, "camera_exposure": "auto",
        })
    if camera.get("vendor_id") == "1532" and camera.get("product_id") == "0e05":
        choices.append({
            "camera_backend": "opencv", "capture_isolation": "thread",
            "camera_fps": 30, "camera_buffers": 1,
            "camera_exposure": "kiyo-low-latency",
        })
    unique = []
    seen = set()
    for choice in choices:
        key = tuple(choice[field] for field in PROFILE_FIELDS)
        if key not in seen:
            seen.add(key)
            unique.append(choice)
    return unique


def _percentile(values: Iterable[float], fraction: float) -> float | None:
    """Return the nearest-rank percentile for finite numeric observations."""
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return None
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize(settings: dict[str, Any], samples: list[dict[str, Any]],
              elapsed: float) -> dict[str, Any]:
    """Reduce status observations to comparable aggregate evidence."""
    unique: dict[int, dict[str, Any]] = {}
    errors = []
    for sample in samples:
        sequence = sample.get("sequence")
        if type(sequence) is int:
            unique[sequence] = sample
        if sample.get("vision_state") == "error":
            errors.append(str(sample.get("vision_error", "camera error")))
    rows = list(unique.values())
    detected = sum(bool(row.get("detected")) for row in rows)
    ages = [row["sample_age_ms"] for row in rows
            if type(row.get("sample_age_ms")) in (int, float)]
    inference = [row["inference_ms"] for row in rows
                 if type(row.get("inference_ms")) in (int, float)]
    coordinate_rates = [row["inference_hz"] for row in rows
                        if type(row.get("inference_hz")) in (int, float)]
    negotiated_rates = [row["camera_fps"] for row in rows
                        if type(row.get("camera_fps")) in (int, float)]
    fallback = next((row.get("capture_backend_fallback") for row in rows
                     if row.get("capture_backend_fallback")), None)
    wrong_reader = any(
        row.get("capture_backend") != settings["camera_backend"] for row in rows
    )
    exposure_unavailable = bool(
        settings["camera_exposure"] != "auto" and rows
        and not any(row.get("camera_exposure_applied") for row in rows)
    )
    negotiated = _percentile(negotiated_rates, .5)
    requested_rate = int(settings["camera_fps"])
    unsupported_rate = bool(
        negotiated is not None and requested_rate > 30
        and negotiated < requested_rate * .80
    )
    return {
        "settings": {field: settings[field] for field in PROFILE_FIELDS},
        "valid": bool(rows) and not errors and fallback is None
                 and not wrong_reader and not exposure_unavailable
                 and not unsupported_rate,
        "samples": len(rows),
        "coordinate_hz": _round(_percentile(coordinate_rates, .5)) if coordinate_rates else
                         round(len(rows) / max(.001, elapsed), 2),
        "continuity": round(detected / len(rows), 4) if rows else 0.0,
        "sample_age_p50_ms": _round(_percentile(ages, .5)),
        "sample_age_p95_ms": _round(_percentile(ages, .95)),
        "inference_p95_ms": _round(_percentile(inference, .95)),
        "negotiated_fps": _round(negotiated),
        "fallback": fallback,
        "error": (
            errors[-1] if errors else
            "The requested camera reader was not active."
            if wrong_reader else
            "The requested exposure control was unavailable."
            if exposure_unavailable else
            f"The camera delivered only {_round(negotiated)} fps."
            if unsupported_rate else None
        ),
    }


def _round(value: float | None) -> float | None:
    """Round an optional measurement for stable user-facing reports."""
    return None if value is None else round(value, 2)


def recommend(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select responsive settings without trading away measured continuity."""
    valid = [result for result in results
             if result.get("valid") and result.get("samples", 0) >= 8
             and result.get("continuity", 0.0) >= .80]
    if not valid:
        return None
    best_continuity = max(result["continuity"] for result in valid)
    safe = [result for result in valid
            if result["continuity"] >= best_continuity - .01]
    def ranking(result: dict[str, Any]) -> tuple[float, float, float, int]:
        """Prefer low tail age, then rate, continuity, and compatible OpenCV."""
        age = result.get("sample_age_p95_ms")
        age = 10_000.0 if age is None else float(age)
        return (
            age,
            -float(result.get("coordinate_hz", 0.0)),
            -float(result.get("continuity", 0.0)),
            0 if result["settings"]["camera_backend"] == "opencv" else 1,
        )
    return min(safe, key=ranking)


def display_name(settings: dict[str, Any]) -> str:
    """Return a compact family-facing candidate name."""
    reader = "OpenCV" if settings["camera_backend"] == "opencv" else "Direct V4L2"
    exposure = {
        "auto": "automatic exposure",
        "low-latency": "fixed-rate automatic exposure",
        "kiyo-low-latency": "Kiyo tested automatic exposure",
    }.get(settings["camera_exposure"], settings["camera_exposure"])
    buffers = settings["camera_buffers"]
    isolation = "separate reader, " if settings["capture_isolation"] == "process" else ""
    return (
        f"{reader}, {isolation}{settings['camera_fps']} fps, {exposure}, "
        f"{buffers} camera buffer{'s' if buffers != 1 else ''}"
    )
