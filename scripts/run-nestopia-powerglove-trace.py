#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/run-nestopia-powerglove-trace.py
# Purpose: Run an exact NES ROM through the isolated native core and capture deterministic Power Glove traces.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Added open, fist, index-point, and Power Punch packet phases.
#   2026-09-04 - Added deterministic exact-ROM native packet tracing.
# Full history: docs/CHANGELOG.md and Git history.

"""Drive the research libretro core without installing it or retaining a ROM."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from powerglove_vision.native_state import NativeStateWriter  # noqa: E402


RETRO_DEVICE_ANALOG = 5
RETRO_DEVICE_JOYPAD = 1
RETRO_DEVICE_GAMEPAD = (1 << 8) | RETRO_DEVICE_JOYPAD
RETRO_DEVICE_POWERGLOVE = (2 << 8) | RETRO_DEVICE_ANALOG
RETRO_DEVICE_ID_JOYPAD_START = 3
RETRO_DEVICE_ID_JOYPAD_MASK = 256
RETRO_ENVIRONMENT_GET_CAN_DUPE = 3
RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY = 9
RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10
RETRO_ENVIRONMENT_GET_VARIABLE = 15
RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE = 17
RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME = 18
RETRO_ENVIRONMENT_GET_CORE_ASSETS_DIRECTORY = 30
RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY = 31
RETRO_ENVIRONMENT_SET_CONTROLLER_INFO = 35
RETRO_ENVIRONMENT_GET_LANGUAGE = 39
RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE = 47
RETRO_ENVIRONMENT_GET_INPUT_BITMASKS = 51


class RetroSystemInfo(ctypes.Structure):
    """Match libretro's immutable core-description structure."""

    _fields_ = [
        ("library_name", ctypes.c_char_p),
        ("library_version", ctypes.c_char_p),
        ("valid_extensions", ctypes.c_char_p),
        ("need_fullpath", ctypes.c_bool),
        ("block_extract", ctypes.c_bool),
    ]


class RetroGameInfo(ctypes.Structure):
    """Match the in-memory game payload accepted by libretro."""

    _fields_ = [
        ("path", ctypes.c_char_p),
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
        ("meta", ctypes.c_char_p),
    ]


EnvironmentCallback = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)
VideoCallback = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t
)
AudioCallback = ctypes.CFUNCTYPE(None, ctypes.c_int16, ctypes.c_int16)
AudioBatchCallback = ctypes.CFUNCTYPE(
    ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t
)
InputPollCallback = ctypes.CFUNCTYPE(None)
InputStateCallback = ctypes.CFUNCTYPE(
    ctypes.c_int16, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint
)


class HeadlessFrontend:
    """Supply the small libretro frontend surface Nestopia needs for tracing."""

    def __init__(self, scratch: Path) -> None:
        self.scratch = scratch
        self.scratch_bytes = os.fsencode(scratch)
        self.pixel_format = 0
        self.frames = 0
        self.last_video_crc = None
        self.last_video = None
        self.last_video_shape = None
        self.phase_crcs: dict[str, set[int]] = {}
        self.phase = "initial"
        self.gamepad_start = False
        self.callbacks = {
            "environment": EnvironmentCallback(self.environment),
            "video": VideoCallback(self.video),
            "audio": AudioCallback(lambda _left, _right: None),
            "audio_batch": AudioBatchCallback(lambda _data, frames: frames),
            "input_poll": InputPollCallback(lambda: None),
            "input_state": InputStateCallback(self.input_state),
        }

    def environment(self, command: int, data: int) -> bool:
        """Answer stable, headless-safe libretro environment queries."""
        command &= 0xFFFF
        if command in (RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY,
                       RETRO_ENVIRONMENT_GET_CORE_ASSETS_DIRECTORY,
                       RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY):
            ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = self.scratch_bytes
            return True
        if command == RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
            self.pixel_format = ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0]
            return self.pixel_format in (0, 1, 2)
        if command == RETRO_ENVIRONMENT_GET_VARIABLE:
            return False
        if command == RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
            return True
        if command in (RETRO_ENVIRONMENT_GET_CAN_DUPE,
                       RETRO_ENVIRONMENT_GET_INPUT_BITMASKS):
            if not data:
                return False
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
            return True
        if command == RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
            return True
        if command == RETRO_ENVIRONMENT_GET_LANGUAGE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if command == RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0] = 3
            return True
        if command == RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
            return True
        return False

    def video(self, data: int, width: int, height: int, pitch: int) -> None:
        """Retain one frame in memory plus hashes used for phase comparison."""
        self.frames += 1
        if not data:
            return
        payload = ctypes.string_at(data, pitch * height)
        self.last_video = payload
        self.last_video_shape = (width, height, pitch)
        self.last_video_crc = zlib.crc32(payload)
        self.phase_crcs.setdefault(self.phase, set()).add(self.last_video_crc)

    def snapshot(self, destination: Path) -> None:
        """Write a temporary RGB PPM for explicit visual validation when requested."""
        if self.last_video is None or self.last_video_shape is None:
            return
        width, height, pitch = self.last_video_shape
        if self.pixel_format != 1:
            raise RuntimeError("temporary snapshots currently require XRGB8888 video")
        rgb = bytearray(width * height * 3)
        target = 0
        for row in range(height):
            source = row * pitch
            for column in range(width):
                blue, green, red = self.last_video[source:source + 3]
                rgb[target:target + 3] = bytes((red, green, blue))
                source += 4
                target += 3
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(f"P6\n{width} {height}\n255\n".encode() + rgb)

    def input_state(self, port: int, device: int, _index: int, ident: int) -> int:
        """Provide a bounded conventional Start pulse before attaching the glove."""
        if port != 0 or device != RETRO_DEVICE_JOYPAD or not self.gamepad_start:
            return 0
        if ident == RETRO_DEVICE_ID_JOYPAD_MASK:
            return 1 << RETRO_DEVICE_ID_JOYPAD_START
        return int(ident == RETRO_DEVICE_ID_JOYPAD_START)


