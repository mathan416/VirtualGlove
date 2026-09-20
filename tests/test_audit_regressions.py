# Project: VirtualGlove
# File: tests/test_audit_regressions.py
# Purpose: Prevent controller, tuning, deployment, and matrix audit regressions.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-05 - Established an intentional manual context in packet-session tests.
#   2026-09-04 - Covered nested documentation support files in the Help audit.
#   2026-09-04 - Cover reliability findings from the development audit.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise failure paths without camera, bridge, or administrator access."""
import json
import re
import runpy
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import Future
from unittest.mock import Mock, patch
from virtualglove import receiver, vision_app
from virtualglove.transport import validate_state
from virtualglove.controller_protocol import ReceiverSessions, decode_message, encode_message
from virtualglove.gesture import GestureEngine, HeldGesture, GestureConfig
from virtualglove.model import Calibration, ControllerState, HandObservation
from virtualglove.matrix import UnoQMatrix, MatrixStatus
from virtualglove.tuning import TuningManager

ROOT = Path(__file__).resolve().parents[1]
CAL = Calibration(.5, .5, .2, 0)
TOKEN = '0123456789abcdef'


def packet(**extra):
    value = ControllerState.released(1, 1, 'off', True).to_transport_dict()
    value.update(extra)
    return value


class AuditRegressionTests(unittest.TestCase):
    def test_code_review_map_matches_the_tracked_checkout(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/build-code-review-map.py"), "--check"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_sigterm_is_one_shot_before_normal_cleanup(self):
        with patch.object(vision_app.signal, "signal") as install, \
             self.assertRaises(KeyboardInterrupt):
            vision_app._shutdown_on_signal(signal.SIGTERM, None)
        install.assert_called_once_with(signal.SIGTERM, signal.SIG_IGN)

    def test_retired_python_and_product_names_are_absent_from_tracked_files(self):
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT
        ).decode().split("\0")
        old_brand, vision = "power" + "glove", "vision"
        retired = re.compile(
            old_brand + r"[_ -]?" + vision + "|" +
            vision + r"[_ -]?" + old_brand,
            re.IGNORECASE,
        )
        matches = []
        for relative in filter(None, tracked):
            path = ROOT / relative
            if not path.is_file():
                continue
            try:
                content = path.read_text()
            except UnicodeDecodeError:
                continue
            if retired.search(relative) or retired.search(content):
                matches.append(relative)
        self.assertEqual(matches, [])

    def test_help_audit_ignores_nested_documentation_support_files(self):
        audit = runpy.run_path(str(ROOT / 'scripts/check-documentation.py'))
        errors = []
        audit['check_help_coverage'](
            [Path('docs/GAMEPLAY_GUIDE.md'), Path('docs/support/README.md')],
            errors,
        )
        self.assertEqual(errors, [])

    def test_documentation_audit_rejects_american_public_spelling(self):
        audit = runpy.run_path(str(ROOT / 'scripts/check-documentation.py'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prose = root / 'guide.md'
            prose.write_text('The interface recognizes this behavior.\n')
            with patch.dict(audit['check_canadian_english'].__globals__, {'ROOT': root}):
                errors = []
                audit['check_canadian_english']([Path('guide.md')], errors)
            self.assertTrue(errors)

            prose.write_text(
                'The interface recognises this behaviour.\n'
                '`recognized` and `center` remain protocol fields.\n'
                '```json\n{"recognized": true, "center": 0.5}\n```\n'
            )
            with patch.dict(audit['check_canadian_english'].__globals__, {'ROOT': root}):
                errors = []
                audit['check_canadian_english']([Path('guide.md')], errors)
            self.assertEqual(errors, [])

    def test_public_web_copy_uses_canadian_english(self):
        from virtualglove.academy_web import LEARN
        from virtualglove.dashboard_web import DASHBOARD
        from virtualglove.joystick_web import JOYSTICK_CONTENT, JOYSTICK_SCRIPT
        from virtualglove.player_web import PLAYER_CONTENT, PLAYER_SCRIPT
        from virtualglove.setup_web import SETUP_CONTENT, SETUP_SCRIPT
        from virtualglove.tuning_web import TUNE_CONTENT, TUNE_SCRIPT

        parts = (
            LEARN, DASHBOARD,
            JOYSTICK_CONTENT, JOYSTICK_SCRIPT,
            PLAYER_CONTENT, PLAYER_SCRIPT,
            SETUP_CONTENT, SETUP_SCRIPT,
            TUNE_CONTENT, TUNE_SCRIPT,
        )
        public_copy = "\n".join(
            part.decode() if isinstance(part, bytes) else part for part in parts
        )
        for phrase in (
            "Center hand", "Center your hand", "Center saved", "Centering…",
            "Personalize", "Personalization", "Exposure behavior",
            "Actual camera behavior", "Help center",
        ):
            self.assertNotIn(phrase, public_copy)
        self.assertIn("Centre hand", public_copy)

    def test_malformed_packets_are_rejected_before_device_access(self):
        invalid = [[], None, "text", packet(axes=[]), packet(buttons={'a':1}),
                   packet(axes={'x':32768}), packet(fingers={'index':4}),
                   packet(confidence=float('nan'))]
        base = packet()
        for key, value in [('sequence',True), ('sequence',-1), ('sequence','1'),
                           ('protocol','virtualglove-vision/1'), ('token',{}),
                           ('sequence',2**40)]:
            invalid.append(dict(base, **{key:value}))
        for value in invalid:
            with self.subTest(payload=value), self.assertRaises(ValueError):
                validate_state(value)
        self.assertEqual(validate_state(packet(buttons={'a':True}))['buttons'], {'a':True})

    def test_rejected_traffic_does_not_postpone_release(self):
        now = [0.]
        sock = Mock()
        sessions = ReceiverSessions(TOKEN, clock=lambda: now[0])
        session, peer = 'a' * 32, ('test', 1)
        _, reply = sessions.receive(
            encode_message('hello', TOKEN, session=session, request='b' * 32), peer
        )
        challenge = decode_message(reply, TOKEN)['challenge']
        valid = encode_message(
            'state', TOKEN, session=session, challenge=challenge,
            state=packet(buttons={'a': True}),
        )
        packets = iter([valid] + [b'[]', b'{}', b'unsigned']*5)
        def receive(_):
            now[0] += .1
            try:
                return next(packets), peer
            except StopIteration:
                raise KeyboardInterrupt
        sock.recvfrom.side_effect = receive
        sock.recvmsg.side_effect = lambda size, space: (lambda pair: (pair[0], [], 0, pair[1]))(sock.recvfrom(size))
        device = Mock()
        release_times = []
        device.release.side_effect = lambda: release_times.append(now[0])
        with patch.object(receiver,'ReceiverSessions',return_value=sessions), \
             patch.object(receiver.socket,'socket',return_value=sock), \
             patch.object(receiver.time,'monotonic',side_effect=lambda:now[0]), \
             patch.object(receiver,'UInputDevice',return_value=device), \
             patch.object(sys,'argv',['receiver','--token',TOKEN]):
            receiver.main()
        self.assertEqual(device.write_state.call_count,1)
        self.assertLessEqual(release_times[0], .4)
        self.assertGreater(len(release_times),1)  # Deadline release precedes cleanup.

    def test_matrix_retries_failed_status_and_profile_with_backoff(self):
        for method, value in [('set_status',MatrixStatus.LOADING), ('set_profile','program_h')]:
            rpc = Mock(side_effect=[OSError('temporary failure'),None])
            matrix = UnoQMatrix(call=rpc)
            with patch('virtualglove.matrix.time.monotonic',return_value=10):
                self.assertFalse(getattr(matrix,method)(value))
                self.assertFalse(getattr(matrix,method)(value))
            self.assertEqual(rpc.call_count,1)
            with patch('virtualglove.matrix.time.monotonic',return_value=11):
                self.assertTrue(getattr(matrix,method)(value))
                self.assertTrue(getattr(matrix,method)(value))
            self.assertEqual(rpc.call_count,2)

    def test_open_steps_request_extension_and_middle_step_requests_curl(self):
        with tempfile.TemporaryDirectory() as directory:
            manager=TuningManager(Path(directory)/'tune.json')
            manager.command({'action':'begin','session':'test-session'})
            manager.command({'action':'select','session':'test-session','gesture':'hand_setup'})
            for phase in range(3):
                manager.phases=[[] for _ in range(phase)]
                manager.observe(HandObservation(phase+1,True,1,.5,.5,.2),CAL,GestureConfig(),True)
                feedback=manager.snapshot()['finger_feedback']
                self.assertEqual(all(item['matches'] for item in feedback.values()),phase != 1)

    def test_program_f_keeps_closed_hand_until_release(self):
        engine=GestureEngine('program_f',calibration=CAL)
        for t,c,expected in [(1,.8,True),(1.1,.4,True),(1.2,.2,False)]:
            hand=HandObservation(t,True,1,.5,.5,.2,
                **{finger+'_curl':c for finger in ('thumb','index','middle','ring','pinky')})
            self.assertEqual(engine.update(hand).buttons['b'],expected)

    def test_ring_actions_and_guard_use_release_cutoffs(self):
        for profile in ('program_e','program_g'):
            engine=GestureEngine(
                profile, GestureConfig(joystick_deadzone=.28), calibration=CAL
            )
            for t,c in [(1,.8),(1.18,.4)]:
                state=engine.update(HandObservation(t,True,1,.8,.5,.2,
                    thumb_curl=.8 if profile == 'program_g' else 0,ring_curl=c))
            if profile == 'program_e':
                self.assertTrue(state.dpad['left'])
                self.assertFalse(state.dpad['right'])
            else:
                self.assertFalse(any(state.dpad.values()))
            state=engine.update(HandObservation(1.2,True,1,.8,.5,.2,
                thumb_curl=.8,ring_curl=.2))
            self.assertTrue(state.dpad['right'])

    def test_menu_debounce_is_short_but_requires_a_stable_pose_and_release(self):
        gesture=HeldGesture()
        self.assertFalse(gesture.update(True,1.0))
        self.assertFalse(gesture.update(False,1.1))
        self.assertFalse(gesture.update(True,1.2))
        self.assertFalse(gesture.update(True,1.3))
        self.assertTrue(gesture.update(True,1.36))
        self.assertFalse(gesture.update(True,1.6))
        self.assertFalse(gesture.update(True,2.0))
        self.assertFalse(gesture.update(False,2.1))
        self.assertFalse(gesture.update(True,2.2))
        self.assertTrue(gesture.update(True,2.36))

    def test_same_profile_transition_starts_new_packet_session(self):
        self.assert_transition_session(False)

    def test_program_h_academy_roundtrip_starts_new_packet_session(self):
        self.assert_transition_session(True)

    def assert_transition_session(self, practice):
        sent=[]
        class Sender:
            last_error=None
            def __init__(self,*args): self.session=0
            def new_session(self): self.session+=1
            def send(self,state): sent.append((self.session,state.sequence)); return True
            def close(self): pass
        count=[0]; requested=[False]
        def frame(_frame, timestamp=None):
            if timestamp is None:
                raise AssertionError("capture timestamp was not forwarded")
            count[0]+=1
            if count[0]>4: raise KeyboardInterrupt
            return SimpleNamespace(observation=HandObservation(timestamp,True,1,.5,.5,.2,index_curl=.8),
                                   frame=SimpleNamespace(shape=(480,640,3)),diagnostics={})
        def request():
            if practice: return None
            if sent and not requested[0]:
                requested[0]=True
                return ('program_h','Dashboard','same profile')
            return None
        practice_stage=[0]
        controller_stage=[0]
        def controller_request():
            if controller_stage[0] == 0:
                controller_stage[0]=1
                return True
            return None
        def practice_request():
            if practice and sent and practice_stage[0] == 0:
                practice_stage[0]=1
                return True
            if practice and count[0] >= 3 and practice_stage[0] == 1:
                practice_stage[0]=2
                return False
            return None
        def background(fn,*args):
            future=Future(); future.set_result(fn(*args)); return future
        capture=Mock(); capture.metadata={"camera_format":"MJPG"}
        capture_sequence=[0]
        def latest_after(_sequence):
            capture_sequence[0]+=1
            return SimpleNamespace(sequence=capture_sequence[0],captured_at=time.monotonic(),
                                   ok=True,frame=Mock())
        capture.latest_after.side_effect=latest_after
        tracker=Mock(); tracker.process.side_effect=frame; tracker.backend='legacy'
        tracker.backend_label='MediaPipe Hands'
        cv=Mock(); cv.imencode.return_value=(False,None)
        v=vision_app
        with patch.object(v,'_background_call',side_effect=background), \
             patch.object(v,'_preload_vision_libraries'), \
             patch.object(v,'_prepare_vision',return_value=(cv,capture,tracker)), \
             patch.object(v,'load_calibration',return_value=CAL), \
             patch.object(v,'UdpSender',Sender), patch.object(v,'ProfileCommandServer') as profiles, \
             patch.object(v,'start_debug_server'), patch.object(v,'UnoQMatrix'), \
             patch.object(v.SharedDebugState,'take_profile_request',side_effect=request), \
             patch.object(v.SharedDebugState,'take_practice_request',side_effect=practice_request), \
             patch.object(v.SharedDebugState,'take_controller_request',side_effect=controller_request), \
             patch.object(sys,'argv',['vision','--receiver','test','--token',TOKEN,
                                      '--profile','program_h']):
            profiles.return_value.take.return_value=None
            v.main()
        terminal=next(i for i,item in enumerate(sent) if item[1]==2147483647)
        resumed=next(item for item in sent[terminal+1:] if item[1] < 2147483647)
        self.assertNotEqual(sent[terminal][0],resumed[0])
        for session, sequence in sent[terminal:sent.index(resumed)]:
            if sequence == 2147483647: self.assertNotEqual(session,resumed[0])

    def test_install_updates_release_profiles_and_code(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('audit_install',ROOT/'scripts/install-package.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();source=root/'release';app=root/'app'
            (source/'config').mkdir(parents=True);(app/'config').mkdir(parents=True)
            (source/'config/profiles.json').write_text('new defaults')
            (app/'config/profiles.json').write_text('personal values')
            (source/'code.py').write_text('updated code')
            (app/'code.py').write_text('old code')
            setup=installer.load_setup(ROOT);setup.BACKUPS=root/'backups'
            with patch.object(installer,'APP',app), \
                 patch.object(installer.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=0,pw_gid=0)), \
                 patch.object(installer.os,'chown'),patch.object(setup,'run'):
                installer.stage_unoq(source,setup)
            self.assertEqual((app/'config/profiles.json').read_text(),'new defaults')
            self.assertEqual((app/'code.py').read_text(),'updated code')
            self.assertTrue(any(path.read_text() == 'personal values'
                                for path in (root/'backups').rglob('profiles.json')))

    def test_shared_payload_excludes_exports_and_artwork_masters(self):
        module=runpy.run_path(str(ROOT/'scripts/application-payload.py'))
        selected=module['selected_files'](ROOT)
        self.assertTrue(any(name.startswith('docs/images/matrix/') for name in selected))
        self.assertIn('uno-q/virtualglove-early-start.service',selected)
        self.assertIn('scripts/measure-dot-input.py', selected)
        self.assertIn('scripts/measure-vision-status.py', selected)
        self.assertIn('scripts/calibrate-reach.py', selected)
        self.assertIn('docs/ENGINEERING_TOOLKIT.md', selected)
        self.assertIn('output/pdf/VirtualGlove-Engineering-Toolkit.pdf', selected)
        self.assertNotIn('scripts/benchmark-vision-replay.py', selected)
        self.assertNotIn('scripts/run-nestopia-powerglove-trace.py', selected)
        development=module['selected_files'](ROOT, include_engineering=True)
        self.assertIn('scripts/benchmark-vision-replay.py', development)
        self.assertIn('scripts/run-nestopia-powerglove-trace.py', development)
        self.assertFalse(any(name.startswith(('output/install/','assets/matrix/')) for name in selected))
        self.assertEqual(
            sorted(name for name in selected if name.endswith('.zip')),
            [
                'hardware/enclosures/bundles/VirtualGlove-Controller-Dock-V1-Print-Files.zip',
                'hardware/enclosures/bundles/VirtualGlove-Controller-Dock-V2-Print-Files.zip',
                'hardware/enclosures/bundles/VirtualGlove-UNO-Q-Case-Print-Files.zip',
            ],
        )
        generators=runpy.run_path(str(ROOT/'scripts/build-installer-scripts.py'))
        for machine in ('uno-q','retropie','recalbox','batocera'):
            self.assertEqual(generators['render'](machine),
                             (ROOT/f'scripts/install-{machine}.sh').read_text())
