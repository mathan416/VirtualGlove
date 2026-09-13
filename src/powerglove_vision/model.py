# Project: VirtualGlove
# File: src/powerglove_vision/model.py
# Purpose: Define the hand-observation, calibration, and virtual-controller data models.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added a shallow signed-wire mapping for the latency-critical sender.
#   2026-09-07 - Distinguished validated MediaPipe landmarks from handedness certainty.
#   2026-09-06 - Preserve and map optional per-player comfortable reach spans.
#   2026-09-05 - Included neutral native hand-pose states in released samples.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
# Full history: docs/CHANGELOG.md and Git history.

"""Define the hand-observation, calibration, and virtual-controller data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


AXIS_MAX = 32767


@dataclass
class HandObservation:
    """Normalized measurements from one video frame."""

    timestamp: float
    detected: bool
    confidence: float = 0.0
    palm_x: float = 0.5
    palm_y: float = 0.5
    palm_scale: float = 0.0
    roll: float = 0.0
    thumb_curl: float = 0.0
    index_curl: float = 0.0
    middle_curl: float = 0.0
    ring_curl: float = 0.0
    pinky_curl: float = 0.0
    confidence_source: str = "generic"
    index_middle_spread: float = 0.0
    middle_ring_spread: float = 0.0
    ring_pinky_spread: float = 0.0

    @property
    def fingers(self) -> dict[str, float]:
        """Return curl measurements keyed by common finger name."""
        return {
            "thumb": self.thumb_curl,
            "index": self.index_curl,
            "middle": self.middle_curl,
            "ring": self.ring_curl,
            "pinky": self.pinky_curl,
        }

    @property
    def usable(self) -> bool:
        """Accept validated MediaPipe landmarks without misusing handedness certainty."""
        return self.detected and (
            self.confidence_source == "handedness" or self.confidence >= 0.70
        )


@dataclass
class Calibration:
    """Store neutral pose plus measured positional jitter around that pose."""
    palm_x: float
    palm_y: float
    palm_scale: float
    roll: float
    noise_x: float = 0.0
    noise_y: float = 0.0
    reach_left: float = 0.0
    reach_right: float = 0.0
    reach_up: float = 0.0
    reach_down: float = 0.0

    def valid_reach(self) -> bool:
        """Zero means legacy camera-field mapping; otherwise require four safe spans."""
        import math
        spans = (self.reach_left, self.reach_right, self.reach_up, self.reach_down)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in spans):
            return False
        return all(v == 0 for v in spans) or all(
            0.05 <= v <= limit + 1e-9 for v, limit in zip(
                spans, (self.palm_x, 1-self.palm_x, self.palm_y, 1-self.palm_y)))


@dataclass
class ControllerState:
    """Represent one complete, sequenced virtual-gamepad update."""
    sequence: int
    timestamp: float
    profile: str
    detected: bool
    confidence: float
    calibrated: bool
    axes: dict[str, int] = field(
        default_factory=lambda: {"x": 0, "y": 0, "z": 0, "roll": 0}
    )
    dpad: dict[str, bool] = field(
        default_factory=lambda: {
            "up": False,
            "down": False,
            "left": False,
            "right": False,
        }
    )
    buttons: dict[str, bool] = field(default_factory=dict)
    fingers: dict[str, int] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)

    def to_dict(self, token: str | None = None) -> dict[str, Any]:
        """Serialize the state with protocol metadata and an optional transport token."""
        result = asdict(self)
        result["protocol"] = "powerglove-vision/1"
        if token:
            result["token"] = token
        return result

    def to_transport_dict(self) -> dict[str, Any]:
        """Return the signed wire payload without recursive dataclass copying."""
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "profile": self.profile,
            "detected": self.detected,
            "confidence": self.confidence,
            "calibrated": self.calibrated,
            "axes": self.axes,
            "dpad": self.dpad,
            "buttons": self.buttons,
            "fingers": self.fingers,
            "events": self.events,
        }

    @classmethod
    def released(
        cls, sequence: int, timestamp: float, profile: str, calibrated: bool = False
    ) -> "ControllerState":
        """Create a neutral state that explicitly releases every supported control."""
        return cls(
            sequence=sequence,
            timestamp=timestamp,
            profile=profile,
            detected=False,
            confidence=0.0,
            calibrated=calibrated,
            buttons={
                "a": False, "b": False, "start": False, "select": False,
                "closed_hand": False, "index_point": False,
            },
            fingers={name: 0 for name in ("thumb", "index", "middle", "ring", "pinky")},
        )
