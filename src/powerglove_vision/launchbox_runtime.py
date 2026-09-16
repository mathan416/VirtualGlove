# Project: VirtualGlove
# File: src/powerglove_vision/launchbox_runtime.py
# Purpose: Supervise the interactive Windows receiver and game-registry service.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added per-user LaunchBox receiver supervision.
# Full history: docs/CHANGELOG.md and Git history.

"""Run LaunchBox console services in the signed-in Windows user session."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .launchbox_hook import default_settings_path


def service_commands(settings: dict) -> tuple[list[str], list[str]]:
    """Build fixed module commands from installer-owned settings."""
    token = str(settings["token_file"])
    native = str(settings["native_state"])
    receiver = [
        sys.executable, "-m", "powerglove_vision.receiver", "--listen", "0.0.0.0",
        "--token-file", token, "--native-state", native,
        "--output-device", "windows-keyboard",
    ]
    games = [
        sys.executable, "-m", "powerglove_vision.game_registry",
        "--settings", str(settings["settings_path"]),
    ]
    return receiver, games


def _lock(stream) -> bool:
    """Acquire a one-byte process lock using the platform's standard runtime."""
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def ensure_background(settings_path: Path) -> None:
    """Start one hidden interactive runtime unless its lock is already held."""
    lock_path = Path(settings_path).parent.parent / "run" / "runtime.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        if not _lock(stream):
            return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    executable = Path(sys.executable).with_name(
        "pythonw.exe" if os.name == "nt" else Path(sys.executable).name
    )
    subprocess.Popen(
        [str(executable), "-m", "powerglove_vision.launchbox_runtime", "run",
         "--settings", str(settings_path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=flags,
    )


def run(settings_path: Path) -> int:
    """Restart both services if configuration changes or either service exits."""
    settings = json.loads(Path(settings_path).read_text())
    settings["settings_path"] = str(settings_path)
    commands = service_commands(settings)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    run_root = Path(settings_path).parent.parent / "run"
    run_root.mkdir(parents=True, exist_ok=True)
    lock_path = run_root / "runtime.lock"
    restart_path = run_root / "restart"
    with lock_path.open("a+b") as lock_stream:
        if lock_stream.tell() == 0:
            lock_stream.write(b"0")
            lock_stream.flush()
        if not _lock(lock_stream):
            return 0
        while True:
            try:
                token_stamp = Path(settings["token_file"]).stat().st_mtime_ns
                if len(Path(settings["token_file"]).read_text().strip()) < 16:
                    time.sleep(1)
                    continue
            except OSError:
                time.sleep(1)
                continue
            restart_stamp = restart_path.stat().st_mtime_ns if restart_path.exists() else 0
            processes = [subprocess.Popen(command, creationflags=flags) for command in commands]
            try:
                while all(process.poll() is None for process in processes):
                    time.sleep(0.5)
                    new_token = Path(settings["token_file"]).stat().st_mtime_ns
                    new_restart = restart_path.stat().st_mtime_ns if restart_path.exists() else 0
                    if new_token != token_stamp or new_restart != restart_stamp:
                        break
            except (KeyboardInterrupt, OSError):
                return 0
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
            time.sleep(0.5)


def main() -> int:
    """Run the installed per-user LaunchBox services."""
    parser = argparse.ArgumentParser(description="Run VirtualGlove services for LaunchBox")
    parser.add_argument("action", choices=("run", "ensure", "restart"), nargs="?", default="run")
    parser.add_argument("--settings", type=Path, default=default_settings_path())
    args = parser.parse_args()
    if args.action == "run":
        return run(args.settings)
    if args.action == "restart":
        marker = args.settings.parent.parent / "run" / "restart"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    ensure_background(args.settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
