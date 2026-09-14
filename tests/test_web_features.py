# Project: VirtualGlove
# File: tests/test_web_features.py
# Purpose: Verify browser-facing Games and Tune safeguards and server-side validation.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added new web route integration tests.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise real browser endpoint handling without hardware dependencies."""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
from powerglove_vision.control_server import ControlState, make_handler, SETUP, LEARN
from powerglove_vision.dashboard_web import DASHBOARD


class WebFeatureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / 'device.json'
        path.write_text(json.dumps({'receiver':'pi.local','token':'test-secret-only','profile':'off'}))
        self.server = HTTPServer(('127.0.0.1',0), make_handler(ControlState(path)))
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.directory.cleanup()

    def post(self, path, data, **headers):
        connection = http.client.HTTPConnection(*self.server.server_address,timeout=3)
        try:
            connection.request('POST',path,json.dumps(data),headers=dict({'Content-Type':'application/json'},**headers))
            response=connection.getresponse()
            return response.status,json.loads(response.read())
        finally: connection.close()

    def test_mutations_require_same_origin_browser_safeguard(self):
        for path in ('/api/games','/api/tuning'):
            action=path.rsplit('/',1)[-1]
            with patch('powerglove_vision.control_server.registry_request') as remote:
                self.assertEqual(self.post(path,{'action':'save'})[0],403)
                self.assertEqual(self.post(path,{'action':'save'},**{'X-VirtualGlove-Action':action,'Origin':'http://untrusted.local'})[0],403)
                remote.assert_not_called()

        with patch('powerglove_vision.control_server.urllib.request.urlopen') as worker:
            self.assertEqual(self.post('/api/gesture-recording', {'action':'begin'})[0], 403)
            self.assertEqual(self.post('/api/rapid-fire', {
                'request_id':'rapid-test', 'game':'Example.nes',
                'rapid_a':True, 'rapid_b':False,
            })[0], 403)
            worker.assert_not_called()

    def test_registry_validation_rejects_duplicate_keys_without_contacting_pi(self):
        with patch('powerglove_vision.control_server.registry_request') as remote:
            status,result=self.post('/api/games',{'action':'validate','document':'{"games":{"a":"program_b","a":"program_c"}}'},**{'X-VirtualGlove-Action':'games'})
            self.assertEqual(status,400)
            self.assertIn('Duplicate',result['error'])
            remote.assert_not_called()

    def test_save_returns_verified_remote_result_without_secret(self):
        with patch('powerglove_vision.control_server.registry_request',return_value={'document':'{"games":{}}','revision':'verified'}) as remote:
            code,result=self.post('/api/games',{'action':'save','document':'{"games":{}}','revision':'old'},**{'X-VirtualGlove-Action':'games'})
            self.assertEqual(code,200)
            self.assertEqual(result['revision'],'verified')
            self.assertNotIn('token',result)
            self.assertEqual(remote.call_args[0][2]['revision'],'old')

    def test_tuning_panel_is_beside_camera_and_practice_is_preserved(self):
        self.assertIn(b'id=game-json',SETUP)
        self.assertGreater(SETUP.index(b'id=games-section'),SETUP.index(b'id=pairing-section'))
        self.assertNotIn(b'<a href=/games>',SETUP)
        self.assertLess(LEARN.index(b'id=learn-camera'),LEARN.index(b'id=tune-thresholds'))
        self.assertIn(b'id=practice-lessons',LEARN)
        self.assertIn(b'Lesson 1 of 16',LEARN)
        self.assertIn(b'th.art-column', LEARN)
        self.assertIn(b'td.art-cell img', LEARN)
        self.assertIn(b'table.program-starters', LEARN)
        self.assertIn(b'th:nth-child(2)', LEARN)
        self.assertLess(LEARN.index(b'id=learn-camera'),LEARN.index(b'<section class=card id=tune-panel'))
        self.assertIn(b'id=rapid-fire-card', DASHBOARD)
        self.assertIn(b'id=gesture-recorder-card', DASHBOARD)
        self.assertIn(b'Changes apply during play', DASHBOARD)
        self.assertIn(b'/api/rapid-fire', DASHBOARD)
        self.assertIn(b'Camera images, player names', DASHBOARD)
