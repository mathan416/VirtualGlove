#!/usr/bin/env python3
# Project: VirtualGlove
# File: src/powerglove_vision/dot_launcher.py
# Purpose: Run the RetroPie calibration display with a renewable native-input lease.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added the ROM-free calibration-test launcher.
# Full history: docs/CHANGELOG.md and Git history.

"""Launch the calibration dot core and keep native Controller delivery active."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from .profile_control import read_token, send_request

SETTINGS = Path("/etc/virtualglove/launcher.json")
CORE = Path("/opt/retropie/libretrocores/lr-powerglove-dot/powerglove_dot_libretro.so")
RETROARCH = Path("/opt/retropie/emulators/retroarch/bin/retroarch")
RETROARCH_CONFIG = Path("/opt/retropie/configs/all/retroarch.cfg")
NATIVE_CONFIG = Path("/opt/retropie/configs/nes/powerglove-native.cfg")


def command() -> list[str]:
    """Return the fixed, content-free RetroArch invocation."""
    return [str(RETROARCH), "-L", str(CORE), "--config", str(RETROARCH_CONFIG),
            "--appendconfig", str(NATIVE_CONFIG)]


def main() -> int:
    """Run the core and safely expire its native-input lease on exit."""
    settings = json.loads(SETTINGS.read_text())
    token = read_token(None, Path(settings["token_file"]))
    for path in (CORE, RETROARCH, RETROARCH_CONFIG, NATIVE_CONFIG):
        if not path.is_file():
            raise SystemExit("VirtualGlove Calibration Test is incomplete; rerun the RetroPie installer.")
    session_id = uuid.uuid4().hex
    process = subprocess.Popen(command(), env={**os.environ,
        "VIRTUALGLOVE_NATIVE_STATE": "/run/virtualglove/native-state"})
    try:
        while process.poll() is None:
            try:
                send_request(settings["uno_q"], int(settings.get("port", 55356)), token,
                             "super_glove_ball", "powerglove-calibration",
                             "VirtualGlove Calibration Test", float(settings.get("timeout", 0.4)),
                             session_id=session_id, lease_seconds=6.0,
                             emulator="lr-powerglove-dot")
            except (OSError, TimeoutError, ValueError, KeyError, TypeError):
                pass
            time.sleep(2.0)
    finally:
        try:
            send_request(settings["uno_q"], int(settings.get("port", 55356)), token,
                         None, "", "", float(settings.get("timeout", 0.4)))
        except (OSError, TimeoutError, ValueError, KeyError, TypeError):
            pass
    return process.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
