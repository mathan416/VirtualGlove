# Project: VirtualGlove
# File: tests/test_latency_diagnostics.py
# Purpose: Verify finite timing traces and reject misleading physical latency evidence.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Required one neutral window and FCEUmm baseline labeling.
#   2026-09-08 - Cover session preflight gates and guided video review helpers.
#   2026-09-07 - Cover receiver-to-native publication timing.
#   2026-09-06 - Cover drops, clock separation, session reuse, and video timing brackets.
# Full history: docs/CHANGELOG.md and Git history.

"""Test diagnostics independently of cameras and game ROMs."""
import importlib.util
import json
import os
import shutil
import signal
import socket
import sys
import time
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from virtualglove.diagnostic_trace import DiagnosticTrace, session_key
from virtualglove.transport import UdpSender
from virtualglove.model import ControllerState
from virtualglove.native_state import decode_record

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trace_analysis = load('analyze-latency-trace')
video_analysis = load('analyze-latency-video')
measure = load('measure-vision-status')
preflight = load('prepare-end-to-end-session')
trace_manager = load('manage-latency-traces')
session_runner = load('run-native-latency-session')


class DiagnosticTests(unittest.TestCase):
    def test_guided_session_supports_all_three_delivery_baselines(self):
        source = (ROOT/'scripts'/'run-native-latency-session.py').read_text()
        self.assertIn("choices=('native', 'dot', 'fceumm')", source)
        self.assertIn('neutral_count = 1', source)
        self.assertNotIn("neutral_count = 1 if args.protocol == 'smoke' else 3", source)

    def test_guided_session_uses_lightweight_status_polling(self):
        report = {'observed_samples':1, 'request_errors':0,
                  'segments':[{'stationary_candidate':True}]}
        with tempfile.TemporaryDirectory() as folder, \
                patch('builtins.input', return_value=''), \
                patch.object(session_runner.time, 'sleep'), \
                patch.object(session_runner.measurement, 'collect', return_value=report) as collect:
            session_runner.collect_window(
                'http://controller/status', Path(folder)/'neutral.json',
                'neutral', 'neutral', 1, poll_interval=.25,
            )
        collect.assert_called_once_with('http://controller/status', 1, .25, 'neutral')

    def test_trace_manager_builds_bounded_ssh_command_and_private_state(self):
        command = trace_manager.ssh_command('pi@10.0.2.37', Path('/tmp/key'),
                                            'retropieconsole.local')
        self.assertEqual(command[-1], 'pi@10.0.2.37')
        self.assertIn('HostKeyAlias=retropieconsole.local', command)
        self.assertIn('APP_HOME', trace_manager.CONTROLLER_START)
        self.assertIn('APP_HOME', trace_manager.CONTROLLER_STOP)
        self.assertIn('controller_was_enabled', trace_manager.CONTROLLER_START)
        self.assertIn('controller_rearmed', trace_manager.CONTROLLER_STOP)
        self.assertIn('KillSignal=SIGINT', trace_manager.RETROPIE_START)
        self.assertIn('retroarch_running', trace_manager.RETROPIE_PREFLIGHT)
        self.assertIn('Receiver trace did not flush', trace_manager.RETROPIE_STOP)
        self.assertLess(trace_manager.RETROPIE_STOP.index("'stop','virtualglove-receiver.service'"),
                        trace_manager.RETROPIE_STOP.index("'rm','-f',drop"))
        self.assertIn("('VIRTUALGLOVE_DIAGNOSTIC_TRACE=%s/receiver' % folder) not in shown",
                      trace_manager.RETROPIE_STOP)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)/'state.json'
            trace_manager.save_state(destination, {'format':'test'})
            self.assertEqual(json.loads(destination.read_text()), {'format':'test'})
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                trace_manager.save_state(destination, {'format':'again'})

    def test_preflight_selects_only_safe_status_and_applies_fixed_gates(self):
        status = dict(worker_running=True, camera_available=True, calibrated=True,
            tracker_backend='legacy', tracker_graph='full',
            camera_width=640, camera_height=480, camera_format='MJPG', camera_fps=30.0,
            build={'commit':'a'*40}, token='must-not-survive', active_player='player-id')
        selected = {key: status.get(key) for key in preflight.STATUS_FIELDS if key in status}
        self.assertNotIn('token', selected)
        self.assertNotIn('active_player', selected)
        checks = preflight.evaluate(selected, {'disk_free_bytes':2**30},
            {'disk_free_bytes':2**30, 'files':{'core_sha256':'b'*64},
             'native_state':{'present':True,'size':64}, 'retroarch_running':False},
            {'commit':'a'*40,'dirty':False})
        failed = {item['name']:item['severity'] for item in checks if not item['passed']}
        self.assertEqual(failed, {})

    def test_prepare_preflight_rejects_running_emulator_before_receiver_restart(self):
        status = dict(worker_running=True, camera_available=False, calibrated=False,
            tracker_backend='legacy', tracker_graph='full',
            camera_width=640, camera_height=480, camera_format='MJPG', camera_fps=30,
            build={'commit':'a'*40})
        controller = {'disk_free_bytes':2**30, 'files':{'calibration_present':True}}
        retropie = {'disk_free_bytes':2**30, 'files':{'core_sha256':'b'*64},
                    'native_state':{'present':True,'size':64}, 'retroarch_running':True}
        checks = preflight.evaluate(status, controller, retropie,
                                    {'commit':'a'*40,'dirty':False})
        errors = {item['name'] for item in checks
                  if not item['passed'] and item['severity'] == 'error'}
        self.assertEqual(errors, {'RetroArch is closed before trace setup'})

    def test_preflight_rejects_wrong_camera_and_missing_native_abi(self):
        status = dict(worker_running=True, camera_available=True, calibrated=True,
            tracker_backend='legacy', tracker_graph='full',
            camera_width=1280, camera_height=720, camera_format='MJPG', camera_fps=60)
        checks = preflight.evaluate(status, {'disk_free_bytes':2**30},
            {'disk_free_bytes':2**30, 'files':{}, 'native_state':{'present':False}},
            {'commit':'a'*40,'dirty':False}, require_gameplay=True)
        errors = {item['name'] for item in checks
                  if not item['passed'] and item['severity'] == 'error'}
        self.assertIn('camera is configured for 640x480 MJPEG', errors)
        self.assertIn('camera is configured for 30 fps', errors)
        self.assertIn('native state ABI is present', errors)

    def test_record_preflight_requires_live_calibration_not_only_a_saved_file(self):
        status = dict(worker_running=True, camera_available=True, calibrated=False,
            tracker_backend='legacy', tracker_graph='full',
            camera_width=640, camera_height=480, camera_format='MJPG', camera_fps=30)
        controller = {'disk_free_bytes':2**30, 'files':{'calibration_present':True}}
        retropie = {'disk_free_bytes':2**30, 'files':{'core_sha256':'b'*64},
                    'native_state':{'present':True,'size':64}, 'retroarch_running':True}
        checks = preflight.evaluate(status, controller, retropie,
                                    {'commit':'a'*40,'dirty':False}, require_gameplay=True)
        errors = {item['name'] for item in checks
                  if not item['passed'] and item['severity'] == 'error'}
        self.assertIn('player calibration is available', errors)

    def test_record_preflight_warns_for_local_tools_but_rejects_runtime_mismatch(self):
        status = dict(worker_running=True, camera_available=True, calibrated=True,
            tracker_backend='legacy', tracker_graph='full',
            camera_width=640, camera_height=480, camera_format='MJPG', camera_fps=30,
            build={'commit':'a'*40})
        controller = {'disk_free_bytes':2**30}
        retropie = {'disk_free_bytes':2**30, 'files':{'core_sha256':'b'*64},
                    'native_state':{'present':True,'size':64}, 'retroarch_running':True}
        checks = preflight.evaluate(status, controller, retropie,
                                    {'commit':'c'*40,'dirty':True}, require_gameplay=True)
        failed = {item['name']:item['severity'] for item in checks if not item['passed']}
        self.assertEqual(failed, {
            'source checkout is clean':'warning',
            'deployed Controller commit matches checkout':'error',
        })

    def test_recalbox_batocera_preflight_uses_merged_fceumm_path(self):
        status = dict(worker_running=True, camera_available=True, calibrated=True,
                      build={'commit': 'a'*40})
        controller = {'disk_free_bytes': 2**30}
        source = {'commit': 'a'*40, 'dirty': False}
        for platform in ('recalbox', 'batocera'):
            console = {'role': platform, 'disk_free_bytes': 2**30,
                       'installation_present': True,
                       'files': {'fceumm_sha256': 'b'*64, 'router_sha256': 'c'*64},
                       'router': {'platform': platform}, 'merged_input_devices': 1,
                       'router_check': {'safe': True, 'enabled_players': [1],
                                        'missing_source_count': 0},
                       'services': {'virtualglove': {'output':
                           'RUNNING controller_router\nRUNNING receiver'}},
                       'retroarch_running': True, 'active_core': 'fceumm_libretro.so'}
            checks = preflight.evaluate_merged_console(status, controller, console,
                                                       source, require_gameplay=True)
            self.assertFalse([check for check in checks if not check['passed']])
            console['active_core'] = 'nestopia_libretro.so'
            failed = {check['name'] for check in preflight.evaluate_merged_console(
                status, controller, console, source, require_gameplay=True)
                if not check['passed'] and check['severity'] == 'error'}
            self.assertEqual(failed, {'FCEUmm is the active core'})

    def test_merged_preflight_prepare_does_not_require_a_running_game(self):
        checks = preflight.evaluate_merged_console(
            {'worker_running': True, 'camera_available': False, 'calibrated': False},
            {'disk_free_bytes': 2**30},
            {'role': 'batocera', 'disk_free_bytes': 2**30,
             'installation_present': True,
             'files': {'fceumm_sha256': 'b'*64, 'router_sha256': 'c'*64},
             'router': {'platform': 'batocera'}, 'merged_input_devices': 1,
             'router_check': {'safe': True, 'enabled_players': [1],
                              'missing_source_count': 0},
             'services': {'virtualglove': {'output': 'RUNNING controller_router'}},
             'retroarch_running': False},
            {'commit': 'a'*40, 'dirty': False})
        failed = {check['name']: check['severity'] for check in checks if not check['passed']}
        self.assertEqual(failed, {'camera is available': 'warning',
                                  'player calibration is available': 'warning',
                                  'receiver process is running': 'warning',
                                  'deployed Controller commit matches checkout': 'warning'})

    def test_batocera_preflight_flags_wifi_buffering_and_missing_install(self):
        console = {'role': 'batocera', 'disk_free_bytes': 2**30,
                   'installation_present': False, 'files': {}, 'router': {},
                   'router_check': {}, 'merged_input_devices': 0,
                   'services': {'virtualglove': {'output': ''}},
                   'connected_wifi': [{'interface': 'wlan0',
                                       'power_save': 'Power save: on'}]}
        checks = preflight.evaluate_merged_console(
            {'worker_running': True}, {'disk_free_bytes': 2**30}, console,
            {'commit': 'a'*40, 'dirty': False})
        failed = {check['name']: check['severity'] for check in checks
                  if not check['passed']}
        self.assertEqual(failed['VirtualGlove console installation is present'], 'error')
        self.assertEqual(failed['Batocera connected Wi-Fi power saving is off'], 'warning')

    def test_batocera_preflight_writes_platform_record_without_legacy_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'batocera'
            status = {'worker_running': True, 'camera_available': True,
                      'calibrated': True, 'build': {'commit': 'a'*40}}
            controller = {'role': 'controller', 'disk_free_bytes': 2**30}
            console = {'role': 'batocera', 'disk_free_bytes': 2**30,
                       'installation_present': True,
                       'files': {'fceumm_sha256': 'b'*64, 'router_sha256': 'c'*64},
                       'router': {'platform': 'batocera'}, 'merged_input_devices': 1,
                       'router_check': {'safe': True},
                       'services': {'virtualglove': {'output':
                           'RUNNING controller_router\nRUNNING receiver'}},
                       'retroarch_running': False}
            arguments = ['prepare-end-to-end-session.py',
                         '--controller-status', 'http://controller/status?statistics=1',
                         '--controller-ssh', 'arduino@controller',
                         '--console-platform', 'batocera', '--console-ssh', 'root@console',
                         '--output-dir', str(destination)]
            with patch.object(sys, 'argv', arguments), \
                 patch.object(preflight, 'fetch_status', return_value=status), \
                 patch.object(preflight, 'git_identity', return_value={
                     'commit': 'a'*40, 'dirty': False}), \
                 patch.object(preflight, 'inspect_remote', side_effect=[controller, console]) as remote:
                self.assertEqual(preflight.main(), 0)
            self.assertEqual([call.args[2] for call in remote.call_args_list],
                             ['controller', 'batocera'])
            report = json.loads((destination / 'preflight.json').read_text())
            self.assertEqual(report['format'], 'virtualglove-end-to-end-preflight/2')
            self.assertEqual(report['console_platform'], 'batocera')
            self.assertEqual(report['console_host']['role'], 'batocera')
            self.assertNotIn('retropie_host', report)
            self.assertEqual((destination / 'preflight.json').stat().st_mode & 0o777, 0o600)

    def test_video_review_selection_and_template_are_bounded(self):
        self.assertEqual(video_analysis.review_selection(20, around='10', radius=2),
                         {8, 9, 10, 11, 12})
        overview = video_analysis.review_selection(100, overview=5)
        self.assertEqual(overview, {0, 25, 50, 74, 99})
        template = video_analysis.annotation_template('a'*64, 'smoke')
        self.assertFalse(template['timing_verified'])
        self.assertEqual(len(template['trials']), 4)
        self.assertTrue(all(item['hand_onset'] is None for item in template['trials']))
        with self.assertRaises(ValueError):
            video_analysis.review_selection(10, explicit='10')

        slow_motion = video_analysis.annotation_template('c'*64, 'smoke', .25, 120)
        self.assertEqual(slow_motion['capture_fps_reported'], 120)
        self.assertEqual(slow_motion['seconds_per_pts_second'], .25)
        self.assertFalse(slow_motion['timing_verified'])

    def test_confidence_source_changes_do_not_split_tracking_segment(self):
        window = measure.StatusWindow('movement')
        for index, (detected, source) in enumerate(((True, 'handedness'),
                                                     (False, 'generic'),
                                                     (True, 'handedness'))):
            window.observe(dict(vision_state='active', timestamp=index+1,
                capture_sequence=index+1, detected=detected, calibrated=True,
                confidence_source=source), 1)
        report = window.report(3)
        self.assertEqual(len(report['segments']), 1)
        self.assertEqual(report['segments'][0]['tracking_losses'], 1)
        self.assertEqual(report['segments'][0]['confidence_source_samples'],
                         {'handedness':2, 'generic':1})

    def test_video_review_template_requires_explicit_human_approval(self):
        template = video_analysis.annotation_template('b'*64, 'full')
        self.assertEqual(len(template['trials']), 40)
        self.assertFalse(template['timing_verified'])
        self.assertTrue(all(item['unoccluded'] is False for item in template['trials']))
        self.assertTrue(all(item['game_onset'] is None for item in template['trials']))

    def test_disabled_does_not_open_files_or_start_thread(self):
        with patch.dict(os.environ, {}, clear=True), patch('os.open') as opened:
            self.assertIsNone(DiagnosticTrace.from_environment('controller'))
            opened.assert_not_called()

    def test_finite_private_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'trace.json'
            trace = DiagnosticTrace(path, 'controller', capacity=2)
            trace.record({'event':'one'})
            trace.record({'event':'two'})
            trace.record({'event':'three'})
            trace.close()
            report = json.loads(path.read_text())
            self.assertEqual(len(report['events']), 2)
            self.assertEqual(report['dropped'], 1)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                DiagnosticTrace(path, 'controller')

    def test_contention_drops_without_waiting_and_deadline_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            trace = DiagnosticTrace(Path(folder)/'trace', 'controller')
            trace.lock.acquire()
            try:
                trace.record({'event':'busy'})
            finally:
                trace.lock.release()
            self.assertEqual(trace.dropped, 1)
            trace.record({'event':'first'})
            trace.deadline_ns = 0
            trace.record({'event':'expired'})
            trace.close()
            self.assertFalse(trace.enabled)

    def test_duration_begins_with_first_event_not_trace_preparation(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('virtualglove.diagnostic_trace.time.monotonic_ns',
                       side_effect=(100, 10_000, 10_001, 10_002)):
                trace = DiagnosticTrace(Path(folder)/'trace', 'controller', seconds=2)
                self.assertIsNone(trace.started_ns)
                self.assertIsNone(trace.deadline_ns)
                trace.record({'event':'first'})
                self.assertEqual(trace.started_ns,10_000)
                self.assertEqual(trace.deadline_ns,2_000_010_000)
                trace.close()

    def test_session_hash_is_stable_but_not_raw_identifier(self):
        self.assertEqual(session_key('a'*32), session_key('a'*32))
        self.assertNotEqual(session_key('a'*32), session_key('b'*32))
        self.assertNotEqual(session_key('a'*32), 'a'*32)

    def test_analysis_joins_resets_and_counts_first_consumption_only(self):
        controller = dict(format='virtualglove-diagnostic/1', role='controller', dropped=0, events=[
            dict(event='send', session=s, sequence=1, start_ns=100, end_ns=200) for s in ('a','b')])
        controller['events'].append(dict(event='vision', session='a', sequence=1, capture_ns=20,
            capture_ready_ns=25, start_ns=30, tracking_end_ns=50, end_ns=70))
        receiver = dict(format='virtualglove-diagnostic/1', role='receiver', dropped=0, events=[
            dict(event='receive', session=s, sequence=1, received_ns=900000000, validated_ns=900000100,
                 publication_start_ns=900000200, end_ns=900000400, published_ns=900000250+i,
                 native_start_ns=900000210, native_end_ns=900000260,
                 guard=2+i*2) for i,s in enumerate(('a','b'))])
        core = [dict(valid=1, sequence=1, guard=2, published_ns=900000250, consumed_ns=t)
                for t in (901000250, 902000250)]
        report = trace_analysis.analyze(controller, receiver, core)
        self.assertEqual(report['correlated_send_receive'], 2)
        self.assertIsNone(report['network_transit_ms'])
        self.assertAlmostEqual(report['timings_ms']['capture_timestamp_to_send']['p50'], .00018)
        self.assertAlmostEqual(report['timings_ms']['capture_read_to_send']['p50'], .000175)
        self.assertAlmostEqual(report['timings_ms']['processing_to_send_start']['p50'], .00003)
        self.assertAlmostEqual(
            report['timings_ms']['receiver_to_native_publication']['p50'], .00026
        )
        self.assertAlmostEqual(report['timings_ms']['native_write']['p50'], .00005)
        self.assertEqual(report['publications_without_observed_consumption'], 1)
        timing = report['timings_ms']['publication_record_to_first_core_consumption']
        self.assertEqual(timing['samples'], 1)
        self.assertEqual(timing['p50'], 1)

    def test_tracking_loss_invalidates_stationary_candidate(self):
        window = measure.StatusWindow('neutral')
        for i, detected in enumerate((True, False, True)):
            window.observe(dict(vision_state='active', timestamp=i+1, capture_sequence=i+1,
                detected=detected, calibrated=True, buttons={}, axes={'x':1,'y':2}), 1)
        segment = window.report(3)['segments'][0]
        self.assertEqual(segment['tracking_losses'], 1)
        self.assertFalse(segment['stationary_candidate'])
        self.assertEqual(segment['observation_interval_ms']['max'], 1000)

    def test_actual_sender_receiver_trace_correlates_session_resets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'token').write_text('diagnostic-test-token-only')
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            sock.close()
            env = dict(os.environ, VIRTUALGLOVE_DIAGNOSTIC_TRACE=str(root/'run'),
                       VIRTUALGLOVE_DIAGNOSTIC_SECONDS='10')
            process = subprocess.Popen([sys.executable, '-m', 'virtualglove.receiver',
                '--listen', '127.0.0.1', '--port', str(port), '--token-file', str(root/'token'),
                '--native-state', str(root/'native'), '--dry-run'], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                with patch.dict(os.environ, env):
                    sender = UdpSender('127.0.0.1', port, 'diagnostic-test-token-only')
                try:
                    for round_number in range(2):
                        if round_number:
                            sender.new_session()
                        deadline, sequence = time.monotonic()+3, 0
                        while time.monotonic() < deadline:
                            sequence += 1
                            state = ControllerState.released(sequence, time.monotonic(), 'super_glove_ball', True)
                            state.detected = True
                            state.axes['x'] = 100 + round_number
                            sender.send(state)
                            time.sleep(.02)
                            if (root/'native').exists():
                                try:
                                    record = decode_record((root/'native').read_bytes())
                                except ValueError:
                                    continue
                                if record['detected'] and record['axes']['x'] == 100+round_number:
                                    break
                        else:
                            self.fail('No authenticated publication')
                finally:
                    sender.close()
                process.send_signal(signal.SIGINT)
                process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
            controller = json.loads(next(root.glob('run.controller.*.json')).read_text())
            receiver = json.loads(next(root.glob('run.receiver.*.json')).read_text())
            report = trace_analysis.analyze(controller, receiver, [])
            self.assertGreaterEqual(report['correlated_send_receive'], 2)
            self.assertEqual(len({e['session'] for e in receiver['events']}), 2)
            self.assertEqual(report['invalid_intervals'], 0)
            self.assertNotIn('diagnostic-test-token-only', json.dumps([controller,receiver]))

    def test_video_brackets_and_occlusion(self):
        annotation = dict(timing_verified=True, trials=[
            dict(label='left-1', direction='left', unoccluded=True, hand_onset=2, game_onset=5),
            dict(label='hidden', unoccluded=False)])
        report, _ = video_analysis.analyze([i/100 for i in range(10)], annotation)
        self.assertAlmostEqual(report['trials'][0]['onset_ms'], 30)
        self.assertAlmostEqual(report['trials'][0]['onset_lower_ms'], 20)
        self.assertAlmostEqual(report['trials'][0]['onset_upper_ms'], 40)
        self.assertEqual(report['rejected_trials'], ['hidden'])

    def test_video_following_and_stationary_remain_separate(self):
        points = [dict(frame=i, hand_x=h, hand_y=10, glove_x=g, glove_y=20)
                  for i,h,g in ((1,0,0),(5,10,0),(10,10,10))]
        annotation = dict(timing_verified=True, trials=[dict(label='right', direction='right',
            unoccluded=True, hand_onset=2, game_onset=6, trajectory=points)],
            stationary=[dict(label='hold', unoccluded=True, tracking_losses=1, points=points)])
        report, _ = video_analysis.analyze([i/100 for i in range(20)], annotation)
        self.assertAlmostEqual(report['trials'][0]['following']['normalized_progress_error_rms'], (1/3)**.5)
        self.assertFalse(report['stationary'][0]['accepted'])
        self.assertEqual(report['stationary'][0]['hand_x']['span'], 10)

    def test_video_rejects_unverified_retiming_gaps_and_no_prior_frame(self):
        with self.assertRaises(ValueError):
            video_analysis.analyze([0,.01,.02], {})
        with self.assertRaises(ValueError):
            video_analysis.analyze([0,.01,.02,.06], dict(timing_verified=True))
        with self.assertRaises(ValueError):
            video_analysis.analyze([0,.01,.01], dict(timing_verified=True))
        with self.assertRaises(ValueError):
            video_analysis.analyze([0,.01,.02], dict(timing_verified=True, trials=[
                dict(label='bad', direction='left', unoccluded=True, hand_onset=0, game_onset=1)]))

    @unittest.skipUnless(shutil.which('c++'), 'C++ compiler unavailable')
    def test_native_buffer_exports_only_on_close_and_stays_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder/'test.cpp'
            source.write_text('#include "diagnostic_trace.h"\n#include <sys/stat.h>\n'
                'int main() { pgv_diagnostic_open(); for(int i=0;i<20003;i++) '
                'pgv_diagnostic_record(true, i, 2, 100); struct stat st; '
                'if(fstat(pgv_diagnostic_fd,&st) || st.st_size) return 2; '
                'pgv_diagnostic_close(); return 0; }')
            subprocess.run(['c++','-std=c++11','-I',str(ROOT/'native/nestopia-powerglove'),
                str(source),'-o',str(folder/'test')], check=True, capture_output=True)
            env = dict(os.environ, VIRTUALGLOVE_CORE_DIAGNOSTIC_TRACE=str(folder/'core.csv'))
            subprocess.run([str(folder/'test')], env=env, check=True)
            lines = (folder/'core.csv').read_text().splitlines()
            self.assertEqual(len(lines), 20002)
            self.assertEqual(lines[-1], '# dropped=3')
            self.assertEqual((folder/'core.csv').stat().st_mode & 0o777, 0o600)
