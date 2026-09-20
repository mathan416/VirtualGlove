# Project: VirtualGlove
# File: tests/test_deployment_backup_rotation.py
# Purpose: Verify routine deployment backups rotate without touching named evidence.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-10 - Added bounded, conservative UNO Q payload-backup coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise deployment-backup selection and deletion in temporary directories."""

from pathlib import Path
import runpy
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[1] / "scripts/rotate-deployment-backups.py"


class DeploymentBackupRotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "virtualglove-backups"
        self.root.mkdir()
        self.module = runpy.run_path(str(MODULE))

    def directory(self, name: str) -> Path:
        path = self.root / name
        path.mkdir()
        (path / "RESTORE.txt").write_text(name)
        return path

    def test_keeps_newest_routine_backups_and_every_named_backup(self):
        routine = [self.directory(f"payload-202609{day:02d}-120000-{day}") for day in range(1, 16)]
        named = [self.directory("reacquisition-trace-20260907"),
                 self.directory("camera-fps-test-20260907")]
        removed = self.module["rotate"](self.root, keep=5)
        self.assertEqual([path.name for path in removed], [path.name for path in reversed(routine[:10])])
        self.assertEqual({path.name for path in self.root.iterdir()},
                         {path.name for path in routine[-5:] + named})

    def test_console_timestamp_backups_rotate_but_migration_names_remain(self):
        routine = [self.directory(f"202609{day:02d}-120000-{day}") for day in range(1, 9)]
        named = [self.directory("pre-controller-router-fef9277"),
                 self.directory("20260905-auto-core-selection")]
        removed = self.module["rotate"](self.root, keep=5)
        self.assertEqual([path.name for path in removed],
                         [path.name for path in reversed(routine[:3])])
        self.assertEqual({path.name for path in self.root.iterdir()},
                         {path.name for path in routine[-5:] + named})

    def test_keep_marker_and_similar_names_are_never_removed(self):
        for day in range(1, 5):
            self.directory(f"payload-2026090{day}-120000-{day}")
        marked = self.root / "payload-20260901-120000-1"
        (marked / self.module["KEEP_MARKER"]).touch()
        almost = self.directory("payload-manual-engineering")
        self.module["rotate"](self.root, keep=2)
        self.assertTrue(marked.is_dir())
        self.assertTrue(almost.is_dir())

    def test_dry_run_reports_without_mutation_and_symlinks_are_skipped(self):
        routine = [self.directory(f"payload-2026090{day}-120000-{day}") for day in range(1, 5)]
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "payload-20260801-120000-1").symlink_to(outside, target_is_directory=True)
        removed = self.module["rotate"](self.root, keep=2, dry_run=True)
        self.assertEqual(len(removed), 2)
        self.assertTrue(all(path.is_dir() for path in routine))
        self.assertTrue(outside.is_dir())

    def test_rejects_unsafe_roots_and_retention_values(self):
        with self.assertRaises(ValueError):
            self.module["rotate"](Path("/"), keep=12)
        for value in (0, 1, 101):
            with self.assertRaises(ValueError):
                self.module["rotate"](self.root, keep=value)


if __name__ == "__main__":
    unittest.main()
