# Project: VirtualGlove
# File: tests/test_setup_status.py
# Purpose: Run Setup's Controller-output status helper without third-party packages.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added rendered armed-idle and delivery-failure coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise rendered Setup status logic in a dependency-free Node harness."""

import shutil
import subprocess
import unittest
from pathlib import Path

from powerglove_vision.control_server import SETUP
from powerglove_vision.dashboard_web import DASHBOARD


class SetupStatusHarnessTests(unittest.TestCase):
    """Verify idle output is not mistaken for an unavailable receiver."""

    @unittest.skipUnless(shutil.which("node"), "Node runtime is not installed")
    def test_dashboard_statistics_tracking_switch(self):
        result = subprocess.run(
            [shutil.which("node"), str(Path(__file__).with_name("dashboard_statistics_harness.cjs"))],
            input=DASHBOARD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode())

    @unittest.skipUnless(shutil.which("node"), "Node runtime is not installed")
    def test_controller_output_states(self):
        """Distinguish armed idle, practice, delivery, and real failure."""
        harness = Path(__file__).with_name("setup_status_harness.mjs")
        result = subprocess.run(
            [shutil.which("node"), str(harness)], input=SETUP,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            (result.stdout + result.stderr).decode("utf-8", "replace"),
        )
        self.assertIn(b"Setup status harness passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
