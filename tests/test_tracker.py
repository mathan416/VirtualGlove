# Project: VirtualGlove
# File: tests/test_tracker.py
# Purpose: Verify depth-aware curl geometry and MediaPipe coordinate selection.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Covered CPU inference node names in two tested MediaPipe releases.
#   2026-09-09 - Covered observable loss-cause attribution across recovery.
#   2026-09-09 - Covered optional one-frame directional reacquisition search.
#   2026-09-09 - Covered capture-time tracking loss and recovery timing.
#   2026-09-09 - Verified preview demand cannot change fused preparation.
#   2026-09-07 - Covered landmark validity, palm anchors, and confidence semantics.
#   2026-09-05 - Covered stable backend identifiers and display names.
#   2026-09-03 - Covered folded fingers, rotation, API variants, and menu recognition.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify camera curl geometry without requiring MediaPipe or a camera."""

import math
import inspect
import unittest
from types import SimpleNamespace

from virtualglove import tracker as tracker_module
from virtualglove.tracker import (
    TRACKER_BACKEND_LABELS, TRACKING_EVIDENCE_OUTPUTS,
    _DirectionalSearchState, _TrackingTelemetry,
    _Point, _camera_curl_points, _configure_tracking_roi, _curl, _finger_bends,
    _finger_curls_from_bends, _start_curls_from_bends, _landmarks_valid,
    _inference_node_threads, _is_cpu_inference_calculator,
    _hand_presence_score_evidence,
    _palm_anchor_candidates, _palm_detector_evidence, _polygon_centroid,
    _prepare_tracker_frame, _translate_tracker_input,
)
from virtualglove.gesture import GestureEngine
from virtualglove.model import HandObservation


def pose_points(closed):
    """Build straight or depth-folded fingers with two right-angle bends."""
    points = [_Point(0, 0, 0)]
    for name in ('thumb', 'index', 'middle', 'ring', 'pinky'):
        finger = [(0, 0, 0), (0, 1, 0), (0, 1, -1), (0, 0, -1)] if name in closed else [(0, i, 0) for i in range(4)]
        points.extend(_Point(*p) for p in finger)
    return points


def finger_curls(points):
    """Collapse the production joint measurements for concise assertions."""
    return _finger_curls_from_bends(_finger_bends(points))


