#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-direction-response.py
# Purpose: Compare deterministic direction-response latency in native Nestopia and FCEUmm.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Added native coordinate filter step-response and jitter checks.
#   2026-09-04 - Added matched native and FCEUmm direction-response benchmarks.
# Full history: docs/CHANGELOG.md and Git history.

"""Measure core input pickup and first input-caused video divergence in frames."""

from __future__ import annotations

import argparse
from dataclasses import replace
import ctypes
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virtualglove.gesture import Calibration, GestureConfig, GestureEngine  # noqa: E402
from virtualglove.model import HandObservation  # noqa: E402
from virtualglove.native_state import NativeStateWriter  # noqa: E402


TRACE_SPEC = importlib.util.spec_from_file_location(
    "powerglove_trace_runner", ROOT / "scripts/run-nestopia-powerglove-trace.py"
)
trace_runner = importlib.util.module_from_spec(TRACE_SPEC)
assert TRACE_SPEC.loader is not None
TRACE_SPEC.loader.exec_module(trace_runner)

RETRO_DEVICE_GAMEPAD = trace_runner.RETRO_DEVICE_GAMEPAD
RETRO_DEVICE_POWERGLOVE = trace_runner.RETRO_DEVICE_POWERGLOVE
JOY_START = 3
JOY_UP = 4
JOY_DOWN = 5
JOY_LEFT = 6
JOY_RIGHT = 7
DIRECTION_IDS = {"up": JOY_UP, "down": JOY_DOWN, "left": JOY_LEFT, "right": JOY_RIGHT}


class BenchmarkFrontend(trace_runner.HeadlessFrontend):
    """Headless frontend that records exactly when a core queries joypad state."""

    def __init__(self, scratch: Path) -> None:
        self.joypad_mask = 0
        self.run_number = 0
        self.queried_runs: set[int] = set()
        self.input_devices: set[int] = set()
        super().__init__(scratch)

    def input_state(self, port: int, device: int, _index: int, ident: int) -> int:
        """Record joypad queries and return the current deterministic mask."""
        if port == 0:
            self.input_devices.add(device)
        if port != 0 or device != trace_runner.RETRO_DEVICE_JOYPAD:
            return 0
        self.queried_runs.add(self.run_number)
        if ident == trace_runner.RETRO_DEVICE_ID_JOYPAD_MASK:
            return self.joypad_mask
        return int(bool(self.joypad_mask & (1 << ident)))


def bind_state(core: ctypes.CDLL) -> None:
    """Bind the libretro savestate calls used for matched branch comparisons."""
    trace_runner.bind(core)
    core.retro_serialize_size.restype = ctypes.c_size_t
    core.retro_serialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    core.retro_serialize.restype = ctypes.c_bool
    core.retro_unserialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    core.retro_unserialize.restype = ctypes.c_bool


class Session:
    """Own one loaded core/ROM pair and its deterministic frontend."""

    def __init__(self, core_path: Path, rom_path: Path, scratch: Path, device: int) -> None:
        self.core = ctypes.CDLL(str(core_path))
        bind_state(self.core)
        self.frontend = BenchmarkFrontend(scratch)
        for name in ("environment", "video", "audio", "audio_batch", "input_poll", "input_state"):
            getattr(self.core, "retro_set_" + ("video_refresh" if name == "video" else "audio_sample_batch" if name == "audio_batch" else "audio_sample" if name == "audio" else name))(self.frontend.callbacks[name])
        information = trace_runner.RetroSystemInfo()
        self.core.retro_get_system_info(ctypes.byref(information))
        self.core.retro_init()
        self.rom = rom_path.read_bytes()
        self.rom_buffer = ctypes.create_string_buffer(self.rom)
        game = trace_runner.RetroGameInfo(
            os.fsencode(rom_path), ctypes.cast(self.rom_buffer, ctypes.c_void_p), len(self.rom), None
        )
        if not self.core.retro_load_game(ctypes.byref(game)):
            raise RuntimeError("core rejected " + rom_path.name)
        self.core.retro_set_controller_port_device(0, device)
        self.name = (information.library_name or b"").decode(errors="replace")
        self.version = (information.library_version or b"").decode(errors="replace")

    def run(self, joypad_mask: int = 0) -> tuple[int | None, bool]:
        """Advance one emulated frame and report its video CRC and input poll."""
        self.frontend.joypad_mask = joypad_mask
        self.frontend.run_number += 1
        run_number = self.frontend.run_number
        self.core.retro_run()
        return self.frontend.last_video_crc, run_number in self.frontend.queried_runs

    def save(self) -> bytes:
        """Serialize the current deterministic emulator state."""
        size = self.core.retro_serialize_size()
        payload = ctypes.create_string_buffer(size)
        if not size or not self.core.retro_serialize(payload, size):
            raise RuntimeError(self.name + " did not produce a savestate")
        return payload.raw

    def load(self, payload: bytes) -> None:
        """Restore a previously serialized emulator state."""
        buffer = ctypes.create_string_buffer(payload)
        if not self.core.retro_unserialize(buffer, len(payload)):
            raise RuntimeError(self.name + " rejected its savestate")

    def close(self) -> None:
        """Unload the ROM and release the libretro core."""
        self.core.retro_unload_game()
        self.core.retro_deinit()


