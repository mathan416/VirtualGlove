# Project: VirtualGlove
# File: src/powerglove_vision/tuning.py
# Purpose: Record gesture measurements and manage expiring global threshold previews.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-07 - Use tracker geometry validity instead of handedness certainty.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Add complete hand-setup backups and explicit calibration restoration.
#   2026-09-06 - Persist separate player sensitivity and Academy progress.
#   2026-09-06 - Added the family-facing personalization wizard and validation gate.
#   2026-09-04 - Added guided gesture sampling and persistent personal thresholds.

"""Personal threshold overlays; samples and previews never become camera recordings."""
from __future__ import annotations

import copy
import math
import threading
import time
from dataclasses import replace, asdict
from pathlib import Path

from .academy_diagnostics import AcademyDiagnostics
from .players import PlayerSettings, calibration_value
from .gesture import load_calibration, save_calibration, GestureConfig, MENU_FINGERS, MENU_GUARD_FINGERS, finger_pose_feedback
from .model import Calibration

DIRECTION_CHANNELS = ("left", "right", "up", "down")
CHANNELS = ("thumb", "index", "middle", "ring", "pinky", "roll_left", "roll_right", "push", "pull")
LEGACY_CHANNELS = DIRECTION_CHANNELS + CHANNELS
REACH_DIRECTIONS = ("left", "right", "up", "down")
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
GESTURES = {key: {key: True} for key in CHANNELS}
GESTURES.update(**MENU_FINGERS, hand_setup={key: True for key in FINGERS},
                closed_hand={key: True for key in FINGERS}, menu_guard=MENU_GUARD_FINGERS)
LABELS = {key: key.replace("_", " ").capitalize() for key in GESTURES}
LABELS.update({key: "Curl " + key + " finger" for key in FINGERS})
LABELS["thumb"] = "Curl thumb"
LABELS["hand_setup"] = "Set up my hand"
LABELS.update(start="Start — Make the V sign", select="Select — Give a thumbs-up", closed_hand="Closed hand",
              menu_guard="Menu guard — thumb and ring", push="Glove Zap — push toward camera", pull="Pull Back — away from camera",
              roll_left="Roll wrist left", roll_right="Roll wrist right")

PROBLEMS = {
    "setup": "Set up a new hand",
    "difficult": "A gesture is hard to trigger",
    "accidental": "A gesture happens accidentally",
    "off_center": "Movement feels off-center",
}
SUGGESTION_BIAS = {
    "setup": (.65, .30),
    "difficult": (.55, .30),
    "accidental": (.75, .40),
}
DEPTH_GESTURES = {"push", "pull"}
MOVEMENT_GESTURES = {"roll_left", "roll_right"}


def tuning_recipe(gesture: str) -> dict:
    """Describe the family-facing recording sequence for one recognition control."""
    if gesture in DEPTH_GESTURES:
        return {"kind": "motion", "durations": [2.0, 6.0, 2.0],
                "steps": ["Starting position", "Three motions and returns", "Return to start"]}
    if gesture in MOVEMENT_GESTURES:
        return {"kind": "movement", "durations": [2.0, 2.0, 2.0],
                "steps": ["Starting position", "Move and hold", "Return to start"]}
    return {"kind": "pose", "durations": [2.0, 2.0, 2.0],
            "steps": ["Open hand", "Make the pose", "Open hand again"]}


def validate_overrides(values: dict) -> dict:
    """Require bounded activation/release pairs for known independent channels."""
    if not isinstance(values, dict) or set(values) - set(CHANNELS):
        raise ValueError("Unknown gesture threshold.")
    for channel, pair in values.items():
        if not isinstance(pair, dict) or set(pair) != {"on", "off"}:
            raise ValueError("Each gesture needs activation and release values.")
        maximum = 1.0 if channel in FINGERS or channel == "pull" else 2.0 if channel.startswith("roll") else 4.0
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in pair.values()):
            raise ValueError("Thresholds must be finite numbers.")
        if not 0 <= pair["off"] < pair["on"] <= maximum:
            raise ValueError("Release must be below activation; values must be between zero and " + str(maximum))
    return copy.deepcopy(values)


