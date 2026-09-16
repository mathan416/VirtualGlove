# Project: VirtualGlove
# File: tests/test_console_monitor.py
# Purpose: Verify hook-free game lifecycle discovery for Recalbox and Batocera.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-14 - Added Recalbox process and authenticated lease coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify safe game discovery and lease updates without platform hooks."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from powerglove_vision import console_monitor


class ConsoleMonitorTests(unittest.TestCase):
    def test_parses_recalbox_fceumm_launch(self):
        game = console_monitor.parse_retroarch(42, [
            "/usr/bin/retroarch", "-L", "/usr/lib/libretro/fceumm_libretro.so",
            "--config", "/tmp/retroarch.cfg",
            "/recalbox/share/roms/nes/Super Mario Bros. (USA).zip",
        ])
        self.assertEqual(game, console_monitor.RunningGame(
            42, "nes", "lr-fceumm",
            "/recalbox/share/roms/nes/Super Mario Bros. (USA).zip"))

    def test_parses_recalbox_native_nestopia_launch(self):
        game = console_monitor.parse_retroarch(43, [
            "/usr/bin/retroarch", "-L",
            "/usr/lib/libretro/nestopia_powerglove_libretro.so",
            "/recalbox/share/roms/nes/Super Glove Ball (USA).7z",
        ])
        self.assertEqual(game, console_monitor.RunningGame(
            43, "nes", "lr-nestopia-powerglove",
            "/recalbox/share/roms/nes/Super Glove Ball (USA).7z"))

    def test_ignores_non_games_and_unknown_rom_layouts(self):
        self.assertIsNone(console_monitor.parse_retroarch(1, ["python3", "worker.py"]))
        self.assertIsNone(console_monitor.parse_retroarch(2, ["retroarch", "--menu"]))
        self.assertIsNone(console_monitor.parse_retroarch(
            3, ["retroarch", "/tmp/unregistered.nes"]))

    def test_newest_procfs_game_wins(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for pid, rom in ((12, "First.nes"), (25, "Second.zip")):
                process = root / str(pid); process.mkdir()
                (process / "cmdline").write_bytes(
                    b"retroarch\0-L\0/usr/lib/libretro/fceumm_libretro.so\0" +
                    ("/recalbox/share/roms/nes/" + rom).encode() + b"\0")
            self.assertEqual(console_monitor.running_game(root).pid, 25)

    def test_once_sends_registered_profile_with_lease(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            token = root / "token"; token.write_text("x" * 24)
            registry = root / "games.json"
            registry.write_text(json.dumps({"games": {"Mario.nes": "program_12"}}))
            settings = root / "launcher.json"
            settings.write_text(json.dumps({
                "uno_q": "virtualglove.local", "port": 55356,
                "token_file": str(token), "registry": str(registry),
            }))
            game = console_monitor.RunningGame(
                7, "nes", "lr-fceumm", "/recalbox/share/roms/nes/Mario.nes")
            with patch.object(console_monitor, "running_game", return_value=game), \
                    patch.object(console_monitor, "send_request") as send:
                console_monitor.monitor(settings, once=True)
            arguments, keywords = send.call_args
            self.assertEqual(arguments[3:6], ("program_12", "nes", game.rom))
            self.assertEqual(keywords["emulator"], "lr-fceumm")
            self.assertEqual(keywords["lease_seconds"], 6.0)
            self.assertRegex(keywords["session_id"], r"^[0-9a-f]{32}$")


if __name__ == "__main__":
    unittest.main()