class TrackerGeometryTests(unittest.TestCase):
    def test_cpu_inference_calculator_names_cover_tested_mediapipe_versions(self):
        self.assertTrue(_is_cpu_inference_calculator("InferenceCalculatorCpu"))
        self.assertTrue(_is_cpu_inference_calculator("InferenceCalculatorXnnpack"))
        self.assertFalse(_is_cpu_inference_calculator("InferenceCalculatorGl"))

    def test_directional_search_uses_measured_gentle_gain_by_default(self):
        parameters = inspect.signature(tracker_module.MediaPipeTracker).parameters
        self.assertTrue(parameters["directional_search"].default)
        self.assertEqual(parameters["directional_search_gain"].default, .275)
        self.assertEqual(parameters["directional_search_recovery_frames"].default, 0)

    def test_directional_search_requires_two_aligned_fast_intervals(self):
        state = _DirectionalSearchState(gain=.5, min_speed=.4, max_offset=.08)
        state.observe(.20, .50, 0.0)
        state.observe(.23, .50, .05)
        self.assertEqual(state.next_offset(.10), (0.0, 0.0))
        state.observe(.26, .50, .10)
        x, y = state.next_offset(.15)
        self.assertAlmostEqual(x, -.015)
        self.assertEqual(y, 0.0)
        self.assertTrue(state.active)

    def test_directional_search_stops_accumulating_on_stop_or_reversal(self):
        state = _DirectionalSearchState(gain=.5, min_speed=.4, max_offset=.08)
        for x, timestamp in ((.20, 0.0), (.23, .05), (.26, .10)):
            state.observe(x, .50, timestamp)
        moving = state.next_offset(.15)
        state.observe(.26, .50, .15)
        self.assertNotEqual(moving, (0.0, 0.0))
        self.assertEqual(state.next_offset(.20), (0.0, 0.0))
        self.assertFalse(state.active)
        state.observe(.23, .50, .20)
        self.assertEqual(state.next_offset(.25), (0.0, 0.0))
        self.assertFalse(state.active)

    def test_directional_search_is_bounded_and_loss_reset_is_immediate(self):
        state = _DirectionalSearchState(gain=1.0, min_speed=.1, max_offset=.02)
        for x, timestamp in ((.20, 0.0), (.30, .05), (.40, .10)):
            state.observe(x, .50, timestamp)
        x, y = state.next_offset(.15)
        self.assertAlmostEqual(math.hypot(x, y), .02)
        state.reset()
        self.assertEqual(state.next_offset(.20), (0.0, 0.0))
        self.assertFalse(state.active)

    def test_directional_search_carries_one_proven_offset_after_a_miss(self):
        state = _DirectionalSearchState(
            gain=.5, min_speed=.4, max_offset=.08, recovery_frames=1,
        )
        for x, timestamp in ((.20, 0.0), (.23, .05), (.26, .10)):
            state.observe(x, .50, timestamp)
        expected = state.next_offset(.15)
        state.observe_missing()
        self.assertEqual(state.phase, "recovery")
        self.assertEqual(state.next_offset(.20), expected)
        self.assertEqual(state.phase, "recovery")
        state.observe_missing()
        self.assertEqual(state.next_offset(.25), (0.0, 0.0))
        self.assertFalse(state.active)

    def test_directional_search_does_not_carry_an_unproven_offset(self):
        state = _DirectionalSearchState(gain=.5, min_speed=.4, max_offset=.08)
        state.observe(.20, .50, 0.0)
        state.observe_missing()
        self.assertEqual(state.next_offset(.05), (0.0, 0.0))
        self.assertEqual(state.phase, "inactive")

    def test_directional_search_can_reproduce_immediate_reset_for_replay(self):
        state = _DirectionalSearchState(
            gain=.5, min_speed=.4, max_offset=.08, recovery_frames=0,
        )
        for x, timestamp in ((.20, 0.0), (.23, .05), (.26, .10)):
            state.observe(x, .50, timestamp)
        self.assertNotEqual(state.next_offset(.15), (0.0, 0.0))
        state.observe_missing()
        self.assertEqual(state.next_offset(.20), (0.0, 0.0))

    def test_directional_input_translation_preserves_shape(self):
        import cv2
        import numpy as np

        rgb = np.arange(5 * 6 * 3, dtype=np.uint8).reshape((5, 6, 3))
        translated = _translate_tracker_input(rgb, (.1, -.1), cv2, np)
        self.assertEqual(translated.shape, rgb.shape)
        self.assertFalse(translated.flags.writeable)
        self.assertIs(_translate_tracker_input(rgb, (0.0, 0.0), cv2, np), rgb)

    def test_fused_preparation_matches_existing_mirrored_rgb_exactly(self):
        import cv2
        import numpy as np

        frame = np.arange(3 * 4 * 3, dtype=np.uint8).reshape((3, 4, 3))
        display, rgb, lane = _prepare_tracker_frame(
            frame, True, False, True, cv2, np,
        )
        expected = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
        self.assertTrue(np.array_equal(rgb, expected))
        self.assertTrue(rgb.flags.c_contiguous)
        self.assertFalse(rgb.flags.writeable)
        self.assertIs(display, frame)
        self.assertEqual(lane, "fused-mirror-bgr-to-rgb")

    def test_preview_does_not_change_fused_inference_preparation(self):
        import cv2
        import numpy as np

        frame = np.arange(3 * 4 * 3, dtype=np.uint8).reshape((3, 4, 3))
        display, rgb, lane = _prepare_tracker_frame(
            frame, True, True, True, cv2, np,
        )
        expected_display = cv2.flip(frame, 1)
        self.assertIs(display, frame)
        self.assertTrue(np.array_equal(
            rgb, cv2.cvtColor(expected_display, cv2.COLOR_BGR2RGB),
        ))
        self.assertEqual(lane, "fused-mirror-bgr-to-rgb")

    def test_nonmirrored_preparation_keeps_existing_contract(self):
        import cv2
        import numpy as np

        frame = np.arange(3 * 4 * 3, dtype=np.uint8).reshape((3, 4, 3))
        display, rgb, lane = _prepare_tracker_frame(
            frame, False, False, True, cv2, np,
        )
        self.assertIs(display, frame)
        self.assertTrue(np.array_equal(rgb, frame[:, :, ::-1]))
        self.assertEqual(lane, "bgr-to-rgb")

    def test_fused_preparation_can_be_disabled_for_repeatable_comparison(self):
        import cv2
        import numpy as np

        frame = np.arange(3 * 4 * 3, dtype=np.uint8).reshape((3, 4, 3))
        display, rgb, lane = _prepare_tracker_frame(
            frame, True, False, False, cv2, np,
        )
        self.assertTrue(np.array_equal(display, cv2.flip(frame, 1)))
        self.assertTrue(np.array_equal(
            rgb, cv2.cvtColor(display, cv2.COLOR_BGR2RGB),
        ))
        self.assertEqual(lane, "preview-compatible")

    def test_tracking_evidence_names_match_the_mediapipe_graph_outputs(self):
        self.assertEqual(TRACKING_EVIDENCE_OUTPUTS, (
            "palm_detections",
            "handlandmarkcpu__hand_presence_score",
        ))

    def test_inference_threads_can_target_palm_and_landmark_models_separately(self):
        palm = "palmdetectioncpu__inferencecalculator__InferenceCalculator"
        landmark = "handlandmarkcpu__inferencecalculator__InferenceCalculator"
        self.assertEqual(_inference_node_threads(palm, 4, 1), 1)
        self.assertEqual(_inference_node_threads(palm, 4, None), 4)
        self.assertEqual(_inference_node_threads(landmark, 4, 1), 4)
        with self.assertRaises(RuntimeError):
            _inference_node_threads("unexpected", 4, 1)

    def test_detector_evidence_distinguishes_skipped_empty_and_unavailable(self):
        self.assertEqual(_palm_detector_evidence(SimpleNamespace()), (None, None))
        self.assertEqual(
            _palm_detector_evidence(SimpleNamespace(palm_detections=None)),
            (None, None),
        )
        self.assertEqual(
            _palm_detector_evidence(SimpleNamespace(palm_detections=[])),
            (True, 0),
        )
        self.assertEqual(
            _palm_detector_evidence(SimpleNamespace(palm_detections=[1])),
            (True, 1),
        )

    def test_hand_presence_evidence_rejects_unavailable_and_nonfinite_values(self):
        name = "handlandmarkcpu__hand_presence_score"
        self.assertIsNone(_hand_presence_score_evidence(SimpleNamespace()))
        self.assertIsNone(_hand_presence_score_evidence(
            SimpleNamespace(**{name: float("nan")})
        ))
        self.assertEqual(_hand_presence_score_evidence(
            SimpleNamespace(**{name: .47})
        ), .47)

    def test_tracking_telemetry_classifies_initial_continuation_and_reacquisition(self):
        telemetry = _TrackingTelemetry()
        initial = telemetry.observe(True, True, 1)
        continued = telemetry.observe(True, None, None)
        redetected = telemetry.observe(True, True, 1)
        missed = telemetry.observe(False, None, None)
        detector_miss = telemetry.observe(False, True, 0)
        recovered = telemetry.observe(True, True, 1)
        self.assertEqual(initial["tracking_path"], "initial_palm_detection")
        self.assertEqual(continued["tracking_path"], "landmark_continuation")
        self.assertEqual(redetected["tracking_path"], "palm_redetection")
        self.assertEqual(missed["tracking_path"], "hand_missing_path_unobservable")
        self.assertEqual(detector_miss["tracking_path"], "palm_detection_no_valid_hand")
        self.assertEqual(recovered["tracking_path"], "palm_reacquisition")
        self.assertTrue(recovered["palm_reacquired"])
        self.assertEqual(recovered["palm_detection_packets_total"], 4)
        self.assertEqual(recovered["palm_redetections_total"], 1)
        self.assertEqual(recovered["palm_reacquisitions_total"], 1)
        self.assertEqual(recovered["hand_missing_results_total"], 2)
        self.assertEqual(recovered["hand_missing_streak"], 0)

    def test_tracking_telemetry_never_guesses_when_detector_is_unobservable(self):
        telemetry = _TrackingTelemetry()
        detected = telemetry.observe(True, None, None)
        missing = telemetry.observe(False, None, None, invalid_landmarks=True)
        self.assertEqual(detected["tracking_path"], "landmark_continuation")
        self.assertEqual(missing["tracking_path"], "hand_missing_path_unobservable")
        self.assertIsNone(missing["palm_detector_invoked"])
        self.assertEqual(missing["invalid_landmark_results_total"], 1)

    def test_tracking_telemetry_times_loss_and_recovery_from_capture_timestamps(self):
        telemetry = _TrackingTelemetry()
        telemetry.observe(True, True, 1, timestamp=10.0, inference_ms=35.0)
        first = telemetry.observe(False, None, None, timestamp=10.04, inference_ms=40.0)
        second = telemetry.observe(False, True, 0, timestamp=10.08, inference_ms=72.0)
        recovered = telemetry.observe(True, True, 1, timestamp=10.12, inference_ms=68.0)
        self.assertAlmostEqual(first["current_tracking_loss_ms"], 40.0)
        self.assertAlmostEqual(second["current_tracking_loss_ms"], 80.0)
        self.assertTrue(recovered["tracking_recovered"])
        self.assertAlmostEqual(recovered["recovery_gap_ms"], 120.0)
        self.assertAlmostEqual(recovered["recovery_missing_span_ms"], 80.0)
        self.assertAlmostEqual(recovered["last_recovery_inference_ms"], 68.0)
        self.assertAlmostEqual(recovered["longest_tracking_loss_ms"], 80.0)
        self.assertEqual(first["tracking_observation_cause"],
                         "graph_no_hand_unobservable")
        self.assertEqual(second["tracking_observation_cause"],
                         "palm_detection_without_valid_hand")
        self.assertEqual(recovered["last_recovery_loss_start_cause"],
                         "graph_no_hand_unobservable")
        self.assertEqual(recovered["last_recovery_missing_causes"], {
            "graph_no_hand_unobservable": 1,
            "palm_detection_without_valid_hand": 1,
        })
        self.assertEqual(recovered["missing_cause_totals"], {
            "invalid_landmark_geometry": 0,
            "palm_detection_without_valid_hand": 1,
            "landmark_presence_below_gate": 0,
            "graph_no_hand_unobservable": 1,
        })

    def test_presence_score_identifies_a_landmark_gate_loss(self):
        telemetry = _TrackingTelemetry()
        telemetry.observe(True, True, 1)
        missing = telemetry.observe(
            False, None, None, hand_presence_score=.48,
        )
        self.assertEqual(missing["tracking_observation_cause"],
                         "landmark_presence_below_gate")
        self.assertEqual(missing["hand_presence_score"], .48)

    def test_normal_gameplay_omits_detailed_cause_dictionaries(self):
        telemetry = _TrackingTelemetry()
        missing = telemetry.observe(
            False, None, None, include_cause_details=False,
        )
        self.assertEqual(missing["tracking_observation_cause"],
                         "graph_no_hand_unobservable")
        self.assertNotIn("missing_cause_totals", missing)
        self.assertNotIn("current_missing_causes", missing)

    def test_invalid_landmarks_are_the_observable_loss_cause(self):
        telemetry = _TrackingTelemetry()
        telemetry.observe(True, True, 1)
        missing = telemetry.observe(
            False, True, 1, invalid_landmarks=True,
        )
        self.assertEqual(missing["tracking_observation_cause"],
                         "invalid_landmark_geometry")
        self.assertEqual(missing["loss_start_cause"],
                         "invalid_landmark_geometry")

    def test_tracking_telemetry_handles_missing_timestamps_without_inventing_latency(self):
        telemetry = _TrackingTelemetry()
        telemetry.observe(True, None, None)
        missing = telemetry.observe(False, None, None)
        recovered = telemetry.observe(True, None, None)
        self.assertIsNone(missing["current_tracking_loss_ms"])
        self.assertTrue(recovered["tracking_recovered"])
        self.assertIsNone(recovered["recovery_gap_ms"])

    def test_tracking_roi_scale_is_bounded_before_graph_construction(self):
        tracker = object.__new__(tracker_module.MediaPipeTracker)
        with self.assertRaises(ValueError):
            tracker_module.MediaPipeTracker.__init__(tracker, tracking_roi_scale=1.9)

    def test_directional_search_settings_are_bounded_before_graph_construction(self):
        for arguments in (
            {"directional_search": "yes"},
            {"directional_search_gain": 1.01},
            {"directional_search_min_speed": -0.01},
            {"directional_search_max_offset": .151},
            {"directional_search_recovery_frames": 2},
        ):
            tracker = object.__new__(tracker_module.MediaPipeTracker)
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                tracker_module.MediaPipeTracker.__init__(tracker, **arguments)

    def test_tracking_evidence_requires_an_explicit_boolean(self):
        tracker = object.__new__(tracker_module.MediaPipeTracker)
        with self.assertRaises(ValueError):
            tracker_module.MediaPipeTracker.__init__(
                tracker, tracking_evidence="yes",
            )

    def test_palm_inference_threads_are_bounded_before_graph_construction(self):
        for value in (0, 3, 5, 1.0, True):
            tracker = object.__new__(tracker_module.MediaPipeTracker)
            with self.subTest(value=value), self.assertRaises(ValueError):
                tracker_module.MediaPipeTracker.__init__(
                    tracker, palm_inference_threads=value,
                )

    def test_tracking_roi_shift_is_bounded_before_graph_construction(self):
        for arguments in (
            {"tracking_roi_shift_x": -.251},
            {"tracking_roi_shift_x": .251},
            {"tracking_roi_shift_y": float("nan")},
            {"tracking_roi_shift_y": float("inf")},
        ):
            tracker = object.__new__(tracker_module.MediaPipeTracker)
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                tracker_module.MediaPipeTracker.__init__(tracker, **arguments)

    def test_fixed_roi_shift_preserves_scale_and_builtin_vertical_framing(self):
        options = SimpleNamespace()
        _configure_tracking_roi(options, 2.25, .05, -.10)
        self.assertEqual(options.scale_x, 2.25)
        self.assertEqual(options.scale_y, 2.25)
        self.assertEqual(options.shift_x, .05)
        self.assertAlmostEqual(options.shift_y, -.20)

        baseline = SimpleNamespace()
        _configure_tracking_roi(baseline, 2.25, 0.0, 0.0)
        self.assertEqual(baseline.shift_x, 0.0)
        self.assertAlmostEqual(baseline.shift_y, -.10)

        horizontal = SimpleNamespace()
        _configure_tracking_roi(horizontal, 2.25, 0.0, 0.0, 2.45, 2.25)
        self.assertEqual(horizontal.scale_x, 2.45)
        self.assertEqual(horizontal.scale_y, 2.25)

    def test_axis_specific_tracking_roi_scale_is_bounded(self):
        for arguments in (
            {"tracking_roi_scale_x": 1.99},
            {"tracking_roi_scale_x": 3.01},
            {"tracking_roi_scale_y": float("nan")},
        ):
            tracker = object.__new__(tracker_module.MediaPipeTracker)
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                tracker_module.MediaPipeTracker.__init__(tracker, **arguments)

    def test_previous_landmark_mode_requires_boolean_before_graph_construction(self):
        tracker = object.__new__(tracker_module.MediaPipeTracker)
        with self.assertRaises(ValueError):
            tracker_module.MediaPipeTracker.__init__(
                tracker, use_previous_landmarks="sometimes"
            )

    def test_detection_confidence_is_bounded_before_graph_construction(self):
        tracker = object.__new__(tracker_module.MediaPipeTracker)
        with self.assertRaises(ValueError):
            tracker_module.MediaPipeTracker.__init__(
                tracker, detection_confidence=1.1
            )

    def test_model_complexity_is_bounded_before_graph_construction(self):
        tracker = object.__new__(tracker_module.MediaPipeTracker)
        with self.assertRaises(ValueError):
            tracker_module.MediaPipeTracker.__init__(
                tracker, model_complexity=2
            )

    def test_handedness_certainty_is_not_position_confidence(self):
        self.assertFalse(HandObservation(1.0, True, confidence=.69).usable)
        self.assertTrue(HandObservation(
            1.0, True, confidence=.01, confidence_source="handedness"
        ).usable)
        self.assertFalse(HandObservation(
            1.0, False, confidence=1.0, confidence_source="handedness"
        ).usable)

    def test_palm_anchor_candidates_translate_without_distortion(self):
        points = [_Point(index / 100, (index % 5) / 20, 0) for index in range(21)]
        original = _palm_anchor_candidates(points)
        moved = _palm_anchor_candidates([
            _Point(point.x + .2, point.y - .1, point.z) for point in points
        ])
        self.assertEqual(set(original), set(moved))
        for name in original:
            self.assertAlmostEqual(moved[name][0] - original[name][0], .2)
            self.assertAlmostEqual(moved[name][1] - original[name][1], -.1)

    def test_polygon_centroid_falls_back_for_degenerate_palm(self):
        self.assertEqual(_polygon_centroid([(0, 0), (1, 0), (2, 0)]), (1, 0))

    def test_landmark_validation_rejects_missing_and_nonfinite_values(self):
        valid = [_Point(.2 + index * .01, .3 + (index % 4) * .01, 0)
                 for index in range(21)]
        self.assertTrue(_landmarks_valid(valid))
        self.assertFalse(_landmarks_valid(valid[:-1]))
        self.assertFalse(_landmarks_valid([_Point(.5, .5, 0) for _ in range(21)]))
        valid[3].x = float("nan")
        self.assertFalse(_landmarks_valid(valid))

    def test_backend_identifiers_have_clear_display_names(self):
        self.assertEqual(TRACKER_BACKEND_LABELS, {
            "legacy": "MediaPipe Hands",
            "tasks-video": "MediaPipe Tasks Video (experimental)",
        })

    def test_precomputed_bends_produce_identical_curls(self):
        points = pose_points({'thumb', 'middle', 'pinky'})
        self.assertEqual(
            _finger_curls_from_bends(_finger_bends(points)),
            finger_curls(points),
        )

    def test_base_knuckle_bend_is_detected_with_straight_outer_joints(self):
        points = pose_points(set())
        points[0] = _Point(0, -1, 0)
        points[5:9] = [_Point(0, 0, -i) for i in range(4)]
        bends = _finger_bends(points)
        self.assertAlmostEqual(_finger_curls_from_bends(bends)['index_curl'], .75)
        self.assertEqual(_start_curls_from_bends(bends)['index_tip_curl'], 0.0)

    def test_single_joint_bend_is_not_diluted(self):
        points = pose_points(set())
        points[5:9] = [_Point(0, 0, 0), _Point(0, 1, 0),
                       _Point(0, 1, -1), _Point(0, 1, -2)]
        self.assertAlmostEqual(finger_curls(points)['index_curl'], .75)

    def test_depth_fold_is_not_mistaken_for_straight(self):
        points = pose_points({'ring', 'pinky'})
        self.assertEqual(_curl(*points[13:16]), 0.0)
        curls = finger_curls(points)
        self.assertAlmostEqual(curls['ring_curl'], 0.75)
        self.assertAlmostEqual(curls['pinky_curl'], 0.75)
        self.assertEqual(curls['index_curl'], 0.0)

    def test_curl_is_invariant_to_rotation_scale_and_translation(self):
        points = pose_points({'ring', 'pinky'})
        expected = finger_curls(points)
        for angle in (0.4, 1.3, 2.8):
            rotated = [_Point(2+p.x*3, 4+3*(p.y*math.cos(angle)-p.z*math.sin(angle)),
                              -5+3*(p.y*math.sin(angle)+p.z*math.cos(angle))) for p in points]
            for name, value in finger_curls(rotated).items():
                self.assertAlmostEqual(value, expected[name])

    def test_world_points_are_used_for_both_mediapipe_apis(self):
        points = pose_points({'ring'})
        for tasks, result in [(True, SimpleNamespace(hand_world_landmarks=[points])),
                              (False, SimpleNamespace(multi_hand_world_landmarks=[SimpleNamespace(landmark=points)]))]:
            self.assertIs(_camera_curl_points(result, [], tasks, 640, 480), points)

    def test_fallback_corrects_aspect_ratio_without_rescaling_depth(self):
        points = _camera_curl_points(SimpleNamespace(), [_Point(.2, .4, -.3)], True, 640, 480)
        self.assertAlmostEqual(points[0].y, .3)
        self.assertEqual(points[0].z, -.3)

    def test_collapsed_joint_stays_neutral(self):
        point = _Point(0, 0, 0)
        self.assertEqual(_curl(point, point, point, True), 0.0)

    def test_folded_menu_poses_suppress_directions_and_fire_once(self):
        for button, closed in [('start', {'ring', 'pinky'}),
                               ('select', {'index', 'middle', 'ring', 'pinky'})]:
            engine = GestureEngine('program_h', calibration_frames=3)
            for t in (0, .03, .06):
                engine.update(HandObservation(t, True, confidence=.95,
                                              palm_x=.5, palm_y=.5, palm_scale=.2))
            curls = finger_curls(pose_points(closed))
            for t in (.1, .85):
                state = engine.update(HandObservation(t, True, palm_x=.8, palm_y=.2, palm_scale=.2, **curls))
                self.assertFalse(any(state.dpad.values()))
            self.assertTrue(state.buttons[button])
            state = engine.update(HandObservation(1.2, True, palm_x=.8, palm_y=.2, palm_scale=.2, **curls))
            self.assertFalse(state.buttons[button])
            self.assertTrue(engine.menu_feedback()['recognized'])