def validate_legacy_overrides(values: dict) -> dict:
    """Accept old directional pairs only while migrating stores and backups."""
    if not isinstance(values, dict) or set(values) - set(LEGACY_CHANNELS):
        raise ValueError("Unknown gesture threshold.")
    active, directions = {}, {}
    for key, value in values.items():
        (directions if key in DIRECTION_CHANNELS else active)[key] = value
    clean = validate_overrides(active)
    for channel, pair in directions.items():
        if (not isinstance(pair, dict) or set(pair) != {"on", "off"}
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                       for v in pair.values())
                or not 0 <= pair["off"] < pair["on"] <= 4.0):
            raise ValueError("Legacy direction thresholds are invalid.")
        clean[channel] = copy.deepcopy(pair)
    return clean


def measurements(observation, calibration):
    """Expose the same unclipped normalized signals used by gameplay recognition."""
    if calibration is None or not observation.detected:
        return {}
    dx = (observation.palm_x - calibration.palm_x) / calibration.palm_scale
    dy = (observation.palm_y - calibration.palm_y) / calibration.palm_scale
    depth = observation.palm_scale / calibration.palm_scale - 1
    angle = observation.roll - calibration.roll
    roll = math.atan2(math.sin(angle), math.cos(angle)) / (math.pi / 2)
    return dict(observation.fingers, left=-dx, right=dx, up=-dy, down=dy,
                roll_left=-roll, roll_right=roll, push=depth, pull=-depth)


