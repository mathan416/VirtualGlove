# Project: VirtualGlove
# File: tests/test_reach.py
# Purpose: Verify comfortable reach, legacy compatibility, and safe guided calibration.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Cover reach on synchronous and independent native movement paths.
# Full history: docs/CHANGELOG.md and Git history.

"""Reach maps per-player endpoints without changing gestures or accepting bad holds."""

import copy
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from virtualglove.model import Calibration, HandObservation
from virtualglove.gesture import GestureEngine, GestureConfig, _field_axis, save_calibration, load_calibration
from virtualglove.players import calibration_value
from virtualglove.tuning import TuningManager

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('calibrate_reach', ROOT/'scripts/calibrate-reach.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class ReachTests(unittest.TestCase):
    def setUp(self):
        self.reference = Calibration(.5, .5, .2, 0, reach_left=.2, reach_right=.3, reach_up=.15, reach_down=.25)

    def test_asymmetric_endpoints_midpoints_and_clamping(self):
        for position, expected in ((.5,0), (.3,-32767), (.8,32767), (.9,32767), (.65,16384), (.4,-16383)):
            self.assertAlmostEqual(_field_axis(position,.5,.08,.2,.3), expected, delta=1)
        self.assertEqual(_field_axis(.08,.5,.08),-32767)
        self.assertEqual(_field_axis(.92,.5,.08),32767)

    def test_old_calibration_loads_and_preserves_original_mapping(self):
        legacy = {k:v for k,v in asdict(self.reference).items() if not k.startswith('reach_')}
        for version in (1,2):
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'calibration.json'
                p.write_text(json.dumps({'version':version,'neutral':legacy}))
                restored=load_calibration(p)
                self.assertTrue(restored.valid_reach())
                self.assertEqual(restored.reach_left,0)
                self.assertEqual(calibration_value({'version':version,'neutral':legacy})['neutral']['reach_down'],0)

    def test_bad_spans_rejected_by_import_and_disk_load(self):
        for spans in [(0,.2,.2,.2),(.01,.2,.2,.2),(.6,.2,.2,.2),(-.2,.2,.2,.2),
                      (float('nan'),.2,.2,.2),(float('inf'),.2,.2,.2),(True,.2,.2,.2),('0.2',.2,.2,.2)]:
            bad=asdict(self.reference)
            bad.update(zip(('reach_left','reach_right','reach_up','reach_down'),spans))
            data={'version':2,'neutral':bad}
            with self.subTest(spans=spans):
                with self.assertRaises(ValueError): calibration_value(data)
                with tempfile.TemporaryDirectory() as d:
                    p=Path(d)/'calibration.json';p.write_text(json.dumps(data))
                    self.assertIsNone(load_calibration(p))

    def test_player_round_trip_and_restart_preserve_reach(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'gesture-tuning.json';manager=TuningManager(p)
            manager.finish_center(self.reference);state=manager.player_snapshot()
            backup=manager.player_command(dict(action='export',player=state['active'],generation=state['generation']))['backup']
            self.assertEqual(backup['calibration']['neutral'],asdict(self.reference))
            manager.player_command(dict(action='restore',player=state['active'],generation=state['generation'],backup=backup,reuse_calibration=True))
            self.assertEqual(manager.apply_calibration_restore(),self.reference)
            self.assertEqual(load_calibration(p.with_name('calibration.json')),self.reference)
            restarted=TuningManager(p)
            self.assertFalse(restarted.needs_center())
            self.assertEqual(restarted.players.active['calibration']['neutral'],asdict(self.reference))

    def test_synchronous_and_motion_paths_both_use_reach(self):
        cfg=GestureConfig(coordinate_smoothing_min=1,coordinate_smoothing_max=1)
        pose=HandObservation(10,True,.95,.8,.35,.2)
        direct=GestureEngine('super_glove_ball',config=cfg,calibration=self.reference)
        fast=GestureEngine('super_glove_ball',config=cfg,calibration=self.reference)
        normal=direct.update(pose);initial=fast.update_native_motion(pose,pose)
        self.assertEqual(normal.axes,initial.axes)
        self.assertEqual(initial.axes['x'],32767);self.assertEqual(initial.axes['y'],-32767)
        moved=fast.update_native_motion(replace(pose,timestamp=10.016,palm_x=.3,palm_y=.75))
        self.assertEqual(moved.axes['x'],-32767);self.assertEqual(moved.axes['y'],32767)

    def test_reach_does_not_change_dpad_buttons_or_depth(self):
        pose=HandObservation(10,True,.95,.65,.6,.25,index_curl=.9)
        legacy=GestureEngine('super_glove_ball',calibration=Calibration(.5,.5,.2,0)).update(pose)
        reach=GestureEngine('super_glove_ball',calibration=self.reference).update(pose)
        self.assertEqual(legacy.buttons,reach.buttons)
        self.assertEqual(legacy.dpad,reach.dpad)
        self.assertEqual(legacy.axes['z'],reach.axes['z'])
        self.assertNotEqual(legacy.axes['x'],reach.axes['x'])

    def test_recentering_preserves_separately_tuned_spans(self):
        engine=GestureEngine('super_glove_ball',calibration=self.reference,calibration_frames=3)
        engine.begin_calibration()
        for i in range(3): engine.update(HandObservation(10+i,True,.95,.5,.5,.2))
        self.assertTrue(engine.calibrated)
        for direction in helper.DIRECTIONS:
            self.assertEqual(
                getattr(engine.calibration,'reach_'+direction),
                getattr(self.reference,'reach_'+direction),
            )


class ReachHelperTests(unittest.TestCase):
    def test_raw_holds_measure_normalized_distance(self):
        for direction,position in [('left',.3),('right',.7),('up',.3),('down',.7)]:
            measured=helper.measure_span(direction,[position]*15,.5,16)
            self.assertAlmostEqual(measured['span'],.2)

    def test_rejects_unreliable_wrong_side_tiny_clipped_and_unstable_holds(self):
        for values,total in [([.3]*11,11),([.3]*15,30),([.7]*15,15),([.49]*15,15),
                             ([.01]*15,15),([.2,.4]*10,20),([float('nan')]*15,15)]:
            with self.subTest(values=values):
                with self.assertRaises(ValueError): helper.measure_span('left',values,.5,total)

    def test_session_rejects_player_changes_tuning_and_output(self):
        session={'player':{'active':'iain','generation':4}}
        worker=helper.ReachSession()
        good={'player':dict(session['player']),'controller_enabled':False}
        worker.check(session,good)
        for bad in [dict(good,player={'active':'other','generation':4}),
                    dict(good,player={'active':'iain','generation':5}),
                    dict(good,controller_enabled=True),dict(good,tuning={'active':True})]:
            with self.assertRaises(ValueError): worker.check(session,bad)

    def test_begin_backs_up_before_stopping_and_uses_practice_without_changing_profile(self):
        with tempfile.TemporaryDirectory() as d:
            worker=helper.ReachSession(Path(d))
            backup={'calibration':{'version':2,'neutral':asdict(Calibration(.5,.5,.2,0))}}
            player={'active':'iain','generation':4,'needs_center':False}
            worker.get=lambda: {'player':player}
            calls=[]
            def post(endpoint,data):
                calls.append((endpoint,data))
                if endpoint=='api/players': return {'backup':backup}
                self.assertTrue(worker.path.exists())
                session=json.loads(worker.path.read_text())
                self.assertEqual(json.loads(Path(session['backup_path']).read_text()),backup)
                self.assertEqual(Path(session['backup_path']).stat().st_mode & 0o777,0o600)
            worker.post=post
            worker.wait_practice=lambda session: calls.append(('practice',{}))
            worker.run('begin')
            self.assertEqual([c[0] for c in calls],['api/players','api/controller','practice'])
            self.assertEqual(calls[1][1],{'enabled':False})
            with self.assertRaises(ValueError): worker.run('begin')

    def test_guided_apply_and_cancel_use_real_player_restore(self):
        for ending in ('apply','cancel'):
            with self.subTest(ending=ending), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);data=root/'data';data.mkdir()
                original=Calibration(.5,.5,.2,0,reach_left=.12,reach_right=.13,reach_up=.14,reach_down=.15)
                save_calibration(data/'calibration.json',original)
                manager=TuningManager(data/'gesture-tuning.json');manager.finish_center(original)
                now=[10.0]
                state={'stopped':False,'practice':False,'position':{'x':.5,'y':.5},'centering':False}
                worker=helper.ReachSession(root,clock=lambda:now[0],sleep=lambda dt:now.__setitem__(0,now[0]+dt))
                def get():
                    if state['centering']:
                        manager.begin_center()
                        reference=Calibration(.5,.5,.2,0)
                        save_calibration(data/'calibration.json',reference);manager.finish_center(reference)
                        state['centering']=False
                    manager.apply_calibration_restore()
                    return dict(player=manager.player_snapshot(),controller_enabled=not state['stopped'],
                        practice_mode=state['practice'],vision_state='active',calibrated=True,calibrating=False,
                        detected=True,confidence=.95,sample_age_ms=100,
                        timestamp=now[0],capture_sequence=int(now[0]*10),palm_position=state['position'])
                def post(endpoint,payload):
                    if endpoint=='api/players': return manager.player_command(payload)
                    if endpoint=='api/controller': state['stopped']=not payload['enabled']
                    elif endpoint=='api/practice': state['practice']=payload['enabled']
                    elif endpoint=='calibrate': state['centering']=True
                    else: self.fail(endpoint)
                worker.get=get;worker.post=post
                worker.run('begin');worker.run('center')
                for direction,position in [('left',{'x':.3,'y':.5}),('right',{'x':.75,'y':.5}),
                                           ('up',{'x':.5,'y':.35}),('down',{'x':.5,'y':.8})]:
                    state['position']=position
                    worker.run(direction)
                worker.run(ending)
                actual=load_calibration(data/'calibration.json')
                if ending=='cancel': self.assertEqual(actual,original)
                else:
                    for direction,span in zip(helper.DIRECTIONS,(.2,.25,.15,.3)):
                        self.assertAlmostEqual(getattr(actual,'reach_'+direction),span)
                self.assertTrue(state['stopped']);self.assertFalse(state['practice'])
                self.assertFalse(manager.needs_center())
                self.assertEqual(json.loads(worker.path.read_text())['state'], 'applied' if ending=='apply' else 'cancelled')
