# Project: VirtualGlove
# File: tests/test_joystick_camera.py
# Purpose: Verify joystick camera practice, lease safety, and browser behavior.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-13 - Added camera-test and lease lifecycle coverage.
# Full history: docs/CHANGELOG.md and Git history.
"""Camera-test lease ownership, browser behavior, and rendered script contracts."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from virtualglove.debug_server import SharedDebugState
from virtualglove.joystick_web import JOYSTICK_SCRIPT, JOYSTICK_CONTENT


class JoystickPracticeTests(unittest.TestCase):
    def test_own_lease_is_distinct_from_other_tabs_and_expires(self):
        shared=SharedDebugState()
        with patch('virtualglove.debug_server.time.monotonic',return_value=100):
            shared.request_practice('other-tab',True)
            self.assertEqual(shared.practice_status('joystick-tab'),dict(practice_mode=True,session_active=False))
            shared.request_practice('joystick-tab',True)
            self.assertTrue(shared.practice_status('joystick-tab')['session_active'])
            shared.request_practice('joystick-tab',False)
            self.assertTrue(shared.practice_status('other-tab')['session_active'])
            self.assertFalse(shared.practice_status('joystick-tab')['session_active'])
            shared.request_practice('joystick-tab',True)
        with patch('virtualglove.debug_server.time.monotonic',return_value=107):
            self.assertEqual(shared.practice_status('joystick-tab'),dict(practice_mode=False,session_active=False))

    def test_reset_cannot_be_mistaken_for_an_owned_lease(self):
        shared=SharedDebugState();shared.request_practice('joystick-tab',True)
        shared.request_practice('',False,reset=True)
        shared.request_practice('new-academy',True)
        shared.request_practice('joystick-tab',True)
        self.assertEqual(shared.practice_status('joystick-tab'),dict(practice_mode=True,session_active=False))


@unittest.skipUnless(shutil.which('node'),'Node needed for JavaScript tests')
class JoystickCameraTests(unittest.TestCase):
    def test_browser_toggle_lifecycle(self):
        harness=Path(__file__).with_name('joystick_camera_harness.js')
        for scenario in ['draft','grid','center','normal','rejected','acquire-failure','failure','stream','save','pagehide','pagehide-pending','release-failure']:
            with self.subTest(scenario=scenario):
                result=subprocess.run(['node',str(harness)],input=json.dumps(dict(script=JOYSTICK_SCRIPT,scenario=scenario)),text=True,capture_output=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_preview_agrees_with_gameplay_frame_boundaries(self):
        from virtualglove.gesture import GestureEngine, GestureConfig, joystick_deadzone_bounds
        from virtualglove.model import Calibration, HandObservation
        samples=[]
        calibrations=[Calibration(.5,.5,.2,0),Calibration(.2,.8,.3,0)]
        for size in [.1,.28,.6,1.0]:
            for calibration in calibrations:
                config=GestureConfig(joystick_deadzone=size)
                bounds=joystick_deadzone_bounds(config,calibration)
                positions_x=[0,bounds['left'],bounds['center_x'],bounds['right'],1]
                positions_y=[0,bounds['top'],bounds['center_y'],bounds['bottom'],1]
                grid=dict(anchor=dict(x=calibration.palm_x,y=calibration.palm_y),
                    center=dict(x=bounds['center_x'],y=bounds['center_y']),
                    half_size=bounds['half_size'],minimum_size=min(1,1.5*calibration.palm_scale))
                for x in positions_x:
                    for y in positions_y:
                        engine=GestureEngine('program_h',config,calibration=calibration)
                        state=engine.update(HandObservation(1,True,.99,x,y,.3,0))
                        expected=dict(left=x<bounds['left'],right=x>bounds['right'],
                                      up=y<bounds['top'],down=y>bounds['bottom'])
                        self.assertEqual(state.dpad,expected)
                        samples.append(dict(size=size,palm=dict(x=x,y=y),dpad=state.dpad,grid=grid))
        result=subprocess.run(['node',str(Path(__file__).with_name('joystick_camera_harness.js'))],
            input=json.dumps(dict(script=JOYSTICK_SCRIPT,scenario='agreement',samples=samples)),
            text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_markup_and_script_parse(self):
        from html.parser import HTMLParser
        class Parser(HTMLParser):
            def __init__(self):super().__init__();self.nodes={};self.parents={};self.stack=[];self.counter=0
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if attrs.get('id'):
                    self.nodes[attrs['id']]=(tag,attrs)
                    self.parents[attrs['id']]=self.stack[-1] if self.stack else None
                self.counter+=1
                if tag not in {'img','input','br','meta','link','hr'}:self.stack.append((tag,self.counter))
            def handle_endtag(self,tag):
                if self.stack and self.stack[-1][0]==tag:self.stack.pop()
        parser=Parser();parser.feed(JOYSTICK_CONTENT)
        tag,attrs=parser.nodes['joystick-camera'];self.assertEqual(tag,'img');self.assertIn('hidden',attrs);self.assertNotIn('src',attrs)
        self.assertIn('joystick-camera-stage',parser.nodes)
        self.assertEqual(parser.nodes['joystick-size'][1]['min'],'0.10')
        self.assertEqual(parser.nodes['joystick-grid'][0],'svg')
        self.assertIn('hidden',parser.nodes['joystick-grid'][1])
        self.assertEqual(parser.nodes['joystick-camera-toggle'][1]['type'],'button')
        self.assertEqual(parser.nodes['joystick-center'][1]['type'],'button')
        self.assertIn('disabled',parser.nodes['joystick-center'][1])
        self.assertEqual(parser.parents['joystick-camera-toggle'],parser.parents['joystick-default'])
        self.assertEqual(parser.parents['joystick-center'],parser.parents['joystick-camera-toggle'])
        self.assertEqual(parser.parents['joystick-default'],parser.parents['joystick-save'])
        self.assertEqual(parser.parents['joystick-camera-toggle'][0],'div')
        self.assertNotIn('Start the controller from Dashboard',JOYSTICK_SCRIPT)
        result=subprocess.run(['node','--check'],input=JOYSTICK_SCRIPT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_setup_places_dead_zone_immediately_after_players(self):
        from virtualglove.setup_web import SETUP_CONTENT
        players=SETUP_CONTENT.index('id=players')
        joystick=SETUP_CONTENT.index('id=joystick-settings')
        matrix=SETUP_CONTENT.index('Matrix attract mode')
        self.assertLess(players,joystick)
        self.assertLess(joystick,matrix)


class PracticeResponseTests(unittest.TestCase):
    def test_http_practice_response_confirms_only_its_session(self):
        import http.client
        from virtualglove.debug_server import start_debug_server
        shared=SharedDebugState();shared.request_practice('another-practice-tab',True)
        server=start_debug_server(shared,'127.0.0.1',0)
        try:
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            for enabled in (True,False):
                client.request('POST','/practice',json.dumps(dict(session='joystick-camera-tab',enabled=enabled)),{'Content-Type':'application/json'})
                response=client.getresponse();self.assertEqual(response.status,200)
                result=json.loads(response.read())
                self.assertEqual(result,dict(practice_mode=True,session_active=enabled))
            client.close()
            self.assertTrue(shared.practice_status('another-practice-tab')['session_active'])
        finally:server.shutdown();server.server_close()
