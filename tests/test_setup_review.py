# Project: VirtualGlove
# File: tests/test_setup_review.py
# Purpose: Exercise Setup recovery, concurrent settings, private worker launch, and receiver release.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Cover concrete findings from the Setup and runtime review.

"""Regression checks for the Setup review without physical controller hardware."""
import http.client
import io
import json
import runpy
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from powerglove_vision import receiver, vision_app
from powerglove_vision.control_server import ControlState, start_control_server
from powerglove_vision.game_registry import atomic_write
from powerglove_vision.profile_control import ProfileCommandServer, PROTOCOL, sign_message

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'private-test-token'


class SetupReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'device.json'
        self.path.write_text(json.dumps(dict(receiver='cabinet.local', token=TOKEN, profile='off')))
        self.state = ControlState(self.path)

    def test_settings_writes_preserve_concurrent_attract_change(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def delayed_write(*args):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test write blocked')
            atomic_write(*args)
        def save():
            try:
                self.state.save_config({'receiver':'new.local','profile':'off'})
            except Exception as error:
                errors.append(error)
        with patch('powerglove_vision.game_registry.atomic_write', side_effect=delayed_write):
            first = threading.Thread(target=save); first.start()
            self.assertTrue(entered.wait(1))
            second = threading.Thread(target=lambda:self.state.save_attract({'mode':'dim'})); second.start()
            release.set(); first.join(2); second.join(2)
        self.assertFalse(errors)
        saved = json.loads(self.path.read_text())
        self.assertEqual((saved['receiver'], saved['matrix_attract']), ('new.local','dim'))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_failed_atomic_save_preserves_original(self):
        before = self.path.read_bytes()
        with patch('powerglove_vision.game_registry.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.state.save_config({'receiver':'new.local','profile':'off'})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.state.revision, 0)

    def test_latest_controller_request_retries_without_replaying_old_intent(self):
        self.state.set_controller_enabled(True)
        with patch('powerglove_vision.control_server.urllib.request.urlopen', side_effect=OSError('offline')):
            self.assertFalse(self.state.flush_controller_request())
        self.state.set_controller_enabled(False)
        with patch('powerglove_vision.control_server.urllib.request.urlopen', return_value=io.BytesIO(b'{"controller_enabled":false}')) as send:
            self.assertTrue(self.state.flush_controller_request())
            self.assertEqual(json.loads(send.call_args[0][0].data), {'enabled':False})
            self.assertTrue(self.state.flush_controller_request())
            self.assertEqual(send.call_count, 1)
        self.assertFalse(self.state.snapshot()['controller_request_pending'])

    def test_new_intent_survives_old_ack(self):
        self.state.set_controller_enabled(True)
        def acknowledge(_request, **kwargs):
            self.state.set_controller_enabled(False)
            return io.BytesIO(b'{"controller_enabled":true}')
        with patch('powerglove_vision.control_server.urllib.request.urlopen', side_effect=acknowledge):
            self.assertFalse(self.state.flush_controller_request())
        self.assertFalse(self.state.controller_enabled())
        self.assertTrue(self.state.snapshot()['controller_request_pending'])

    def test_worker_error_retries_but_rejected_start_disarms(self):
        self.state.set_controller_enabled(True)
        with patch('powerglove_vision.control_server.urllib.request.urlopen',
                   side_effect=urllib.error.HTTPError('http://worker',503,'unavailable',{},None)):
            self.assertFalse(self.state.flush_controller_request())
        self.assertTrue(self.state.controller_enabled())
        self.state.set_controller_enabled(True)
        with patch('powerglove_vision.control_server.urllib.request.urlopen',
                   side_effect=urllib.error.HTTPError('http://worker',400,'needs center',{},None)):
            with self.assertRaisesRegex(ValueError, 'rejected'):
                self.state.flush_controller_request()
        self.assertFalse(self.state.controller_enabled())
        self.assertTrue(self.state.snapshot()['controller_request_pending'])

    def test_unexpected_ack_is_retried(self):
        self.state.set_controller_enabled(True)
        with patch('powerglove_vision.control_server.urllib.request.urlopen', return_value=io.BytesIO(b'[]')):
            self.assertFalse(self.state.flush_controller_request())
        self.assertTrue(self.state.snapshot()['controller_request_pending'])

    def test_rotation_disarms_and_preserves_attract(self):
        self.state.set_controller_enabled(True)
        self.state.save_attract({'mode':'off'})
        self.state.save_config({'receiver':'cabinet.local','profile':'off','rotate_token':True})
        self.assertFalse(self.state.controller_enabled())
        saved = json.loads(self.path.read_text())
        self.assertNotEqual(saved['token'], TOKEN)
        self.assertEqual(saved['matrix_attract'], 'off')

    def test_config_requires_json_and_same_origin(self):
        servers, state = start_control_server(self.path, '127.0.0.1', 0, 0)
        self.addCleanup(servers.shutdown)
        port = servers.servers[0].server_address[1]
        for headers, expected in [({'Content-Type':'text/plain'},400),
                                  ({'Content-Type':'application/json','Origin':'http://elsewhere.invalid'},403),
                                  ({'Content-Type':'application/json','Sec-Fetch-Site':'cross-site'},403)]:
            with self.subTest(headers=headers):
                conn = http.client.HTTPConnection('127.0.0.1',port,timeout=2)
                conn.request('POST','/api/config',json.dumps({'receiver':'changed.local'}),headers)
                response = conn.getresponse(); response.read(); conn.close()
                self.assertEqual(response.status, expected)
        self.assertEqual(state.load_config()['receiver'], 'cabinet.local')

    def test_controller_api_reports_pending_delivery(self):
        servers, state = start_control_server(self.path, '127.0.0.1', 0, 0)
        self.addCleanup(servers.shutdown)
        conn = http.client.HTTPConnection('127.0.0.1',servers.servers[0].server_address[1],timeout=2)
        with patch('powerglove_vision.control_server.urllib.request.urlopen', side_effect=OSError('offline')):
            conn.request('POST','/api/controller','{"enabled":true}',{'Content-Type':'application/json'})
            response = conn.getresponse(); result = json.loads(response.read()); conn.close()
        self.assertEqual(response.status, 202)
        self.assertTrue(result['pending'])

    def test_worker_launch_keeps_token_in_private_file(self):
        namespace = runpy.run_path(str(ROOT/'python/main.py'))
        command = namespace['worker_command']({'token':TOKEN}, Path('/tmp/model'))
        self.assertNotIn(TOKEN, command)
        self.assertNotIn('--token', command)
        self.assertIn('--device-config', command)
        self.assertEqual(command[command.index('--profile') + 1], 'off')
        args = vision_app.build_parser().parse_args(['--receiver','cabinet.local','--device-config',str(self.path)])
        self.assertEqual(args.profile, 'off')
        self.assertEqual(vision_app.load_worker_token(args), TOKEN)
        loader = namespace['load_device_config']; loader.__globals__['CONFIG_PATH'] = self.path.with_name('new.json')
        loader()
        self.assertEqual(self.path.with_name('new.json').stat().st_mode & 0o777, 0o600)

    def test_socket_timeout_releases_native_state_before_cleanup(self):
        sock, device, native = Mock(), Mock(), Mock()
        packet = json.dumps(dict(protocol='virtualglove-vision/1',token=TOKEN,sequence=7,session='test')).encode()
        def after_timeout(_size):
            native.release.assert_called_once_with(8)
            raise KeyboardInterrupt
        calls = [0]
        def receive(size):
            calls[0] += 1
            if calls[0] == 1:return packet, ('test',1)
            if calls[0] == 2:raise socket.timeout()
            return after_timeout(size)
        sock.recvfrom.side_effect = receive
        sock.recvmsg.side_effect = lambda size, space: (lambda pair: (pair[0], [], 0, pair[1]))(sock.recvfrom(size))
        with patch.object(receiver.socket,'socket',return_value=sock), patch.object(receiver,'UInputDevice',return_value=device), patch.object(receiver,'NativeStateWriter',return_value=native), patch('sys.argv',['receiver','--token',TOKEN,'--allow-legacy-controller']):
            self.assertEqual(receiver.main(),0)

    def test_profile_listener_survives_nested_json(self):
        server = ProfileCommandServer('127.0.0.1',0,TOKEN)
        self.addCleanup(server.close)
        client = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.addCleanup(client.close)
        client.sendto(b'['*1200+b']'*1200, server.socket.getsockname())
        request = sign_message(dict(protocol=PROTOCOL,kind='set_profile',request_id='after-nesting',profile=None,system='nes',rom=''), TOKEN)
        client.sendto(json.dumps(request).encode(),server.socket.getsockname())
        deadline = time.monotonic()+1
        result = None
        while result is None and time.monotonic()<deadline:
            result = server.take(); time.sleep(.005)
        self.assertIsNotNone(result)
        self.assertTrue(server._thread.is_alive())
