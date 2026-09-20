# Project: VirtualGlove
# File: tests/test_kiyo_camera.py
# Purpose: Verify narrow Kiyo controls and opt-in camera configuration.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Test descriptor bounds, HDR command, exposure verification, and camera identity.
# Full history: docs/CHANGELOG.md and Git history.

"""Camera commands must be bounded, model-specific, and never save onboard."""

import ctypes
from pathlib import Path
import runpy
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from virtualglove import kiyo_camera as kiyo
from virtualglove import camera_controls
from virtualglove.vision_app import (
    _camera_rate_attempts, _first_direct_frame, _open_camera, build_parser,
)


class KiyoTests(unittest.TestCase):
    def test_direct_startup_retries_transient_invalid_frames(self):
        expected = object()

        class Source:
            def __init__(self):
                self.reads = 0

            def read_with_timestamp(self):
                self.reads += 1
                if self.reads == 1:
                    raise RuntimeError('camera marked the direct MJPEG frame invalid')
                if self.reads == 2:
                    return False, None, 1.0
                return True, expected, 2.5

        source = Source()
        frame, captured_at = _first_direct_frame(source, timeout=1.0)
        self.assertIs(frame, expected)
        self.assertEqual(captured_at, 2.5)
        self.assertEqual(source.reads, 3)

    def test_process_capture_does_not_warm_a_frame_in_parent(self):
        class Candidate:
            def __init__(self):
                self.released = False

            def set(self, _name, _value):
                return True

            def get(self, name):
                return {
                    fake_cv2.CAP_PROP_FOURCC: int.from_bytes(b'MJPG', 'little'),
                    fake_cv2.CAP_PROP_FRAME_WIDTH: 640,
                    fake_cv2.CAP_PROP_FRAME_HEIGHT: 480,
                    fake_cv2.CAP_PROP_FPS: 30,
                    fake_cv2.CAP_PROP_BUFFERSIZE: 2,
                }[name]

            def read(self):
                raise AssertionError('parent must not dequeue a process-isolated frame')

            def release(self):
                self.released = True

        candidate = Candidate()
        fake_cv2 = SimpleNamespace(
            CAP_V4L2=200,
            CAP_ANY=0,
            CAP_PROP_FOURCC=6,
            CAP_PROP_FRAME_WIDTH=3,
            CAP_PROP_FRAME_HEIGHT=4,
            CAP_PROP_FPS=5,
            CAP_PROP_BUFFERSIZE=38,
            VideoWriter_fourcc=lambda *letters: int.from_bytes(
                ''.join(letters).encode(), 'little'
            ),
            VideoCapture=lambda _device, _backend: candidate,
        )
        isolated = MagicMock()
        isolated.metadata = {}
        args = SimpleNamespace(
            camera='auto', camera_manual_exposure_test=None,
            camera_manual_gain_test=None, camera_manual_exposure=78,
            camera_manual_gain=96, camera_exposure='manual',
            capture_backend='direct-v4l2', capture_isolation='process',
            camera_format='MJPG', width=640, height=480, fps=30,
            camera_buffers=2, kiyo_hdr_off=False,
        )
        with patch.dict('sys.modules', {'cv2': fake_cv2}), \
             patch('virtualglove.vision_app.camera_candidates',
                   return_value=['/dev/video0']), \
             patch('virtualglove.vision_app.sys.platform', 'linux'), \
             patch('virtualglove.process_capture.ProcessDirectV4L2Capture',
                   return_value=isolated) as process_capture:
            returned_cv2, returned_capture = _open_camera(args)
        self.assertIs(returned_cv2, fake_cv2)
        self.assertIs(returned_capture, isolated)
        self.assertTrue(candidate.released)
        process_capture.assert_called_once()

    def test_process_opencv_opens_only_in_child(self):
        fake_cv2 = SimpleNamespace(CAP_V4L2=200, CAP_ANY=0)
        isolated = MagicMock()
        isolated.metadata = {}
        args = SimpleNamespace(
            camera='auto', camera_manual_exposure_test=None,
            camera_manual_gain_test=None, camera_manual_exposure=78,
            camera_manual_gain=96, camera_exposure='auto',
            capture_backend='opencv', capture_isolation='process',
            camera_format='MJPG', width=640, height=480, fps=30,
            camera_buffers=1, kiyo_hdr_off=False,
        )
        with patch.dict('sys.modules', {'cv2': fake_cv2}), \
             patch('virtualglove.vision_app.camera_candidates',
                   return_value=['/dev/video0']), \
             patch('virtualglove.vision_app.sys.platform', 'linux'), \
             patch('virtualglove.process_capture.ProcessOpenCVCapture',
                   return_value=isolated) as process_capture:
            returned_cv2, returned_capture = _open_camera(args)
        self.assertIs(returned_cv2, fake_cv2)
        self.assertIs(returned_capture, isolated)
        process_capture.assert_called_once()

    def test_descriptor_identity_and_invalid_lengths(self):
        descriptor=bytes([20,0x24,6,7])+kiyo.GUID
        self.assertEqual(kiyo.extension_unit(bytes([2,1])+descriptor),7)
        for data in (b'',b'\0\1',b'\x20\x24',bytes([20,0x24,6,7])+bytes(16)):
            with self.assertRaises(ValueError): kiyo.extension_unit(data)

    def test_only_hdr_off_and_standard_exposure_commands_are_sent(self):
        commands=[]
        def ioctl(fd,request,data):
            if isinstance(data,kiyo.ExtensionQuery):
                if data.query==0x85: ctypes.c_uint16.from_address(data.data).value=8
                else: commands.append(ctypes.string_at(data.data,data.size))
            elif request==0xc008561c: commands.append(struct.unpack('Ii',data))
            else:
                control,_=struct.unpack('Ii',data)
                struct.pack_into('i',data,4,3 if control==kiyo.AUTO_EXPOSURE else 0)
        kiyo.apply_controls(3,7,ioctl)
        self.assertEqual(commands,[bytes.fromhex('ff02000000000000'),(kiyo.AUTO_EXPOSURE,3),(kiyo.DYNAMIC_FRAMERATE,0)])

    def test_unexpected_control_length_never_writes(self):
        for size in (0,7,65,65535):
            calls=[]
            def ioctl(fd,request,data):
                calls.append(data.query)
                ctypes.c_uint16.from_address(data.data).value=size
            with self.assertRaises(ValueError): kiyo.apply_controls(3,7,ioctl)
            self.assertEqual(calls,[0x85])

    def test_other_cameras_are_not_opened_for_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            usb=Path(directory);(usb/'idVendor').write_text('1234');(usb/'idProduct').write_text('0e05')
            camera=usb/'video4linux';camera.mkdir();(camera/'video2').mkdir()
            with patch.object(kiyo.sys,'platform','linux'), patch.object(kiyo.os,'open') as opened:
                self.assertFalse(kiyo.configure_kiyo('/dev/video2',camera))
                opened.assert_not_called()

    def test_identity_can_be_checked_without_opening_camera(self):
        with tempfile.TemporaryDirectory() as directory:
            usb=Path(directory);(usb/'idVendor').write_text('1532');(usb/'idProduct').write_text('0e05')
            descriptor=bytes([20,0x24,6,7])+kiyo.GUID
            (usb/'descriptors').write_bytes(descriptor)
            camera=usb/'video4linux';camera.mkdir();(camera/'video2').mkdir()
            with patch.object(kiyo.sys,'platform','linux'), patch.object(kiyo.os,'open') as opened:
                self.assertEqual(kiyo.kiyo_extension_unit('/dev/video2',camera),7)
                opened.assert_not_called()

    def test_controls_stay_opt_in_and_supervisor_passes_config(self):
        args=build_parser().parse_args(['--receiver','test','--token','x'*16])
        self.assertEqual(args.camera_buffers,1);self.assertFalse(args.kiyo_hdr_off)
        root=Path(__file__).resolve().parents[1]
        command=runpy.run_path(str(root/'python/main.py'))['worker_command']
        original=command({},Path('/tmp/model'))
        self.assertNotIn('--camera-buffers',original);self.assertNotIn('--kiyo-hdr-off',original)
        candidate=command({'camera_buffers':2,'kiyo_hdr_off':True},Path('/tmp/model'))
        self.assertEqual(candidate[candidate.index('--camera-buffers')+1],'2')
        self.assertEqual(candidate[candidate.index('--camera-exposure')+1],
                         'kiyo-low-latency')
        self.assertEqual(candidate[candidate.index('--inference-threads')+1], '4')
        self.assertEqual(candidate[candidate.index('--tracking-confidence')+1], '0.35')
        self.assertEqual(candidate[candidate.index('--tracking-roi-scale')+1], '2.25')
        self.assertEqual(candidate[candidate.index('--fps')+1], '0')
        tuned=command({'tracking_confidence':.45},Path('/tmp/model'))
        self.assertEqual(tuned[tuned.index('--tracking-confidence')+1], '0.45')
        roi=command({'tracking_roi_scale':2.25},Path('/tmp/model'))
        self.assertEqual(roi[roi.index('--tracking-roi-scale')+1], '2.25')
        self.assertEqual(command({'camera_fps':30},Path('/tmp/model'))[
            command({'camera_fps':30},Path('/tmp/model')).index('--fps')+1], '30')
        self.assertEqual(command({'camera_fps':25},Path('/tmp/model'))[
            command({'camera_fps':25},Path('/tmp/model')).index('--fps')+1], '0')
        direct=command({'camera_backend':'direct-v4l2',
                        'camera_exposure':'low-latency',
                        'tracker_graph':'lean-image'},Path('/tmp/model'))
        self.assertEqual(direct[direct.index('--capture-backend')+1], 'direct-v4l2')
        self.assertEqual(direct[direct.index('--camera-exposure')+1], 'low-latency')
        self.assertEqual(direct[direct.index('--tracker-graph')+1], 'lean-image')

    def test_complete_worker_cache_is_preferred_offline(self):
        root=Path(__file__).resolve().parents[1]
        namespace=runpy.run_path(str(root/'python/main.py'))
        environment={'UV_CACHE_DIR':'/cache'}
        with patch.object(namespace['subprocess'], 'run',
                          return_value=SimpleNamespace(returncode=0)) as probe:
            selected=namespace['prefer_retained_worker_cache'](environment)
        self.assertEqual(selected['UV_OFFLINE'], '1')
        self.assertNotIn('UV_OFFLINE', environment)
        self.assertEqual(probe.call_args[1]['env']['UV_OFFLINE'], '1')

    def test_incomplete_worker_cache_preserves_online_fallback(self):
        root=Path(__file__).resolve().parents[1]
        namespace=runpy.run_path(str(root/'python/main.py'))
        environment={'UV_CACHE_DIR':'/cache'}
        for outcome in (SimpleNamespace(returncode=1),
                        __import__('subprocess').TimeoutExpired('uv', 30)):
            with self.subTest(outcome=type(outcome).__name__):
                with patch.object(namespace['subprocess'], 'run',
                                  side_effect=outcome if isinstance(outcome, Exception) else None,
                                  return_value=None if isinstance(outcome, Exception) else outcome):
                    selected=namespace['prefer_retained_worker_cache'](environment)
                self.assertIs(selected, environment)
                self.assertNotIn('UV_OFFLINE', selected)

    def test_manual_exposure_test_requires_valid_pair_and_direct_capture(self):
        root=Path(__file__).resolve().parents[1]
        command=runpy.run_path(str(root/'python/main.py'))['worker_command']
        valid=command({'camera_backend':'direct-v4l2',
                       'camera_manual_exposure_test':78,
                       'camera_manual_gain_test':96},Path('/tmp/model'))
        self.assertEqual(valid[valid.index('--camera-manual-exposure-test')+1],'78')
        self.assertEqual(valid[valid.index('--camera-manual-gain-test')+1],'96')
        for settings in (
            {'camera_backend':'opencv','camera_manual_exposure_test':78,
             'camera_manual_gain_test':96},
            {'camera_backend':'direct-v4l2','camera_manual_exposure_test':78},
            {'camera_backend':'direct-v4l2','camera_manual_exposure_test':'78',
             'camera_manual_gain_test':96},
            {'camera_backend':'direct-v4l2','camera_manual_exposure_test':0,
             'camera_manual_gain_test':96},
        ):
            candidate=command(settings,Path('/tmp/model'))
            self.assertNotIn('--camera-manual-exposure-test',candidate)
            self.assertNotIn('--camera-manual-gain-test',candidate)

    def test_saved_manual_exposure_uses_production_flags(self):
        root=Path(__file__).resolve().parents[1]
        command=runpy.run_path(str(root/'python/main.py'))['worker_command']
        manual=command({'camera_backend':'direct-v4l2','camera_exposure':'manual',
                        'camera_manual_exposure':78,'camera_manual_gain':96},
                       Path('/tmp/model'))
        self.assertEqual(manual[manual.index('--camera-exposure')+1],'manual')
        self.assertEqual(manual[manual.index('--camera-manual-exposure')+1],'78')
        self.assertEqual(manual[manual.index('--camera-manual-gain')+1],'96')
        for settings in (
            {'camera_backend':'opencv','camera_exposure':'manual',
             'camera_manual_exposure':78,'camera_manual_gain':96},
            {'camera_backend':'direct-v4l2','camera_exposure':'manual',
             'camera_manual_exposure':78},
        ):
            candidate=command(settings,Path('/tmp/model'))
            self.assertEqual(candidate[candidate.index('--camera-exposure')+1],'auto')
            self.assertNotIn('--camera-manual-exposure',candidate)

    def test_manual_report_includes_advertised_limits(self):
        controls=(camera_controls.EXPOSURE_AUTO,
                  camera_controls.EXPOSURE_AUTO_PRIORITY,
                  camera_controls.EXPOSURE_ABSOLUTE,camera_controls.GAIN)
        values={control:3 if control==camera_controls.EXPOSURE_AUTO else 0
                for control in controls}
        def ioctl(_fd,request,data):
            control=struct.unpack_from('I',data,0)[0]
            if request==camera_controls.VIDIOC_QUERYCTRL:
                struct.pack_into('II',data,0,control,1)
                minimum,maximum,default=(1,1000,100) if control==camera_controls.EXPOSURE_ABSOLUTE else (0,255,0)
                struct.pack_into('iiii',data,40,minimum,maximum,1,default)
                struct.pack_into('I',data,56,0)
            elif request==camera_controls.VIDIOC_S_CTRL:
                _,value=struct.unpack('Ii',data);values[control]=value
            elif request==camera_controls.VIDIOC_G_CTRL:
                struct.pack_into('i',data,4,values[control])
        report=camera_controls.configure_manual_on_fd(7,78,96,ioctl)
        self.assertTrue(report['applied'])
        self.assertEqual(report['limits']['exposure'],
                         {'minimum':1,'maximum':1000,'step':1,'default':100})
        self.assertEqual(report['limits']['gain'],
                         {'minimum':0,'maximum':255,'step':1,'default':0})

    def test_standard_low_latency_controls_are_queried_before_writes(self):
        values={camera_controls.EXPOSURE_AUTO:3,
                camera_controls.EXPOSURE_AUTO_PRIORITY:1}
        writes=[]
        def ioctl(_fd,request,data):
            control=struct.unpack_from('I',data,0)[0]
            if request==camera_controls.VIDIOC_QUERYCTRL:
                struct.pack_into('II',data,0,control,1)
                data[8:16]=b'exposure'
                struct.pack_into('iiii',data,40,0,3,1,1)
                struct.pack_into('I',data,56,0)
            elif request==camera_controls.VIDIOC_S_CTRL:
                _,value=struct.unpack('Ii',data);values[control]=value;writes.append((control,value))
            elif request==camera_controls.VIDIOC_G_CTRL:
                struct.pack_into('i',data,4,values[control])
        with patch.object(camera_controls.sys,'platform','linux'), \
             patch.object(camera_controls.os,'open',return_value=7), \
             patch.object(camera_controls.os,'close'):
            report=camera_controls.configure_low_latency('/dev/video2',ioctl)
        self.assertTrue(report['applied'])
        self.assertEqual(writes,[(camera_controls.EXPOSURE_AUTO,3),
                                 (camera_controls.EXPOSURE_AUTO_PRIORITY,0)])

    def test_unsupported_standard_controls_never_write(self):
        writes=[]
        def ioctl(_fd,request,_data):
            if request==camera_controls.VIDIOC_QUERYCTRL:raise OSError('unsupported')
            writes.append(request)
        with patch.object(camera_controls.sys,'platform','linux'), \
             patch.object(camera_controls.os,'open',return_value=7), \
             patch.object(camera_controls.os,'close'):
            report=camera_controls.configure_low_latency('/dev/video9',ioctl)
        self.assertFalse(report['supported']);self.assertEqual(writes,[])

    def test_manual_active_stream_queries_every_control_before_writing(self):
        controls=(camera_controls.EXPOSURE_AUTO,
                  camera_controls.EXPOSURE_AUTO_PRIORITY,
                  camera_controls.EXPOSURE_ABSOLUTE,camera_controls.GAIN)
        values={control:3 if control==camera_controls.EXPOSURE_AUTO else 0
                for control in controls}
        events=[]
        def ioctl(_fd,request,data):
            control=struct.unpack_from('I',data,0)[0]
            if request==camera_controls.VIDIOC_QUERYCTRL:
                events.append(('query',control))
                struct.pack_into('II',data,0,control,1);data[8:16]=b'control'
                struct.pack_into('iiii',data,40,0,1000,1,0)
                struct.pack_into('I',data,56,0)
            elif request==camera_controls.VIDIOC_S_CTRL:
                _,value=struct.unpack('Ii',data);values[control]=value
                events.append(('write',control,value))
            elif request==camera_controls.VIDIOC_G_CTRL:
                struct.pack_into('i',data,4,values[control])
        report=camera_controls.configure_manual_on_fd(7,78,96,ioctl)
        self.assertTrue(report['applied'])
        self.assertEqual([item[1] for item in events[:4]],list(controls))
        self.assertTrue(all(item[0]=='query' for item in events[:4]))
        self.assertEqual([item for item in events if item[0]=='write'],[
            ('write',camera_controls.EXPOSURE_AUTO_PRIORITY,0),
            ('write',camera_controls.EXPOSURE_AUTO,1),
            ('write',camera_controls.EXPOSURE_ABSOLUTE,78),
            ('write',camera_controls.GAIN,96),
        ])

    def test_manual_active_stream_restores_automatic(self):
        queried={}
        writes=[]
        def ioctl(_fd,request,data):
            control=struct.unpack_from('I',data,0)[0]
            if request==camera_controls.VIDIOC_QUERYCTRL:
                queried[control]=True;struct.pack_into('II',data,0,control,1)
                struct.pack_into('iiii',data,40,0,3,1,0);struct.pack_into('I',data,56,0)
            elif request==camera_controls.VIDIOC_S_CTRL:
                _,value=struct.unpack('Ii',data);writes.append((control,value))
            elif request==camera_controls.VIDIOC_G_CTRL:
                struct.pack_into('i',data,4,writes[-1][1])
        self.assertTrue(camera_controls.restore_automatic_on_fd(7,ioctl))
        self.assertEqual(writes,[(camera_controls.EXPOSURE_AUTO,3),
                                 (camera_controls.EXPOSURE_AUTO_PRIORITY,0)])

    def test_every_camera_rate_falls_back_to_driver_negotiation(self):
        self.assertEqual(_camera_rate_attempts(0), (30, None))
        self.assertEqual(_camera_rate_attempts(30), (30, None))
        self.assertEqual(_camera_rate_attempts(60), (60, None))
