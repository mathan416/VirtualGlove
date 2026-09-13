# Project: VirtualGlove
# File: tests/test_players.py
# Purpose: Verify player migration, persistent progress, bounded backups, and atomic changes.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Cover player isolation, stale writes, calibration gates, and recovery.

"""Exercise persisted user data rather than matching implementation strings."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from powerglove_vision.tuning import TuningManager


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "gesture-tuning.json"
        self.path.write_text(json.dumps({"version": 1, "thresholds": {"index": {"on": .6, "off": .4}}}))
        self.manager = TuningManager(self.path)

    def command(self, action, **extra):
        state = self.manager.player_snapshot()
        return self.manager.player_command(dict(action=action, player=state["active"], generation=state["generation"], **extra))

    def test_legacy_settings_migrate_only_after_a_successful_write(self):
        self.assertEqual(json.loads(self.path.read_text())["version"], 1)
        self.assertEqual(self.manager.saved["index"]["on"], .6)
        self.command("rename", name="Alex")
        restored = TuningManager(self.path)
        self.assertEqual(restored.player_snapshot()["players"][0]["name"], "Alex")
        self.assertEqual(restored.saved, self.manager.saved)
        self.assertEqual(json.loads(self.path.read_text())["version"], 6)

    def test_version_two_player_data_migrates_with_progress_and_backup(self):
        saved={'version':2,'active':'default','generation':4,'players':{'default':{
            'name':'Iain','thresholds':{},'progress':{'course':1,'completed':[0,1],'lesson':2},'needs_center':False}}}
        self.path.write_text(json.dumps(saved))
        self.manager=TuningManager(self.path)
        self.command('rename',name='Iain B')
        self.assertEqual(self.manager.player_snapshot()['progress']['completed'],[0,1])
        self.assertEqual(json.loads(self.path.with_name('gesture-tuning-v2-backup.json').read_text()),saved)
        self.assertEqual(json.loads(self.path.read_text())['version'],6)

    def test_players_isolate_tuning_and_progress(self):
        self.command("progress", progress={"course":1,"completed":[0,1],"lesson":2})
        new = self.command("create", name="Sam")
        self.assertEqual(new["progress"]["completed"], [])
        self.assertTrue(self.manager.needs_center())
        self.manager.players.save_thresholds({"thumb":{"on":.7,"off":.3}})
        self.command("select", id="default")
        self.assertEqual(self.manager.saved, {"index":{"on":.6,"off":.4}})
        self.assertEqual(self.manager.player_snapshot()["progress"]["completed"], [0,1])

    def test_progress_survives_restart_and_stale_tabs_cannot_undo_reset(self):
        state=self.command("progress", progress={"course":1,"completed":list(range(16)),"lesson":15})
        self.assertEqual(len(TuningManager(self.path).player_snapshot()["progress"]["completed"]),16)
        self.command("reset_progress")
        with self.assertRaises(ValueError):
            self.manager.player_command({"action":"progress","player":state["active"],"generation":state["generation"],"progress":state["progress"]})
        self.assertEqual(self.manager.player_snapshot()["progress"]["completed"],[])

    def test_export_is_allowlisted_and_restore_requires_fresh_center(self):
        backup=self.command("export")["backup"]
        self.assertEqual(set(backup),{"format","version","name","thresholds","joystick_deadzone","calibration","effective_thresholds","source"})
        backup["thresholds"]={"thumb":{"on":.7,"off":.4}}
        self.command("restore",backup=backup)
        self.assertTrue(self.manager.needs_center())
        self.assertEqual(TuningManager(self.path).saved,backup["thresholds"])
        self.manager.begin_center()
        self.manager.finish_center()
        self.assertFalse(TuningManager(self.path).needs_center())

    def test_complete_backup_roundtrip_reuses_confirmed_calibration(self):
        from powerglove_vision.gesture import save_calibration, load_calibration
        from powerglove_vision.model import Calibration
        reference=Calibration(.4,.6,.2,.3,.01,.02)
        path=self.path.with_name('calibration.json')
        save_calibration(path,reference)
        backup=self.command('export')['backup']
        self.assertEqual(backup['format'],'virtualglove-hand-setup')
        self.assertEqual(backup['version'],4)
        self.assertEqual(backup['calibration']['neutral']['palm_x'],.4)
        backup['name']='Iain'
        self.command('restore',backup=backup,reuse_calibration=True)
        self.assertTrue(self.manager.needs_center())
        with self.assertRaises(ValueError):self.command('export')
        restarted=TuningManager(self.path)
        self.assertEqual(restarted.apply_calibration_restore(),reference)
        self.assertFalse(restarted.needs_center())
        self.assertEqual(load_calibration(path),reference)
        self.assertEqual(restarted.player_snapshot()['players'][0]['name'],'Iain')
        self.assertIsNone(restarted.apply_calibration_restore())

    def test_pending_restore_survives_write_failure_and_is_cancelled_by_switch(self):
        backup=self.command('export')['backup']
        backup['calibration']={'version':2,'neutral':dict(palm_x=.5,palm_y=.5,palm_scale=.2,roll=0)}
        self.command('restore',backup=backup,reuse_calibration=True)
        with patch('powerglove_vision.tuning.save_calibration',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.manager.apply_calibration_restore()
        self.assertTrue(TuningManager(self.path).player_snapshot()['restoring_calibration'])
        with patch('powerglove_vision.game_registry.atomic_write',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.manager.apply_calibration_restore()
        self.assertTrue(self.manager.needs_center())
        self.command('create',name='Other')
        self.assertIsNone(self.manager.apply_calibration_restore())
        self.assertTrue(self.manager.needs_center())

    def test_version_one_portable_backups_are_rejected_without_mutation(self):
        old={'format':'powerglove-hand-settings','version':1,'name':'Old','thresholds':{'index':{'on':.8,'off':.4}}}
        before=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'Version-1'):
            self.command('restore',backup=old)
        self.assertEqual(self.path.read_bytes(),before)

    def test_original_version_two_backups_remain_supported(self):
        backup=self.command('export')['backup']
        backup['format']='powerglove-hand-setup'
        backup['version']=2
        del backup['joystick_deadzone'];del backup['effective_thresholds'];del backup['source']
        self.command('restore',backup=backup)
        self.assertTrue(self.manager.needs_center())

    def test_version_four_store_migrates_largest_activation_and_discards_releases(self):
        saved={'version':4,'active':'default','generation':1,'calibration_restore':None,
               'players':{'default':{'name':'Iain','thresholds':{
                   'left':{'on':.31,'off':.12},'right':{'on':.47,'off':.15},
                   'up':{'on':.35,'off':.2},'down':{'on':.4,'off':.1},
                   'index':{'on':.6,'off':.3}},
                   'progress':{'course':1,'completed':[],'lesson':0},
                   'needs_center':False,'calibration':None}}}
        self.path.write_text(json.dumps(saved))
        manager=TuningManager(self.path)
        self.assertEqual(manager.players.active['joystick_deadzone'],.47)
        self.assertEqual(manager.saved,{'index':{'on':.6,'off':.3}})
        state=manager.player_snapshot()
        manager.player_command({'action':'rename','player':state['active'],
                                'generation':state['generation'],'name':'Iain B'})
        self.assertEqual(json.loads(self.path.read_text())['version'],6)
        self.assertEqual(json.loads(self.path.with_name('gesture-tuning-v4-backup.json').read_text()),saved)

    def test_version_two_backup_migrates_largest_activation(self):
        backup=self.command('export')['backup']
        backup['format']='powerglove-hand-setup'
        backup['version']=2
        del backup['joystick_deadzone'];del backup['effective_thresholds'];del backup['source']
        backup['thresholds'].update({
            'left':{'on':.34,'off':.1},'right':{'on':.52,'off':.2},
            'up':{'on':.41,'off':.2},'down':{'on':.38,'off':.1}})
        self.command('restore',backup=backup)
        self.assertEqual(self.manager.players.active['joystick_deadzone'],.52)
        self.assertNotIn('left',self.manager.saved)

    def test_player_selection_automatically_restores_its_isolated_center(self):
        from powerglove_vision.model import Calibration
        first=Calibration(.3,.4,.2,0)
        second=Calibration(.6,.5,.3,0)
        self.manager.begin_center();self.manager.finish_center(first)
        self.command('create',name='Sam')
        self.assertFalse(self.manager.player_snapshot()['has_saved_calibration'])
        self.manager.begin_center();self.manager.finish_center(second)
        self.command('select',id='default')
        self.assertTrue(self.manager.needs_center())
        self.assertTrue(self.manager.player_snapshot()["restoring_calibration"])
        with self.assertRaises(ValueError):self.command("export")
        restarted=TuningManager(self.path)
        self.assertEqual(restarted.apply_calibration_restore(),first)
        self.assertFalse(restarted.needs_center())

    def test_latest_player_selection_replaces_pending_center(self):
        from powerglove_vision.model import Calibration
        first=Calibration(.3,.4,.2,0)
        second=Calibration(.6,.5,.3,0)
        self.manager.begin_center();self.manager.finish_center(first)
        other=self.command('create',name='Sam')['active']
        self.manager.begin_center();self.manager.finish_center(second)
        self.command('select',id='default')
        self.command('select',id=other)
        self.assertEqual(self.manager.apply_calibration_restore(),second)
        self.assertFalse(self.manager.needs_center())

    def test_effective_thresholds_are_complete_and_import_is_explicit(self):
        from powerglove_vision.tuning import CHANNELS
        backup=self.command('export')['backup']
        self.assertEqual(set(backup['effective_thresholds']),set(CHANNELS))
        self.assertEqual(set(backup['source']),{'version','commit'})
        self.command('restore',backup=backup)
        self.assertEqual(self.manager.saved,backup['thresholds'])
        self.command('restore',backup=backup,use_effective_thresholds=True)
        self.assertEqual(self.manager.saved,backup['effective_thresholds'])
        # Explicit saved values survive different future default thresholds.
        from powerglove_vision.gesture import GestureConfig
        effective=self.manager.configuration(GestureConfig())
        self.assertEqual(effective.pair('index'),tuple(backup['effective_thresholds']['index'][k] for k in ('on','off')))

    def test_invalid_calibration_never_changes_settings(self):
        import copy
        backup=self.command('export')['backup']
        reference={'version':2,'neutral':dict(palm_x=.5,palm_y=.5,palm_scale=.2,roll=0)}
        original=self.path.read_bytes()
        for field,value in [('palm_x',float('nan')),('palm_scale',0),('roll',99),('noise_x',True),('token','secret')]:
            invalid=copy.deepcopy(reference);invalid['neutral'][field]=value
            with self.assertRaises(ValueError):self.command('restore',backup=dict(backup,calibration=invalid),reuse_calibration=True)
            self.assertEqual(self.path.read_bytes(),original)

    def test_calibration_for_a_previous_player_does_not_unlock_new_player(self):
        self.command("create",name="Alex")
        self.manager.begin_center()
        self.command("select",id="default")
        self.manager.finish_center()
        self.assertTrue(self.manager.needs_center())

    def test_bad_imports_and_failed_writes_leave_file_and_memory_unchanged(self):
        original=self.path.read_bytes()
        backup=self.command("export")["backup"]
        for bad in (dict(backup,token="private"),dict(backup,calibration={}),dict(backup,thresholds={"index":{"on":float('nan'),"off":.1}}),{}):
            with self.assertRaises(ValueError):self.command("restore",backup=bad)
        with patch('powerglove_vision.game_registry.atomic_write',side_effect=OSError):
            with self.assertRaises(OSError):self.command("create",name="Unwritten")
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(len(self.manager.player_snapshot()["players"]),1)

    def test_tuning_lease_blocks_switching_and_restoration(self):
        self.manager.command({"action":"begin","session":"test-session"})
        with self.assertRaises(ValueError):self.command("create",name="Alex")
        self.assertEqual(self.command("read")["active"],"default")

    def test_player_limit_and_invalid_progress(self):
        for n in range(11):self.command("create",name="Player "+str(n))
        with self.assertRaises(ValueError):self.command("create",name="Overflow")
        for value in ({"course":1,"completed":[16],"lesson":0},{"course":True,"completed":[],"lesson":0},{"course":1,"completed":[True],"lesson":0}):
            with self.assertRaises(ValueError):self.command("progress",progress=value)

    def test_corruption_is_not_silently_overwritten_by_progress(self):
        self.path.write_text('{broken')
        self.manager=TuningManager(self.path)
        self.assertIsNotNone(self.manager.player_snapshot()["error"])
        with self.assertRaises(ValueError):self.command("progress",progress={"course":1,"completed":[],"lesson":0})
        self.assertEqual(self.path.read_text(),'{broken')


if __name__ == '__main__':
    unittest.main()
