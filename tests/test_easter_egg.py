# Project: VirtualGlove
# File: tests/test_easter_egg.py
# Purpose: Verify the non-blocking Vulcan-salute recognition and overlay.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-13 - Added gesture easter-egg coverage.
# Full history: docs/CHANGELOG.md and Git history.
"""Visual-only Vulcan-salute recognition and overlay behavior."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from virtualglove.gesture import GestureEngine, vulcan_salute_pose
from virtualglove.model import Calibration, HandObservation
from virtualglove.tracker import _Point, _finger_spreads
from virtualglove.web_common import EASTER_EGG_SCRIPT, _page


def hand(timestamp, *, salute=True, **changes):
    values=dict(timestamp=timestamp,detected=True,confidence=.95,palm_x=.5,
                palm_y=.5,palm_scale=.2,index_middle_spread=.22,
                middle_ring_spread=.72,ring_pinky_spread=.24)
    if not salute:
        values.update(index_middle_spread=.42,middle_ring_spread=.44,
                      ring_pinky_spread=.40)
    values.update(changes)
    return HandObservation(**values)


class VulcanSaluteTests(unittest.TestCase):
    def test_tracker_normalizes_the_three_adjacent_tip_gaps(self):
        points=[_Point(0,0,0) for _ in range(21)]
        points[5]=_Point(0,0,0);points[17]=_Point(2,0,0)
        points[8]=_Point(0,1,0);points[12]=_Point(.4,1,0)
        points[16]=_Point(1.6,1,0);points[20]=_Point(2,1,0)
        spreads=_finger_spreads(points)
        self.assertAlmostEqual(spreads["index_middle_spread"],.2)
        self.assertAlmostEqual(spreads["middle_ring_spread"],.6)
        self.assertAlmostEqual(spreads["ring_pinky_spread"],.2)

    def test_pose_requires_extended_fingers_and_distinct_middle_ring_split(self):
        self.assertTrue(vulcan_salute_pose(hand(1)))
        self.assertFalse(vulcan_salute_pose(hand(1,salute=False)))
        self.assertFalse(vulcan_salute_pose(hand(1,index_curl=.5)))
        self.assertFalse(vulcan_salute_pose(hand(1,confidence=.2)))
        self.assertFalse(vulcan_salute_pose(hand(1,middle_ring_spread=.49)))

    def test_hold_release_and_cooldown_do_not_change_controller_output(self):
        engine=GestureEngine('program_h',calibration=Calibration(.5,.5,.2,0))
        for timestamp in (1.0,1.4,1.66):
            state=engine.update(hand(timestamp))
        self.assertEqual(engine.easter_egg_feedback(),{'spock_sequence':1})
        self.assertFalse(any(state.dpad.values()))
        self.assertFalse(any(state.buttons.values()))
        engine.update(hand(32.0))
        self.assertEqual(engine.easter_egg_feedback()['spock_sequence'],1)
        engine.update(hand(32.1,salute=False))
        engine.update(hand(32.2,salute=False))
        engine.update(hand(32.3))
        engine.update(hand(33.0))
        self.assertEqual(engine.easter_egg_feedback()['spock_sequence'],1)
        engine.update(hand(33.1,salute=False))
        engine.update(hand(33.41,salute=False))
        engine.update(hand(33.5))
        engine.update(hand(34.16))
        self.assertEqual(engine.easter_egg_feedback()['spock_sequence'],2)

    def test_feedback_exposes_no_landmarks_or_hand_measurements(self):
        engine=GestureEngine('practice',calibration=Calibration(.5,.5,.2,0))
        self.assertEqual(engine.easter_egg_feedback(),{'spock_sequence':0})


@unittest.skipUnless(shutil.which('node'),'Node needed for JavaScript tests')
class EasterEggOverlayTests(unittest.TestCase):
    def test_overlay_lifecycle_and_accessibility_contract(self):
        harness=Path(__file__).with_name('easter_egg_harness.js')
        result=subprocess.run(['node',str(harness)],
            input=json.dumps({'script':EASTER_EGG_SCRIPT}),text=True,
            capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        page=_page('Test','<p>Test</p>','').decode()
        self.assertIn('id=spock-toast',page)
        self.assertIn('pointer-events:none',page)
        self.assertIn('id=spock-announcement',page)
        self.assertIn('aria-live=polite',page)
        self.assertIn('aria-atomic=true',page)
        self.assertIn('prefers-reduced-motion:reduce',page)

    def test_every_live_camera_page_forwards_status_to_the_overlay(self):
        from virtualglove.academy_web import LEARN
        from virtualglove.dashboard_web import DASHBOARD
        from virtualglove.joystick_web import JOYSTICK_SCRIPT
        from virtualglove.ready_web import READY
        for page in (DASHBOARD,LEARN,READY,JOYSTICK_SCRIPT.encode()):
            self.assertIn(b'updateEasterEgg',page)
