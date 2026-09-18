# Project: VirtualGlove
# File: src/virtualglove/launchbox_hook.py
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
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

from .profile_control import load_registry, read_token, select_profile_settings, send_request
from .retroarch_hotkeys import conflicts as hotkey_conflicts, format_conflicts


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
    if data.get("input_route") != "network-retropad":
        raise ValueError("LaunchBox input route is unsupported; rerun the current installer")
    port = data.get("retroarch_remote_port")
    if not isinstance(port, int) or isinstance(port, bool) or not 49152 <= port <= 65535:
        raise ValueError("LaunchBox RetroPad port is invalid; rerun the current installer")
    return data


def launch_command(settings: dict, rom: Path, selection: dict | None,
                   native_ready: bool = True) -> tuple[list[str], str]:
    """Select the native core only for Super Glove Ball and build a shell-free command."""
    if rom.suffix.casefold() not in SUPPORTED_ROM_EXTENSIONS:
        raise ValueError("LaunchBox supplied an unsupported ROM type")
    native = (native_ready and selection is not None
              and selection.get("profile") == "super_glove_ball")
    core = settings["native_core"] if native else settings["fceumm_core"]
    emulator = "lr-nestopia-powerglove" if native else "lr-fceumm"
    command = [settings["retroarch"], "-L", core]
    append_config = settings.get(
        "retroarch_native_config" if native else "retroarch_config"
    )
    if append_config:
        command.extend(("--appendconfig", str(append_config)))
    command.append(str(rom))
    return command, emulator


def native_core_ready(settings: dict) -> bool:
    """Reject a missing or changed native DLL before a Super Glove Ball launch."""
    path = Path(settings["native_core"])
    if not path.is_file():
        return False
    expected = settings.get("native_core_sha256")
    if expected is None:
        return True
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return False
    return digest.hexdigest() == expected.casefold()


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
    conflict = hotkey_conflicts([
        Path(settings.get("retroarch_main_config", Path(settings["retroarch"]).with_name("retroarch.cfg"))),
        Path(settings["retroarch_config"]),
    ]) if settings.get("retroarch_config") else []
    if conflict:
        message = (
            "Physical keyboard backup has a RetroArch command conflict; "
            "VirtualGlove RetroPad input remains available: " + format_conflicts(conflict)
        )
        print(message, file=sys.stderr)
        warning = settings.get("input_warning")
        if warning:
            try:
                Path(warning).write_text(message + "\n")
            except OSError:
                pass
    elif settings.get("input_warning"):
        try:
            Path(settings["input_warning"]).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
    wants_native = selection is not None and selection.get("profile") == "super_glove_ball"
    native_ready = not wants_native or native_core_ready(settings)
    if wants_native and not native_ready:
        print("Nestopia (VirtualGlove) is missing or changed; using FCEUmm joystick mode.",
              file=sys.stderr)
    command, emulator = launch_command(settings, rom, selection, native_ready=native_ready)
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
        # LaunchBox invokes this Python bridge directly. Ensure its per-user
        # receiver is alive on every launch so reboot and upgrade recovery do
        # not depend on a batch wrapper or a long-lived installer process.
        from .launchbox_runtime import ensure_background
        ensure_background(args.settings)
        return run_game(settings, args.rom)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"VirtualGlove LaunchBox setup error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
