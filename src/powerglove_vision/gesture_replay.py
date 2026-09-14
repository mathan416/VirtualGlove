# Project: VirtualGlove
# File: src/powerglove_vision/gesture_replay.py
# Purpose: Record and replay privacy-preserving gesture recognition regressions.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT

"""Record derived hand observations and verify their controller results later."""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import asdict, fields

from .gesture import GestureConfig, GestureEngine, RECOGNITION_PROFILES
from .model import Calibration, ControllerState, HandObservation


FORMAT = "virtualglove-gesture-regression"
VERSION = 1
MAX_FRAMES = 900
MAX_DURATION_MS = 60_000
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_OBSERVATION_FIELDS = {item.name for item in fields(HandObservation)}
_CONFIG_FIELDS = {item.name for item in fields(GestureConfig)}
_CALIBRATION_FIELDS = {item.name for item in fields(Calibration)}
_EXPECTED_FIELDS = {
    "profile", "detected", "calibrated", "axes", "dpad", "buttons", "fingers", "events",
}


def _finite_number(value, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _state_signature(state: ControllerState) -> dict:
    """Keep only deterministic, gameplay-visible recognition results."""
    return {
        "profile": state.profile,
        "detected": state.detected,
        "calibrated": state.calibrated,
        "axes": dict(state.axes),
        "dpad": dict(state.dpad),
        "buttons": dict(state.buttons),
        "fingers": dict(state.fingers),
        "events": list(state.events),
    }


class GestureRegressionRecorder:
    """Hold one bounded recording in memory; never persist camera imagery."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self._phase = "idle"
        self._error = ""
        self._header: dict = {}
        self._frames: list[dict] = []
        self._started_at: float | None = None
        self._wall_started: float | None = None
        self._engine: GestureEngine | None = None

    def begin(self, engine: GestureEngine) -> None:
        """Begin from the exact effective recognition configuration."""
        if engine.profile not in RECOGNITION_PROFILES or not engine.calibrated:
            raise ValueError("Select an active profile and center your hand before recording.")
        assert engine.calibration is not None
        with self.lock:
            if self._phase == "recording":
                raise ValueError("A gesture recording is already active.")
            self._phase = "recording"
            self._error = ""
            self._frames = []
            self._started_at = None
            self._wall_started = time.monotonic()
            self._header = {
                "profile": engine.profile,
                "rapid_a": engine.rapid_a,
                "rapid_b": engine.rapid_b,
                "configuration": asdict(engine.config),
                "calibration": asdict(engine.calibration),
            }
            self._engine = GestureEngine(
                engine.profile, engine.config, calibration=engine.calibration,
                rapid_a=engine.rapid_a, rapid_b=engine.rapid_b,
            )

    def fail(self, message: str) -> None:
        with self.lock:
            self._phase = "idle"
            self._error = message
            self._header = {}
            self._frames = []
            self._started_at = None
            self._wall_started = None
            self._engine = None

    def record(self, observation: HandObservation) -> None:
        with self.lock:
            self._expire_locked()
            if self._phase != "recording":
                return
            if self._started_at is None:
                self._started_at = observation.timestamp
            elapsed = max(0.0, (observation.timestamp - self._started_at) * 1000.0)
            if len(self._frames) >= MAX_FRAMES or elapsed > MAX_DURATION_MS:
                self._phase = "stopped"
                self._wall_started = None
                return
            assert self._engine is not None
            at_ms = round(elapsed, 3)
            replay_observation = HandObservation(
                timestamp=at_ms / 1000.0,
                **{key: value for key, value in asdict(observation).items()
                   if key != "timestamp"},
            )
            state = self._engine.update(replay_observation)
            sample = asdict(observation)
            sample.pop("timestamp", None)
            self._frames.append({
                "at_ms": at_ms,
                "observation": sample,
                "expected": _state_signature(state),
            })

    def stop(self) -> None:
        with self.lock:
            self._expire_locked()
            if self._phase == "stopped":
                return
            if self._phase != "recording":
                raise ValueError("No gesture recording is active.")
            self._phase = "stopped"
            self._wall_started = None

    def discard(self) -> None:
        with self.lock:
            self._phase = "idle"
            self._error = ""
            self._header = {}
            self._frames = []
            self._started_at = None
            self._wall_started = None
            self._engine = None

    def _expire_locked(self) -> None:
        if (self._phase == "recording" and self._wall_started is not None
                and time.monotonic() - self._wall_started >= MAX_DURATION_MS / 1000):
            self._phase = "stopped"
            self._wall_started = None

    def snapshot(self) -> dict:
        with self.lock:
            self._expire_locked()
            duration = self._frames[-1]["at_ms"] if self._frames else 0
            return {
                "phase": self._phase,
                "frames": len(self._frames),
                "duration_ms": duration,
                "download_ready": self._phase == "stopped" and bool(self._frames),
                "error": self._error,
                "privacy": "Derived hand measurements only; no camera images are stored.",
            }

    def document(self) -> bytes:
        with self.lock:
            self._expire_locked()
            if self._phase != "stopped" or not self._frames:
                raise ValueError("Stop a non-empty recording before downloading it.")
            payload = {"format": FORMAT, "version": VERSION, **self._header,
                       "frames": list(self._frames)}
        body = (json.dumps(payload, indent=2, allow_nan=False) + "\n").encode()
        if len(body) > MAX_DOCUMENT_BYTES:
            raise ValueError("Gesture recording is too large to download.")
        return body


def _validated_dataclass(data, allowed: set[str], required: set[str], name: str):
    if not isinstance(data, dict) or set(data) - allowed or not required <= set(data):
        raise ValueError(f"Invalid {name} fields")
    return data


def load_recording(raw: bytes | str) -> dict:
    """Parse a bounded version-1 recording without accepting unrelated data."""
    encoded = raw.encode() if isinstance(raw, str) else raw
    if not isinstance(encoded, bytes) or len(encoded) > MAX_DOCUMENT_BYTES:
        raise ValueError("Gesture recording must be smaller than 2 MiB.")
    try:
        data = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Gesture recording is not valid JSON.") from exc
    expected_top = {"format", "version", "profile", "rapid_a", "rapid_b",
                    "configuration", "calibration", "frames"}
    if not isinstance(data, dict) or set(data) != expected_top:
        raise ValueError("Gesture recording has unknown or missing fields.")
    if data["format"] != FORMAT or data["version"] != VERSION:
        raise ValueError("Unsupported gesture recording format or version.")
    if data["profile"] not in RECOGNITION_PROFILES:
        raise ValueError("Gesture recording has an unknown profile.")
    if type(data["rapid_a"]) is not bool or type(data["rapid_b"]) is not bool:
        raise ValueError("Gesture recording rapid-fire values must be Boolean.")
    config = _validated_dataclass(data["configuration"], _CONFIG_FIELDS,
                                  _CONFIG_FIELDS, "configuration")
    calibration = _validated_dataclass(data["calibration"], _CALIBRATION_FIELDS,
                                       _CALIBRATION_FIELDS, "calibration")
    for key, value in calibration.items():
        _finite_number(value, "calibration." + key)
    frames = data["frames"]
    if not isinstance(frames, list) or not frames or len(frames) > MAX_FRAMES:
        raise ValueError("Gesture recording must contain 1 to 900 frames.")
    previous = -1.0
    for frame in frames:
        if not isinstance(frame, dict) or set(frame) != {"at_ms", "observation", "expected"}:
            raise ValueError("Gesture recording contains an invalid frame.")
        at_ms = _finite_number(frame["at_ms"], "frame.at_ms")
        if at_ms < previous or at_ms < 0 or at_ms > MAX_DURATION_MS:
            raise ValueError("Gesture recording frame times are invalid.")
        previous = at_ms
        observation = _validated_dataclass(
            frame["observation"], _OBSERVATION_FIELDS - {"timestamp"},
            _OBSERVATION_FIELDS - {"timestamp"}, "observation")
        for key, value in observation.items():
            if key == "detected":
                if type(value) is not bool:
                    raise ValueError("observation.detected must be Boolean")
            elif key == "confidence_source":
                if not isinstance(value, str) or len(value) > 64:
                    raise ValueError("observation.confidence_source must be short text")
            else:
                _finite_number(value, "observation." + key)
        expected = frame["expected"]
        if not isinstance(expected, dict) or set(expected) != _EXPECTED_FIELDS:
            raise ValueError("Gesture recording expected output is invalid.")
        if expected["profile"] != data["profile"]:
            raise ValueError("Gesture recording frame profile does not match.")
        if type(expected["detected"]) is not bool or type(expected["calibrated"]) is not bool:
            raise ValueError("Gesture recording state flags must be Boolean.")
        if not all(isinstance(expected[key], dict) for key in ("axes", "dpad", "buttons", "fingers")):
            raise ValueError("Gesture recording controller fields must be objects.")
        if not isinstance(expected["events"], list) or not all(
                isinstance(event, str) and len(event) <= 128 for event in expected["events"]):
            raise ValueError("Gesture recording events must be short text.")
    # Constructors perform the remaining bounds and type validation used by runtime.
    GestureConfig(**config)
    Calibration(**calibration)
    return data


def replay_recording(raw: bytes | str) -> dict:
    """Replay a recording and return a bounded, machine-readable regression report."""
    data = load_recording(raw)
    engine = GestureEngine(
        data["profile"], GestureConfig(**data["configuration"]),
        calibration=Calibration(**data["calibration"]),
        rapid_a=data["rapid_a"], rapid_b=data["rapid_b"],
    )
    mismatches = []
    for index, frame in enumerate(data["frames"]):
        observation = HandObservation(timestamp=frame["at_ms"] / 1000.0,
                                      **frame["observation"])
        actual = _state_signature(engine.update(observation))
        if actual != frame["expected"] and len(mismatches) < 20:
            mismatches.append({"frame": index, "at_ms": frame["at_ms"],
                               "expected": frame["expected"], "actual": actual})
    # The bounded mismatch list may truncate details; count all differences in one pass.
    verifier = GestureEngine(data["profile"], GestureConfig(**data["configuration"]),
                             calibration=Calibration(**data["calibration"]),
                             rapid_a=data["rapid_a"], rapid_b=data["rapid_b"])
    mismatch_count = 0
    for frame in data["frames"]:
        actual = _state_signature(verifier.update(HandObservation(
            timestamp=frame["at_ms"] / 1000.0, **frame["observation"])))
        mismatch_count += actual != frame["expected"]
    return {"passed": mismatch_count == 0, "frames": len(data["frames"]),
            "mismatch_count": mismatch_count, "mismatches": mismatches}
