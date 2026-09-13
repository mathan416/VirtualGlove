# Project: VirtualGlove
# File: tests/test_gesture.py
# Purpose: Verify calibration, hysteresis, safety release, menu poses, and supported gesture profiles.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Verified native fist and index-point recognition states.
#   2026-09-05 - Verified two-frame, motion-confirmed push and pull recognition.
#   2026-09-05 - Verified Menu Guard easing remains isolated from general curls.
#   2026-09-05 - Verified the eased thumb-only B pose remains distinct from Closed Hand.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Verified Program I throttle, brake, steering, turbo, and weapons.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify calibration, hysteresis, safety release, menu poses, and supported gesture profiles."""

import unittest

from powerglove_vision.gesture import GestureConfig, GestureEngine
from powerglove_vision.model import HandObservation


def hand(t: float, **changes) -> HandObservation:
    values = dict(
        timestamp=t,
        detected=True,
        confidence=0.95,
        palm_x=0.5,
        palm_y=0.5,
        palm_scale=0.2,
        roll=0.0,
    )
    values.update(changes)
    return HandObservation(**values)


def calibrated_engine(profile="bad_street_brawler") -> GestureEngine:
    engine = GestureEngine(profile, GestureConfig(loss_release_ms=100), calibration_frames=3)
    for t in (0.00, 0.03, 0.06):
        engine.update(hand(t))
    assert engine.calibrated
    return engine