def first_divergence(neutral: list[int | None], changed: list[int | None]) -> int | None:
    """Return the first one-based frame whose output differs between matched branches."""
    return next((index for index, pair in enumerate(zip(neutral, changed), 1) if pair[0] != pair[1]), None)


def matched_branches(session: Session, saved: bytes, baseline_mask: int, changed_mask: int,
                     frames: int, before_frame=None, report_input_poll: bool = True) -> dict:
    """Run baseline and changed inputs from the exact same serialized machine state."""
    outputs = []
    queried = []
    for branch, mask in (("baseline", baseline_mask), ("changed", changed_mask)):
        session.load(saved)
        branch_outputs = []
        branch_queries = []
        for frame in range(1, frames + 1):
            if before_frame is not None:
                before_frame(branch, frame)
            crc, was_queried = session.run(mask)
            branch_outputs.append(crc)
            branch_queries.append(was_queried)
        outputs.append(branch_outputs)
        queried.append(branch_queries)
    divergence = first_divergence(outputs[0], outputs[1])
    result = {
        "first_video_divergence_frame": divergence,
        "first_video_divergence_ms_at_60hz": (
            round(divergence * 1000 / 60, 1) if divergence is not None else None
        ),
        "compared_frames": frames,
    }
    if report_input_poll:
        result["libretro_input_polled_on_frame_1"] = queried[1][0]
    return result


def observation(timestamp: float, dx: float = 0.0, dy: float = 0.0) -> HandObservation:
    """Create one deterministic open-hand camera observation around calibrated center."""
    return HandObservation(
        timestamp=timestamp, detected=True, confidence=1.0,
        palm_x=.5 + dx * .2, palm_y=.5 + dy * .2, palm_scale=.2,
        thumb_curl=0, index_curl=0, middle_curl=0, ring_curl=0, pinky_curl=0,
    )


def recognition_results() -> dict:
    """Prove each side activates and the centre box releases on the next sample."""
    result = {}
    vectors = {"left": (-.31, 0), "right": (.31, 0), "up": (0, -.31), "down": (0, .31)}
    releases = {"left": (-.30, 0), "right": (.30, 0), "up": (0, -.30), "down": (0, .30)}
    calibration = Calibration(.5, .5, .2, 0, 0, 0)
    for direction in DIRECTION_IDS:
        engine = GestureEngine("program_g", GestureConfig(joystick_deadzone=.60), calibration=calibration)
        dx, dy = vectors[direction]
        activated = engine.update(replace(observation(1.0), palm_x=.5+dx, palm_y=.5+dy)).dpad
        dx, dy = releases[direction]
        released = engine.update(replace(observation(1.1), palm_x=.5+dx, palm_y=.5+dy)).dpad
        result[direction] = {
            "displacement_units": "camera_frame_fraction",
            "activation_displacement": .31,
            "activated": activated[direction],
            "release_displacement": .30,
            "released": not any(released.values()),
        }
    return result


