# Project: VirtualGlove
# File: tests/test_joystick_deadzone.py
# Purpose: Verify per-player digital direction threshold persistence.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-12 - Verified the 60% default without overwriting saved choices.
#   2026-09-06 - Added per-player joystick dead-zone regression coverage.
# Full history: docs/CHANGELOG.md and Git history.
"""Verify player-isolated dead-zone persistence without resetting hand setup."""
import copy
import tempfile
import unittest
from pathlib import Path
from powerglove_vision.tuning import TuningManager
from powerglove_vision.gesture import GestureConfig

class JoystickTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'gesture-tuning.json'
        self.manager = TuningManager(self.path)

    def command(self, action, **extra):
        s = self.manager.player_snapshot()
        return self.manager.player_command(dict(action=action, player=s['active'], generation=s['generation'], **extra))

    def test_save_persists_and_preserves_other_player_fields(self):
        before = copy.deepcopy(self.manager.players.active)
        old = self.manager.configuration(GestureConfig())
        state = self.command('joystick_deadzone', value=.5)
        after = self.manager.players.active
        for key in before:
            if key != 'joystick_deadzone':
                self.assertEqual(before[key], after[key])
        self.assertEqual(old.pair('left'), (.28, .14))
        self.assertEqual(self.manager.configuration(GestureConfig()).chosen_joystick_deadzone(), .5)
        self.assertEqual(TuningManager(self.path).player_snapshot()['joystick'], state['joystick'])
        self.assertEqual(self.command('export')['backup']['joystick_deadzone'], .5)
        self.assertNotIn('down', self.command('export')['backup']['thresholds'])

    def test_new_players_use_standard_size_without_changing_existing_players(self):
        first = self.manager.player_snapshot()['active']
        self.assertEqual(self.manager.players.active['joystick_deadzone'], .60)
        self.command('joystick_deadzone', value=.42)
        self.command('create', name='Second')
        self.assertEqual(self.manager.players.active['joystick_deadzone'], .60)
        self.command('select', id=first)
        self.assertEqual(self.manager.players.active['joystick_deadzone'], .42)

    def test_minimum_and_existing_numeric_values_survive_reload(self):
        for value in [.10,.13,.14,.28,.42,.60,1.0]:
            with self.subTest(value=value):
                self.command('joystick_deadzone', value=value)
                before=copy.deepcopy(self.manager.players.data)
                disk=self.path.read_bytes()
                restored=TuningManager(self.path)
                self.assertEqual(restored.players.data,before)
                self.assertEqual(restored.player_snapshot()['joystick'],dict(
                    deadzone=value,effective_deadzone=value,jitter_protected=False,
                    hand_size_protected=False,hand_size_minimum=None))
                self.assertEqual(self.path.read_bytes(),disk)

    def test_invalid_and_stale_requests_do_not_write(self):
        original = self.manager.player_snapshot()
        for value in [True, None, '0.4', .099, 1.01, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                self.command('joystick_deadzone', value=value)
        self.assertFalse(self.path.exists())
        self.command('joystick_deadzone', value=.4)
        with self.assertRaises(ValueError):
            self.manager.player_command(dict(action='joystick_deadzone', player=original['active'], generation=original['generation'], value=.8))
        self.assertEqual(self.manager.players.active['joystick_deadzone'], .4)

    def test_player_isolation_and_tuning_exclusion(self):
        first = self.manager.player_snapshot()['active']
        self.command('joystick_deadzone', value=.4)
        self.command('create', name='Second')
        self.command('joystick_deadzone', value=.6)
        self.command('select', id=first)
        self.assertEqual(self.manager.players.active['joystick_deadzone'], .4)
        self.manager.session = 'active-test'
        self.manager.expires = self.manager.clock() + 30
        with self.assertRaises(ValueError):
            self.command('joystick_deadzone', value=.7)

    def test_snapshot_reports_hand_floor_without_changing_saved_number(self):
        from powerglove_vision.model import Calibration
        reference=Calibration(.5, .5, .5, 0, noise_x=.61, noise_y=.02)
        self.manager.players.active['calibration']={'version':2,'neutral':vars(reference)}
        state = self.manager.player_snapshot()['joystick']
        self.assertEqual(state['deadzone'], .60)
        self.assertEqual(state['effective_deadzone'], .75)
        self.assertFalse(state['jitter_protected'])
        self.assertTrue(state['hand_size_protected'])
        self.assertEqual(state['hand_size_minimum'], .75)

if __name__ == '__main__':
    unittest.main()