def bind(core: ctypes.CDLL) -> None:
    """Declare the libretro ABI used by the headless trace runner."""
    core.retro_set_environment.argtypes = [EnvironmentCallback]
    core.retro_set_video_refresh.argtypes = [VideoCallback]
    core.retro_set_audio_sample.argtypes = [AudioCallback]
    core.retro_set_audio_sample_batch.argtypes = [AudioBatchCallback]
    core.retro_set_input_poll.argtypes = [InputPollCallback]
    core.retro_set_input_state.argtypes = [InputStateCallback]
    core.retro_get_system_info.argtypes = [ctypes.POINTER(RetroSystemInfo)]
    core.retro_load_game.argtypes = [ctypes.POINTER(RetroGameInfo)]
    core.retro_load_game.restype = ctypes.c_bool
    core.retro_set_controller_port_device.argtypes = [ctypes.c_uint, ctypes.c_uint]


def phase_state(name: str) -> dict:
    """Return the one-variable-at-a-time sample for a named trace phase."""
    state = {
        "detected": True, "calibrated": True,
        "axes": {"x": 0, "y": 0, "z": 0, "roll": 0},
        "buttons": {},
    }
    if name == "x_min":
        state["axes"]["x"] = -32767
    elif name == "x_max":
        state["axes"]["x"] = 32767
    elif name == "y_min":
        state["axes"]["y"] = -32767
    elif name == "y_max":
        state["axes"]["y"] = 32767
    elif name == "start":
        state["buttons"]["start"] = True
    elif name == "fist":
        state["buttons"]["closed_hand"] = True
    elif name == "index_point":
        state["buttons"]["index_point"] = True
    elif name == "power_punch":
        state["axes"]["z"] = 32767
        state["buttons"]["closed_hand"] = True
    elif name == "tracking_lost":
        state["detected"] = False
    elif name == "uncalibrated":
        state["calibrated"] = False
    return state


def trace_summary(path: Path) -> dict:
    """Extract packet framing evidence without including ROM contents."""
    phase = "before_phases"
    result = {"boundary_count": 0, "read_bit_count": 0, "phases": {}}
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("PGV phase="):
            phase = line.split("=", 1)[1].split()[0]
            result["phases"].setdefault(phase, {"packets": 0, "packet_values": {}})
        elif line.startswith("PGV packet boundary"):
            result["boundary_count"] += 1
        elif line.startswith("PGV read bit"):
            result["read_bit_count"] += 1
        elif line.startswith("PGV packet clock") and phase in result["phases"]:
            packet = line.split("bytes=", 1)[-1]
            current = result["phases"][phase]
            current["packets"] += 1
            current["packet_values"][packet] = current["packet_values"].get(packet, 0) + 1
    for current in result["phases"].values():
        current["packet_values"] = dict(sorted(
            current["packet_values"].items(), key=lambda item: (-item[1], item[0])
        ))
    return result


