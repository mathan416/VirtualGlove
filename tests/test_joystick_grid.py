# Project: VirtualGlove
# File: tests/test_joystick_grid.py
# Purpose: Verify calibrated joystick dead-zone overlay geometry and safety.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-13 - Added calibrated camera-grid coverage.
# Full history: docs/CHANGELOG.md and Git history.
"""Read-only practice grid bounds use the same saved reference as direction logic."""
import copy
from types import SimpleNamespace
import unittest
from pathlib import Path
import ast

from virtualglove.gesture import GestureConfig, GestureEngine
from virtualglove.model import Calibration
from virtualglove.vision_app import _joystick_grid_status


class JoystickGridTests(unittest.TestCase):
    def engine(self, **values):
        reference=Calibration(**dict(dict(palm_x=.3,palm_y=.7,palm_scale=.2,roll=0),**values))
        return SimpleNamespace(calibration=reference,calibrated=True,config=GestureConfig(joystick_deadzone=.6))

    def test_saved_center_and_nominal_sizes_drive_bounds(self):
        for size in (.6,.1,1):
            engine=self.engine(palm_x=.3,palm_y=.7,palm_scale=.04)
            engine.config=GestureConfig(joystick_deadzone=size)
            before=copy.deepcopy(engine);grid=_joystick_grid_status(engine,True)
            half=size/2
            self.assertEqual(grid['anchor'],{'x':.3,'y':.7})
            self.assertEqual(grid['minimum_size'],.06)
            self.assertEqual(grid['half_size'],half)
            self.assertEqual(grid['center'],{
                'x':min(1-half,max(half,.3)),
                'y':min(1-half,max(half,.7)),
            })
            self.assertEqual(engine.calibration,before.calibration)
            self.assertEqual(engine.config,before.config)

    def test_hand_size_floor_enlarges_box_without_using_jitter(self):
        for noise in (0,.9):
            engine=self.engine(palm_x=.5,palm_y=.5,palm_scale=.2,noise_x=noise,noise_y=noise)
            engine.config=GestureConfig(joystick_deadzone=.1)
            grid=_joystick_grid_status(engine,True)
            self.assertAlmostEqual(grid['minimum_size'],.3)
            self.assertAlmostEqual(grid['half_size'],.15)
            self.assertEqual(grid['center'],{'x':.5,'y':.5})

    def test_edge_center_translates_full_box_instead_of_clipping(self):
        engine=self.engine(palm_x=.02,palm_y=.97,palm_scale=.2)
        grid=_joystick_grid_status(engine,True)
        self.assertEqual(grid['anchor'],{'x':.02,'y':.97})
        self.assertEqual(grid['center'],{'x':.3,'y':.7})
        self.assertEqual(grid['half_size'],.3)
        self.assertAlmostEqual(grid['center']['x']-grid['half_size'],0)
        self.assertAlmostEqual(grid['center']['x']+grid['half_size'],.6)
        self.assertAlmostEqual(grid['center']['y']-grid['half_size'],.4)
        self.assertAlmostEqual(grid['center']['y']+grid['half_size'],1)

    def test_omitted_outside_practice_and_without_active_valid_calibration(self):
        engine=self.engine()
        self.assertIsNone(_joystick_grid_status(engine,False))
        self.assertIsNone(_joystick_grid_status(engine,True,True))
        self.assertIsNone(_joystick_grid_status(None,True))
        engine.calibrated=False;self.assertIsNone(_joystick_grid_status(engine,True))
        engine.calibrated=True;engine.calibration=None;self.assertIsNone(_joystick_grid_status(engine,True))
        for values in [dict(palm_x=-.1),dict(palm_y=1.1),dict(palm_scale=0),dict(palm_scale=float('inf')),
                       dict(noise_x=float('nan')),dict(roll=4),dict(reach_left=.5)]:
            with self.subTest(values=values):self.assertIsNone(_joystick_grid_status(self.engine(**values),True))

    def test_engine_calibration_in_progress_does_not_publish_old_bounds(self):
        engine=GestureEngine('program_h',GestureConfig(joystick_deadzone=.6),calibration=Calibration(.5,.5,.2,0))
        self.assertIsNotNone(_joystick_grid_status(engine,True))
        engine.begin_calibration()
        self.assertIsNone(_joystick_grid_status(engine,True))

    def test_status_publication_is_conditional_and_has_no_persistence(self):
        # The actual publication block is executed with both kinds of practice state.
        source=Path('src/virtualglove/vision_app.py').read_text()
        tree=ast.parse(source)
        assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='_joystick_grid_status')
        condition=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and any(isinstance(x,ast.Constant) and x.value=='joystick_grid' for x in ast.walk(n)) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='grid')
        code=compile(ast.fix_missing_locations(ast.Module(body=[assignment,condition],type_ignores=[])),'grid-status','exec')
        for practice,needs,error in [(False,False,None),(True,True,None),(True,False,'save failed'),(True,False,None)]:
            scope=dict(engine=self.engine(),practice_mode=practice,needs_center=needs,calibration_save_error=error,status={},_joystick_grid_status=_joystick_grid_status)
            exec(code,scope)
            self.assertEqual('joystick_grid' in scope['status'],practice and not needs and not error)
