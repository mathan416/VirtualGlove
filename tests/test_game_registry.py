# Project: VirtualGlove
# File: tests/test_game_registry.py
# Purpose: Exercise registry validation, atomic recovery, and paired service authentication.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added game registry integrity and network regression tests.
# Full history: docs/CHANGELOG.md and Git history.

"""Test real registry edits and paired service exchanges in isolated directories."""
import json
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

from virtualglove.game_registry import (
    PROTOCOL, RegistryStore, RegistryService, validate_document,
    make_registry_handler, registry_request,
)
from virtualglove.profile_control import sign_message, verify_message
from virtualglove.controller_router import RouterService, router_request

ORIGINAL = '{"games":{"Joust (USA).7z":"program_b"}}'
CHANGED = '{"games":{"Joust (USA).7z":"program_h"}}'


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'games.json'
        self.path.write_text(ORIGINAL)
        self.store = RegistryStore(self.path)
        self.token_path = self.path.with_name('token')
        self.token = 'isolated-test-token-only'
        self.token_path.write_text(self.token)
        self.now = 10.
        self.service = RegistryService(self.store, self.token_path, lambda: self.now)

    def test_rejects_bad_documents_and_casefold_collisions(self):
        for text in ('{', '[]', '{"games":[]}', '{"games":{"a":"invalid"}}',
                     '{"games":{"a":{"profile":"program_1","rapid_a":0}}}',
                     '{"games":{"a":{"profile":"program_1","extra":false}}}',
                     '{"games":{"a":"program_b","a":"program_c"}}',
                     '{"games":{"A":"program_b","a":"program_c"}}',
                     '{"games":{"/roms/a":"program_b","a":"program_c"}}',
                     '{"games":{"":"program_b"}}', '{"games":{},"number":NaN}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_document(text)

    def test_preserves_metadata_and_existing_path_form(self):
        text = '{"note":"custom","games":{"/roms/Joust.7z":"program_b"}}'
        self.assertEqual(validate_document(text)['note'], 'custom')

    def test_save_restore_and_stale_editor(self):
        revision = self.store.snapshot()['revision']
        saved = self.store.operate('save', {'document': CHANGED, 'revision': revision})
        self.assertEqual(saved['document'], CHANGED)
        self.assertEqual(self.store.backup.read_text(), ORIGINAL)
        with self.assertRaisesRegex(ValueError, 'changed elsewhere'):
            self.store.operate('save', {'document': ORIGINAL, 'revision': revision})
        restored = self.store.operate('restore', {'revision': saved['revision']})
        self.assertEqual(restored['document'], ORIGINAL)
        self.assertEqual(self.store.backup.read_text(), CHANGED)

    def test_interrupted_replace_preserves_current_registry(self):
        import os
        real_replace = os.replace
        def fail_current(source, target):
            if Path(target) == self.path:
                raise OSError('simulated full disk')
            real_replace(source, target)
        with patch('virtualglove.game_registry.os.replace', side_effect=fail_current):
            with self.assertRaises(OSError):
                self.store.operate('save', {'document': CHANGED, 'revision': self.store.snapshot()['revision']})
        self.assertEqual(self.path.read_text(), ORIGINAL)
        self.assertEqual(self.store.backup.read_text(), ORIGINAL)
        self.assertFalse(list(self.path.parent.glob('.games.json.*')))

    def request(self, operation='read'):
        challenge = self.service.exchange({'protocol': PROTOCOL, 'operation': 'challenge', 'request_id': 'abc'})
        self.assertTrue(verify_message(challenge, self.token))
        return sign_message(dict(protocol=PROTOCOL, operation=operation, request_id='abc', challenge=challenge['challenge']), self.token)

    def test_authentication_replay_and_expiry(self):
        request = self.request()
        tampered = dict(request, operation='save')
        with self.assertRaises(ValueError): self.service.exchange(tampered)
        response = self.service.exchange(request)
        self.assertTrue(verify_message(response, self.token))
        self.assertEqual(response['result']['document'], ORIGINAL)
        with self.assertRaises(ValueError): self.service.exchange(request)
        request = self.request()
        self.now += 16
        with self.assertRaises(ValueError): self.service.exchange(request)

    def test_nonce_capacity_recovers_and_token_rotation_takes_effect(self):
        for i in range(64):
            self.request()
        with self.assertRaises(ValueError): self.request()
        self.now += 16
        request = self.request()
        self.token_path.write_text('a-different-test-token')
        with self.assertRaises(ValueError): self.service.exchange(request)

    def test_actual_http_client_save_restore_and_bad_pairing(self):
        server = HTTPServer(('127.0.0.1', 0), make_registry_handler(self.service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            settings = {'receiver': '127.0.0.1', 'token': self.token}
            port = server.server_address[1]
            old = registry_request(settings, 'read', port=port)
            saved = registry_request(settings, 'save', {'revision': old['revision'], 'document': CHANGED}, port)
            restored = registry_request(settings, 'restore', {'revision': saved['revision']}, port)
            self.assertEqual(restored['document'], ORIGINAL)
            with self.assertRaises(ValueError):
                registry_request(dict(settings, token='wrong-secret-token'), 'read', port=port)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_inputs_endpoint_uses_separate_authenticated_protocol(self):
        class InputStore:
            def operate(self, operation, payload):
                return {"operation": operation, "watch_ms": payload.get("watch_ms", 0)}

        inputs = RouterService(InputStore(), self.token_path, lambda: self.now)
        server = HTTPServer(('127.0.0.1', 0), make_registry_handler(self.service, inputs))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            settings = {'receiver': '127.0.0.1', 'token': self.token}
            result = router_request(settings, 'check', {'watch_ms': 750},
                                    port=server.server_address[1])
            self.assertEqual(result, {"operation": "check", "watch_ms": 750})
            with self.assertRaises(ValueError):
                router_request(dict(settings, token='wrong-secret-token'), 'read',
                               port=server.server_address[1])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_offline_client_preserves_actionable_error(self):
        with patch('virtualglove.game_registry.urllib.request.OpenerDirector.open', side_effect=OSError):
            with self.assertRaisesRegex(ValueError, 'update its VirtualGlove setup'):
                registry_request({'receiver':'127.0.0.1', 'token':self.token}, 'read')
