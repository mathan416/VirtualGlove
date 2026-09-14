# Project: VirtualGlove
# File: src/powerglove_vision/gesture.py
# Purpose: Convert calibrated hand observations into stable gamepad states for supported gesture profiles.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Kept zero-noise engineering simulations finite and deterministic.
#   2026-09-10 - Bridged one extra native X/Y inference gap without extending actions.
#   2026-09-07 - Made bounded native X/Y coherent, edge-clamped, and noise-aware.
#   2026-09-07 - Corrected native smoothing cadence and saturated legacy jitter handling.
#   2026-09-06 - Preserve and map optional per-player comfortable reach spans.
#   2026-09-06 - Add opt-in independent native hand movement tracking.
#   2026-09-05 - Published native fist and index-point poses for Super Glove Ball.
#   2026-09-05 - Added motion-confirmed depth gestures and a faster deliberate Start hold.
#   2026-09-05 - Eased Menu Guard entry without loosening general finger recognition.
#   2026-09-05 - Eased the default thumb-only B pose without changing other fingers.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Corrected Program I throttle and turbo output for Knight Rider.
#   2026-09-03 - Persist and restore neutral-hand calibration.

"""Convert calibrated hand observations into stable gamepad states for supported gesture profiles."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from collections import deque
from dataclasses import asdict, dataclass, field, replace

from .model import AXIS_MAX, Calibration, ControllerState, HandObservation


def load_calibration(path: Path) -> Calibration | None:
    """Read a finite, versioned neutral reference; reject missing or corrupt data."""
    try:
        data = json.loads(path.read_text())
        if data["version"] not in (1, 2):
            return None
        neutral = data["neutral"]
        value = Calibration(
            palm_x=neutral["palm_x"], palm_y=neutral["palm_y"],
            palm_scale=neutral["palm_scale"], roll=neutral["roll"],
            noise_x=neutral.get("noise_x", 0.0), noise_y=neutral.get("noise_y", 0.0),
            **{k: neutral.get(k, 0.0) for k in ("reach_left", "reach_right", "reach_up", "reach_down")},
        )
        if not all(type(v) in (int, float) and math.isfinite(v) for v in asdict(value).values()):
            return None
        if (not value.valid_reach() or value.palm_scale <= 0 or not 0 <= value.noise_x <= 1
                or not 0 <= value.noise_y <= 1):
            return None
        return value
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save_calibration(path: Path, calibration: Calibration) -> None:
    """Atomically persist a completed reference without truncating the previous one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
            name = handle.name
            json.dump({"version": 2, "neutral": asdict(calibration)}, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


NUMBER_PROGRAM_PROFILES = tuple(f"program_{number}" for number in range(1, 15))
LETTER_PROGRAM_PROFILES = tuple(f"program_{letter}" for letter in "abcdefghi")
PROGRAM_PROFILES = NUMBER_PROGRAM_PROFILES + LETTER_PROGRAM_PROFILES
GAME_PROFILES = ("bad_street_brawler", "super_glove_ball")
SUPPORTED_PROFILES = PROGRAM_PROFILES + GAME_PROFILES
RECOGNITION_PROFILES = SUPPORTED_PROFILES + ("practice",)
PROGRAM_12_JUMP_SECONDS = 0.25


def rapid_fire_defaults(profile: str) -> tuple[bool, bool]:
    """Return A/B pulse defaults explicitly documented for this profile."""
    return {
        "program_7": (True, False),
        "program_b": (True, False),
        "program_h": (True, True),
        "bad_street_brawler": (False, True),
    }.get(profile, (False, False))


@dataclass(frozen=True)
class GestureConfig:
    """Hold movement, curl, roll, depth, pulse, and tracking-loss thresholds."""
    # Full-frame width and height of the centered joystick region.
    joystick_deadzone: float = 0.60
    coordinate_edge_margin: float = 0.08
    coordinate_smoothing_min: float = 0.70
    coordinate_smoothing_max: float = 1.00
    coordinate_motion_boost: float = 4.00
    # Native X/Y speed curve. Calibration noise is converted back to camera
    # units and multiplied by this value; the fixed floor covers legacy
    # calibrations that did not retain a useful jitter measurement.
    motion_noise_multiplier: float = 1.25
    motion_noise_floor: float = 0.003
    motion_noise_exit_ratio: float = 1.50
    # Weight used just beyond the noise floor. It rises smoothly to one at the
    # configured number of calibrated reach spans per second. The reference
    # interval matches the proven MediaPipe inference cadence on the Controller;
    # it prevents a 10 Hz observation from being treated as six 60 Hz updates.
    motion_slow_follow: float = 0.55
    motion_full_speed: float = 2.50
    motion_follow_reference_ms: float = 100.0
    # Latest-coordinate mode normally publishes MediaPipe verbatim. Following
    # a brief dropout only, one contradictory or unusually distant result is
    # held for confirmation instead of exposing a reacquisition jump.
    native_recovery_max_ms: float = 250.0
    native_recovery_min_step: float = 0.015
    native_recovery_alignment: float = 0.50
    native_recovery_max_jump: float = 0.25
    native_recovery_forward_alignment: float = 0.90
    curl_on: float = 0.50
    curl_off: float = 0.35
    thumb_on: float = 0.38
    thumb_off: float = 0.28
    roll_on: float = 0.58
    roll_off: float = 0.40
    push_on: float = 0.34
    push_off: float = 0.18
    depth_confirm_frames: int = 2
    depth_motion_window_ms: int = 250
    depth_motion_delta: float = 0.10
    pulse_hz: float = 7.0
    loss_release_ms: int = 120
    # Native continuous X/Y may retain its last visible position for one extra
    # inference interval during a fast sweep. Actions still release using the
    # shorter general loss guard above, and reacquisition remains unchanged.
    native_xy_loss_hold_ms: int = 180
    thresholds: dict = field(default_factory=dict)

    def pair(self, channel: str) -> tuple[float, float]:
        """Resolve independent personal thresholds over existing profile defaults."""
        if channel in self.thresholds:
            value = self.thresholds[channel]
            return value["on"], value["off"]
        prefix = ("thumb" if channel == "thumb" else
                  "roll" if channel.startswith("roll_") else
                  "push" if channel in ("push", "pull") else "curl")
        return getattr(self, prefix + "_on"), getattr(self, prefix + "_off")

    def menu_limit(self, finger: str, closed: bool, default: float) -> float:
        """Keep legacy menu cutoffs until this finger has a personal adjustment."""
        return self.pair(finger)[0 if closed else 1] if finger in self.thresholds else default

    def chosen_joystick_deadzone(self) -> float:
        """Return the configured scalar centre-box size."""
        return self.joystick_deadzone

    def effective_joystick_deadzone(self, calibration: Calibration) -> float:
        """Return the frame fraction after the calibrated hand-size safety floor."""
        return min(1.0, max(
            self.chosen_joystick_deadzone(),
            1.5 * calibration.palm_scale,
        ))


def joystick_deadzone_bounds(config: GestureConfig, calibration: Calibration):
    """Return one square centered on saved neutral, translated intact into frame."""
    size = config.effective_joystick_deadzone(calibration)
    half = size / 2
    center_x = _clamp(calibration.palm_x, half, 1 - half)
    center_y = _clamp(calibration.palm_y, half, 1 - half)
    return {
        "center_x": center_x,
        "center_y": center_y,
        "half_size": half,
        "left": center_x - half,
        "right": center_x + half,
        "top": center_y - half,
        "bottom": center_y + half,
    }


MENU_FINGERS = {
    "start": {"index": False, "middle": False, "ring": True, "pinky": True},
    "select": {"thumb": False, "index": True, "middle": True, "ring": True, "pinky": True},
}
MENU_GUARD_FINGERS = {
    "thumb": True, "index": False, "middle": False, "ring": True, "pinky": False,
}
MENU_GUARD_ON = {"thumb": 0.26, "ring": 0.44}
MENU_GUARD_OFF = {"thumb": 0.20, "ring": 0.35}


def vulcan_salute_pose(observation: HandObservation) -> bool:
    """Recognize an open hand with a deliberate middle/ring finger split."""
    if not observation.usable:
        return False
    if any(value > 0.32 for value in observation.fingers.values()):
        return False
    neighbours = max(observation.index_middle_spread,
                     observation.ring_pinky_spread, 0.01)
    return (
        observation.middle_ring_spread >= 0.50
        and observation.middle_ring_spread >= neighbours * 1.65
        and observation.index_middle_spread <= 0.60
        and observation.ring_pinky_spread <= 0.60
    )


def finger_pose_feedback(config, gesture, requirements, values):
    """Use the same finger boundaries for menu recognition and tuning feedback."""
    feedback = {}
    for finger, closed in requirements.items():
        if finger not in ("thumb", "index", "middle", "ring", "pinky"):
            continue
        value = values.get(finger)
        if gesture in MENU_FINGERS:
            limit = config.menu_limit(finger, closed, .42 if closed else .32 if finger == "thumb" else .28)
            matches = value is not None and (value > limit if closed else value < limit)
        elif gesture == "menu_guard" and closed and finger not in config.thresholds:
            # A compound guard can accept a comfortable curl while its exact
            # three-fingers-open shape keeps it distinct from V and a fist.
            limit = MENU_GUARD_ON[finger]
            matches = value is not None and value >= limit
        else:
            limit = config.pair(finger)[0 if closed else 1]
            matches = value is not None and (value >= limit if closed else value < limit)
        feedback[finger] = {"expected": "curled" if closed else "extended",
                            "matches": bool(matches), "value": value, "threshold": limit}
    return feedback


def _clamp(value: float, low: float, high: float) -> float:
    """Limit a floating-point value to an inclusive range."""
    return max(low, min(high, value))


def _axis(value: float) -> int:
    """Convert a normalized signed value to the virtual gamepad axis range."""
    return round(_clamp(value, -1.0, 1.0) * AXIS_MAX)


def _field_axis(position: float, center: float, margin: float,
                negative_span: float = 0.0, positive_span: float = 0.0) -> int:
    """Map comfortable reach to full range, or use legacy camera boundaries."""
    return _axis(_field_coordinate(
        position, center, margin, negative_span, positive_span
    ))


def _field_coordinate(position: float, center: float, margin: float,
                      negative_span: float = 0.0, positive_span: float = 0.0) -> float:
    """Map and clamp one camera coordinate to the normalized gameplay field."""
    if negative_span >= 0.05 and positive_span >= 0.05:
        return _clamp(
            (position - center) / (negative_span if position < center else positive_span),
            -1.0, 1.0,
        )
    edge = _clamp(margin, 0.0, 0.45)
    span = center - edge if position < center else 1.0 - edge - center
    return _clamp((position - center) / max(0.05, span), -1.0, 1.0)


def _camera_coordinate(field: float, center: float, margin: float,
                       negative_span: float = 0.0, positive_span: float = 0.0) -> float:
    """Convert one clamped gameplay coordinate back to camera space."""
    if negative_span >= 0.05 and positive_span >= 0.05:
        span = negative_span if field < 0 else positive_span
    else:
        edge = _clamp(margin, 0.0, 0.45)
        span = center - edge if field < 0 else 1.0 - edge - center
    return center + _clamp(field, -1.0, 1.0) * max(0.05, span)


def _circular_delta(value: float, origin: float) -> float:
    """Return the shortest signed angular difference in radians."""
    return math.atan2(math.sin(value - origin), math.cos(value - origin))


class Hysteresis:
    """Track one threshold with separate activation and release points."""
    def __init__(self) -> None:
        self.active = False

    def positive(self, value: float, on: float, off: float) -> bool:
        """Update and return the positive-direction threshold state."""
        self.active = value >= (off if self.active else on)
        return self.active

    def negative(self, value: float, on: float, off: float) -> bool:
        """Update and return the negative-direction threshold state."""
        self.active = value <= -(off if self.active else on)
        return self.active


class HeldGesture:
    """Turns a deliberately held pose into one short button pulse."""

    def __init__(
        self,
        hold_seconds: float = 0.15,
        pulse_seconds: float = 0.18,
        release_seconds: float = 0.0,
    ) -> None:
        self.hold_seconds = hold_seconds
        self.pulse_seconds = pulse_seconds
        self.release_seconds = release_seconds
        self.started_at: float | None = None
        self.release_started_at: float | None = None
        self.pulse_until = 0.0
        self.fired = False

    def update(self, matches: bool, now: float) -> bool:
        """Return a short pulse after a pose remains stable for the configured hold time."""
        if not matches:
            self.started_at = None
            if self.fired and self.release_seconds > 0:
                if self.release_started_at is None:
                    self.release_started_at = now
                elif now - self.release_started_at >= self.release_seconds:
                    self.fired = False
                    self.release_started_at = None
            else:
                self.fired = False
                self.release_started_at = None
            return now < self.pulse_until
        self.release_started_at = None
        if self.fired:
            return now < self.pulse_until
        if self.started_at is None:
            self.started_at = now
        if not self.fired and now - self.started_at >= self.hold_seconds:
            self.fired = True
            self.pulse_until = now + self.pulse_seconds
        return now < self.pulse_until

    def cancel(self) -> None:
        """Discard both a forming pose and any pulse that is still active."""
        self.started_at = None
        self.release_started_at = None
        self.pulse_until = 0.0
        self.fired = False


class GestureEngine:
    """Turns continuous landmark measurements into stable controller state."""

    def __init__(
        self,
        profile: str,
        config: GestureConfig | None = None,
        calibration_frames: int = 24,
        calibration: Calibration | None = None,
        rapid_a: bool | None = None,
        rapid_b: bool | None = None,
    ) -> None:
        if profile not in RECOGNITION_PROFILES:
            raise ValueError(f"unknown profile: {profile}")
        if rapid_a is not None and type(rapid_a) is not bool:
            raise ValueError("rapid_a must be a boolean")
        if rapid_b is not None and type(rapid_b) is not bool:
            raise ValueError("rapid_b must be a boolean")
        self.profile = profile
        self.config = config or GestureConfig()
        default_rapid_a, default_rapid_b = rapid_fire_defaults(profile)
        self.rapid_a = default_rapid_a if rapid_a is None else rapid_a
        self.rapid_b = default_rapid_b if rapid_b is None else rapid_b
        self.calibration_frames = calibration_frames
        self.calibration = calibration
        self._samples: deque[HandObservation] = deque(maxlen=calibration_frames)
        self._calibrating = calibration is None
        self._sequence = 0
        self._last_seen = 0.0
        self._last_state: ControllerState | None = None
        self._filtered_palm_x: float | None = None
        self._filtered_palm_y: float | None = None
        self._motion_time: float | None = None
        self._motion_raw_x: float | None = None
        self._motion_raw_y: float | None = None
        self._motion_anchor_x: float | None = None
        self._motion_anchor_y: float | None = None
        self._motion_direction_x = 0
        self._motion_direction_y = 0
        self._motion_moving_x = False
        self._motion_moving_y = False
        self._latest_history: deque[tuple[float, float, float]] = deque(maxlen=3)
        self._latest_recovery_pending = False
        self._latest_confirmation_pending = False
        self._push_was_active = False
        self._pull_was_active = False
        self._depth_history: deque[tuple[float, float]] = deque(maxlen=32)
        self._push_candidate_frames = 0
        self._pull_candidate_frames = 0
        self._push_motion = 0.0
        self._pull_motion = 0.0
        self._program_toggle = False
        self._program_ready = profile != "program_9"
        self._last_horizontal: str | None = None
        self._program_action_started: float | None = None
        self._program_pose_was_active = False
        self._program_action_until = 0.0
        self._zap_until = 0.0
        # Start is especially disruptive during play. Require a deliberate V
        # hold, then a sustained non-V release before allowing another pulse.
        self._start_gesture = HeldGesture(hold_seconds=0.50, release_seconds=0.30)
        self._select_gesture = HeldGesture()
        self._program_12_rapid_started_at: float | None = None
        self._menu_guard_active = False
        self._vulcan_candidate_at: float | None = None
        self._vulcan_release_at: float | None = None
        self._vulcan_last_trigger = float("-inf")
        self._vulcan_armed = True
        self._vulcan_sequence = 0
        self._switches = {
            name: Hysteresis()
            for name in (
                # Direction switches remain as current-value holders for
                # Programs F/I; joystick classification itself is stateless.
                "left",
                "right",
                "up",
                "down",
                "thumb",
                "index",
                "middle",
                "ring",
                "pinky",
                "roll_left",
                "roll_right",
                "pull",
            )
        }

    @property
    def calibrated(self) -> bool:
        """Return whether a complete neutral-hand calibration is active."""
        return self.calibration is not None and not self._calibrating

    def begin_calibration(self) -> None:
        """Clear prior samples and begin a fresh neutral-hand calibration."""
        self._samples.clear()
        for switch in self._switches.values():
            switch.active = False
        self._calibrating = True
        self._push_was_active = False
        self._pull_was_active = False
        self._reset_depth_candidates(clear_active=True)
        self._program_toggle = False
        self._program_ready = self.profile != "program_9"
        self._last_horizontal = None
        self._program_action_started = None
        self._program_pose_was_active = False
        self._program_action_until = 0.0
        self._zap_until = 0.0
        self._program_12_rapid_started_at = None
        self._menu_guard_active = False
        self._vulcan_candidate_at = None
        self._vulcan_release_at = None
        self._vulcan_armed = True
        self._filtered_palm_x = None
        self._filtered_palm_y = None
        self._reset_native_motion()

    def _reset_native_motion(self, keep_latest_recovery: bool = False) -> None:
        """Discard native curve history without changing recognition state."""
        self._motion_time = None
        self._motion_raw_x = self._motion_raw_y = None
        self._motion_anchor_x = self._motion_anchor_y = None
        self._motion_direction_x = self._motion_direction_y = 0
        self._motion_moving_x = self._motion_moving_y = False
        self._motion_settle_pending = False
        if not keep_latest_recovery:
            self._latest_history.clear()
            self._latest_recovery_pending = False
            self._latest_confirmation_pending = False

    def _latest_point(
        self, x: float, y: float, timestamp: float, reference: Calibration
    ) -> tuple[float, float]:
        """Publish Latest verbatim except for one ambiguous reacquisition hold."""
        cfg = self.config
        if self._latest_confirmation_pending:
            # Two consecutive recovered measurements are enough to confirm a
            # real reversal or a new location. Accept the newest one verbatim.
            self._latest_confirmation_pending = False
            self._latest_history.clear()
            self._latest_history.append((timestamp, x, y))
            return x, y
        if not self._latest_recovery_pending:
            self._latest_history.append((timestamp, x, y))
            return x, y

        history = tuple(self._latest_history)
        self._latest_recovery_pending = False
        self._latest_history.clear()
        if not history:
            self._latest_history.append((timestamp, x, y))
            return x, y

        last = history[-1]
        reach_x = self._native_axis_reach("x", x - last[1], reference)
        reach_y = self._native_axis_reach("y", y - last[2], reference)
        recovered = ((x - last[1]) / reach_x, (y - last[2]) / reach_y)
        recovered_size = math.hypot(*recovered)
        unusually_distant = recovered_size > cfg.native_recovery_max_jump
        if len(history) < 3:
            if unusually_distant:
                self._latest_confirmation_pending = True
                self._latest_history.append(last)
                return last[1], last[2]
            self._latest_history.append((timestamp, x, y))
            return x, y

        first, middle, last = history
        dt_first = middle[0] - first[0]
        dt_last = last[0] - middle[0]
        gap_ms = (timestamp - last[0]) * 1000
        if (dt_first <= 0 or dt_last <= 0 or gap_ms < 0
                or gap_ms > cfg.native_recovery_max_ms):
            self._latest_history.append((timestamp, x, y))
            return x, y

        reach_x = self._native_axis_reach("x", last[1] - middle[1], reference)
        reach_y = self._native_axis_reach("y", last[2] - middle[2], reference)
        first_step = ((middle[1] - first[1]) / reach_x,
                      (middle[2] - first[2]) / reach_y)
        last_step = ((last[1] - middle[1]) / reach_x,
                     (last[2] - middle[2]) / reach_y)
        first_size = math.hypot(*first_step)
        last_size = math.hypot(*last_step)
        alignment = (
            (first_step[0] * last_step[0] + first_step[1] * last_step[1])
            / max(1e-9, first_size * last_size)
        )
        established = (
            min(first_size, last_size) >= cfg.native_recovery_min_step
            and alignment >= cfg.native_recovery_alignment
        )
        contradictory = False
        aligned_forward = False
        if established:
            direction = (last_step[0] / last_size, last_step[1] / last_size)
            recovered_forward = (
                recovered[0] * direction[0] + recovered[1] * direction[1]
            )
            contradictory = recovered_forward < -cfg.native_recovery_min_step
            aligned_forward = (
                recovered_forward / max(1e-9, recovered_size)
                >= cfg.native_recovery_forward_alignment
            )
        if not contradictory and (not unusually_distant or aligned_forward):
            self._latest_history.append((timestamp, x, y))
            return x, y

        # Do not invent a forward position or expose the questionable result.
        # Hold the last reliable coordinate for one result; the next fresh
        # measurement confirms either continued travel or a real reversal.
        self._latest_confirmation_pending = True
        self._latest_history.append(last)
        return last[1], last[2]

    @staticmethod
    def _smoothstep(value: float) -> float:
        """Return a bounded gradual transition from zero to one."""
        value = _clamp(value, 0.0, 1.0)
        return value * value * (3.0 - 2.0 * value)

    def _native_point(
        self, x: float, y: float, dt: float, reference: Calibration
    ) -> tuple[float, float]:
        """Filter a coherent X/Y point from raw velocity without overshoot."""
        cfg = self.config
        previous = (self._filtered_palm_x, self._filtered_palm_y)
        raw = (self._motion_raw_x, self._motion_raw_y)
        anchor = (self._motion_anchor_x, self._motion_anchor_y)
        if any(value is None for value in (*previous, *raw, *anchor)):
            self._motion_raw_x, self._motion_raw_y = x, y
            self._motion_anchor_x, self._motion_anchor_y = x, y
            self._motion_direction_x = self._motion_direction_y = 0.0
            self._motion_moving_x = self._motion_moving_y = False
            self._motion_settle_pending = False
            return x, y

        scale_noise_x, scale_noise_y = reference.noise_x, reference.noise_y
        # Calibration stores jitter in palm-width units and saturates unusably
        # noisy samples at 1.0. Older/saturated files are valid for centre and
        # scale, but 1.0 is not a useful native-motion noise estimate: using it
        # creates a large dead zone followed by a visible jump.
        if scale_noise_x >= 1.0:
            scale_noise_x = 0.0
        if scale_noise_y >= 1.0:
            scale_noise_y = 0.0
        noise_x = max(1e-9, cfg.motion_noise_floor,
                      scale_noise_x * reference.palm_scale * cfg.motion_noise_multiplier)
        noise_y = max(1e-9, cfg.motion_noise_floor,
                      scale_noise_y * reference.palm_scale * cfg.motion_noise_multiplier)
        delta_x, delta_y = x - raw[0], y - raw[1]
        anchor_x, anchor_y = x - anchor[0], y - anchor[1]
        delta_noise = math.hypot(delta_x / noise_x, delta_y / noise_y)
        anchor_noise = math.hypot(anchor_x / noise_x, anchor_y / noise_y)
        moving = self._motion_moving_x or self._motion_moving_y
        exit_ratio = max(1.0, cfg.motion_noise_exit_ratio)

        self._motion_raw_x, self._motion_raw_y = x, y
        if not moving and anchor_noise <= exit_ratio:
            return previous
        if not moving:
            moving = True

        reach_x = self._native_axis_reach("x", delta_x, reference)
        reach_y = self._native_axis_reach("y", delta_y, reference)
        direction_x, direction_y = delta_x / reach_x, delta_y / reach_y
        magnitude = math.hypot(direction_x, direction_y)
        old_x, old_y = self._motion_direction_x, self._motion_direction_y
        old_magnitude = math.hypot(old_x, old_y)
        reversal = (
            delta_noise > 1.0 and magnitude > 0 and old_magnitude > 0
            and direction_x * old_x + direction_y * old_y < 0
        )
        stopped = delta_noise <= 1.0
        if reversal:
            self._motion_anchor_x, self._motion_anchor_y = x, y
            self._motion_direction_x, self._motion_direction_y = direction_x, direction_y
            self._motion_moving_x = self._motion_moving_y = True
            self._motion_settle_pending = False
            return x, y

        if stopped:
            error_noise = math.hypot(
                (x - previous[0]) / noise_x,
                (y - previous[1]) / noise_y,
            )
            if self._motion_settle_pending or error_noise <= 1.0:
                result = (x, y)
                self._motion_anchor_x, self._motion_anchor_y = x, y
                self._motion_direction_x = self._motion_direction_y = 0.0
                self._motion_moving_x = self._motion_moving_y = False
                self._motion_settle_pending = False
                return result
            # Settle to the edge of measured noise now and finish on the next
            # fresh result, avoiding the old per-axis raw-coordinate snap.
            alpha = _clamp(1.0 - 1.0 / error_noise, 0.0, 1.0)
            self._motion_settle_pending = True
        else:
            speed = magnitude / max(dt, 1e-9)
            fraction = speed / max(cfg.motion_full_speed, 1e-9)
            slow = _clamp(cfg.motion_slow_follow, 0.0, 1.0)
            alpha = slow + (1.0 - slow) * self._smoothstep(fraction)
            reference_interval = max(1 / 240, cfg.motion_follow_reference_ms / 1000)
            alpha = 1.0 - (1.0 - alpha) ** (dt / reference_interval)
            alpha = _clamp(alpha, 0.0, 1.0)
            self._motion_settle_pending = False

        result_x = _clamp(previous[0] + alpha * (x - previous[0]),
                          min(previous[0], x), max(previous[0], x))
        result_y = _clamp(previous[1] + alpha * (y - previous[1]),
                          min(previous[1], y), max(previous[1], y))
        self._motion_moving_x = self._motion_moving_y = moving
        if not stopped and magnitude > 0:
            self._motion_direction_x, self._motion_direction_y = direction_x, direction_y
        return result_x, result_y

    def _native_axis_reach(
        self, axis: str, delta: float, reference: Calibration
    ) -> float:
        """Return the calibrated camera span in the current axis direction."""
        cfg = self.config
        if axis == "x":
            measured = reference.reach_right if delta >= 0 else reference.reach_left
            fallback = ((1.0 - cfg.coordinate_edge_margin - reference.palm_x)
                        if delta >= 0 else reference.palm_x - cfg.coordinate_edge_margin)
        else:
            measured = reference.reach_down if delta >= 0 else reference.reach_up
            fallback = ((1.0 - cfg.coordinate_edge_margin - reference.palm_y)
                        if delta >= 0 else reference.palm_y - cfg.coordinate_edge_margin)
        return max(0.05, measured if measured > 0 else fallback)

    def _collect_calibration(self, observation: HandObservation) -> None:
        """Accumulate valid frames and derive a stable neutral-hand reference."""
        # MediaPipe's exposed score describes handedness, not landmark quality.
        # Tracker geometry validation supplies its usability decision instead.
        if observation.usable and observation.palm_scale > 0.01:
            self._samples.append(observation)
        if len(self._samples) < self.calibration_frames:
            return
        count = len(self._samples)
        sin_roll = sum(math.sin(item.roll) for item in self._samples)
        cos_roll = sum(math.cos(item.roll) for item in self._samples)
        palm_x = sum(item.palm_x for item in self._samples) / count
        palm_y = sum(item.palm_y for item in self._samples) / count
        palm_scale = max(0.01, sum(item.palm_scale for item in self._samples) / count)
        percentile_index = max(0, math.ceil(count * .95) - 1)
        noise_x = sorted(abs(item.palm_x - palm_x) / palm_scale for item in self._samples)[percentile_index]
        noise_y = sorted(abs(item.palm_y - palm_y) / palm_scale for item in self._samples)[percentile_index]
        prior_reach = (
            {name: getattr(self.calibration, name) for name in (
                "reach_left", "reach_right", "reach_up", "reach_down"
            )}
            if self.calibration is not None else {}
        )
        candidate = Calibration(
            palm_x=palm_x,
            palm_y=palm_y,
            palm_scale=palm_scale,
            roll=math.atan2(sin_roll, cos_roll),
            noise_x=min(1.0, noise_x),
            noise_y=min(1.0, noise_y),
            **prior_reach,
        )
        # Re-centering measures neutral pose and jitter; it must not silently
        # discard a separately tuned comfortable reach. If the new centre made
        # an old endpoint geometrically unsafe, fall back to the full-field
        # mapping rather than persisting an invalid calibration.
        self.calibration = candidate if candidate.valid_reach() else replace(
            candidate, reach_left=0.0, reach_right=0.0,
            reach_up=0.0, reach_down=0.0,
        )
        self._calibrating = False
        # The completed neutral sample seeds the short motion window without
        # making first use depend on an otherwise unrelated extra frame.
        self._depth_history.append((observation.timestamp, 0.0))

    def curl_feedback(self, observation: HandObservation) -> dict:
        """Expose held finger switches to Learn, independent of game button pulses."""
        ready = self.calibrated and observation.detected
        return {name: bool(ready and self._switches[name].active)
                for name in ("thumb", "index", "middle", "ring", "pinky")}

    def push_feedback(self, observation: HandObservation) -> dict:
        """Expose continuous depth state so Learn cannot miss a one-frame push event."""
        ready = self.calibrated and observation.detected
        depth = observation.palm_scale / self.calibration.palm_scale - 1 if ready else 0.0
        return {"active": bool(ready and self._push_was_active),
                "depth": depth, "threshold": self.config.pair("push")[0],
                "candidate_frames": self._push_candidate_frames,
                "confirmation_frames": self.config.depth_confirm_frames,
                "motion": self._push_motion,
                "motion_required": self.config.depth_motion_delta}

    def pull_feedback(self, observation: HandObservation) -> dict:
        """Expose continuous pull recognition in Learn, independent of game mappings."""
        ready = self.calibrated and observation.detected
        depth = 1.0 - observation.palm_scale / self.calibration.palm_scale if ready else 0.0
        return {"active": bool(ready and self._switches["pull"].active),
                "depth": depth, "threshold": self.config.pair("pull")[0],
                "candidate_frames": self._pull_candidate_frames,
                "confirmation_frames": self.config.depth_confirm_frames,
                "motion": self._pull_motion,
                "motion_required": self.config.depth_motion_delta}

    def _reset_depth_candidates(self, clear_active: bool = False) -> None:
        """Discard unconfirmed depth motion and optionally neutralize confirmed states."""
        self._depth_history.clear()
        self._push_candidate_frames = 0
        self._pull_candidate_frames = 0
        self._push_motion = 0.0
        self._pull_motion = 0.0
        if clear_active:
            self._push_was_active = False
            self._switches["pull"].active = False

    def _update_depth(self, depth: float, timestamp: float) -> tuple[bool, bool]:
        """Confirm deliberate push/pull motion, then retain it with hysteresis."""
        cfg = self.config
        previous_depth = self._depth_history[-1][1] if self._depth_history else None
        self._depth_history.append((timestamp, depth))
        window_start = timestamp - max(0, cfg.depth_motion_window_ms) / 1000.0
        while self._depth_history and self._depth_history[0][0] < window_start:
            self._depth_history.popleft()
        depths = [value for _sample_at, value in self._depth_history]
        self._push_motion = max(0.0, depth - min(depths))
        self._pull_motion = max(0.0, max(depths) - depth)
        frames = max(1, int(cfg.depth_confirm_frames))
        reversal = max(0.001, cfg.depth_motion_delta / 4)

        push_on, push_off = cfg.pair("push")
        if self._push_was_active:
            pushing = depth >= push_off
            self._push_candidate_frames = 0
        else:
            if previous_depth is not None and depth < previous_depth - reversal:
                self._push_candidate_frames = 0
            if depth >= push_on:
                self._push_candidate_frames += 1
            else:
                self._push_candidate_frames = 0
            pushing = (
                self._push_candidate_frames >= frames
                and self._push_motion >= cfg.depth_motion_delta
            )

        pull_on, pull_off = cfg.pair("pull")
        pull_active = self._switches["pull"].active
        if pull_active:
            pulling = depth <= -pull_off
            self._pull_candidate_frames = 0
        else:
            if previous_depth is not None and depth > previous_depth + reversal:
                self._pull_candidate_frames = 0
            if depth <= -pull_on:
                self._pull_candidate_frames += 1
            else:
                self._pull_candidate_frames = 0
            pulling = (
                self._pull_candidate_frames >= frames
                and self._pull_motion >= cfg.depth_motion_delta
            )

        self._switches["pull"].active = pulling
        return pushing, pulling

    def menu_feedback(self) -> dict:
        """Expose held menu recognition to Learn independently of short button pulses."""
        state = self._last_state
        if not self.calibrated or state is None or not state.detected:
            return {"pose": None, "recognized": False, "held_seconds": 0.0}
        for name, gesture in (("start", self._start_gesture), ("select", self._select_gesture)):
            if gesture.started_at is not None:
                return {"pose": name, "recognized": gesture.fired,
                        "held_seconds": max(0.0, state.timestamp - gesture.started_at)}
        return {"pose": None, "recognized": False, "held_seconds": 0.0}

    def recognition_feedback(self) -> dict:
        """Expose compound and roll recognition independently of output mappings."""
        switches = self._switches
        return {
            "roll_left": switches["roll_left"].active,
            "roll_right": switches["roll_right"].active,
            "closed_hand": all(
                switches[name].active for name in ("thumb", "index", "middle", "ring", "pinky")
            ),
            "menu_guard": self._menu_guard_active,
        }

    def program_feedback(self, state: ControllerState | None = None) -> dict:
        """Expose bounded, non-biometric guidance for the active numeric program."""
        if self.profile == "program_2":
            state = self._last_state if state is None else state
            centered = None
            if self.calibrated and state is not None and state.detected:
                centered = not any(
                    self._switches[name].active
                    for name in ("left", "right", "up", "down")
                )
            return {"centered": centered}
        if self.profile == "program_9":
            return {"ready": self._program_ready}
        return {}

    def _update_vulcan_salute(self, observation: HandObservation) -> None:
        """Debounce the visual-only salute without changing controller state."""
        timestamp = observation.timestamp
        if vulcan_salute_pose(observation):
            self._vulcan_release_at = None
            if not self._vulcan_armed:
                return
            if self._vulcan_candidate_at is None:
                self._vulcan_candidate_at = timestamp
            elif (timestamp - self._vulcan_candidate_at >= 0.65
                  and timestamp - self._vulcan_last_trigger >= 30.0):
                self._vulcan_sequence += 1
                self._vulcan_last_trigger = timestamp
                self._vulcan_armed = False
            return
        self._vulcan_candidate_at = None
        if self._vulcan_armed:
            self._vulcan_release_at = None
        elif self._vulcan_release_at is None:
            self._vulcan_release_at = timestamp
        elif timestamp - self._vulcan_release_at >= 0.30:
            self._vulcan_armed = True
            self._vulcan_release_at = None

    def easter_egg_feedback(self) -> dict:
        """Publish only a monotonic visual-event counter, never hand geometry."""
        return {"spock_sequence": self._vulcan_sequence}

    def update_native_motion(
        self, observation: HandObservation, gesture: HandObservation | None = None,
        *, bounded: bool = True,
    ) -> ControllerState:
        """Update native X/Y without replaying gestures or extending their lifetime.

        The motion tracker bounds gesture age against its source camera frame.
        Only a newly completed recognition may update gesture/depth state. A
        single brief landmark dropout holds the last X/Y while releasing every
        action; sustained loss returns the native controller to neutral.
        ``bounded=False`` publishes each newest MediaPipe coordinate unchanged
        during normal tracking. After a brief loss only, one contradictory or
        unusually distant reacquisition may hold the last reliable coordinate
        until the next fresh result confirms the new position.
        """
        if self.profile != "super_glove_ball" or not self.calibrated:
            raise ValueError("native motion requires calibrated Super Glove Ball")
        previous_time = self._motion_time
        previous_x, previous_y = self._filtered_palm_x, self._filtered_palm_y
        if not observation.detected:
            lost_ms = (observation.timestamp - self._last_seen) * 1000
            native_hold_ms = max(
                self.config.loss_release_ms,
                min(250, max(0, self.config.native_xy_loss_hold_ms)),
            )
            if (self._last_state is not None and self._last_state.detected
                    and 0 <= lost_ms < native_hold_ms):
                # Hold the visible edge coordinate for this brief dropout, but
                # discard its history so reacquisition begins at the first new
                # clamped measurement rather than travelling from the held edge.
                if not bounded and len(self._latest_history) >= 3:
                    self._latest_recovery_pending = True
                    self._reset_native_motion(keep_latest_recovery=True)
                else:
                    self._reset_native_motion()
                self._sequence += 1
                axes = dict(self._last_state.axes)
                axes["z"] = axes["roll"] = 0
                self._last_state = replace(
                    self._last_state,
                    sequence=self._sequence,
                    timestamp=observation.timestamp,
                    confidence=0.0,
                    axes=axes,
                    dpad=dict.fromkeys(self._last_state.dpad, False),
                    buttons=dict.fromkeys(self._last_state.buttons, False),
                    fingers=dict.fromkeys(self._last_state.fingers, 0),
                    events=[],
                )
                return self._last_state
            self._last_seen = observation.timestamp - native_hold_ms / 1000 - 1
            self._reset_native_motion()
            return self.update(observation)
        if gesture is not None:
            self.update(gesture)
            # A delayed recognition must not rewind the movement filter.
            self._filtered_palm_x, self._filtered_palm_y = previous_x, previous_y
        else:
            self._sequence += 1
        if self._last_state is None or not self._last_state.detected:
            return ControllerState.released(
                self._sequence, observation.timestamp, self.profile, self.calibrated
            )
        cfg, reference = self.config, self.calibration
        if (previous_time is not None
                and observation.timestamp - previous_time
                > max(.25, cfg.loss_release_ms / 1000)):
            # The receiver will already have neutralized an interrupted stream.
            # Do not resume from motion history the game can no longer hold.
            self._reset_native_motion()
            previous_time = None
        # Velocity uses consecutive selected coordinates and source timestamps,
        # never the distance from a lagging filtered position.
        dt = (1 / 60 if previous_time is None else
              max(1 / 240, observation.timestamp - previous_time))
        field_x = _field_coordinate(
            observation.palm_x, reference.palm_x, cfg.coordinate_edge_margin,
            reference.reach_left, reference.reach_right,
        )
        field_y = _field_coordinate(
            observation.palm_y, reference.palm_y, cfg.coordinate_edge_margin,
            reference.reach_up, reference.reach_down,
        )
        selected_x = _camera_coordinate(
            field_x, reference.palm_x, cfg.coordinate_edge_margin,
            reference.reach_left, reference.reach_right,
        )
        selected_y = _camera_coordinate(
            field_y, reference.palm_y, cfg.coordinate_edge_margin,
            reference.reach_up, reference.reach_down,
        )
        if bounded:
            selected_x, selected_y = self._native_point(
                selected_x, selected_y, dt, reference
            )
        else:
            selected_x, selected_y = self._latest_point(
                selected_x, selected_y, observation.timestamp, reference
            )
            self._motion_raw_x, self._motion_raw_y = selected_x, selected_y
            self._motion_anchor_x, self._motion_anchor_y = selected_x, selected_y
            self._motion_moving_x = self._motion_moving_y = False
            self._motion_direction_x = self._motion_direction_y = 0.0
            self._motion_settle_pending = False
        self._filtered_palm_x, self._filtered_palm_y = selected_x, selected_y
        self._motion_time = observation.timestamp
        axes = dict(self._last_state.axes)
        axes.update(
            x=_field_axis(self._filtered_palm_x, reference.palm_x, cfg.coordinate_edge_margin,
                          reference.reach_left, reference.reach_right),
            y=_field_axis(self._filtered_palm_y, reference.palm_y, cfg.coordinate_edge_margin,
                          reference.reach_up, reference.reach_down),
        )
        buttons = dict(self._last_state.buttons)
        if gesture is None:
            buttons["start"] = buttons["select"] = False
        self._last_state = replace(
            self._last_state, sequence=self._sequence, timestamp=observation.timestamp,
            axes=axes, buttons=buttons, events=[] if gesture is None else self._last_state.events,
        )
        return self._last_state

    def update(self, observation: HandObservation) -> ControllerState:
        """Map one observation to a debounced controller state with safe tracking-loss release."""
        self._motion_time = None
        self._sequence += 1
        if self._calibrating:
            self._collect_calibration(observation)
            return ControllerState.released(
                self._sequence, observation.timestamp, self.profile, self.calibrated
            )

        self._update_vulcan_salute(observation)

        if observation.detected:
            self._last_seen = observation.timestamp
        lost_for = observation.timestamp - self._last_seen
        if not observation.detected and lost_for * 1000 >= self.config.loss_release_ms:
            self._reset_depth_candidates(clear_active=True)
            self._zap_until = 0.0
            self._pull_was_active = False
            self._start_gesture.update(False, observation.timestamp)
            self._select_gesture.update(False, observation.timestamp)
            self._program_12_rapid_started_at = None
            self._menu_guard_active = False
            self._filtered_palm_x = None
            self._filtered_palm_y = None
            for switch in self._switches.values():
                switch.active = False
            self._last_state = ControllerState.released(
                self._sequence, observation.timestamp, self.profile, self.calibrated
            )
            return self._last_state
        if not observation.detected:
            self._reset_depth_candidates(clear_active=False)
            self._zap_until = 0.0
            if (self.profile == "bad_street_brawler" and self._last_state is not None
                    and self._last_state.dpad.get("left") and self._last_state.dpad.get("right")):
                self._last_state = replace(self._last_state, dpad=dict.fromkeys(self._last_state.dpad, False))
            if self._last_state is not None:
                return replace(
                    self._last_state,
                    sequence=self._sequence,
                    timestamp=observation.timestamp,
                    detected=False,
                    confidence=0.0,
                    events=[],
                )
            return ControllerState.released(
                self._sequence, observation.timestamp, self.profile, self.calibrated
            )

        assert self.calibration is not None
        reference = self.calibration
        # Depth and wrist gestures retain their calibrated references.
        depth = observation.palm_scale / reference.palm_scale - 1.0
        roll = _circular_delta(observation.roll, reference.roll) / (math.pi / 2)

        cfg = self.config
        # Stabilize continuous coordinates without delaying deliberate motion.
        # A nearly stationary hand gets stronger filtering; a large change
        # raises alpha toward the configured maximum and catches up quickly.
        if self._filtered_palm_x is None or self._filtered_palm_y is None:
            self._filtered_palm_x = observation.palm_x
            self._filtered_palm_y = observation.palm_y
        else:
            for name, value in (
                ("_filtered_palm_x", observation.palm_x),
                ("_filtered_palm_y", observation.palm_y),
            ):
                previous = getattr(self, name)
                alpha = _clamp(
                    cfg.coordinate_smoothing_min
                    + abs(value - previous) * cfg.coordinate_motion_boost,
                    cfg.coordinate_smoothing_min,
                    cfg.coordinate_smoothing_max,
                )
                setattr(self, name, previous + alpha * (value - previous))
        # The original glove's joystick-compatible layout is a stateless 3x3
        # grid. The square boundary belongs to centre, so returning to it
        # releases positional directions on this very inference result.
        bounds = joystick_deadzone_bounds(cfg, reference)
        dpad = {
            "left": observation.palm_x < bounds["left"],
            "right": observation.palm_x > bounds["right"],
            "up": observation.palm_y < bounds["top"],
            "down": observation.palm_y > bounds["bottom"],
        }
        for name in ("left", "right", "up", "down"):
            self._switches[name].active = dpad[name]
        thumb = self._switches["thumb"].positive(
            observation.thumb_curl, *cfg.pair("thumb")
        )
        index = self._switches["index"].positive(
            observation.index_curl, *cfg.pair("index")
        )
        middle = self._switches["middle"].positive(
            observation.middle_curl, *cfg.pair("middle")
        )
        for finger in ("ring", "pinky"):
            self._switches[finger].positive(observation.fingers[finger], *cfg.pair(finger))
        roll_left = self._switches["roll_left"].negative(
            roll, *cfg.pair("roll_left")
        )
        roll_right = self._switches["roll_right"].positive(
            roll, *cfg.pair("roll_right")
        )

        events: list[str] = []
        pushing, _pulling = self._update_depth(depth, observation.timestamp)
        if pushing and not self._push_was_active:
            events.append("glove_zap")
        self._push_was_active = pushing

        # Menu guard uses the activation boundary for its two curled fingers
        # and the lower release boundary for its three extended fingers. This
        # leaves an intentional deadband before a partly curled pinky can count
        # as the V-sign's curled pinky. Guard has priority and cancels any Start
        # pulse already forming or active.
        if self._menu_guard_active:
            # Retain the two curled fingers through their release band. The
            # three extended fingers stay strict: as soon as the pinky leaves
            # its clearly-straight range, guard releases into the deliberate
            # deadband before that finger can help form a V-sign.
            curled_hold = all(
                observation.fingers[name] >= (
                    cfg.pair(name)[1] if name in cfg.thresholds else MENU_GUARD_OFF[name]
                )
                for name in ("thumb", "ring")
            )
            extended_hold = all(
                observation.fingers[name] <= cfg.pair(name)[1]
                for name in ("index", "middle", "pinky")
            )
            self._menu_guard_active = curled_hold and extended_hold
        else:
            self._menu_guard_active = all(item["matches"] for item in finger_pose_feedback(
                cfg, "menu_guard", MENU_GUARD_FINGERS, observation.fingers).values())

        # Deliberate, held menu poses avoid needing an electronic glove.
        # V sign = Start; thumbs-up with the four fingers closed = Select.
        start_pose = not self._menu_guard_active and all(item["matches"] for item in finger_pose_feedback(
            cfg, "start", MENU_FINGERS["start"], observation.fingers).values())
        select_pose = not self._menu_guard_active and all(item["matches"] for item in finger_pose_feedback(
            cfg, "select", MENU_FINGERS["select"], observation.fingers).values())
        if self._menu_guard_active:
            self._start_gesture.cancel()
            self._select_gesture.cancel()
            start = select = False
        else:
            start = self._start_gesture.update(start_pose, observation.timestamp)
            select = self._select_gesture.update(select_pose, observation.timestamp)
        menu_pose = start_pose or select_pose or start or select
        if menu_pose:
            dpad = {name: False for name in dpad}

        pulse_on = int(observation.timestamp * cfg.pulse_hz * 2) % 2 == 0
        closed_hand = all(
            self._switches[name].active
            for name in ("thumb", "index", "middle", "ring", "pinky")
        )
        index_point = (
            observation.index_curl < cfg.pair("index")[1]
            and all(self._switches[name].active for name in ("middle", "ring", "pinky"))
        )
        if self.profile == "bad_street_brawler":
            brawler_a = middle or roll_left or roll_right
            buttons = {
                "a": brawler_a and (pulse_on or not self.rapid_a) and not menu_pose,
                # Only the documented thumb-B action is pulsed by default. The
                # middle-finger A+B grab remains held independently.
                "b": (middle or (thumb and (pulse_on or not self.rapid_b))) and not menu_pose,
                "start": start,
                "select": select,
                "glove_zap": pushing,
            }
            if roll_left:
                dpad["left"] = True
            if roll_right:
                dpad["right"] = True
            # The cartridge recognizes its Glove Zap as simultaneous Left+Right.
            # Emit one 180 ms pulse per push edge; never leak it into menu poses.
            if menu_pose:
                self._zap_until = 0.0
            elif "glove_zap" in events:
                self._zap_until = observation.timestamp + 0.18
            if observation.timestamp < self._zap_until:
                dpad = {"left": True, "right": True, "up": False, "down": False}
                buttons["a"] = buttons["b"] = False
        elif self.profile == "super_glove_ball":
            buttons = {
                "a": index and not menu_pose,
                "b": thumb and not menu_pose,
                "start": start,
                "select": select,
                "glove_zap": False,
                "closed_hand": closed_hand and not menu_pose,
                "index_point": index_point and not menu_pose,
            }
        else:
            dpad, buttons = self._program_mapping(
                observation, dpad,
                thumb, index, middle, pulse_on, menu_pose, start, select,
            )

        # Menu guard is a shared recognition safety pose, not a Program G
        # mapping. Keep its state available to practice/native consumers while
        # suppressing ordinary game movement and action buttons everywhere.
        menu_guard = self._menu_guard_active
        if menu_guard:
            dpad = {name: False for name in dpad}
            buttons["a"] = buttons["b"] = buttons["start"] = buttons["select"] = False
            buttons["closed_hand"] = buttons["index_point"] = False
        buttons["menu_guard"] = menu_guard

        fingers = {
            name: round(_clamp(value, 0.0, 1.0) * 3)
            for name, value in observation.fingers.items()
        }
        self._last_state = ControllerState(
            sequence=self._sequence,
            timestamp=observation.timestamp,
            profile=self.profile,
            detected=True,
            confidence=observation.confidence,
            calibrated=True,
            axes={
                # Native coordinates span the usable camera field on each side
                # of neutral. Direction switches retain hand-relative thresholds.
                "x": _field_axis(
                    self._filtered_palm_x, reference.palm_x, cfg.coordinate_edge_margin,
                    reference.reach_left, reference.reach_right
                ),
                "y": _field_axis(
                    self._filtered_palm_y, reference.palm_y, cfg.coordinate_edge_margin,
                    reference.reach_up, reference.reach_down
                ),
                "z": _axis(depth / 0.75),
                "roll": _axis(roll),
            },
            dpad=dpad,
            buttons=buttons,
            fingers=fingers,
            events=events,
        )
        return self._last_state

    def _program_mapping(
        self,
        observation: HandObservation,
        dpad: dict[str, bool],
        thumb: bool,
        index: bool,
        middle: bool,
        pulse_on: bool,
        menu_pose: bool,
        start: bool,
        select: bool,
    ) -> tuple[dict[str, bool], dict[str, bool]]:
        """Implement the built-in Programs 1-14 and cartridge Programs A-I.

        These mappings deliberately emit ordinary NES controls, so the target
        game needs no Power Glove support and Bad Street Brawler is not needed
        as a loader.
        """
        profile = self.profile
        a = b = False
        # Consume the recognition states already updated for this frame. These
        # retain activation until release, just like Learn's movement feedback.
        roll_left = self._switches["roll_left"].active
        roll_right = self._switches["roll_right"].active
        pushing = self._push_was_active
        pulling = self._switches["pull"].active
        ring = self._switches["ring"].active
        pinky = self._switches["pinky"].active
        last_three = middle and ring and pinky
        last_three_open = all(
            observation.fingers[name] <= self.config.pair(name)[1]
            for name in ("middle", "ring", "pinky")
        )
        four_open = (
            observation.index_curl <= self.config.pair("index")[1]
            and last_three_open
        )
        four_closed = index and last_three
        closed_hand = thumb and four_closed
        raw_dpad = dict(dpad)
        if raw_dpad["left"] != raw_dpad["right"]:
            self._last_horizontal = "left" if raw_dpad["left"] else "right"

        if profile in {"program_1", "program_2"}:
            a, b = thumb, index
            if last_three and not self._program_pose_was_active:
                self._program_action_until = observation.timestamp + .18
            self._program_pose_was_active = last_three
            if observation.timestamp < self._program_action_until:
                dpad = {name: False for name in dpad}
                if self._last_horizontal is not None:
                    dpad["right" if self._last_horizontal == "left" else "left"] = True
                b = True
        elif profile == "program_3":
            dpad["up"], dpad["down"] = pushing, pulling
            a, b = thumb, index
        elif profile == "program_4":
            dpad = {name: False for name in dpad}
            if pulling:
                a = b = False
            elif abs(_circular_delta(observation.roll, self.calibration.roll)) >= math.pi * .75:
                a, b = thumb, True
            elif roll_right:
                dpad["up"] = dpad["right"] = True
                a = thumb
            elif roll_left:
                dpad["up"] = dpad["left"] = True
                a = thumb
            else:
                dpad["up"] = four_open
                dpad["down"] = four_closed
                dpad["right"] = not index and last_three
                dpad["left"] = index and last_three_open
                a = thumb
                b = False
        elif profile == "program_5":
            dpad["up"], dpad["down"] = pushing, pulling
            dpad["left"] = dpad["left"] or roll_left
            dpad["right"] = dpad["right"] or roll_right
            a, b = thumb, index
        elif profile == "program_6":
            dpad["up"], dpad["down"] = pushing, pulling
            a, b = index, thumb
            if last_three:
                a = b = True
            if closed_hand and pushing:
                dpad = {"up": True, "down": False, "left": False, "right": False}
                a = b = False
            if roll_right:
                if self._program_action_started is None:
                    self._program_action_started = observation.timestamp
                elapsed = observation.timestamp - self._program_action_started
                if elapsed < .32:
                    phase = int(elapsed / .08)
                    dpad = {"up": False, "down": False,
                            "left": phase % 2 == 0, "right": phase % 2 == 1}
            else:
                self._program_action_started = None
        elif profile == "program_7":
            dpad = {name: False for name in dpad}
            a = b = False
            if roll_right:
                dpad["down"] = True
            elif closed_hand and pulling:
                select = not self._pull_was_active
            elif closed_hand and pushing:
                right_punch = observation.palm_x >= self.calibration.palm_x
                high_punch = observation.palm_y < self.calibration.palm_y
                a, b = right_punch, not right_punch
                dpad["up"] = high_punch
            elif four_open:
                dpad["left"], dpad["right"] = raw_dpad["left"], raw_dpad["right"]
                dpad["down"] = raw_dpad["down"]
            if thumb and four_open:
                a = True
            self._pull_was_active = pulling
        elif profile == "program_8":
            dpad["up"], dpad["down"] = pushing, pulling
            running = any(dpad.values())
            a = thumb and running
            b = index or roll_left or pulling or (thumb and not running)
        elif profile == "program_9":
            if closed_hand:
                self._program_ready = True
            dpad = {name: False for name in dpad}
            a = b = False
            if self._program_ready:
                dpad["left"] = roll_left
                dpad["right"] = roll_right
                dpad["up"] = closed_hand and pushing
                dpad["down"] = raw_dpad["up"]
                a = closed_hand
                b = raw_dpad["down"]
        elif profile == "program_10":
            dpad = {"up": False, "down": False, "left": index, "right": last_three}
            a = thumb
            b = not raw_dpad["down"]
            if index and last_three:
                dpad["left"] = dpad["right"] = False
        elif profile == "program_11":
            a, b = thumb, index
            if last_three:
                dpad = {name: False for name in dpad}
                dpad["left"] = int(observation.timestamp * 12) % 2 == 0
                dpad["right"] = not dpad["left"]
                b = True
        elif profile == "program_12":
            if menu_pose or not thumb:
                self._program_12_rapid_started_at = None
                a = False
            elif self.rapid_a:
                if self._program_12_rapid_started_at is None:
                    self._program_12_rapid_started_at = observation.timestamp
                short_gap = 1.0 / (self.config.pulse_hz * 2.0)
                elapsed = observation.timestamp - self._program_12_rapid_started_at
                a = elapsed % (PROGRAM_12_JUMP_SECONDS + short_gap) < PROGRAM_12_JUMP_SECONDS
            else:
                self._program_12_rapid_started_at = None
                a = True
            b = index or (middle and not last_three)
            if last_three:
                slow_on = int(observation.timestamp * self.config.pulse_hz) % 2 == 0
                dpad["left"] = raw_dpad["left"] and slow_on
                dpad["right"] = raw_dpad["right"] and slow_on
        elif profile == "program_13":
            dpad = {name: False for name in dpad}
            a, b = thumb, index
        elif profile == "program_14":
            dpad = {name: False for name in dpad}
            a = b = start = select = False

        elif profile == "program_a":
            # Pinball: index/right flipper, thumb/left flipper, roll/tilt.
            dpad = {name: False for name in dpad}
            if pulling and not self._pull_was_active:
                self._program_toggle = not self._program_toggle
            self._pull_was_active = pulling
            combined = self._program_toggle and (index or thumb)
            a = index or combined
            dpad["up"] = thumb or combined
            b = (roll_left or roll_right)
        elif profile == "program_b":
            # Joust: lateral steering and pulsed finger flap.
            dpad["up"] = dpad["down"] = False
            dpad["left"] = dpad["left"] and pulse_on
            dpad["right"] = dpad["right"] and pulse_on
            a = index or middle
            b = thumb
        elif profile == "program_c":
            # Gyruss: wrist rotation, straight index fires, pull back bombs.
            dpad = {name: False for name in dpad}
            dpad["left"] = roll_left
            dpad["right"] = roll_right
            a = observation.index_curl < self.config.pair("index")[1]
            b = pulling
        elif profile == "program_d":
            # Reverse all four directions.
            dpad = {
                "up": dpad["down"], "down": dpad["up"],
                "left": dpad["right"], "right": dpad["left"],
            }
            a, b = thumb, index
        elif profile == "program_e":
            # Defender II: hand position, thumb fire, wrist smart bomb.
            a = thumb
            b = (roll_left or roll_right)
            if self._switches["ring"].active:
                dpad["left"] = int(observation.timestamp * 12) % 2 == 0
                dpad["right"] = not dpad["left"]
        elif profile == "program_f":
            # Sesame Street: moving an open hand = Yes, closed hand = No.
            moving = any(self._switches[name].active for name in ("left", "right", "up", "down"))
            closed = all(self._switches[name].active for name in observation.fingers)
            dpad = {name: False for name in dpad}
            a = moving and not closed
            b = closed
        elif profile == "program_g":
            # Gun Smoke: position moves and index/push fire. Shared menu guard
            # suppression is applied after every profile mapping.
            if (roll_left or roll_right):
                dpad["left"] = roll_left
                dpad["right"] = roll_right
            a = index
            b = pushing
        elif profile == "program_h":
            # General play/training: conventional motion and pulsed buttons.
            a = thumb
            b = index
        elif profile == "program_i":
            # Knight Rider/driving: wrist steering, finger throttle, hand brake.
            dpad = {name: False for name in dpad}
            dpad["left"] = roll_left
            dpad["right"] = roll_right
            dpad["down"] = self._switches["down"].active
            turbo = pushing
            dpad["up"] = index or turbo
            a = turbo
            b = thumb

        if profile in PROGRAM_PROFILES:
            if profile != "program_12":
                a = a and (pulse_on or not self.rapid_a)
            b = b and (pulse_on or not self.rapid_b)
        if menu_pose:
            a = b = False
        return dpad, {
            "a": a,
            "b": b,
            "start": start,
            "select": select,
            "glove_zap": False,
        }
