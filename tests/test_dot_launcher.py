# Project: VirtualGlove
# File: tests/test_dot_launcher.py
# Purpose: Verify the ROM-free calibration utility's fixed launch contract.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added calibration utility coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Test the safe fixed command and native profile used by the dot utility."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from virtualglove import dot_launcher


class DotLauncherTests(unittest.TestCase):
    def test_command_is_content_free_and_uses_native_options(self):
        command = dot_launcher.command()
        self.assertEqual(command[0], str(dot_launcher.RETROARCH))
        self.assertEqual(command[1:3], ["-L", str(dot_launcher.CORE)])
        self.assertIn(str(dot_launcher.RETROARCH_CONFIG), command)
        self.assertIn(str(dot_launcher.NATIVE_CONFIG), command)
        self.assertFalse(any(Path(value).suffix.casefold() in {".nes", ".zip", ".7z"}
                             for value in command))

    def test_session_uses_native_profile_and_releases_on_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "launcher.json"
            token = root / "token"
            token.write_text("0123456789abcdef")
            settings.write_text('{"uno_q":"controller.local","token_file":"' +
                                str(token) + '"}')
            files = [root / name for name in ("core", "retroarch", "retroarch.cfg", "native.cfg")]
            for path in files:
                path.write_text("test")
            polls = iter((None, 0))
            process = SimpleNamespace(poll=lambda: next(polls), returncode=0)
            with patch.object(dot_launcher, "SETTINGS", settings), \
                 patch.object(dot_launcher, "CORE", files[0]), \
                 patch.object(dot_launcher, "RETROARCH", files[1]), \
                 patch.object(dot_launcher, "RETROARCH_CONFIG", files[2]), \
                 patch.object(dot_launcher, "NATIVE_CONFIG", files[3]), \
                 patch.object(dot_launcher.subprocess, "Popen", return_value=process), \
                 patch.object(dot_launcher.time, "sleep"), \
                 patch.object(dot_launcher, "send_request") as send:
                self.assertEqual(dot_launcher.main(), 0)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(send.call_args_list[0][0][3], "super_glove_ball")
            self.assertEqual(send.call_args_list[0][1]["emulator"], "lr-powerglove-dot")
            self.assertIsNone(send.call_args_list[1][0][3])


if __name__ == "__main__":
    unittest.main()
