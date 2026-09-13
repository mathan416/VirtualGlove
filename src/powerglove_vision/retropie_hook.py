# Project: VirtualGlove
# File: src/powerglove_vision/retropie_hook.py
# Purpose: Translate RetroPie launch and exit events into authenticated VirtualGlove profile requests.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Made absent process filesystems safe before lazy iteration.
#   2026-09-05 - Renew registered-game sessions while RetroArch is running.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-04 - Repaired persistent profile transport and asynchronous queue acknowledgements.
# Full history: docs/CHANGELOG.md and Git history.

"""Translate RetroPie launch and exit events into authenticated VirtualGlove profile requests."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .profile_control import load_registry, read_token, select_profile_settings, send_request


DEFAULT_SESSION_FILE = Path.home() / ".cache" / "virtualglove" / "active-game.json"
KNOWN_CORES = {
    "fceumm_libretro.so": "lr-fceumm",
    "nestopia_powerglove_libretro.so": "lr-nestopia-powerglove",
    "powerglove_dot_libretro.so": "lr-powerglove-dot",
}


def _write_session(path: Path, session_id: str) -> None:
    """Publish the current user-owned session identifier without following links."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("refusing symbolic game-session path")
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(temporary), flags, 0o600)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"session_id": session_id}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _session_is_current(path: Path, session_id: str) -> bool:
    """Return whether the session marker still belongs to this game launch."""
    try:
        if path.is_symlink():
            return False
        data = json.loads(path.read_text())
        return isinstance(data, dict) and data.get("session_id") == session_id
    except (OSError, ValueError, TypeError):
        return False


def _clear_session(path: Path, session_id: str | None = None) -> None:
    """Remove only the expected session marker, leaving a newer game untouched."""
    if session_id is not None and not _session_is_current(path, session_id):
        return
    try:
        if path.is_symlink():
            return
        path.unlink()
    except FileNotFoundError:
        pass


def _retroarch_running(proc_root: Path = Path("/proc")) -> bool:
    """Check for the RetroArch process used by every supported NES core."""
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "comm").read_text().strip().casefold().startswith("retroarch"):
                return True
        except OSError:
            continue
    return False


def _running_retroarch_emulator(proc_root: Path = Path("/proc")) -> str:
    """Identify the newest running supported core; unknown cores safely mean joystick."""
    candidates: list[tuple[int, str]] = []
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return ""
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if not (entry / "comm").read_text().strip().casefold().startswith("retroarch"):
                continue
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
            emulator = ""
            for index, argument in enumerate(arguments[:-1]):
                if argument == b"-L":
                    emulator = KNOWN_CORES.get(Path(os.fsdecode(arguments[index + 1])).name, "")
                    break
            candidates.append((int(entry.name), emulator))
        except (OSError, ValueError, UnicodeError):
            continue
    return max(candidates, default=(0, ""))[1]


def _start_session_process(args: argparse.Namespace, session_id: str) -> None:
    """Start a detached, user-owned lease refresher without delaying game launch."""
    command = [
        sys.executable, "-m", "powerglove_vision.retropie_hook", "session",
        args.system, args.emulator, args.rom, args.command,
        "--settings", str(args.settings), "--session-file", str(args.session_file),
        "--session-id", session_id,
        "--heartbeat-seconds", str(args.heartbeat_seconds),
        "--lease-seconds", str(args.lease_seconds),
        "--startup-wait", str(args.startup_wait),
    ]
    subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
    )