def percentile(values, fraction):
    """Return a deterministic nearest-rank statistic without another dependency."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def validate_recorded_pose(gesture: str, phases: list, config: GestureConfig) -> None:
    """Require complete finger poses, allowing at most ten percent tracking noise."""
    fingers = {key: closed for key, closed in GESTURES[gesture].items() if key in FINGERS}
    if not fingers:
        return
    for index, phase in enumerate(phases):
        requirements = fingers if index == 1 else dict.fromkeys(fingers, False)
        label = ("first open-hand", "gesture", "final open-hand")[index]
        feedback = [finger_pose_feedback(config, gesture, requirements, sample) for sample in phase]
        minimum = math.ceil(len(phase) * .9)
        for finger, closed in requirements.items():
            matches = sum(frame[finger]["matches"] for frame in feedback)
            if matches < minimum:
                expected = "curled" if closed else "extended"
                raise ValueError(
                    f"Keep your {finger} {expected} during the {label} recording "
                    f"({matches}/{len(phase)} measurements matched; at least 90% required). "
                    "Record again. If comfortable extension is not recognized, try Set up my hand first.")
        if sum(all(item["matches"] for item in frame.values()) for frame in feedback) < minimum:
            raise ValueError(f"Hold all required fingers in position together during the {label} recording. "
                             "At least 90% of measurements must match the complete pose. Record again.")


def suggest(gesture: str, phases: list, config: GestureConfig | None = None,
            activation_fraction: float = .65, release_fraction: float = .30) -> dict:
    """Separate rest noise from one performed gesture and two open-hand recordings."""
    if len(phases) != 3 or any(len(phase) < 12 for phase in phases):
        raise ValueError("Record open hand, the gesture, and open hand again.")
    required = GESTURES[gesture]
    for phase in phases:
        for sample in phase:
            if any(not isinstance(sample.get(key), (int, float)) or isinstance(sample.get(key), bool)
                   or not math.isfinite(sample[key]) for key in required):
                raise ValueError("Missing or invalid finger measurements. Record all three steps again.")
    suggestion = {}
    for channel, positive in GESTURES[gesture].items():
        # Extended fingers in a menu pose often also remain extended at rest.
        # Keep their current thresholds rather than inventing an unsupported adjustment.
        rest = [sample[channel] for i in (0, 2) for sample in phases[i]]
        active = [[sample[channel] for sample in phases[i]] for i in (1,)]
        if not positive:
            continue
        low = max(0.0, percentile(rest, .95))
        # Depth recording deliberately includes three returns to neutral, so use
        # its upper quartile rather than treating the returns as failed motion.
        active_fraction = .75 if gesture in DEPTH_GESTURES else .10
        high = min(percentile(repetition, active_fraction) for repetition in active)
        gap = high - low
        if gap < .08:
            raise ValueError("The resting and performed measurements overlap for " + channel + ". Try a clearer movement and fully release it.")
        suggestion[channel] = {
            "on": round(low + gap * activation_fraction, 4),
            "off": round(low + gap * release_fraction, 4),
        }
    suggestion = validate_overrides(suggestion)
    current = config if config is not None else GestureConfig()
    candidate = replace(current, thresholds=dict(current.thresholds, **suggestion))
    validate_recorded_pose(gesture, phases, candidate)
    return suggestion


class TuningManager:
    """Own one leased tuning session and commit only explicitly saved overlays."""
    def __init__(self, path, clock=time.monotonic):
        self.path, self.clock = Path(path), clock
        self.lock = threading.RLock()
        self.players = PlayerSettings(self.path, validate_overrides, CHANNELS,
                                      validate_legacy_overrides, LEGACY_CHANNELS)
        if not self.players.error and not self.players.active["needs_center"] and self.players.active["calibration"] is None:
            reference = load_calibration(self.path.with_name("calibration.json"))
            if reference is not None:
                self.players.active["calibration"] = calibration_value({"version":2,"neutral":asdict(reference)})
        self.saved = copy.deepcopy(self.players.active["thresholds"])
        self.error = self.players.error
        self.center_generation = None
        self.session = None
        self.expires = 0
        self.gesture = "index"
        self.preview = None
        self.phases = []
        self.recording = None
        self.latest = {}
        self.last_observed = -100.0
        self.ready = False
        self.effective = {}
        self.base_config = GestureConfig()
        self.revision = 0
        self.last_frame = None
        self.calibration = None
        self.finger_feedback = {}
        self.image_quality = {}
        self.frame_size = (640, 480)
        self.diagnostics = AcademyDiagnostics(self.path.parent, clock)
        self.problem = None
        self.wizard_step = "problem"
        self.ready_since = None
        self.test_started = None
        self.test_was_active = False
        self.test_cycles = 0
        self.test_neutral_seconds = 0.0
        self.test_last_at = None
        self.test_passed = False
        self._configuration_cache = None

    def player_snapshot(self):
        """Read player state under the same lock as recognition settings."""
        with self.lock:
            result = self.players.snapshot()
            config = replace(self.base_config, thresholds=copy.deepcopy(self.saved),
                             joystick_deadzone=self.players.active["joystick_deadzone"])
            chosen = config.chosen_joystick_deadzone()
            reference = self.players.active["calibration"]
            effective = chosen
            minimum = None
            if not self.players.active["needs_center"] and reference is not None:
                calibration = Calibration(**reference["neutral"])
                minimum = min(1.0, 1.5 * calibration.palm_scale)
                effective = config.effective_joystick_deadzone(calibration)
            result["joystick"] = {
                "deadzone": chosen,
                "effective_deadzone": effective,
                "jitter_protected": False,
                "hand_size_protected": effective > chosen + 1e-9,
                "hand_size_minimum": minimum,
            }
            return result

    def player_command(self, data):
        """Change presets without overlapping an active tuning session."""
        with self.lock:
            self._expire()
            if self.session and data.get("action") not in ("read", "progress", "ready_progress", "export"):
                raise ValueError("Finish tuning and switch Tune gestures off before changing players or restoring settings.")
            if data.get("action") == "joystick_deadzone" and (
                    self.center_generation is not None or self.players.data["calibration_restore"] is not None):
                raise ValueError("Wait for hand centering or calibration restore to finish before saving the dead zone.")
            if data.get("action") == "export":
                result = self.players.command(data)
                if self.players.data["calibration_restore"] is not None:
                    raise ValueError("Calibration restore is still being applied. Try the backup again shortly.")
                reference = self.players.active["calibration"]
                if reference is None and not self.needs_center():
                    current = load_calibration(self.path.with_name("calibration.json"))
                    reference = calibration_value({"version":2,"neutral":asdict(current)}) if current else None
                backup = result["backup"]
                from .versioning import current_identity
                identity = current_identity()
                # Use shipped configuration even before the camera has ever run.
                config_path = Path(__file__).resolve().parents[2] / "config/profiles.json"
                import json
                configured = json.loads(config_path.read_text()) if config_path.exists() else {}
                base = GestureConfig(**configured.get("recognition", configured.get("program_defaults", {})))
                effective = replace(base, thresholds=copy.deepcopy(self.saved),
                                    joystick_deadzone=self.players.active["joystick_deadzone"])
                backup.update(calibration=copy.deepcopy(reference),
                    effective_thresholds={key:dict(zip(("on","off"),effective.pair(key))) for key in CHANNELS},
                    source={"version":str(identity.get("version", "unknown")) + ("+modified" if identity.get("dirty") else ""), "commit":identity.get("commit") or "unknown"})
                return result
            result = self.players.command(data)
            if data.get("action") == "joystick_deadzone":
                self.revision += 1
                return self.player_snapshot()
            if data.get("action") == "read":
                return self.player_snapshot()
            if data.get("action") in ("create", "select", "delete", "restore", "reuse_calibration"):
                self.saved = copy.deepcopy(self.players.active["thresholds"])
                self.error = self.players.error
                self.preview, self.phases, self.recording = None, [], None
                self.center_generation = None
                self.revision += 1
            return result

    def apply_calibration_restore(self):
        """Finish a durable restore before the worker can resume output; retry after crashes."""
        from .model import Calibration
        with self.lock:
            pending = self.players.data["calibration_restore"]
            if pending is None:
                return None
            reference = Calibration(**pending["neutral"])
            save_calibration(self.path.with_name("calibration.json"), reference)
            data = copy.deepcopy(self.players.data)
            data["calibration_restore"] = None
            data["players"][data["active"]]["needs_center"] = False
            data["players"][data["active"]]["calibration"] = copy.deepcopy(pending)
            self.players.commit(data)
            self.calibration = reference
            return reference

    def _reach_snapshot(self):
        """Expose exact spans and safe limits without changing the calibration."""
        pending = self.players.data["calibration_restore"]
        reference = self.calibration
        if pending is not None:
            from .model import Calibration
            reference = Calibration(**pending["neutral"])
        elif reference is None and self.players.active["calibration"] is not None:
            from .model import Calibration
            reference = Calibration(**self.players.active["calibration"]["neutral"])
        elif reference is None:
            reference = load_calibration(self.path.with_name("calibration.json"))
        if reference is None:
            return {"available": False, "pending": bool(pending)}
        values = {name: getattr(reference, "reach_" + name) for name in REACH_DIRECTIONS}
        margin = self.base_config.coordinate_edge_margin
        effective = dict(values)
        if all(value == 0 for value in values.values()):
            effective = {
                "left": reference.palm_x - margin,
                "right": 1 - margin - reference.palm_x,
                "up": reference.palm_y - margin,
                "down": 1 - margin - reference.palm_y,
            }
        camera_width, camera_height = self.frame_size
        width = max(0.0, effective["left"] + effective["right"]) * camera_width
        height = max(0.0, effective["up"] + effective["down"]) * camera_height
        return {
            "available": True,
            "values": values,
            "limits": {
                "left": {"min": .05, "max": max(0.0, reference.palm_x - .025)},
                "right": {"min": .05, "max": max(0.0, .975 - reference.palm_x)},
                "up": {"min": .05, "max": max(0.0, reference.palm_y - .025)},
                "down": {"min": .05, "max": max(0.0, .975 - reference.palm_y)},
            },
            "custom": any(value != 0 for value in values.values()),
            "pending": bool(pending),
            "camera_width": camera_width,
            "camera_height": camera_height,
            "dimensions": {
                "width": round(width, 1),
                "height": round(height, 1),
                "aspect": round(width / height, 3) if height else None,
            },
        }

    def _reach_candidate(self, incoming, *, reset=False):
        """Replace only four reach spans on the current calibrated reference."""
        reference = self.calibration
        if reference is None:
            reference = load_calibration(self.path.with_name("calibration.json"))
        if reference is None:
            raise ValueError("Center your hand before changing movement reach.")
        if self.players.data["calibration_restore"] is not None:
            raise ValueError("Wait for the current reach values to finish saving.")
        if reset:
            values = dict.fromkeys(REACH_DIRECTIONS, 0.0)
        else:
            if not isinstance(incoming, dict) or set(incoming) != set(REACH_DIRECTIONS):
                raise ValueError("Enter left, right, up, and down reach values together.")
            values = {}
            for name in REACH_DIRECTIONS:
                value = incoming[name]
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("Reach values must be finite numbers.")
                values[name] = float(value)
            if any(value == 0 for value in values.values()):
                raise ValueError("Use Restore full camera field instead of mixing zero and custom reach values.")
            limits = self._reach_snapshot()["limits"]
            if any(not limits[name]["min"] <= values[name] <= limits[name]["max"]
                   for name in REACH_DIRECTIONS):
                raise ValueError("Reach values must stay inside the safe camera area.")
        return replace(reference, **{"reach_" + name: value for name, value in values.items()})

    def needs_center(self):
        """Keep delivery paused until explicit calibration follows a preset change."""
        with self.lock:
            return bool(self.players.error or self.players.active["needs_center"])

    def begin_center(self):
        """Associate a requested calibration with the active player generation."""
        with self.lock:
            self.center_generation = self.players.data["generation"]

    def finish_center(self, reference=None):
        """Persist successful calibration only for its original player."""
        with self.lock:
            generation = self.center_generation
            if generation is None and not self.players.active["needs_center"]:
                generation = self.players.data["generation"]
            self.players.centered(generation, reference)
            self.center_generation = None

    def _expire(self):
        """Discard temporary state when the browser lease ends."""
        self.diagnostics.expire()
        if self.session and self.clock() >= self.expires:
            self.session = None
            self.preview = None
            self.phases = []
            self.recording = None
            self.revision += 1
        if self.recording and self.clock() - self.recording[0] >= self.recording[2]:
            samples = self.recording[1]
            self.recording = None
            if len(samples) >= 12:
                self.phases.append(samples)
                self.error = None
                self.wizard_step = "record"
            else:
                self.error = "Not enough clear hand measurements. Keep your palm visible and retry this step."
                self.wizard_step = "record"

    def active(self) -> bool:
        """Return whether an unexpired tuning owner exists."""
        with self.lock:
            self._expire()
            return self.session is not None

    def configuration(self, config):
        """Overlay personal or preview thresholds without altering shipped defaults."""
        with self.lock:
            self._expire()
            cache_key = (id(config), self.revision)
            if self._configuration_cache is not None and self._configuration_cache[0] == cache_key:
                return self._configuration_cache[1]
            values = dict(self.saved)
            values.update(self.preview or {})
            deadzone = self.players.active["joystick_deadzone"]
            configured = config
            if values or deadzone != config.chosen_joystick_deadzone():
                configured = replace(config, thresholds=copy.deepcopy(values), joystick_deadzone=deadzone)
            self._configuration_cache = (cache_key, configured)
            return configured

    def snapshot(self) -> dict:
        """Return browser-safe progress and measurements without recording images."""
        with self.lock:
            self._expire()
            return {"active": bool(self.session), "gesture": self.gesture,
                    "mode": "hand_setup" if self.gesture == "hand_setup" else "gesture",
                    "total_phases": 3,
                    "finger_feedback": copy.deepcopy(self.finger_feedback) if self.ready and self.clock() - self.last_observed < 2 else {},
                    "gestures": LABELS, "components": list(GESTURES[self.gesture]),
                    "saved": copy.deepcopy(self.saved), "effective": copy.deepcopy(self.effective),
                    "preview": copy.deepcopy(self.preview), "measurements": dict(self.latest),
                    "recording": self.recording is not None, "completed_phases": len(self.phases),
                    "samples": len(self.recording[1]) if self.recording else 0,
                    "ready": self.ready and self.clock() - self.last_observed < 2,
                    "stable_ready": bool(self.ready_since is not None and self.clock() - self.ready_since >= 1),
                    "problem": self.problem, "problems": PROBLEMS, "wizard_step": self.wizard_step,
                    "recipe": tuning_recipe(self.gesture),
                    "test": {"active": self.test_started is not None, "cycles": self.test_cycles,
                             "neutral_seconds": round(self.test_neutral_seconds, 1),
                             "passed": self.test_passed},
                    "image_quality": copy.deepcopy(self.image_quality),
                    "reach": self._reach_snapshot(),
                    "diagnostic": self.diagnostics.snapshot(),
                    "error": self.error, "revision": self.revision}

    def invalidate(self):
        """Invalidate measurement sessions after an explicit neutral calibration."""
        with self.lock:
            self.phases, self.recording, self.preview = [], None, None
            self._reset_test()
            self.revision += 1
            self.error = "Neutral calibration changed. Record your open hand again."

    def observe(self, observation, calibration, config, calibrated, *, frame=None,
                image_quality=None, performance=None, recognized=None):
        """Sample each worker frame once, accepting only calibrated valid hands."""
        with self.lock:
            self._expire()
            if self.calibration is not None and calibration != self.calibration and self.session:
                self.invalidate()
            self.calibration = calibration
            if not self.session:
                self.ready = False
                self.finger_feedback = {}
                return
            self.last_observed = self.clock()
            self.base_config = replace(config, thresholds={})
            self.image_quality = dict(image_quality or {})
            shape = getattr(frame, "shape", ())
            if len(shape) >= 2 and all(type(value) is int and value > 0 for value in shape[:2]):
                self.frame_size = (shape[1], shape[0])
            self.ready = (calibrated and observation.usable
                          and self.image_quality.get("whole_hand_visible", True))
            if self.ready:
                if self.ready_since is None:
                    self.ready_since = self.clock()
            else:
                self.ready_since = None
            self.latest = measurements(observation, calibration)
            requirements = GESTURES[self.gesture]
            if len(self.phases) in (0, 2):
                requirements = dict.fromkeys(requirements, False)
            self.finger_feedback = finger_pose_feedback(config, self.gesture, requirements, self.latest)
            self.effective = {key: dict(zip(("on", "off"), config.pair(key))) for key in CHANNELS}
            self._observe_test(config, set(recognized or ()))
            if frame is not None:
                self.diagnostics.observe(frame, {
                    "detected": observation.detected,
                    "confidence": observation.confidence,
                    "confidence_source": observation.confidence_source,
                    "inference_ms": (performance or {}).get("inference_ms"),
                    "sample_age_ms": (performance or {}).get("sample_age_ms"),
                    "hand_luma": self.image_quality.get("hand_luma"),
                    "recognized": list(recognized or ()),
                })
            if not self.recording:
                return
            started, samples, duration = self.recording
            if (calibrated and observation.usable
                    and observation.timestamp != self.last_frame and len(samples) < 180
                    and all(math.isfinite(v) for v in self.latest.values())):
                samples.append(dict(self.latest))
            self.last_frame = observation.timestamp
            if self.clock() - started >= duration:
                self.recording = None
                if len(samples) < 12:
                    self.error = "Not enough clear hand measurements. Keep your palm visible and retry this step."
                else:
                    self.phases.append(samples)
                    self.error = None

    def _reset_test(self) -> None:
        """Clear the temporary guided preview-validation state."""
        self.test_started = None
        self.test_was_active = False
        self.test_cycles = 0
        self.test_neutral_seconds = 0.0
        self.test_last_at = None
        self.test_passed = False

    def _selected_active(self, config: GestureConfig) -> bool:
        """Evaluate the selected preview using the same component boundaries."""
        if not self.ready:
            return False
        if self.gesture in ("start", "select", "closed_hand", "menu_guard", "hand_setup"):
            requirements = GESTURES[self.gesture]
            return all(item["matches"] for item in finger_pose_feedback(
                config, self.gesture, requirements, self.latest).values())
        on = config.pair(self.gesture)[0]
        return self.latest.get(self.gesture, 0.0) >= on

    def _observe_test(self, config: GestureConfig, recognized: set[str]) -> None:
        """Count complete preview activations, releases, and neutral time."""
        if self.test_started is None or self.test_passed:
            return
        now = self.clock()
        # Depth gestures keep the gameplay two-frame/motion confirmation rule;
        # a stationary near or far hand cannot pass the guided test.
        active = self.gesture in recognized if self.gesture in DEPTH_GESTURES else self._selected_active(config)
        if self.test_last_at is not None and not active:
            self.test_neutral_seconds += max(0.0, min(.5, now - self.test_last_at))
        if self.test_was_active and not active:
            self.test_cycles += 1
        self.test_was_active = active
        self.test_last_at = now
        self.test_passed = self.test_cycles >= 2 and self.test_neutral_seconds >= 3.0
        if self.test_passed:
            self.wizard_step = "save"

    def command(self, data: dict) -> dict:
        """Validate ownership, stage recordings, preview changes, and atomically save."""
        with self.lock:
            self._expire()
            action, session = data.get("action"), data.get("session")
            if not isinstance(session, str) or not 8 <= len(session) <= 128 or not all(c.isalnum() or c in "-_" for c in session):
                raise ValueError("A valid tuning session is required.")
            if action == "begin":
                if "player" in data and (data["player"] != self.players.data["active"] or data.get("generation") != self.players.data["generation"]):
                    raise ValueError("The player changed. Reload Glove Academy before tuning.")
                if self.session and self.session != session:
                    raise ValueError("Another Learn tab is tuning. Close it or wait for its session to expire.")
                self.session, self.expires = session, self.clock() + 6
            elif self.session != session:
                raise ValueError("Tuning session expired. Switch to Tune again.")
            else:
                self.expires = self.clock() + 6
            if action in ("begin", "heartbeat"):
                return self.snapshot()
            if action == "end":
                self.diagnostics.cancel()
                self.expires = 0
                self._expire()
            elif action == "select":
                gesture = data.get("gesture")
                if gesture not in GESTURES:
                    raise ValueError("Choose a supported gesture.")
                self.gesture, self.phases, self.recording, self.preview = gesture, [], None, None
                self.error = None
                self.finger_feedback = {}
                self.wizard_step = "record"
                self._reset_test()
                self.revision += 1
            elif action == "choose_problem":
                problem = data.get("problem")
                if problem not in PROBLEMS:
                    raise ValueError("Choose what you would like to fix.")
                self.problem = problem
                self.phases, self.recording, self.preview = [], None, None
                self._reset_test()
                if problem == "setup":
                    self.gesture, self.wizard_step = "hand_setup", "record"
                elif problem == "off_center":
                    self.wizard_step = "center"
                else:
                    self.wizard_step = "gesture"
                self.error = None
                self.revision += 1
            elif action == "record":
                if self.recording or len(self.phases) >= 3:
                    raise ValueError("Finish or restart this recording first.")
                if not self.ready or self.clock() - self.last_observed >= 2:
                    raise ValueError("Show your whole hand clearly and wait for tracking.")
                self.preview = None
                self.revision += 1
                self.error = None
                self.recording = (self.clock(), [], 3.0)
            elif action == "wizard_record":
                if self.recording or len(self.phases) >= 3:
                    raise ValueError("Finish or restart this recording first.")
                if self.ready_since is None or self.clock() - self.ready_since < 1:
                    raise ValueError("Keep your whole hand clearly visible for a moment, then try again.")
                recipe = tuning_recipe(self.gesture)
                self.preview = None
                self._reset_test()
                self.wizard_step = "recording"
                self.error = None
                self.revision += 1
                self.recording = (self.clock(), [], recipe["durations"][len(self.phases)])
            elif action == "suggest":
                self.preview = None
                self.revision += 1
                activation, release = SUGGESTION_BIAS.get(self.problem or "setup", SUGGESTION_BIAS["setup"])
                self.preview = suggest(self.gesture, self.phases, self.configuration(self.base_config),
                                       activation, release)
                self.wizard_step = "test"
                self._reset_test()
                self.revision += 1
            elif action == "start_test":
                if not self.preview:
                    raise ValueError("Analyze the recordings before testing the adjustment.")
                self._reset_test()
                self.test_started = self.clock()
                self.test_last_at = self.test_started
                self.wizard_step = "test"
            elif action == "wizard_save":
                if not self.test_passed or not self.preview:
                    raise ValueError("Complete the guided try-it test before saving.")
                merged = dict(self.saved, **validate_overrides(self.preview))
                self.players.save_thresholds(merged)
                self.saved, self.preview = merged, None
                self.wizard_step = "done"
                self.error = None
                self.revision += 1
            elif action == "wizard_back":
                self.phases, self.recording, self.preview = [], None, None
                self._reset_test()
                if self.wizard_step in ("record", "recording") and self.problem in ("difficult", "accidental"):
                    self.wizard_step = "gesture"
                else:
                    self.wizard_step = "problem"
                    self.problem = None
                self.error = None
                self.revision += 1
            elif action == "diagnostic_begin":
                self.diagnostics.begin()
            elif action == "diagnostic_record":
                if self.ready_since is None or self.clock() - self.ready_since < 1:
                    raise ValueError("Keep your whole hand clearly visible before recording this step.")
                self.diagnostics.record()
            elif action == "diagnostic_cancel":
                self.diagnostics.cancel()
            elif action in ("reach_save", "reach_reset"):
                candidate = self._reach_candidate(
                    data.get("reach"), reset=action == "reach_reset"
                )
                self.players.stage_calibration(candidate)
                self.error = None
                self.revision += 1
            elif action in ("preview", "save"):
                values = validate_overrides(data.get("thresholds"))
                if not values or set(values) - set(GESTURES[self.gesture]):
                    raise ValueError("Adjust only the selected gesture's components.")
                if action == "save":
                    merged = dict(self.saved, **values)
                    self.players.save_thresholds(merged)
                    self.saved, self.preview = merged, None
                else:
                    self.preview = values
                    self.wizard_step = "test"
                    self._reset_test()
                self.error = None
                self.revision += 1
            elif action == "reset":
                merged = {k: v for k, v in self.saved.items() if k not in GESTURES[self.gesture]}
                self.players.save_thresholds(merged)
                self.saved, self.preview, self.error = merged, None, None
                self.revision += 1
            elif action == "discard":
                self.phases, self.recording, self.preview, self.error = [], None, None, None
                self.revision += 1
            else:
                raise ValueError("Unknown tuning operation.")
            return self.snapshot()
