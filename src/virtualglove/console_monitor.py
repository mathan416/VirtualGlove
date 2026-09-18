# Project: VirtualGlove
# File: src/virtualglove/console_monitor.py
# Purpose: Follow RetroArch game sessions on consoles without launch-hook support.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added bounded RetroArch session discovery for Recalbox.
# Full history: docs/CHANGELOG.md and Git history.

"""Discover RetroArch games and maintain authenticated VirtualGlove leases."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .profile_control import load_registry, read_token, select_profile_settings, send_request
from .retropie_hook import KNOWN_CORES


ROM_EXTENSIONS = {".7z", ".nes", ".zip"}


@dataclass(frozen=True)
class RunningGame:
    """One supported running RetroArch process."""

    pid: int
    system: str
    emulator: str
    rom: str


def _system_from_rom(rom: Path) -> str:
    """Derive the console system from a conventional shared ROM path."""
    parts = rom.parts
    for marker in ("roms", "rom"):
        try:
            index = parts.index(marker)
        except ValueError:
            continue
        if index + 1 < len(parts):
            return parts[index + 1]
    return ""


def parse_retroarch(pid: int, arguments: list[str]) -> RunningGame | None:
    """Extract the core and ROM from one RetroArch command line."""
    if not arguments or not Path(arguments[0]).name.casefold().startswith("retroarch"):
        return None
    emulator = ""
    for index, argument in enumerate(arguments[:-1]):
        if argument == "-L":
            emulator = KNOWN_CORES.get(Path(arguments[index + 1]).name, "")
            break
    candidates = [Path(argument) for argument in arguments[1:]
                  if Path(argument).suffix.casefold() in ROM_EXTENSIONS]
    if not candidates:
        return None
    rom = candidates[-1]
    system = _system_from_rom(rom)
    if not system:
        return None
    return RunningGame(pid, system, emulator, str(rom))


def running_game(proc_root: Path = Path("/proc")) -> RunningGame | None:
    """Return the newest supported RetroArch game visible in procfs."""
    games = []
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            arguments = [os.fsdecode(value) for value in
                         (entry / "cmdline").read_bytes().split(b"\0") if value]
            game = parse_retroarch(int(entry.name), arguments)
            if game is not None:
                games.append(game)
        except (OSError, ValueError, UnicodeError):
            continue
    return max(games, key=lambda item: item.pid, default=None)


def _neutral(settings: dict, token: str) -> None:
    """Best-effort release of the previous authenticated game lease."""
    try:
        send_request(settings["uno_q"], int(settings.get("port", 55356)),
                     token, None, "", "", float(settings.get("timeout", 0.4)))
    except (OSError, TimeoutError, ValueError, KeyError, TypeError):
        pass


def monitor(settings_path: Path, proc_root: Path = Path("/proc"),
            heartbeat_seconds: float = 2.0, lease_seconds: float = 6.0,
            once: bool = False) -> None:
    """Follow games without modifying the console's protected launcher."""
    if not 0.25 <= heartbeat_seconds <= 5.0:
        raise ValueError("heartbeat interval is out of range")
    if not 2.0 <= lease_seconds <= 15.0:
        raise ValueError("lease duration is out of range")
    current: RunningGame | None = None
    session_id = ""
    settings = token = None
    while True:
        game = running_game(proc_root)
        if game != current:
            if current is not None and settings is not None and token is not None:
                _neutral(settings, token)
            current = game
            session_id = uuid.uuid4().hex if game is not None else ""
            settings = token = None
        if game is not None:
            try:
                settings = json.loads(settings_path.read_text())
                token = read_token(None, Path(settings["token_file"]))
                registry = load_registry(Path(settings["registry"]))
                selection = select_profile_settings(registry, game.system, game.rom)
                if selection is not None:
                    send_request(
                        settings["uno_q"], int(settings.get("port", 55356)), token,
                        selection["profile"], game.system, game.rom,
                        float(settings.get("timeout", 0.4)), session_id=session_id,
                        lease_seconds=lease_seconds, emulator=game.emulator,
                        rapid_a=selection.get("rapid_a"),
                        rapid_b=selection.get("rapid_b"),
                    )
            except (OSError, TimeoutError, ValueError, KeyError, TypeError,
                    json.JSONDecodeError):
                pass
        if once:
            return
        time.sleep(heartbeat_seconds)


def build_parser() -> argparse.ArgumentParser:
    """Create the bounded console-monitor command-line parser."""
    parser = argparse.ArgumentParser(
        description="Maintain VirtualGlove game sessions by observing RetroArch")
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--heartbeat-seconds", type=float, default=2.0)
    parser.add_argument("--lease-seconds", type=float, default=6.0)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    """Run the monitor until stopped by its platform service."""
    args = build_parser().parse_args()
    monitor(args.settings, heartbeat_seconds=args.heartbeat_seconds,
            lease_seconds=args.lease_seconds, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
