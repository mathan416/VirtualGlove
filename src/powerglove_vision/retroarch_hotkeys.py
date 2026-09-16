# Project: VirtualGlove
# File: src/powerglove_vision/retroarch_hotkeys.py
# Purpose: Reject LaunchBox keyboard mappings that collide with RetroArch commands.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-16 - Added effective LaunchBox RetroArch hotkey auditing.
# Full history: docs/CHANGELOG.md and Git history.

"""Audit RetroArch keyboard commands without treating Player binds as hotkeys."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


VIRTUALGLOVE_KEYS = {"up", "down", "left", "right", "x", "z", "enter", "rshift"}
INTENTIONAL_PLAYER1 = {
    "input_player1_a": "x", "input_player1_b": "z",
    "input_player1_start": "enter", "input_player1_select": "rshift",
    "input_player1_up": "up", "input_player1_down": "down",
    "input_player1_left": "left", "input_player1_right": "right",
}


def conflicts(paths: list[Path]) -> list[dict]:
    """Return effective RetroArch commands that consume VirtualGlove keys."""
    effective = {}
    for path in paths:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            match = re.match(r'^\s*([A-Za-z0-9_]+)\s*=\s*"?([^"#\s]+)', line)
            if not match:
                continue
            setting, value = match.group(1), match.group(2).casefold()
            if setting.startswith("input_"):
                effective[setting] = {"path": str(path), "line": number,
                                      "setting": setting, "key": value}
    return [item for setting, item in effective.items()
            if not setting.endswith(("_btn", "_axis")) and
            INTENTIONAL_PLAYER1.get(setting) != item["key"] and
            item["key"] in VIRTUALGLOVE_KEYS]


def format_conflicts(found: list[dict]) -> str:
    """Format exact conflicting settings and source locations for the user."""
    return "; ".join("%s uses %s (%s:%d)" %
                     (item["setting"], item["key"], item["path"], item["line"])
                     for item in found)


def main() -> int:
    """Audit requested RetroArch configuration files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, action="append", required=True)
    args = parser.parse_args()
    found = conflicts(args.config)
    if found:
        print("VirtualGlove keyboard conflict: " + format_conflicts(found))
        return 1
    print("PASS  No VirtualGlove keyboard keys are assigned to RetroArch commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