def run(args: argparse.Namespace) -> dict:
    """Load one exact ROM and execute the controlled native-input phases."""
    os.environ["VIRTUALGLOVE_NATIVE_STATE"] = str(args.state)
    os.environ["VIRTUALGLOVE_TRACE"] = "1"
    args.scratch.mkdir(parents=True, exist_ok=True)
    args.state.parent.mkdir(parents=True, exist_ok=True)

    trace_descriptor = os.open(args.trace_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    saved_stderr = os.dup(2)
    os.dup2(trace_descriptor, 2)
    os.close(trace_descriptor)
    writer = None
    core = None
    try:
        core = ctypes.CDLL(str(args.core))
        bind(core)
        frontend = HeadlessFrontend(args.scratch)
        core.retro_set_environment(frontend.callbacks["environment"])
        core.retro_set_video_refresh(frontend.callbacks["video"])
        core.retro_set_audio_sample(frontend.callbacks["audio"])
        core.retro_set_audio_sample_batch(frontend.callbacks["audio_batch"])
        core.retro_set_input_poll(frontend.callbacks["input_poll"])
        core.retro_set_input_state(frontend.callbacks["input_state"])

        information = RetroSystemInfo()
        core.retro_get_system_info(ctypes.byref(information))
        core.retro_init()

        rom = args.rom.read_bytes()
        rom_buffer = ctypes.create_string_buffer(rom)
        game = RetroGameInfo(
            os.fsencode(args.rom), ctypes.cast(rom_buffer, ctypes.c_void_p), len(rom), None
        )
        if not core.retro_load_game(ctypes.byref(game)):
            raise RuntimeError("Nestopia rejected the supplied ROM")
        gamepad_startup = args.startup_device == "gamepad"
        core.retro_set_controller_port_device(
            0, RETRO_DEVICE_GAMEPAD if gamepad_startup else RETRO_DEVICE_POWERGLOVE
        )

        writer = NativeStateWriter(args.state)
        phases = ((
            ("boot_gamepad", 420), ("start_gamepad", 1), ("glove_neutral", 240)
        ) if gamepad_startup else (
            ("boot_neutral", 420),
            ("start_physical" if args.start_source == "gamepad" else "start", 18),
            ("after_start", 120)
        )) + (
            ("x_min", 120),
            ("x_center", 120),
            ("x_max", 120),
            ("y_min", 120),
            ("y_center", 120),
            ("y_max", 120),
            ("open_hand", 60),
            ("fist", 60),
            ("open_after_fist", 60),
            ("index_point", 60),
            ("open_after_point", 60),
            ("power_punch", 60),
            ("open_after_punch", 60),
            ("tracking_lost", 30),
            ("uncalibrated", 30),
            ("stale", 30),
        )
        sequence = 0
        for name, count in phases:
            frontend.phase = name
            frontend.gamepad_start = name in ("start_gamepad", "start_physical")
            if gamepad_startup and name == "glove_neutral":
                core.retro_set_controller_port_device(0, RETRO_DEVICE_POWERGLOVE)
            os.write(2, f"PGV phase={name} frames={count}\n".encode())
            sample = phase_state(name)
            for _ in range(count):
                sequence += 1
                state = {
                    "sequence": sequence,
                    "profile": "super_glove_ball",
                    "detected": sample["detected"],
                    "calibrated": sample["calibrated"],
                    "axes": sample["axes"],
                    "fingers": {},
                    "buttons": sample["buttons"],
                }
                writer.write(state, arrived_ns=1 if name == "stale" else None)
                core.retro_run()
            if args.snapshot_dir is not None:
                frontend.snapshot(args.snapshot_dir / f"{name}.ppm")

        core.retro_unload_game()
        core.retro_deinit()
        return {
            "core": (information.library_name or b"").decode(errors="replace"),
            "version": (information.library_version or b"").decode(errors="replace"),
            "rom_size": len(rom),
            "rom_sha256": hashlib.sha256(rom).hexdigest(),
            "frames": frontend.frames,
            "pixel_format": frontend.pixel_format,
            "video_crc_counts": {
                name: len(values) for name, values in frontend.phase_crcs.items()
            },
            "trace_log": str(args.trace_log),
            "snapshot_dir": str(args.snapshot_dir) if args.snapshot_dir else None,
        }
    finally:
        if writer is not None:
            writer.close()
        os.dup2(saved_stderr, 2)
        os.close(saved_stderr)


def parser() -> argparse.ArgumentParser:
    """Build the exact-ROM trace command-line interface."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--core", type=Path, required=True)
    result.add_argument("--rom", type=Path, required=True)
    result.add_argument("--trace-log", type=Path, required=True)
    result.add_argument("--state", type=Path, required=True)
    result.add_argument("--scratch", type=Path, required=True)
    result.add_argument("--snapshot-dir", type=Path)
    result.add_argument("--startup-device", choices=("glove", "gamepad"), default="glove")
    result.add_argument("--start-source", choices=("native", "gamepad"), default="native")
    return result


def main() -> int:
    """Run the requested trace and print its non-ROM summary as JSON."""
    args = parser().parse_args()
    summary = run(args)
    summary["trace_evidence"] = trace_summary(args.trace_log)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
