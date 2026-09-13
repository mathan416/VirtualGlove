# Project: VirtualGlove
# File: tests/test_tuning.py
# Purpose: Verify gesture sampling, preview leases, global overrides, and persistence safety.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Kept independent finger tuning coverage with the eased thumb default.
#   2026-09-04 - Added personal tuning regression coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise tuning against deterministic hand observations rather than camera hardware."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from powerglove_vision.tuning import (
    TuningManager, suggest, CHANNELS, REACH_DIRECTIONS, validate_overrides, tuning_recipe,
)
from powerglove_vision.gesture import GestureConfig, GestureEngine, SUPPORTED_PROFILES, MENU_FINGERS, finger_pose_feedback
from powerglove_vision.model import Calibration, HandObservation
from powerglove_vision.debug_server import SharedDebugState


class TuningTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'gesture-tuning.json'
        self.now = 10.
        self.manager = TuningManager(self.path, lambda: self.now)
        self.command('begin')
        self.calibration = Calibration(.5, .5, .2, 0)
        self.manager.observe(HandObservation(0, True, .99, .5,.5,.2,0), self.calibration, GestureConfig(), True)

    def command(self, action, **extra):
        return self.manager.command(dict(action=action, session='test-session', **extra))

    def phases(self):
        return [[dict.fromkeys(CHANNELS, .1 if i % 2 == 0 else .8) for _ in range(20)] for i in range(3)]

    def test_three_recordings_produce_release_below_activation(self):
        pair = suggest('index', self.phases())['index']
        self.assertGreater(pair['off'], .1)
        self.assertLess(pair['off'], pair['on'])
        self.assertLess(pair['on'], .8)

    def test_problem_biases_and_motion_recipes(self):
        phases = self.phases()
        difficult = suggest('index', phases, activation_fraction=.55)['index']
        standard = suggest('index', phases)['index']
        accidental = suggest('index', phases, activation_fraction=.75, release_fraction=.40)['index']
        self.assertLess(difficult['on'], standard['on'])
        self.assertGreater(accidental['on'], standard['on'])
        self.assertGreater(accidental['off'], standard['off'])
        self.assertEqual(tuning_recipe('push')['durations'], [2.0, 6.0, 2.0])
        self.assertNotIn('left', self.manager.snapshot()['gestures'])
        self.assertEqual(tuning_recipe('roll_left')['kind'], 'movement')
        self.assertEqual(tuning_recipe('start')['kind'], 'pose')

    def test_wizard_requires_stable_hand_and_guided_test_before_save(self):
        state = self.command('choose_problem', problem='difficult')
        self.assertEqual(state['wizard_step'], 'gesture')
        self.command('select', gesture='index')
        with self.assertRaisesRegex(ValueError, 'moment'):
            self.command('wizard_record')
        self.now += 1.1
        self.manager.observe(HandObservation(2, True, .99, .5,.5,.2,0,index_curl=.1),
                             self.calibration, GestureConfig(), True)
        self.command('wizard_record')
        self.assertTrue(self.manager.snapshot()['recording'])
        self.manager.recording = None
        self.manager.preview = {'index': {'on': .4, 'off': .2}}
        self.manager.wizard_step = 'test'
        with self.assertRaisesRegex(ValueError, 'try-it'):
            self.command('wizard_save')
        self.command('start_test')
        timestamp = 10
        for seconds, curl in ((.5, .1), (.5, .1), (.5, .1), (.5, .1), (.5, .1), (.5, .1),
                              (.1, .8), (.1, .1),
                              (.1, .8), (.1, .1)):
            self.now += seconds
            timestamp += 1
            config = self.manager.configuration(GestureConfig())
            self.manager.observe(
                HandObservation(timestamp, True, .99, .5,.5,.2,0,index_curl=curl),
                self.calibration, config, True,
            )
        self.assertTrue(self.manager.snapshot()['test']['passed'])
        self.command('wizard_save')
        self.assertEqual(self.manager.saved['index'], {'on': .4, 'off': .2})
        self.assertEqual(self.manager.snapshot()['wizard_step'], 'done')

    def test_off_center_routes_to_explicit_center_without_recording(self):
        state = self.command('choose_problem', problem='off_center')
        self.assertEqual(state['wizard_step'], 'center')
        self.assertEqual(state['completed_phases'], 0)

    def test_depth_guided_test_uses_motion_confirmed_recognition(self):
        self.command('choose_problem', problem='difficult')
        self.command('select', gesture='push')
        self.manager.preview = {'push': {'on': .2, 'off': .1}}
        self.manager.wizard_step = 'test'
        self.command('start_test')
        timestamp = 20
        # A stationary hand beyond the numerical boundary never counts.
        for _ in range(8):
            self.now += .5
            timestamp += 1
            self.manager.observe(
                HandObservation(timestamp, True, .99, .5, .5, .3, 0),
                self.calibration, self.manager.configuration(GestureConfig()), True,
                recognized=[],
            )
        self.assertEqual(self.manager.snapshot()['test']['cycles'], 0)
        # Only the engine's confirmed recognition state supplies activations.
        for active in (True, False, True, False):
            self.now += .1
            timestamp += 1
            self.manager.observe(
                HandObservation(timestamp, True, .99, .5, .5, .3, 0),
                self.calibration, self.manager.configuration(GestureConfig()), True,
                recognized=['push'] if active else [],
            )
        self.assertEqual(self.manager.snapshot()['test']['cycles'], 2)

    def test_idle_manager_skips_live_measurement_work_and_reuses_configuration(self):
        manager = TuningManager(self.path, lambda: self.now)
        config = GestureConfig(joystick_deadzone=.60)
        self.assertIs(manager.configuration(config), config)
        self.assertIs(manager.configuration(config), config)
        manager.observe(
            HandObservation(1, True, .99, .7, .2, .3, 1.0, index_curl=.8),
            self.calibration, config, True,
        )
        self.assertEqual(manager.latest, {})
        self.assertFalse(manager.ready)

    def test_noisy_overlapping_incomplete_or_inconsistent_samples_rejected(self):
        with self.assertRaises(ValueError): suggest('index', self.phases()[:2])
        for phase in (0, 1, 2):
            data = self.phases()
            for sample in data[phase]: sample['index'] = .78 if phase % 2 == 0 else .12
            with self.subTest(phase=phase), self.assertRaises(ValueError): suggest('index', data)

    def test_compound_suggestions_adjust_closed_components(self):
        phases = self.phases()
        for sample in phases[1]: sample['index'] = sample['middle'] = .1
        self.assertEqual(set(suggest('start', phases)), {'ring','pinky'})
        guard = self.phases()
        for sample in guard[1]:
            sample['index'] = sample['middle'] = sample['pinky'] = .1
        self.assertEqual(set(suggest('menu_guard', guard)), {'thumb','ring'})

    def test_preview_expiry_and_session_ownership(self):
        self.command('preview', thresholds={'index': {'on':.3, 'off':.2}})
        self.assertEqual(self.manager.configuration(GestureConfig()).pair('index'), (.3,.2))
        with self.assertRaises(ValueError):
            self.manager.command({'action':'begin','session':'another-session'})
        self.now += 7
        self.assertFalse(self.manager.active())
        self.assertEqual(self.manager.configuration(GestureConfig()).pair('index'), (.5,.35))
        self.assertFalse(self.path.exists())

    def test_save_global_independence_restart_and_reset(self):
        self.command('save', thresholds={'index': {'on':.3, 'off':.2}})
        reloaded = TuningManager(self.path)
        for profile in SUPPORTED_PROFILES:
            cfg = reloaded.configuration(GestureConfig())
            engine = GestureEngine(profile, cfg, calibration=self.calibration)
            hand = HandObservation(1, True, .99, .5,.5,.2,0,index_curl=.4,thumb_curl=.37)
            engine.update(hand)
            self.assertTrue(engine.curl_feedback(hand)['index'])
            self.assertFalse(engine.curl_feedback(hand)['thumb'])
        self.command('reset')
        self.assertFalse(TuningManager(self.path).saved)

    def test_invalid_and_failed_saves_leave_previous_settings(self):
        self.command('save', thresholds={'index':{'on':.3,'off':.2}})
        original = self.path.read_text()
        for pair in ({'on':.2,'off':.3}, {'on':float('nan'),'off':.1}, {'on':True,'off':0}, {'on':1.1,'off':.2}):
            with self.assertRaises(ValueError): validate_overrides({'index':pair})
        with patch('powerglove_vision.game_registry.atomic_write', side_effect=OSError):
            with self.assertRaises(OSError): self.command('save', thresholds={'index':{'on':.8,'off':.6}})
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(self.manager.saved['index']['on'], .3)

    def test_reach_save_changes_only_reach_and_restores_after_restart(self):
        from dataclasses import asdict
        from powerglove_vision.gesture import load_calibration, save_calibration
        reference = Calibration(.5, .5, .2, .3, .01, .02, .3, .25, .4, .35)
        save_calibration(self.path.with_name('calibration.json'), reference)
        self.manager.calibration = reference
        self.command('save', thresholds={'index': {'on': .3, 'off': .2}})
        before = self.manager.players.data.copy()
        values = {'left': .28, 'right': .22, 'up': .38, 'down': .32}
        state = self.command('reach_save', reach=values)
        self.assertTrue(state['reach']['pending'])
        self.assertEqual(state['reach']['values'], values)
        self.assertEqual(self.manager.players.active['thresholds'], before['players']['default']['thresholds'])
        restarted = TuningManager(self.path)
        applied = restarted.apply_calibration_restore()
        expected = Calibration(.5, .5, .2, .3, .01, .02, .28, .22, .38, .32)
        self.assertEqual(applied, expected)
        self.assertEqual(load_calibration(self.path.with_name('calibration.json')), expected)
        original = asdict(reference)
        actual = asdict(applied)
        for name in set(original) - {'reach_left', 'reach_right', 'reach_up', 'reach_down'}:
            self.assertEqual(actual[name], original[name])

    def test_reach_reset_preserves_calibration_and_rejects_bad_values(self):
        from powerglove_vision.gesture import save_calibration
        reference = Calibration(.5, .5, .2, .3, .01, .02, .3, .25, .4, .35)
        save_calibration(self.path.with_name('calibration.json'), reference)
        self.manager.calibration = reference
        original = self.path.read_bytes() if self.path.exists() else None
        invalid = (
            {'left': .2},
            {'left': 0, 'right': .2, 'up': .2, 'down': .2},
            {'left': True, 'right': .2, 'up': .2, 'down': .2},
            {'left': float('nan'), 'right': .2, 'up': .2, 'down': .2},
            {'left': .49, 'right': .2, 'up': .2, 'down': .2},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.command('reach_save', reach=values)
            self.assertEqual(self.path.read_bytes() if self.path.exists() else None, original)
        state = self.command('reach_reset')
        self.assertTrue(state['reach']['pending'])
        self.assertEqual(set(state['reach']['values'].values()), {0.0})
        applied = self.manager.apply_calibration_restore()
        self.assertEqual(
            (applied.reach_left, applied.reach_right, applied.reach_up, applied.reach_down),
            (0, 0, 0, 0),
        )

    def test_failed_or_concurrent_reach_save_is_non_mutating(self):
        from powerglove_vision.gesture import save_calibration
        reference = Calibration(.5, .5, .2, 0)
        save_calibration(self.path.with_name('calibration.json'), reference)
        self.manager.calibration = reference
        values = {'left': .2, 'right': .2, 'up': .2, 'down': .2}
        with patch('powerglove_vision.game_registry.atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.command('reach_save', reach=values)
        self.assertIsNone(self.manager.players.data['calibration_restore'])
        self.command('reach_save', reach=values)
        with self.assertRaisesRegex(ValueError, 'finish saving'):
            self.command('reach_save', reach=values)
        with self.assertRaises(ValueError):
            self.manager.command({'action': 'reach_reset', 'session': 'another-session'})

    def test_reach_is_isolated_per_player_and_included_in_backup(self):
        from powerglove_vision.gesture import save_calibration
        first = Calibration(.5, .5, .2, 0, reach_left=.2, reach_right=.2,
                            reach_up=.2, reach_down=.2)
        save_calibration(self.path.with_name('calibration.json'), first)
        self.manager.calibration = first
        self.manager.finish_center(first)
        self.command('end')
        second_id = self.manager.player_command({
            'action': 'create', 'name': 'Second',
            'player': 'default', 'generation': self.manager.players.data['generation'],
        })['active']
        second = Calibration(.4, .6, .2, 0, reach_left=.15, reach_right=.25,
                             reach_up=.3, reach_down=.2)
        self.manager.begin_center()
        self.manager.finish_center(second)
        self.manager.calibration = second
        self.command('begin')
        changed = {'left': .14, 'right': .24, 'up': .29, 'down': .19}
        self.command('reach_save', reach=changed)
        self.manager.apply_calibration_restore()
        backup = self.manager.player_command({
            'action': 'export', 'player': second_id,
            'generation': self.manager.players.data['generation'],
        })['backup']
        self.assertEqual(
            {name: backup['calibration']['neutral']['reach_' + name]
             for name in REACH_DIRECTIONS},
            changed,
        )
        self.assertEqual(
            self.manager.players.data['players']['default']['calibration']['neutral']['reach_left'],
            first.reach_left,
        )

    def test_fresh_high_confidence_frames_only_and_calibration_invalidation(self):
        self.command('record')
        def observe(t, confidence=.9):
            hand = HandObservation(t,True,confidence,.5,.5,.2,0,index_curl=.1)
            self.manager.observe(hand,self.calibration,GestureConfig(),True)
        for i in range(15): observe(1)
        self.assertEqual(self.manager.snapshot()['samples'],1)
        observe(2,.1)
        self.assertEqual(self.manager.snapshot()['samples'],1)
        for i in range(15): observe(3+i)
        self.now += 3.1
        observe(19)
        self.assertEqual(self.manager.snapshot()['completed_phases'],1)
        self.manager.invalidate()
        self.assertEqual(self.manager.snapshot()['completed_phases'],0)

    def test_tuning_keeps_practice_active_despite_dashboard_reset(self):
        shared = SharedDebugState()
        shared.tuning = self.manager
        self.assertTrue(shared.take_practice_request())
        shared.request_profile('program_g', 'RetroPie launch hook', 'Gun.Smoke')
        shared.request_practice('',False,reset=True)
        self.assertTrue(shared.practice_active)
        self.assertEqual(shared.take_profile_request()[0], 'program_g')
        self.command('end')
        self.assertFalse(shared.take_practice_request())

    def test_camera_loss_finishes_recording_with_useful_error(self):
        self.command('record')
        self.now += 3.1
        state = self.manager.snapshot()
        self.assertFalse(state['recording'])
        self.assertIn('Not enough', state['error'])
        self.assertEqual(state['completed_phases'], 0)

    def test_hand_setup_then_individual_tuning_preserves_extended_thresholds(self):
        self.command('select', gesture='hand_setup')
        self.manager.phases = self.phases()
        state = self.command('suggest')
        self.assertEqual(state['mode'], 'hand_setup')
        self.assertEqual(len(state['preview']), 5)
        self.command('save', thresholds=state['preview'])
        original = dict(self.manager.saved)
        self.command('select', gesture='start')
        phases = self.phases()
        for sample in phases[1]:
            sample['index'] = sample['middle'] = .1
            sample['ring'] = sample['pinky'] = .65
        self.manager.phases = phases
        state = self.command('suggest')
        self.assertEqual(set(state['preview']), {'ring', 'pinky'})
        self.command('save', thresholds=state['preview'])
        self.assertEqual(self.manager.saved['index'], original['index'])
        self.assertEqual(self.manager.saved['middle'], original['middle'])
        self.command('select', gesture='hand_setup')
        self.command('reset')
        self.assertEqual(self.manager.saved, {})

    def test_recording_three_phases_and_failed_analysis_clears_preview(self):
        self.command('select', gesture='hand_setup')
        for phase in range(3):
            self.command('record')
            for frame in range(15):
                value = .7 if phase == 1 else .1
                hand = HandObservation(100+phase*20+frame, True, .99, .5,.5,.2,0,
                                       **{k+'_curl': value for k in ('thumb','index','middle','ring','pinky')})
                self.manager.observe(hand, self.calibration, GestureConfig(), True)
            self.now += 3.1
            self.command('heartbeat')
            self.manager.observe(hand, self.calibration, GestureConfig(), True)
        self.assertEqual(self.manager.snapshot()['completed_phases'], 3)
        with self.assertRaises(ValueError): self.command('record')
        self.assertEqual(len(self.command('suggest')['preview']), 5)
        for sample in self.manager.phases[2]: sample['thumb'] = .69
        with self.assertRaisesRegex(ValueError, 'thumb'): self.command('suggest')
        self.assertIsNone(self.manager.preview)
        self.assertFalse(self.path.exists())

    def test_short_recording_and_stale_tracking_rejected(self):
        phases = self.phases()
        phases[1] = phases[1][:11]
        with self.assertRaises(ValueError): suggest('hand_setup', phases)
        self.now += 2.1
        with self.assertRaisesRegex(ValueError, 'tracking'): self.command('record')
        self.assertEqual(self.manager.snapshot()['finger_feedback'], {})

    def test_menu_feedback_matches_recognition_with_default_and_personal_values(self):
        personal = suggest('hand_setup', self.phases())
        for cfg in (GestureConfig(), GestureConfig(thresholds=personal)):
            for gesture, requirements in MENU_FINGERS.items():
                for failure in (None, *requirements):
                    values = {finger: .8 if closed else .1 for finger, closed in requirements.items()}
                    if failure:
                        values[failure] = .1 if requirements[failure] else .8
                    hand = HandObservation(1, True, .99, .5,.5,.2,0,
                                           **{k+'_curl': v for k,v in values.items()})
                    engine = GestureEngine('bad_street_brawler', cfg, calibration=self.calibration)
                    engine.update(hand)
                    feedback = finger_pose_feedback(cfg, gesture, requirements, hand.fingers)
                    self.assertEqual(all(f['matches'] for f in feedback.values()), failure is None)
                    held = engine._start_gesture if gesture == 'start' else engine._select_gesture
                    self.assertEqual(held.started_at is not None, failure is None)
                    self.command('select', gesture=gesture)
                    self.manager.phases = self.phases()[:1]
                    self.manager.observe(hand, self.calibration, cfg, True)
                    self.assertEqual(self.manager.snapshot()['finger_feedback'], feedback)

    def test_hand_setup_recognizes_personal_extension_above_default_cutoff(self):
        phases = self.phases()
        for i, phase in enumerate(phases):
            for sample in phase:
                for finger in ('thumb', 'index', 'middle', 'ring', 'pinky'):
                    sample[finger] = .65 if i == 1 else .38
        cfg = GestureConfig(thresholds=suggest('hand_setup', phases))
        for gesture, requirements in MENU_FINGERS.items():
            values = {finger: .65 if closed else .38 for finger, closed in requirements.items()}
            hand = HandObservation(1, True, .99, .5,.5,.2,0,
                                   **{k+'_curl': v for k,v in values.items()})
            self.assertFalse(all(x['matches'] for x in finger_pose_feedback(
                GestureConfig(), gesture, requirements, hand.fingers).values()))
            engine = GestureEngine('bad_street_brawler', cfg, calibration=self.calibration)
            first = engine.update(hand)
            self.assertFalse(first.buttons[gesture])
            hand.timestamp = 1.8
            held = engine.update(hand)
            self.assertTrue(held.buttons[gesture])


    def test_each_extended_finger_is_required_in_every_recording(self):
        for gesture, extended in (("start", ("index", "middle")), ("select", ("thumb",))):
            for finger in extended:
                for phase_index in range(3):
                    phases = self.phases()
                    for sample in phases[1]:
                        for name in extended: sample[name] = .1
                    for sample in phases[phase_index]: sample[finger] = .6
                    with self.subTest(gesture=gesture, finger=finger, phase=phase_index):
                        with self.assertRaisesRegex(ValueError, finger + " extended"):
                            suggest(gesture, phases)

    def test_personal_extension_and_strict_boundary_are_used_by_analysis(self):
        for gesture, extended in (("start", ("index", "middle")), ("select", ("thumb",))):
            phases = self.phases()
            for phase in phases:
                for sample in phase:
                    for finger in extended: sample[finger] = .38
            personal = {finger: {"on": .6, "off": .4} for finger in extended}
            with self.assertRaisesRegex(ValueError, "extended"): suggest(gesture, phases)
            result = suggest(gesture, phases, GestureConfig(thresholds=personal))
            self.assertTrue(set(result).isdisjoint(extended))
            for sample in phases[1]: sample[extended[0]] = .4
            with self.assertRaisesRegex(ValueError, "extended"):
                suggest(gesture, phases, GestureConfig(thresholds=personal))

    def test_simultaneous_pose_and_noise_tolerance(self):
        phases = self.phases()
        for sample in phases[1]: sample['index'] = sample['middle'] = .1
        phases[1][0]['index'] = phases[1][1]['index'] = .7
        suggest('start', phases)  # Eighteen out of twenty complete poses.
        phases[1][2]['middle'] = phases[1][3]['middle'] = .7
        with self.assertRaisesRegex(ValueError, 'together'): suggest('start', phases)

    def test_failed_extended_check_clears_preview_without_changing_saved_values(self):
        self.command('save', thresholds={'index': {'on': .6, 'off': .4}})
        original = self.path.read_text()
        self.command('select', gesture='start')
        phases = self.phases()
        for phase in phases:
            for sample in phase: sample['index'] = sample['middle'] = .1
        for sample in phases[1]: sample['ring'] = sample['pinky'] = .8
        self.manager.phases = phases
        self.command('suggest')
        for sample in phases[1]: sample['index'] = .5
        with self.assertRaisesRegex(ValueError, 'index extended'): self.command('suggest')
        self.assertIsNone(self.manager.preview)
        self.assertEqual(self.path.read_text(), original)

    def test_missing_or_nonfinite_required_finger_samples_are_rejected(self):
        for value in (None, float('nan'), float('inf'), True):
            phases = self.phases()
            for sample in phases[1]: sample['index'] = sample['middle'] = .1
            phases[1][0]['index'] = value
            with self.assertRaisesRegex(ValueError, 'invalid'): suggest('start', phases)
