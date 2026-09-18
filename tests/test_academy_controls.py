# Project: VirtualGlove
# File: tests/test_academy_controls.py
# Purpose: Run the rendered Glove Academy JavaScript control harness without third-party packages.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Added dependency-free rendered Academy interaction coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Run the rendered Glove Academy JavaScript control harness."""

import shutil
import subprocess
import unittest
from pathlib import Path

from virtualglove.control_server import LEARN


class AcademyControlHarnessTests(unittest.TestCase):
    """Exercise the real inline browser logic when a Node runtime is available."""

    @unittest.skipUnless(shutil.which("node"), "Node runtime is not installed")
    def test_every_academy_control_and_lesson_transition(self):
        harness = Path(__file__).with_name("academy_controls_harness.mjs")
        result = subprocess.run(
            [shutil.which("node"), str(harness)], input=LEARN,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            (result.stdout + result.stderr).decode("utf-8", "replace"),
        )
        self.assertIn(b"Glove Academy control harness passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
