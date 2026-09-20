# Project: VirtualGlove
# File: tests/test_academy_diagnostics.py
# Purpose: Verify private Academy diagnostic lifecycle and aggregate reports.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Added diagnostic deletion and privacy coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify diagnostic deletion, abandonment, and aggregate-only reporting."""

import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from virtualglove.academy_diagnostics import AcademyDiagnostics, CUES


class _Frame:
    shape = (48, 64, 3)


class _Writer:
    def __init__(self, path, *_args):
        self.path = Path(path)
        self.path.touch()
        self.frames = 0
        self.closed = False

    def isOpened(self):
        return True

    def write(self, _frame):
        self.frames += 1

    def release(self):
        self.closed = True


class AcademyDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 10.0
        self.manager = AcademyDiagnostics(Path(self.temp.name), lambda: self.now)

    def test_completed_capture_deletes_video_and_keeps_aggregate_only(self):
        fake_cv2 = SimpleNamespace(VideoWriter=_Writer, VideoWriter_fourcc=lambda *_args: 1)
        with patch.dict(sys.modules, {'cv2': fake_cv2}):
            self.manager.begin()
            for _cue in CUES:
                self.manager.record()
                for _ in range(3):
                    self.manager.observe(_Frame(), {
                        'detected': True, 'confidence': .95, 'inference_ms': 90,
                        'sample_age_ms': 110, 'hand_luma': 80, 'recognized': ['index'],
                    })
                self.now += _cue[3] + .1
                self.manager.observe(_Frame(), {
                    'detected': True, 'confidence': .95, 'inference_ms': 90,
                    'sample_age_ms': 110, 'hand_luma': 80, 'recognized': ['index'],
                })
        state = self.manager.snapshot()
        self.assertTrue(state['complete'])
        self.assertTrue(state['report']['raw_video_deleted'])
        self.assertFalse(self.manager.output.exists())
        self.assertNotIn('frames_data', state['report'])
        self.assertEqual(len(state['report']['summary']), len(CUES))

    def test_cancel_and_abandonment_delete_temporary_video(self):
        self.manager.begin()
        self.manager.output.touch()
        self.manager.cancel()
        self.assertFalse(self.manager.output.exists())
        self.manager.begin()
        self.manager.output.touch()
        self.now += 1801
        self.manager.expire()
        self.assertFalse(self.manager.output.exists())
        self.assertFalse(self.manager.active)