def coordinate_filter_results() -> dict:
    """Measure the shared full-field native X/Y filter without an emulator queue."""
    calibration = Calibration(.5, .5, .2, 0, 0, 0)
    engine = GestureEngine("super_glove_ball", calibration=calibration)
    engine.update(observation(0.0))
    jitter_values = [
        engine.update(HandObservation(
            timestamp=index * .025, detected=True, confidence=1.0,
            palm_x=x, palm_y=.5, palm_scale=.2,
        )).axes["x"]
        for index, x in enumerate((.502, .498, .501, .499), 1)
    ]
    movement_started = .125
    target_x = round((.80 - .50) / (.50 - engine.config.coordinate_edge_margin) * 32767)
    samples = []
    reached_ms = None
    for timestamp in (movement_started, .200, .275):
        value = engine.update(HandObservation(
            timestamp=timestamp, detected=True, confidence=1.0,
            palm_x=.80, palm_y=.20, palm_scale=.2,
        )).axes["x"]
        fraction = min(1.0, abs(value) / abs(target_x))
        samples.append({"elapsed_ms": round((timestamp - movement_started) * 1000),
                        "x": value, "target_fraction": round(fraction, 3)})
        if reached_ms is None and fraction >= .90:
            reached_ms = round((timestamp - movement_started) * 1000)
    return {
        "target_x": target_x,
        "reaches_90_percent_ms": reached_ms,
        "meets_150_ms_target": reached_ms is not None and reached_ms <= 150,
        "stationary_jitter_span": max(jitter_values) - min(jitter_values),
        "samples": samples,
    }


def prepare_fceumm_gun_smoke(session: Session) -> bytes:
    """Advance Gun Smoke from boot into active play using conventional Start."""
    for _ in range(120):
        session.run()
    for _ in range(3):
        session.run(1 << JOY_START)
    for _ in range(780):
        session.run()
    return session.save()


def prepare_fceumm_super_glove_ball(session: Session) -> bytes:
    """Advance Super Glove Ball into play using only conventional joypad input."""
    for _ in range(420):
        session.run()
    for _ in range(18):
        session.run(1 << JOY_START)
    for _ in range(180):
        session.run()
    return session.save()


def benchmark_fceumm(core: Path, rom: Path, scratch: Path, frames: int,
                     prepare=prepare_fceumm_gun_smoke) -> dict:
    """Measure each D-pad direction in stock FCEUmm from one matched game state."""
    session = Session(core, rom, scratch, RETRO_DEVICE_GAMEPAD)
    try:
        saved = prepare(session)
        directions = {}
        for name, ident in DIRECTION_IDS.items():
            mask = 1 << ident
            activation = matched_branches(session, saved, 0, mask, frames)
            session.load(saved)
            for _ in range(8):
                session.run(mask)
            active_saved = session.save()
            release = matched_branches(session, active_saved, mask, 0, frames)
            directions[name] = {"activation": activation, "release": release}
        return {
            "core": session.name, "version": session.version,
            "rom_sha256": hashlib.sha256(session.rom).hexdigest(),
            "input_mode": "standard_libretro_joypad",
            "libretro_callback_devices": sorted(session.frontend.input_devices),
            "recognition": recognition_results(), "directions": directions,
        }
    finally:
        session.close()


def native_sample(writer: NativeStateWriter, sequence: int, x: int = 0, y: int = 0) -> None:
    """Publish one valid calibrated native X/Y sample for a benchmark frame."""
    writer.write({
        "sequence": sequence, "profile": "super_glove_ball",
        "detected": True, "calibrated": True,
        "axes": {"x": x, "y": y, "z": 0, "roll": 0},
        "fingers": {}, "buttons": {},
    })


def prepare_native(session: Session, writer: NativeStateWriter) -> bytes:
    """Advance Super Glove Ball into native gameplay without a gamepad fallback."""
    sequence = 0
    for _ in range(420):
        sequence += 1; native_sample(writer, sequence); session.run()
    for _ in range(18):
        sequence += 1
        writer.write({
            "sequence": sequence, "profile": "super_glove_ball",
            "detected": True, "calibrated": True,
            "axes": {"x": 0, "y": 0, "z": 0, "roll": 0},
            "fingers": {}, "buttons": {"start": True},
        })
        session.run()
    for _ in range(180):
        sequence += 1; native_sample(writer, sequence); session.run()
    return session.save()