class GestureTests(unittest.TestCase):
    def test_calibration_suppresses_output(self):
        engine = GestureEngine("bad_street_brawler", calibration_frames=3)
        state = engine.update(hand(0.0, palm_x=0.8))
        self.assertFalse(state.calibrated)
        self.assertFalse(any(state.dpad.values()))

    def test_calibration_uses_only_confident_complete_hand_samples(self):
        engine = GestureEngine("bad_street_brawler", calibration_frames=3)
        for t, changes in (
            (0.0, {"confidence": .69, "palm_x": .9}),
            (0.1, {"palm_scale": .01, "palm_x": .9}),
            (0.2, {"detected": False, "palm_x": .9}),
        ):
            self.assertFalse(engine.update(hand(t, **changes)).calibrated)
        for t, x in ((.3, .49), (.4, .50), (.5, .51)):
            engine.update(hand(t, palm_x=x))
        self.assertTrue(engine.calibrated)
        self.assertAlmostEqual(engine.calibration.palm_x, .5)

    def test_repeated_calibration_from_same_pose_stays_close(self):
        first = GestureEngine("super_glove_ball", calibration_frames=4)
        second = GestureEngine("super_glove_ball", calibration_frames=4)
        for index, (x, y, scale, roll) in enumerate((
            (.598, .621, .064, -2.04),
            (.603, .618, .063, -2.02),
            (.600, .623, .065, -2.03),
            (.601, .620, .064, -2.05),
        )):
            first.update(hand(index / 10, palm_x=x, palm_y=y,
                              palm_scale=scale, roll=roll))
        for index, (x, y, scale, roll) in enumerate((
            (.602, .619, .064, -2.03),
            (.599, .622, .065, -2.04),
            (.604, .620, .063, -2.02),
            (.600, .621, .064, -2.05),
        )):
            second.update(hand(index / 10, palm_x=x, palm_y=y,
                               palm_scale=scale, roll=roll))
        self.assertAlmostEqual(first.calibration.palm_x,
                               second.calibration.palm_x, delta=.003)
        self.assertAlmostEqual(first.calibration.palm_y,
                               second.calibration.palm_y, delta=.003)
        self.assertAlmostEqual(first.calibration.palm_scale,
                               second.calibration.palm_scale, delta=.002)
        self.assertAlmostEqual(first.calibration.roll,
                               second.calibration.roll, delta=.02)

    def test_comfortable_index_curl_uses_shared_held_state(self):
        engine = calibrated_engine("program_h")
        for t, curl, active in ((.1, .29, False), (.2, .54, True),
                                (.3, .45, True), (.4, .34, False)):
            observation = hand(t, index_curl=curl)
            engine.update(observation)
            self.assertEqual(engine.curl_feedback(observation)["index"], active)

    def test_comfortable_thumb_fold_triggers_b_without_becoming_closed_hand(self):
        """A natural thumb-to-palm fold should not require an exaggerated bend."""
        engine = calibrated_engine("super_glove_ball")
        self.assertEqual(engine.config.pair("thumb"), (.38, .28))
        state = engine.update(hand(.1, thumb_curl=.41))
        self.assertTrue(state.buttons["b"])
        self.assertTrue(engine.curl_feedback(hand(.1, thumb_curl=.41))["thumb"])
        self.assertFalse(engine.recognition_feedback()["closed_hand"])
        held = engine.update(hand(.2, thumb_curl=.31))
        self.assertTrue(held.buttons["b"])
        released = engine.update(hand(.3, thumb_curl=.27))
        self.assertFalse(released.buttons["b"])
        observation = hand(.5, index_curl=.58)
        engine.update(observation)
        self.assertFalse(engine.curl_feedback(HandObservation(.6, False))["index"])
        engine.begin_calibration()
        self.assertFalse(engine.curl_feedback(observation)["index"])
        for t in (.7, .8, .9):
            engine.update(hand(t))
        observation = hand(1., index_curl=.4)
        engine.update(observation)
        self.assertFalse(engine.curl_feedback(observation)["index"])

    def test_super_glove_ball_publishes_fist_open_and_index_point(self):
        """Native poses use all five shared finger switches and release immediately."""
        engine = calibrated_engine("super_glove_ball")
        fist = engine.update(hand(
            .10, thumb_curl=.8, index_curl=.8, middle_curl=.8,
            ring_curl=.8, pinky_curl=.8,
        ))
        self.assertTrue(fist.buttons["closed_hand"])
        self.assertFalse(fist.buttons["index_point"])

        opened = engine.update(hand(.20))
        self.assertFalse(opened.buttons["closed_hand"])
        self.assertFalse(opened.buttons["index_point"])

        pointing = engine.update(hand(
            .30, index_curl=.1, middle_curl=.8, ring_curl=.8, pinky_curl=.8,
        ))
        self.assertFalse(pointing.buttons["closed_hand"])
        self.assertTrue(pointing.buttons["index_point"])

        ambiguous = engine.update(hand(
            .40, index_curl=.40, middle_curl=.8, ring_curl=.8, pinky_curl=.8,
        ))
        self.assertFalse(ambiguous.buttons["index_point"])

    def test_comfortable_v_requires_both_curled_and_both_straight_fingers(self):
        pose = dict(index_curl=.23, middle_curl=.22, ring_curl=.50, pinky_curl=.45)
        engine = calibrated_engine("program_h")
        for t in (.1, .2, .26, .59):
            state = engine.update(hand(t, palm_x=.8, **pose))
            self.assertFalse(any(state.dpad.values()))
        self.assertFalse(state.buttons["start"])
        state = engine.update(hand(.61, palm_x=.8, **pose))
        self.assertTrue(state.buttons["start"])
        engine.update(hand(1.2, **pose))
        self.assertTrue(engine.menu_feedback()["recognized"])
        for changes in (dict(ring_curl=.25), dict(pinky_curl=.25),
                        dict(index_curl=.54), dict(middle_curl=.54)):
            candidate = dict(pose, **changes)
            engine = calibrated_engine("program_h")
            for t in (.1, .85):
                state = engine.update(hand(t, **candidate))
            self.assertFalse(state.buttons["start"])
            self.assertFalse(engine.menu_feedback()["recognized"])

    def test_start_uses_500_ms_hold_and_300_ms_release_guard(self):
        pose = dict(index_curl=.2, middle_curl=.2, ring_curl=.8, pinky_curl=.8)
        engine = calibrated_engine("program_h")
        self.assertFalse(engine.update(hand(.10, **pose)).buttons["start"])
        self.assertFalse(engine.update(hand(.599, **pose)).buttons["start"])
        self.assertTrue(engine.update(hand(.601, **pose)).buttons["start"])
        engine.update(hand(.70))
        engine.update(hand(.99))
        engine.update(hand(1.01))
        self.assertFalse(engine.update(hand(1.02, **pose)).buttons["start"])
        self.assertTrue(engine.update(hand(1.521, **pose)).buttons["start"])

    def test_comfortable_thumbs_up_requires_thumb_open_and_all_fingers_closed(self):
        pose = dict(thumb_curl=.21, index_curl=.46, middle_curl=.58,
                    ring_curl=.47, pinky_curl=.46)
        engine = calibrated_engine("program_h")
        for t in (.1, .2, .26):
            state = engine.update(hand(t, palm_x=.8, **pose))
            self.assertFalse(any(state.dpad.values()))
        self.assertTrue(state.buttons["select"])
        engine.update(hand(1.2, **pose))
        self.assertTrue(engine.menu_feedback()["recognized"])
        for name in pose:
            candidate = dict(pose)
            candidate[name] = .55 if name == "thumb_curl" else .25
            engine = calibrated_engine("program_h")
            for t in (.1, .85):
                state = engine.update(hand(t, **candidate))
            self.assertFalse(state.buttons["select"])
            self.assertNotEqual(engine.menu_feedback()["pose"], "select")

    def test_center_box_classifies_all_eight_directions_and_releases_immediately(self):
        engine = calibrated_engine()
        positions = {
            "left": (.3, .50, {"left"}), "right": (.7, .50, {"right"}),
            "up": (.50, .3, {"up"}), "down": (.50, .7, {"down"}),
            "up_left": (.3, .3, {"up", "left"}),
            "up_right": (.7, .3, {"up", "right"}),
            "down_left": (.3, .7, {"down", "left"}),
            "down_right": (.7, .7, {"down", "right"}),
        }
        for index, (name, (x, y, expected)) in enumerate(positions.items(), 1):
            with self.subTest(region=name):
                state = engine.update(hand(index / 10, palm_x=x, palm_y=y))
                self.assertEqual({key for key, value in state.dpad.items() if value}, expected)
                self.assertFalse(any(engine.update(hand(index / 10 + .01)).dpad.values()))

    def test_center_box_boundary_is_inside_and_reversal_has_no_memory(self):
        engine = calibrated_engine()
        self.assertFalse(any(engine.update(hand(.1, palm_x=.64, palm_y=.36)).dpad.values()))
        self.assertTrue(engine.update(hand(.2, palm_x=.7)).dpad["right"])
        reversed_state = engine.update(hand(.3, palm_x=.3))
        self.assertTrue(reversed_state.dpad["left"])
        self.assertFalse(reversed_state.dpad["right"])

    def test_legacy_direction_pairs_do_not_override_the_center_box(self):
        engine = calibrated_engine()
        engine.config = GestureConfig(
            joystick_deadzone=.28,
            thresholds={"right": {"on": .9, "off": .8}},
        )
        self.assertTrue(engine.update(hand(.1, palm_x=.7)).dpad["right"])

    def test_calibrated_hand_size_but_not_noise_sets_minimum_center_box(self):
        engine = GestureEngine("program_h", calibration_frames=5)
        for t, x in enumerate((.47, .53, .48, .52, .50)):
            engine.update(hand(t / 30, palm_x=x))
        self.assertGreater(engine.calibration.noise_x, .1)
        self.assertAlmostEqual(engine.config.effective_joystick_deadzone(engine.calibration),.30)
        self.assertFalse(any(engine.update(hand(1,palm_x=.65,palm_y=.35)).dpad.values()))
        self.assertTrue(engine.update(hand(2,palm_x=.650001)).dpad['right'])

    def test_joystick_box_uses_saved_center_and_translates_intact_at_edges(self):
        from powerglove_vision.gesture import joystick_deadzone_bounds
        from powerglove_vision.model import Calibration
        config=GestureConfig(joystick_deadzone=.3)
        center=Calibration(.3,.7,.1,0)
        centered=joystick_deadzone_bounds(config,center)
        for key,value in dict(center_x=.3,center_y=.7,half_size=.15,left=.15,
                              right=.45,top=.55,bottom=.85).items():
            self.assertAlmostEqual(centered[key],value)
        edge=Calibration(.02,.97,.1,0)
        bounds=joystick_deadzone_bounds(config,edge)
        self.assertAlmostEqual(bounds['left'],0);self.assertAlmostEqual(bounds['right'],.3)
        self.assertAlmostEqual(bounds['top'],.7);self.assertAlmostEqual(bounds['bottom'],1)
        engine=GestureEngine('program_h',config,calibration=edge)
        self.assertFalse(any(engine.update(hand(.1,palm_x=.3,palm_y=.7)).dpad.values()))
        state=engine.update(hand(.2,palm_x=.300001,palm_y=.699999))
        self.assertTrue(state.dpad['right']);self.assertTrue(state.dpad['up'])

    def test_live_hand_size_does_not_make_joystick_bounds_breathe(self):
        from powerglove_vision.model import Calibration
        engine=GestureEngine('program_h',GestureConfig(joystick_deadzone=.1),
                             calibration=Calibration(.5,.5,.2,0))
        for index,scale in enumerate((.08,.2,.6),1):
            with self.subTest(live_scale=scale):
                self.assertFalse(any(engine.update(hand(index,palm_x=.65,palm_scale=scale)).dpad.values()))
                self.assertTrue(engine.update(hand(index+.1,palm_x=.650001,palm_scale=scale)).dpad['right'])

    def test_middle_finger_is_a_plus_b(self):
        state = calibrated_engine().update(hand(0.1, middle_curl=0.9))
        self.assertTrue(state.buttons["a"])
        self.assertTrue(state.buttons["b"])

    def test_push_is_edge_triggered(self):
        engine = calibrated_engine()
        first = engine.update(hand(0.1, palm_scale=0.28))
        held = engine.update(hand(0.2, palm_scale=0.28))
        self.assertEqual(first.events, [])
        self.assertEqual(held.events, ["glove_zap"])
        self.assertTrue(engine.push_feedback(hand(.2, palm_scale=.28))["active"])
        self.assertFalse(engine.push_feedback(HandObservation(.3, False))["active"])
        engine.begin_calibration()
        self.assertFalse(engine.push_feedback(hand(.4, palm_scale=.28))["active"])

    def test_depth_motion_rejects_spikes_and_stationary_near_far_hands(self):
        push = calibrated_engine()
        push.update(hand(.90))
        spike = push.update(hand(1.00, palm_scale=.30))
        self.assertEqual(spike.events, [])
        self.assertFalse(push.update(hand(1.05)).buttons["glove_zap"])
        # With no neutral observation in the 250 ms window, an already-near
        # stationary hand cannot manufacture a push merely by being large.
        self.assertFalse(push.update(hand(2.00, palm_scale=.30)).buttons["glove_zap"])
        self.assertFalse(push.update(hand(2.08, palm_scale=.30)).buttons["glove_zap"])

        pull = calibrated_engine()
        pull.update(hand(.90))
        pull.update(hand(1.00, palm_scale=.12))
        pull.update(hand(1.05))
        self.assertFalse(pull.pull_feedback(hand(1.05))["active"])
        pull.update(hand(2.00, palm_scale=.12))
        pull.update(hand(2.08, palm_scale=.12))
        self.assertFalse(pull.pull_feedback(hand(2.08, palm_scale=.12))["active"])

    def test_depth_candidates_confirm_with_motion_and_cancel_on_reversal(self):
        engine = calibrated_engine()
        engine.update(hand(.90))
        first = engine.update(hand(1.00, palm_scale=.30))
        self.assertEqual(first.events, [])
        reversed_sample = engine.update(hand(1.05, palm_scale=.28))
        self.assertEqual(reversed_sample.events, [])
        confirmed = engine.update(hand(1.12, palm_scale=.28))
        self.assertEqual(confirmed.events, ["glove_zap"])
        released = engine.update(hand(1.20, palm_scale=.22))
        self.assertFalse(released.buttons["glove_zap"])

    def test_pull_learning_feedback_uses_personal_thresholds_and_releases(self):
        engine = calibrated_engine()
        engine.config = GestureConfig(thresholds={"pull": {"on": .25, "off": .10}})
        for t, scale, expected in ((.1, .2, False), (.15, .14, False), (.2, .14, True),
                                   (.3, .17, True), (.4, .19, False),
                                   (.45, .14, False), (.5, .14, True)):
            observation = hand(t, palm_scale=scale)
            state = engine.update(observation)
            feedback = engine.pull_feedback(observation)
            self.assertEqual(feedback["active"], expected)
            self.assertEqual(feedback["threshold"], .25)
            self.assertEqual(state.events, [])
            self.assertFalse(state.buttons.get("glove_zap", False))
        missing = HandObservation(.8, False)
        engine.update(missing)
        self.assertFalse(engine.pull_feedback(missing)["active"])
        observation = hand(.9, palm_scale=.17)
        engine.update(observation)
        self.assertFalse(engine.pull_feedback(observation)["active"])
        engine.update(hand(1, palm_scale=.14))
        engine.begin_calibration()
        self.assertFalse(engine.pull_feedback(hand(1.1, palm_scale=.14))["active"])

    def test_tracking_loss_releases_controls(self):
        engine = calibrated_engine()
        engine.update(hand(0.1, palm_x=0.7))
        state = engine.update(HandObservation(timestamp=0.25, detected=False))
        self.assertFalse(any(state.dpad.values()))
        self.assertFalse(state.detected)

    def test_brief_tracking_dropout_does_not_chatter(self):
        engine = calibrated_engine()
        engine.update(hand(0.10, palm_x=0.7))
        state = engine.update(HandObservation(timestamp=0.15, detected=False))
        self.assertTrue(state.dpad["right"])
        self.assertFalse(state.detected)

    def test_super_glove_preserves_analogue_and_fingers(self):
        engine = calibrated_engine("super_glove_ball")
        state = engine.update(hand(0.1, palm_x=0.58, ring_curl=0.8))
        expected_x = round((0.58 - 0.50) / (0.50 - engine.config.coordinate_edge_margin) * 32767)
        self.assertEqual(state.axes["x"], expected_x)
        self.assertEqual(state.fingers["ring"], 2)

    def test_continuous_coordinates_span_the_usable_camera_field(self):
        left = calibrated_engine("super_glove_ball").update(hand(0.1, palm_x=0.08))
        right = calibrated_engine("super_glove_ball").update(hand(0.1, palm_x=0.92))
        top = calibrated_engine("super_glove_ball").update(hand(0.1, palm_y=0.08))
        bottom = calibrated_engine("super_glove_ball").update(hand(0.1, palm_y=0.92))
        self.assertEqual(left.axes["x"], -32767)
        self.assertEqual(right.axes["x"], 32767)
        self.assertEqual(top.axes["y"], -32767)
        self.assertEqual(bottom.axes["y"], 32767)

    def test_continuous_coordinates_smooth_jitter_but_follow_large_motion(self):
        engine = calibrated_engine("super_glove_ball")
        first = engine.update(hand(0.1, palm_x=0.60))
        jitter = engine.update(hand(0.2, palm_x=0.602))
        usable_half_width = 0.50 - engine.config.coordinate_edge_margin
        raw_jitter_step = round(0.002 / usable_half_width * 32767)
        self.assertLess(jitter.axes["x"] - first.axes["x"], raw_jitter_step)
        moved = engine.update(hand(0.3, palm_x=0.80))
        raw_large_motion = round((0.80 - 0.50) / usable_half_width * 32767)
        self.assertEqual(moved.axes["x"], raw_large_motion)

    def test_continuous_filter_resets_after_tracking_loss(self):
        engine = calibrated_engine("super_glove_ball")
        engine.update(hand(0.1, palm_x=0.70))
        engine.update(HandObservation(timestamp=0.3, detected=False))
        centered = engine.update(hand(0.4))
        self.assertEqual(centered.axes["x"], 0)

    def test_all_cartridge_free_programs_are_available(self):
        for letter in "abcdefghi":
            with self.subTest(program=letter):
                engine = calibrated_engine(f"program_{letter}")
                state = engine.update(hand(0.1, palm_x=0.62, index_curl=0.9))
                self.assertEqual(state.profile, f"program_{letter}")

    def test_program_d_reverses_directions(self):
        state = calibrated_engine("program_d").update(hand(0.1, palm_x=0.7))
        self.assertTrue(state.dpad["left"])
        self.assertFalse(state.dpad["right"])

    def test_program_b_pulses_joust_flap(self):
        state = calibrated_engine("program_b").update(hand(0.15, index_curl=0.9))
        self.assertTrue(state.buttons["a"])

    def test_program_i_maps_driving_controls_to_the_nes_pad(self):
        engine = calibrated_engine("program_i")
        throttle = engine.update(hand(0.10, index_curl=0.9))
        self.assertTrue(throttle.dpad["up"])
        self.assertFalse(throttle.buttons["a"])

        engine.update(hand(0.15, palm_scale=0.28, index_curl=0.9))
        turbo = engine.update(hand(0.20, palm_scale=0.30, index_curl=0.9))
        self.assertTrue(turbo.dpad["up"])
        self.assertTrue(turbo.buttons["a"])

        weapons = engine.update(hand(0.30, thumb_curl=0.9))
        self.assertTrue(weapons.buttons["b"])

        brake = engine.update(hand(0.40, palm_y=0.7))
        self.assertTrue(brake.dpad["down"])

        steering = engine.update(hand(0.50, roll=-1.2))
        self.assertTrue(steering.dpad["left"])

    def test_nonpositional_game_movements_hold_between_personal_activation_and_release(self):
        import math
        # Exercise every mapping that previously bypassed movement release.
        cases = [
            ("program_a", "roll_left", "buttons", "b"),
            ("program_e", "roll_right", "buttons", "b"),
            ("program_c", "roll_left", "dpad", "left"),
            ("program_c", "roll_right", "dpad", "right"),
            ("program_c", "pull", "buttons", "b"),
            ("program_g", "roll_left", "dpad", "left"),
            ("program_g", "roll_right", "dpad", "right"),
            ("program_g", "push", "buttons", "b"),
            ("program_i", "roll_left", "dpad", "left"),
            ("program_i", "roll_right", "dpad", "right"),
            ("program_i", "push", "buttons", "a"),
        ]
        for profile, channel, output, button in cases:
            with self.subTest(profile=profile, channel=channel):
                engine = calibrated_engine(profile)
                engine.config = GestureConfig(
                    depth_confirm_frames=1, depth_motion_delta=0,
                    thresholds={channel: {"on": .6, "off": .2}},
                )
                for t, magnitude, expected in ((.1,.4,False),(.2,.7,True),(.3,.4,True),(.4,.1,False),(.5,.4,False)):
                    changes = {}
                    if channel.startswith('roll'):
                        changes['roll'] = magnitude * math.pi / 2 * (-1 if channel == 'roll_left' else 1)
                    elif channel in ('push','pull'):
                        changes['palm_scale'] = .2 * (1 + magnitude * (-1 if channel == 'pull' else 1))
                    else:
                        changes['palm_x' if channel in ('left','right') else 'palm_y'] = .5 + .2*magnitude*(-1 if channel in ('left','up') else 1)
                    observation = hand(t, **changes)
                    state = engine.update(observation)
                    self.assertEqual(getattr(state, output)[button], expected)
                    if channel in ('push','pull'):
                        feedback = getattr(engine, channel+'_feedback')(observation)
                        self.assertEqual(feedback['active'], expected)

    def test_pinball_pull_toggle_requires_release_before_retrigger(self):
        engine = calibrated_engine('program_a')
        for t, scale, toggled in ((.1,.12,False),(.15,.12,True),(.2,.15,True),
                                  (.3,.12,True),(.4,.2,True),(.45,.12,True),(.5,.12,False)):
            state = engine.update(hand(t, palm_scale=scale, index_curl=.8))
            self.assertEqual(state.dpad['up'], toggled)

    def test_movement_state_resets_after_tracking_loss(self):
        engine = calibrated_engine('program_i')
        engine.update(hand(.1,palm_scale=.28))
        engine.update(HandObservation(.5,False))
        state = engine.update(hand(.6,palm_scale=.25))
        self.assertFalse(state.buttons['a'])
        self.assertFalse(engine.push_feedback(hand(.6,palm_scale=.25))['active'])

    def test_held_v_sign_pulses_start_without_attacking(self):
        engine = calibrated_engine()
        pose = dict(index_curl=0.1, middle_curl=0.1, ring_curl=0.9, pinky_curl=0.9)
        forming = engine.update(hand(0.10, **pose))
        pulse = engine.update(hand(0.85, **pose))
        held = engine.update(hand(1.10, **pose))
        self.assertFalse(forming.buttons["start"])
        self.assertTrue(pulse.buttons["start"])
        self.assertFalse(pulse.buttons["a"])
        self.assertFalse(held.buttons["start"])
        self.assertEqual(engine.menu_feedback()["pose"], "start")
        self.assertTrue(engine.menu_feedback()["recognized"])
        engine.update(hand(1.5))
        self.assertIsNone(engine.menu_feedback()["pose"])

    def test_v_sign_requires_sustained_release_before_it_can_rearm(self):
        engine = calibrated_engine()
        pose = dict(index_curl=0.1, middle_curl=0.1, ring_curl=0.9, pinky_curl=0.9)
        engine.update(hand(.10, **pose))
        self.assertTrue(engine.update(hand(.76, **pose)).buttons["start"])

        # A momentary recognition break must not turn the same hand shape into
        # a second pause command when the V pose immediately returns.
        engine.update(hand(1.00))
        self.assertFalse(engine.update(hand(1.10, **pose)).buttons["start"])
        self.assertFalse(engine.update(hand(2.00, **pose)).buttons["start"])

        # Rearm only after a continuous, clearly non-V interval, then require
        # the full deliberate hold again.
        engine.update(hand(2.10))
        engine.update(hand(2.41))
        self.assertFalse(engine.update(hand(2.50, **pose)).buttons["start"])
        self.assertTrue(engine.update(hand(3.16, **pose)).buttons["start"])

    def test_held_thumbs_up_pulses_select_without_attacking(self):
        engine = calibrated_engine()
        pose = dict(thumb_curl=0.1, index_curl=0.9, middle_curl=0.9, ring_curl=0.9, pinky_curl=0.9)
        engine.update(hand(0.10, **pose))
        pulse = engine.update(hand(0.85, **pose))
        self.assertTrue(pulse.buttons["select"])
        self.assertFalse(pulse.buttons["a"])
        self.assertFalse(pulse.buttons["b"])
        engine.update(hand(1.10, **pose))
        self.assertEqual(engine.menu_feedback()["pose"], "select")
        self.assertTrue(engine.menu_feedback()["recognized"])

    def test_menu_guard_is_exact_and_suppresses_every_mapping(self):
        from powerglove_vision.gesture import SUPPORTED_PROFILES
        pose = dict(thumb_curl=.9, ring_curl=.9)
        for profile in SUPPORTED_PROFILES:
            engine = calibrated_engine(profile)
            guarded = engine.update(hand(.1, palm_x=.62, index_curl=.1, middle_curl=.1,
                                         pinky_curl=.1, **pose))
            self.assertTrue(engine.recognition_feedback()["menu_guard"], profile)
            self.assertTrue(guarded.buttons["menu_guard"], profile)
            self.assertFalse(any(guarded.dpad.values()), profile)
            self.assertFalse(guarded.buttons["a"] or guarded.buttons["b"], profile)
            self.assertFalse(guarded.buttons["start"] or guarded.buttons["select"], profile)
            released = engine.update(hand(.2, palm_x=.62, index_curl=.9, **pose))
            self.assertFalse(engine.recognition_feedback()["menu_guard"], profile)
            self.assertFalse(released.buttons["menu_guard"], profile)

    def test_menu_guard_accepts_a_comfortable_thumb_and_ring_curl(self):
        engine = calibrated_engine("program_g")
        guarded = engine.update(hand(.1, palm_x=.62, thumb_curl=.27,
                                     index_curl=.1, middle_curl=.1,
                                     ring_curl=.45, pinky_curl=.1))
        self.assertTrue(guarded.buttons["menu_guard"])
        self.assertFalse(guarded.buttons["a"] or guarded.buttons["b"])

        held = engine.update(hand(.2, palm_x=.62, thumb_curl=.22,
                                  index_curl=.1, middle_curl=.1,
                                  ring_curl=.40, pinky_curl=.1))
        self.assertTrue(held.buttons["menu_guard"])

    def test_menu_guard_easing_does_not_lower_general_ring_threshold(self):
        engine = calibrated_engine("program_g")
        state = engine.update(hand(.1, ring_curl=.45))
        self.assertEqual(state.fingers["ring"], 1)

    def test_menu_guard_and_v_sign_have_a_deadband_and_never_overlap(self):
        engine = calibrated_engine("program_g")
        common = dict(thumb_curl=.9, index_curl=.1, middle_curl=.1, ring_curl=.9)

        guard = engine.update(hand(.10, pinky_curl=.34, **common))
        self.assertTrue(guard.buttons["menu_guard"])
        self.assertFalse(guard.buttons["start"])

        deadband = engine.update(hand(.20, pinky_curl=.40, **common))
        self.assertFalse(deadband.buttons["menu_guard"])
        self.assertFalse(deadband.buttons["start"])
        self.assertIsNone(engine.menu_feedback()["pose"])

        forming_v = engine.update(hand(.30, pinky_curl=.45, **common))
        start = engine.update(hand(.96, pinky_curl=.45, **common))
        self.assertFalse(forming_v.buttons["menu_guard"])
        self.assertTrue(start.buttons["start"])
        self.assertFalse(start.buttons["menu_guard"])

    def test_menu_guard_retains_curled_fingers_through_release_hysteresis(self):
        engine = calibrated_engine("program_g")
        common = dict(palm_x=.8, index_curl=0, middle_curl=0, pinky_curl=0)
        active = engine.update(hand(.10, thumb_curl=.8, ring_curl=.8, **common))
        self.assertTrue(active.buttons["menu_guard"])
        held = engine.update(hand(.20, thumb_curl=.4, ring_curl=.4, **common))
        self.assertTrue(held.buttons["menu_guard"])
        self.assertFalse(any(held.dpad.values()))
        released = engine.update(hand(.30, thumb_curl=.3, ring_curl=.3, **common))
        self.assertFalse(released.buttons["menu_guard"])
        self.assertTrue(released.dpad["right"])

    def test_menu_guard_cancels_a_forming_or_active_start_pulse(self):
        engine = calibrated_engine("super_glove_ball")
        v = dict(index_curl=.1, middle_curl=.1, ring_curl=.9, pinky_curl=.9)
        engine.update(hand(.10, **v))
        self.assertTrue(engine.update(hand(.76, **v)).buttons["start"])

        guard = engine.update(hand(.77, thumb_curl=.9, index_curl=.1,
                                   middle_curl=.1, ring_curl=.9, pinky_curl=.1))
        self.assertTrue(guard.buttons["menu_guard"])
        self.assertFalse(guard.buttons["start"])
        self.assertFalse(guard.buttons["select"])
        self.assertIsNone(engine.menu_feedback()["pose"])


