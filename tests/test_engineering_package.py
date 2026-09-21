# Project: VirtualGlove
# File: tests/test_engineering_package.py
# Purpose: Keep research tools separate from ordinary release installers.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Added reproducibility, environment, and clean-extraction checks.
#   2026-09-09 - Added Engineering Tools package coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify the optional tools archive is complete, private-data-free, and separate."""

import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILDER = runpy.run_path(str(ROOT / "scripts/build-engineering-tools-package.py"))
SETUP_SPEC = importlib.util.spec_from_file_location(
    "engineering_setup", ROOT / "scripts/setup-engineering-tools.py"
)
SETUP = importlib.util.module_from_spec(SETUP_SPEC)
SETUP_SPEC.loader.exec_module(SETUP)


class EngineeringPackageTests(unittest.TestCase):
    def test_archive_contains_tools_and_shared_source_but_no_private_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "tools.zip"
            BUILDER["build"]("0.4.0-test", output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                prefix = "VirtualGlove-Engineering-Tools/"
                manifest = json.loads(archive.read(prefix + "engineering-tools.json"))
                self.assertEqual(manifest["format"], 2)
                self.assertIn("scripts/benchmark-vision-replay.py", manifest["tool_files"])
                self.assertIn("scripts/measure-vision-status.py", manifest["tool_files"])
                self.assertIn(prefix + "scripts/benchmark-vision-replay.py", names)
                self.assertIn(prefix + "scripts/measure-vision-status.py", names)
                self.assertIn(prefix + "scripts/check-engineering-toolkit.py", names)
                self.assertIn(prefix + "scripts/setup-engineering-tools.py", names)
                self.assertIn(prefix + "scripts/build-nestopia-powerglove.sh", names)
                self.assertIn(prefix + "docs/ENGINEERING_TOOLKIT.md", names)
                self.assertIn(prefix + "README.md", names)
                self.assertIn(prefix + "src/virtualglove/gesture.py", names)
                self.assertIn(prefix + "native/nestopia-powerglove/diagnostic_trace.h", names)
                self.assertIn(prefix + "native/nestopia-powerglove/nestopia-powerglove.patch", names)
                guide = archive.read(prefix + "docs/ENGINEERING_TOOLKIT.md").decode()
                self.assertIn("## Diagnose Controller Router", guide)
                self.assertIn("## Diagnose LaunchBox input", guide)
                self.assertIn("### Batocera and Recalbox latency acceptance", guide)
                self.assertIn("The bounded trace manager below remains", guide)
                self.assertIn("/recalbox/share/system/virtualglove/", guide)
                self.assertIn("/userdata/system/virtualglove/", guide)
                self.assertIn("network-retropad", guide)
                self.assertNotIn(prefix + "scripts/deploy-uno-q-wifi.sh", names)
                self.assertNotIn(prefix + "scripts/build-docs-pdf.py", names)
                self.assertNotIn(prefix + "scripts/build-install-packages.py", names)
                self.assertNotIn(prefix + "scripts/record-vision-benchmark.py", names)
                self.assertNotIn(prefix + "scripts/compare-motion-matrix.py", names)
                self.assertNotIn(prefix + "scripts/analyze-motion-samples.py", names)
                self.assertFalse(any(name.endswith((".so", ".dll", ".dylib", ".a", ".tar.gz"))
                                     for name in names))
                self.assertFalse(any("/data/" in name or "/tests/" in name
                                     or name.endswith((".mov", ".mp4", ".nes", ".7z"))
                                     for name in names))
            self.assertTrue(output.with_suffix(".zip.sha256").is_file())
            self.assertLess(output.stat().st_size, 5_000_000)

    def test_same_inputs_produce_identical_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            BUILDER["build"]("0.4.0-test", first)
            BUILDER["build"]("0.4.0-test", second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_clean_extraction_passes_dependency_free_self_check(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            output = directory / "tools.zip"
            BUILDER["build"]("0.4.0-test", output)
            with zipfile.ZipFile(output) as archive:
                archive.extractall(directory / "extracted")
            root = directory / "extracted" / "VirtualGlove-Engineering-Tools"
            environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(
                [sys.executable, "scripts/check-engineering-toolkit.py"],
                cwd=root, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertIn("Engineering Toolkit check passed", result.stdout)

    def test_release_workflows_use_current_toolkit_self_check(self):
        for name in ("quality.yml", "install-release.yml"):
            workflow = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn("python scripts/check-engineering-toolkit.py", workflow)
            self.assertNotIn("scripts/analyze-motion-samples.py", workflow)

    def test_environment_check_rejects_changed_record(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "environment.json"
            record.write_text(json.dumps({
                "format": 1,
                "mode": "engineering-analysis",
                "toolkit_version": "wrong-release",
                "python": "3.12.0",
                "platform": "test",
                "packages": ["numpy==1.26.4"],
            }))
            identity = {"version": [3, 12, 0], "platform": "test"}
            with patch.object(SETUP, "python_identity", return_value=identity), \
                    patch.object(SETUP, "toolkit_version", return_value="0.4.0-test"), \
                    patch.object(SETUP, "frozen_packages", return_value=["numpy==1.26.4"]):
                with self.assertRaisesRegex(SystemExit, "toolkit_version"):
                    SETUP.verify_environment(
                        Path("python"), record, "engineering-analysis"
                    )


if __name__ == "__main__":
    unittest.main()
