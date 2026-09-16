# Project: VirtualGlove
# File: src/powerglove_vision/launchbox_hook.py
# Purpose: Launch NES games from LaunchBox with authenticated VirtualGlove profile leases.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added exact-ROM LaunchBox-to-RetroArch game leases.
# Full history: docs/CHANGELOG.md and Git history.

"""LaunchBox-to-RetroArch bridge for exact-ROM VirtualGlove profile selection."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable

from .profile_control import load_registry, read_token, select_profile_settings, send_request


SUPPORTED_ROM_EXTENSIONS = {".nes", ".zip", ".7z"}


def default_settings_path() -> Path:
    """Return the per-user Windows settings path without inventing a shared location."""
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        return Path.home() / "AppData" / "Local" / "VirtualGlove" / "data" / "launcher.json"
    return Path(root) / "VirtualGlove" / "data" / "launcher.json"


def load_settings(path: Path) -> dict:
    """Load the bounded local launcher settings required by the Windows bridge."""
    data = json.loads(Path(path).read_text())
    required = ("retroarch", "fceumm_core", "native_core", "registry", "token_file", "uno_q")
    if not isinstance(data, dict) or any(not isinstance(data.get(key), str) or not data[key]
                                        for key in required):
        raise ValueError("LaunchBox settings are incomplete")
    for key in ("retroarch", "fceumm_core", "native_core", "registry", "token_file"):
        if "\x00" in data[key]:
            raise ValueError("LaunchBox settings contain an invalid path")
    return data


def launch_command(settings: dict, rom: Path, selection: dict | None) -> tuple[list[str], str]:
    """Select the native core only for Super Glove Ball and build a shell-free command."""
    if rom.suffix.casefold() not in SUPPORTED_ROM_EXTENSIONS:
        raise ValueError("LaunchBox supplied an unsupported ROM type")
    native = selection is not None and selection.get("profile") == "super_glove_ball"
    core = settings["native_core"] if native else settings["fceumm_core"]
    emulator = "lr-nestopia-powerglove" if native else "lr-fceumm"
    command = [settings["retroarch"], "-L", core]
    append_config = settings.get("retroarch_config")
    if append_config:
        command.extend(("--appendconfig", str(append_config)))
    command.append(str(rom))
    return command, emulator


def run_game(
    settings: dict,
    rom: Path,
    *,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    request: Callable[..., dict] = send_request,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run RetroArch and renew an authenticated lease until that exact process exits."""
    rom = Path(rom)
    try:
        registry = load_registry(Path(settings["registry"]))
        selection = select_profile_settings(registry, "nes", rom.name)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # A damaged or unavailable optional registry must not turn LaunchBox
        # into a game-launch blocker. Fall back to ordinary FCEUmm with no lease.
        selection = None
    command, emulator = launch_command(settings, rom, selection)
    environment = os.environ.copy()
    environment["VIRTUALGLOVE_NATIVE_STATE"] = str(settings.get(
        "native_state", default_settings_path().parent.parent / "run" / "native-state.bin"
    ))
    process = popen(command, env=environment)
    if selection is None:
        return int(process.wait())

    try:
        token = read_token(None, Path(settings["token_file"]))
    except (OSError, ValueError):
        # LaunchBox must remain usable before pairing or if its token was
        # removed. RetroArch still runs, but no gesture lease is asserted.
        return int(process.wait())
    session_id = uuid.uuid4().hex
    heartbeat = float(settings.get("heartbeat_seconds", 2.0))
    lease = float(settings.get("lease_seconds", 6.0))
    timeout = float(settings.get("timeout", 0.4))
    if not 0.25 <= heartbeat <= 5.0 or not 2.0 <= lease <= 15.0:
        process.terminate()
        raise ValueError("LaunchBox game lease timing is out of range")

    try:
        while process.poll() is None:
            try:
                request(
                    settings["uno_q"], int(settings.get("port", 55356)), token,
                    selection["profile"], "nes", rom.name, timeout,
                    session_id=session_id, lease_seconds=lease, emulator=emulator,
                    rapid_a=selection.get("rapid_a"), rapid_b=selection.get("rapid_b"),
                )
            except (OSError, TimeoutError, ValueError, KeyError, TypeError):
                pass
            sleep(heartbeat)
        return int(process.wait())
    finally:
        try:
            request(
                settings["uno_q"], int(settings.get("port", 55356)), token,
                None, "", "", timeout,
            )
        except (OSError, TimeoutError, ValueError, KeyError, TypeError):
            pass


def build_parser() -> argparse.ArgumentParser:
    """Build the LaunchBox emulator-wrapper command line."""
    parser = argparse.ArgumentParser(description="Launch a LaunchBox NES game with VirtualGlove")
    parser.add_argument("rom", type=Path)
    parser.add_argument("--settings", type=Path, default=default_settings_path())
    return parser


def main() -> int:
    """Launch the game even when VirtualGlove profile signalling is unavailable."""
    args = build_parser().parse_args()
    try:
        settings = load_settings(args.settings)
        return run_game(settings, args.rom)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"VirtualGlove LaunchBox setup error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