if __name__ == "__main__":
    unittest.main()


class CalibrationRetentionTests(unittest.TestCase):
    """Verify saved neutral references survive engine replacement and explicit recalibration."""

    def test_roundtrip_and_replacement(self):
        import tempfile
        from pathlib import Path
        from powerglove_vision.gesture import load_calibration, save_calibration
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            self.assertIsNone(load_calibration(path))
            original = calibrated_engine()
            save_calibration(path, original.calibration)
            restored = GestureEngine("super_glove_ball", calibration_frames=3,
                                     calibration=load_calibration(path))
            self.assertTrue(restored.calibrated)
            state = restored.update(hand(1))
            self.assertFalse(any(state.dpad.values()))
            restored.begin_calibration()
            for t in (2, 3, 4):
                restored.update(hand(t, palm_x=0.7))
            save_calibration(path, restored.calibration)
            self.assertAlmostEqual(load_calibration(path).palm_x, 0.7)

    def test_invalid_saved_reference(self):
        import tempfile
        from pathlib import Path
        from powerglove_vision.gesture import load_calibration
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            for value in ('broken', '{}', '{"version":1,"neutral":{"palm_x":0,"palm_y":0,"palm_scale":0,"roll":0}}'):
                path.write_text(value)
                self.assertIsNone(load_calibration(path))



    def test_brawler_zap_pulses_both_directions_once_per_push(self):
        engine = calibrated_engine()
        engine.config = GestureConfig(thresholds={"push": {"on": .3, "off": .1}})
        engine.update(hand(.9, palm_scale=.20))
        first = engine.update(hand(1., palm_scale=.28, middle_curl=.8))
        self.assertFalse(first.dpad['left'] or first.dpad['right'])
        confirmed = engine.update(hand(1.1, palm_scale=.28, middle_curl=.8))
        self.assertTrue(confirmed.dpad['left'] and confirmed.dpad['right'])
        self.assertFalse(confirmed.buttons['a'] or confirmed.buttons['b'])
        held = engine.update(hand(1.3, palm_scale=.28))
        self.assertFalse(held.dpad['left'] or held.dpad['right'])
        engine.update(hand(1.4, palm_scale=.20))
        engine.update(hand(1.45, palm_scale=.28))
        again = engine.update(hand(1.5, palm_scale=.28))
        self.assertTrue(again.dpad['left'] and again.dpad['right'])

    def test_brawler_zap_cancels_on_menu_tracking_loss_and_calibration(self):
        for interrupt in ('menu', 'loss', 'calibrate'):
            engine = calibrated_engine()
            engine.update(hand(1., palm_scale=.35))
            if interrupt == 'menu':
                result = engine.update(hand(1.03, palm_scale=.35, ring_curl=.8, pinky_curl=.8))
                self.assertFalse(result.dpad['left'] and result.dpad['right'])
                result = engine.update(hand(1.06, palm_scale=.35))
            elif interrupt == 'loss':
                result = engine.update(hand(1.03, detected=False))
            else:
                engine.begin_calibration()
                result = engine.update(hand(1.03, palm_scale=.35))
            self.assertFalse(result.dpad['left'] and result.dpad['right'], interrupt)

    def test_other_profiles_do_not_emit_brawler_zap_combination(self):
        from powerglove_vision.gesture import SUPPORTED_PROFILES
        for profile in SUPPORTED_PROFILES:
            if profile == 'bad_street_brawler': continue
            result = calibrated_engine(profile).update(hand(1., palm_scale=.35))
            self.assertFalse(result.dpad['left'] and result.dpad['right'], profile)