def benchmark_native(core: Path, rom: Path, state: Path, scratch: Path, frames: int) -> dict:
    """Measure signed coordinate steps through the exact-ROM native path."""
    os.environ["VIRTUALGLOVE_NATIVE_STATE"] = str(state)
    os.environ.pop("VIRTUALGLOVE_TRACE", None)
    writer = NativeStateWriter(state)
    session = Session(core, rom, scratch, RETRO_DEVICE_POWERGLOVE)
    try:
        saved = prepare_native(session, writer)
        sequence = 10000
        stimuli = {
            "left": (-32767, 0), "right": (32767, 0),
            # Native-state Y follows camera coordinates: negative is up.
            "up": (0, -32767), "down": (0, 32767),
        }
        directions = {}
        for name, (x, y) in stimuli.items():
            def before(branch, _frame, x=x, y=y):
                """Publish neutral or changed coordinates before each branch frame."""
                nonlocal sequence
                sequence += 1
                native_sample(writer, sequence, *(x, y) if branch == "changed" else (0, 0))
            activation = matched_branches(
                session, saved, 0, 0, frames, before, report_input_poll=False
            )

            session.load(saved)
            for _ in range(8):
                sequence += 1
                native_sample(writer, sequence, x, y)
                session.run()
            active_saved = session.save()

            def before_release(branch, _frame, x=x, y=y):
                """Continue the hold or return the changed branch to neutral."""
                nonlocal sequence
                sequence += 1
                native_sample(writer, sequence, *((0, 0) if branch == "changed" else (x, y)))

            release = matched_branches(
                session, active_saved, 0, 0, frames, before_release,
                report_input_poll=False,
            )
            directions[name] = {"activation": activation, "release": release}

        sweep = {}
        for magnitude in (1024, 2048, 4096, 8192, 16384, 32767):
            def before(branch, _frame, magnitude=magnitude):
                """Publish one positive-X magnitude only to the changed branch."""
                nonlocal sequence
                sequence += 1
                native_sample(writer, sequence, magnitude if branch == "changed" else 0, 0)
            sweep[str(magnitude)] = matched_branches(
                session, saved, 0, 0, frames, before, report_input_poll=False
            )
        return {
            "core": session.name, "version": session.version,
            "rom_sha256": hashlib.sha256(session.rom).hexdigest(),
            "input_mode": "native_power_glove_packet",
            "directions": directions, "positive_x_sweep": sweep,
        }
    finally:
        session.close()
        writer.close()


def parser() -> argparse.ArgumentParser:
    """Build the deterministic benchmark command-line interface."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--nestopia-core", type=Path, required=True)
    result.add_argument("--super-glove-ball-rom", type=Path, required=True)
    result.add_argument("--fceumm-core", type=Path, required=True)
    result.add_argument(
        "--fceumm-rom", type=Path,
        help="Optional positional FCEUmm reference ROM (Gun Smoke in the recorded report)",
    )
    result.add_argument("--scratch", type=Path, required=True)
    result.add_argument("--frames", type=int, default=12)
    result.add_argument("--output", type=Path)
    return result


def main() -> int:
    """Run requested core lanes and emit their machine-readable report."""
    args = parser().parse_args()
    if not 1 <= args.frames <= 120:
        raise ValueError("--frames must be between 1 and 120")
    args.scratch.mkdir(parents=True, exist_ok=True)
    result = {
        "unit": "emulated_frames",
        "native_coordinate_filter": coordinate_filter_results(),
        "native_super_glove_ball": benchmark_native(
            args.nestopia_core, args.super_glove_ball_rom,
            args.scratch / "native-state", args.scratch / "nestopia", args.frames,
        ),
        "fceumm_super_glove_ball": benchmark_fceumm(
            args.fceumm_core, args.super_glove_ball_rom,
            args.scratch / "fceumm-super-glove-ball", args.frames,
            prepare_fceumm_super_glove_ball,
        ),
    }
    if args.fceumm_rom:
        result["fceumm_gun_smoke"] = benchmark_fceumm(
            args.fceumm_core, args.fceumm_rom,
            args.scratch / "fceumm-reference", args.frames,
        )
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
