# Project: VirtualGlove
# File: tests/test_numeric_programs.py
# Purpose: Verify the original Power Glove Programs 1-14 and their safe adaptations.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-13 - Added Programs 1-14 mapping and rapid-fire coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise numeric program mappings without camera or network dependencies."""

import math
import unittest

from virtualglove.gesture import (
    GestureConfig, GestureEngine, SUPPORTED_PROFILES, rapid_fire_defaults,
)
from tests.test_gesture import calibrated_engine, hand


class NumericProgramTests(unittest.TestCase):
    def test_all_numeric_profiles_are_supported(self):
        self.assertTrue(all(f"program_{number}" in SUPPORTED_PROFILES
                            for number in range(1, 15)))
        for number in range(1, 15):
            expected = (True, False) if number == 7 else (False, False)
            self.assertEqual(rapid_fire_defaults(f"program_{number}"), expected)

    def test_only_explicitly_documented_profiles_enable_rapid_fire(self):
        enabled = {
            "program_7": (True, False),
            "program_b": (True, False),
            "program_h": (True, True),
            "bad_street_brawler": (False, True),
        }
        for profile in SUPPORTED_PROFILES:
            with self.subTest(profile=profile):
                self.assertEqual(
                    rapid_fire_defaults(profile),
                    enabled.get(profile, (False, False)),
                )
        self.assertEqual(rapid_fire_defaults("off"), (False, False))

    def test_program_1_turns_opposite_and_respects_rapid_override(self):
        engine = GestureEngine(
            "program_1", GestureConfig(joystick_deadzone=.28),
            calibration=calibrated_engine().calibration,
            rapid_a=False, rapid_b=False,
        )
        engine.update(hand(.10, palm_x=.8))
        state = engine.update(hand(.20, middle_curl=.8, ring_curl=.8, pinky_curl=.8))
        self.assertTrue(state.dpad["left"])
        self.assertTrue(state.buttons["b"])
        held = engine.update(hand(.45, middle_curl=.8, ring_curl=.8, pinky_curl=.8))
        self.assertFalse(held.buttons["b"])
        self.assertTrue(engine.update(hand(.55, thumb_curl=.8)).buttons["a"])

    def test_program_2_reports_center_without_exposing_geometry(self):
        engine = calibrated_engine("program_2")
        engine.update(hand(.15))
        self.assertEqual(engine.program_feedback(), {"centered": True})
        engine.update(hand(.25, palm_x=.9))
        self.assertEqual(engine.program_feedback(), {"centered": False})
        missing = engine.update(hand(.50, detected=False))
        self.assertEqual(engine.program_feedback(missing), {"centered": None})

    def test_program_3_uses_depth_for_vertical_movement(self):
        engine = calibrated_engine("program_3")
        engine.update(hand(.10, palm_scale=.30))
        pushed = engine.update(hand(.20, palm_scale=.30))
        self.assertTrue(pushed.dpad["up"])
        self.assertFalse(pushed.dpad["down"])

    def test_program_4_finger_treads_and_wrist_diagonals(self):
        engine = GestureEngine("program_4", calibration=calibrated_engine().calibration,
                               rapid_a=False, rapid_b=False)
        right = engine.update(hand(.10, middle_curl=.8, ring_curl=.8, pinky_curl=.8))
        self.assertTrue(right.dpad["right"])
        left = engine.update(hand(.20, index_curl=.8))
        self.assertTrue(left.dpad["left"])
        diagonal = engine.update(hand(.30, roll=math.pi / 2))
        self.assertTrue(diagonal.dpad["up"])
        self.assertTrue(diagonal.dpad["right"])
        upright = engine.update(hand(.40, roll=math.pi))
        self.assertTrue(upright.buttons["b"])
        self.assertFalse(any(upright.dpad.values()))

    def test_program_5_combines_depth_and_bank(self):
        engine = calibrated_engine("program_5")
        engine.update(hand(.10, palm_scale=.30, roll=-math.pi / 2))
        state = engine.update(hand(.20, palm_scale=.30, roll=-math.pi / 2))
        self.assertTrue(state.dpad["up"])
        self.assertTrue(state.dpad["left"])

    def test_program_6_last_three_is_combined_attack(self):
        engine = GestureEngine("program_6", calibration=calibrated_engine().calibration,
                               rapid_a=False, rapid_b=False)
        thumb = engine.update(hand(.05, thumb_curl=.8))
        self.assertFalse(thumb.buttons["a"])
        self.assertTrue(thumb.buttons["b"])
        self.assertTrue(engine.update(hand(.08, index_curl=.8)).buttons["a"])
        state = engine.update(hand(.10, middle_curl=.8, ring_curl=.8, pinky_curl=.8))
        self.assertTrue(state.buttons["a"] and state.buttons["b"])
        fist = dict(thumb_curl=.8, index_curl=.8, middle_curl=.8,
                    ring_curl=.8, pinky_curl=.8, palm_scale=.30)
        engine.update(hand(.20))
        engine.update(hand(.25, **fist))
        climbing = engine.update(hand(.35, **fist))
        self.assertTrue(climbing.dpad["up"])
        self.assertFalse(climbing.buttons["a"] or climbing.buttons["b"])

    def test_program_7_maps_right_high_punch(self):
        engine = GestureEngine("program_7", calibration=calibrated_engine().calibration,
                               rapid_a=False, rapid_b=False)
        pose = dict(palm_x=.7, palm_y=.3, palm_scale=.30, thumb_curl=.8,
                    index_curl=.8, middle_curl=.8, ring_curl=.8, pinky_curl=.8)
        engine.update(hand(.05))
        engine.update(hand(.10, **pose))
        state = engine.update(hand(.20, **pose))
        self.assertTrue(state.buttons["a"])
        self.assertTrue(state.dpad["up"])
        block = engine.update(hand(.30, roll=math.pi / 2))
        self.assertTrue(block.dpad["down"])
        fist = dict(thumb_curl=.8, index_curl=.8, middle_curl=.8,
                    ring_curl=.8, pinky_curl=.8, palm_scale=.12)
        engine.update(hand(.40))
        engine.update(hand(.45, **fist))
        star = engine.update(hand(.55, **fist))
        self.assertTrue(star.buttons["select"])

    def test_program_8_changes_thumb_action_while_running(self):
        engine = GestureEngine("program_8", calibration=calibrated_engine().calibration,
                               rapid_a=False, rapid_b=False)
        swing = engine.update(hand(.10, thumb_curl=.8))
        self.assertTrue(swing.buttons["b"])
        run_back = engine.update(hand(.20, palm_x=.9, thumb_curl=.8))
        self.assertTrue(run_back.buttons["a"])

    def test_program_9_requires_fist_and_never_rapid_fires(self):
        engine = calibrated_engine("program_9")
        self.assertFalse(engine.program_feedback()["ready"])
        self.assertFalse(engine.update(hand(.10, roll=math.pi / 2)).dpad["right"])
        fist = dict(thumb_curl=.8, index_curl=.8, middle_curl=.8,
                    ring_curl=.8, pinky_curl=.8)
        self.assertTrue(engine.update(hand(.20, **fist)).buttons["a"])
        self.assertTrue(engine.program_feedback()["ready"])
        self.assertTrue(engine.update(hand(.30, palm_y=.9)).buttons["b"])
        self.assertTrue(engine.update(hand(.40, palm_y=.1)).dpad["down"])
        self.assertTrue(engine.update(hand(.50, roll=-math.pi / 2)).dpad["left"])
        brake = engine.update(hand(.30, palm_y=.9))
        self.assertTrue(brake.buttons["b"])

    def test_program_10_fist_holds_b_without_conflicting_steering(self):
        engine = GestureEngine("program_10", calibration=calibrated_engine().calibration,
                               rapid_a=False, rapid_b=False)
        fist = dict(thumb_curl=.8, index_curl=.8, middle_curl=.8,
                    ring_curl=.8, pinky_curl=.8)
        state = engine.update(hand(.10, **fist))
        self.assertTrue(state.buttons["b"])
        self.assertFalse(state.dpad["left"] or state.dpad["right"])
        lowered = engine.update(hand(.20, palm_y=.9))
        self.assertFalse(lowered.buttons["b"])
        released = engine.update(hand(.20, palm_y=.9))
        self.assertFalse(released.buttons["b"])

    def test_program_11_thrashes_and_program_12_slows(self):
        pose = dict(palm_x=.9, middle_curl=.8, ring_curl=.8, pinky_curl=.8)
        eleven = GestureEngine("program_11", calibration=calibrated_engine().calibration,
                               rapid_a=False, rapid_b=False).update(hand(.10, **pose))
        self.assertTrue(eleven.buttons["b"])
        self.assertTrue(eleven.dpad["left"] or eleven.dpad["right"])
        engine = GestureEngine("program_12", calibration=calibrated_engine().calibration,
                               rapid_a=False, rapid_b=False)
        self.assertFalse(engine.update(hand(.15, **pose)).dpad["right"])
        slowed = engine.update(hand(.30, **pose))
        self.assertTrue(slowed.dpad["right"])
        self.assertFalse(slowed.buttons["b"])

    def test_program_12_holds_a_by_default_and_repeats_long_rapid_pulses(self):
        held = GestureEngine(
            "program_12", calibration=calibrated_engine().calibration,
        )
        self.assertTrue(held.update(hand(.10, thumb_curl=.8)).buttons["a"])
        self.assertTrue(held.update(hand(.50, thumb_curl=.8)).buttons["a"])
        self.assertFalse(held.update(hand(.60)).buttons["a"])

        rapid = GestureEngine(
            "program_12", calibration=calibrated_engine().calibration,
            rapid_a=True,
        )
        self.assertTrue(rapid.update(hand(.10, thumb_curl=.8)).buttons["a"])
        self.assertTrue(rapid.update(hand(.34, thumb_curl=.8)).buttons["a"])
        self.assertFalse(rapid.update(hand(.36, thumb_curl=.8)).buttons["a"])
        self.assertTrue(rapid.update(hand(.43, thumb_curl=.8)).buttons["a"])
        self.assertFalse(rapid.update(hand(.70, thumb_curl=.8)).buttons["a"])
        self.assertFalse(rapid.update(hand(.71)).buttons["a"])
        self.assertTrue(rapid.update(hand(.72, thumb_curl=.8)).buttons["a"])

        self.assertFalse(rapid.update(hand(.90, detected=False)).buttons["a"])
        self.assertTrue(rapid.update(hand(1.0, thumb_curl=.8)).buttons["a"])

    def test_program_13_has_buttons_only_and_14_is_neutral(self):
        thirteen = GestureEngine("program_13", calibration=calibrated_engine().calibration,
                                 rapid_a=False, rapid_b=False)
        state = thirteen.update(hand(.10, palm_x=.9, thumb_curl=.8))
        self.assertTrue(state.buttons["a"])
        self.assertFalse(any(state.dpad.values()))
        fourteen = calibrated_engine("program_14").update(
            hand(.15, palm_x=.9, thumb_curl=.8, index_curl=.8)
        )
        self.assertFalse(any(fourteen.dpad.values()))
        self.assertFalse(fourteen.buttons["a"] or fourteen.buttons["b"])


if __name__ == "__main__":
    unittest.main()