def _run_session(args: argparse.Namespace, settings: dict, token: str,
                 selection: dict) -> int:
    """Renew one game lease while its marker and RetroArch process remain active."""
    if isinstance(selection, str):  # Preserve the internal helper's older test/caller contract.
        selection = {"profile": selection}
    session_id = args.session_id
    if (not session_id or not session_id.isascii() or not session_id.isalnum()
            or not 16 <= len(session_id) <= 64):
        raise ValueError("invalid game session")
    deadline = time.monotonic() + args.startup_wait
    while _session_is_current(args.session_file, session_id) and not _retroarch_running():
        if time.monotonic() >= deadline:
            _clear_session(args.session_file, session_id)
            return 0
        time.sleep(0.1)
    while _session_is_current(args.session_file, session_id) and _retroarch_running():
        emulator = _running_retroarch_emulator()
        try:
            send_request(
                settings["uno_q"], int(settings.get("port", 55356)), token,
                selection["profile"], args.system, args.rom,
                float(settings.get("timeout", 0.4)),
                session_id=session_id, lease_seconds=args.lease_seconds,
                emulator=emulator,
                rapid_a=selection.get("rapid_a"),
                rapid_b=selection.get("rapid_b"),
            )
        except (OSError, TimeoutError, ValueError, KeyError, TypeError):
            pass
        time.sleep(args.heartbeat_seconds)
    if _session_is_current(args.session_file, session_id):
        try:
            send_request(
                settings["uno_q"], int(settings.get("port", 55356)), token,
                None, "", "", float(settings.get("timeout", 0.4)),
            )
        except (OSError, TimeoutError, ValueError, KeyError, TypeError):
            pass
        _clear_session(args.session_file, session_id)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the parser for RetroPie runcommand lifecycle arguments."""
    parser = argparse.ArgumentParser(description="RetroPie VirtualGlove launch hook")
    parser.add_argument("action", choices=("start", "end", "session"))
    parser.add_argument("system", nargs="?", default="")
    parser.add_argument("emulator", nargs="?", default="")
    parser.add_argument("rom", nargs="?", default="")
    parser.add_argument("command", nargs="?", default="")
    parser.add_argument("--settings", type=Path, default=Path("/etc/virtualglove/launcher.json"))
    parser.add_argument("--session-file", type=Path, default=DEFAULT_SESSION_FILE)
    parser.add_argument("--session-id")
    parser.add_argument("--heartbeat-seconds", type=float, default=2.0)
    parser.add_argument("--lease-seconds", type=float, default=6.0)
    parser.add_argument("--startup-wait", type=float, default=20.0)
    return parser


def main() -> int:
    """Select and request a profile without ever blocking the game launch on failure."""
    args = build_parser().parse_args()
    try:
        settings = json.loads(args.settings.read_text())
        token = read_token(None, Path(settings["token_file"]))
        selection = None
        if args.action in ("start", "session"):
            registry_path = Path(settings.get("registry", "/etc/virtualglove/games.json"))
            selection = select_profile_settings(
                load_registry(registry_path), args.system, args.rom
            )
        profile = selection["profile"] if selection else None
        if args.action == "session":
            if profile is None:
                _clear_session(args.session_file, args.session_id)
                return 0
            return _run_session(args, settings, token, selection)
        if args.action == "start" and profile is not None:
            if not 0.25 <= args.heartbeat_seconds <= 5.0:
                raise ValueError("heartbeat interval is out of range")
            if not 2.0 <= args.lease_seconds <= 15.0:
                raise ValueError("game lease is out of range")
            if not 1.0 <= args.startup_wait <= 60.0:
                raise ValueError("emulator startup wait is out of range")
            session_id = uuid.uuid4().hex
            _write_session(args.session_file, session_id)
            _start_session_process(args, session_id)
            print(f"VirtualGlove game session started: {profile}")
            return 0
        _clear_session(args.session_file)
        ack = send_request(
            settings["uno_q"], int(settings.get("port", 55356)), token,
            profile, args.system, args.rom, float(settings.get("timeout", 0.4)),
            rapid_a=selection.get("rapid_a") if selection else None,
            rapid_b=selection.get("rapid_b") if selection else None,
        )
    except (OSError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        # Never prevent a game from launching if the gesture controller is down.
        print(f"VirtualGlove unavailable: {exc}")
        return 0
    if ack.get("accepted") is True and ack.get("profile") == profile:
        state = "queued" if ack.get("queued") else "acknowledged"
        print(f"VirtualGlove profile {state}: {profile or 'off'}")
    else:
        print(f"VirtualGlove profile rejected: requested {profile or 'off'}; UNO Q reported {ack.get('profile') or 'off'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
