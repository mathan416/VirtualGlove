# Project: VirtualGlove
# File: tests/test_realtime.py
# Purpose: Verify newest-frame capture and non-blocking diagnostic preview work.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Covered Dashboard cadence and off-thread preview mirroring.
#   2026-09-07 - Allowed slower CI runners to schedule the capture thread.
#   2026-09-05 - Added low-latency camera and preview pipeline coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify the real-time pipeline without MediaPipe or camera hardware."""

import queue
import json
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from virtualglove.diagnostic_trace import DiagnosticTrace

from virtualglove.debug_server import SharedDebugState
from virtualglove.realtime import (
    DashboardCadence, LatestFrameCapture, LatestPreviewEncoder, LatestStatusPublisher,
    RollingPerformance,
)
from virtualglove.v4l2_capture import DirectV4L2Capture


class QueuedCapture:
    """Supply deterministic frames to the capture worker."""

    def __init__(self):
        self.frames = queue.Queue()
        self.released = False

    def read(self):
        return self.frames.get(timeout=1)

    def release(self):
        self.released = True
        self.frames.put((False, None))


class FakeJpeg:
    def __init__(self, payload):
        self.payload = payload

    def tobytes(self):
        return self.payload


class FakeCv2:
    FONT_HERSHEY_SIMPLEX = 0
    IMWRITE_JPEG_QUALITY = 1
    INTER_AREA = 3

    def __init__(self, encoded=b"jpeg"):
        self.encoded = encoded
        self.drawn = []

    def putText(self, frame, label, *_args):
        self.drawn.append((frame, label))

    def line(self, frame, start, end, *_args):
        self.drawn.append((frame, "line", start, end))

    def circle(self, frame, center, *_args):
        self.drawn.append((frame, "circle", center))

    def resize(self, _frame, size, **_kwargs):
        resized = SimpleNamespace(shape=(size[1], size[0], 3))
        self.drawn.append((resized, "resize", size))
        return resized

    def flip(self, frame, axis):
        mirrored = SimpleNamespace(shape=frame.shape)
        self.drawn.append((mirrored, "flip", axis))
        return mirrored

    def imencode(self, _extension, _frame, _options):
        return True, FakeJpeg(self.encoded)


class RealtimePipelineTests(unittest.TestCase):
    def test_dashboard_cadence_throttles_coordinates_but_publishes_events(self):
        cadence = DashboardCadence(10)
        self.assertTrue(cadence.due(1.0, ("tracking", False)))
        self.assertFalse(cadence.due(1.01, ("tracking", False)))
        self.assertTrue(cadence.due(1.02, ("tracking", True)))
        self.assertFalse(cadence.due(1.03, ("tracking", True)))
        self.assertTrue(cadence.due(1.13, ("tracking", True)))
        self.assertTrue(cadence.due(1.14, ("tracking", True), force=True))

    def test_direct_camera_restores_controls_before_stream_close(self):
        source=DirectV4L2Capture.__new__(DirectV4L2Capture)
        source.fd=7;source.running=True;source.maps=[];events=[]
        source.before_close=lambda fd:events.append(('restore',fd))
        with patch('virtualglove.v4l2_capture.fcntl.ioctl',
                   side_effect=lambda fd,op,data:events.append(('ioctl',op))), \
             patch('virtualglove.v4l2_capture.os.close',
                   side_effect=lambda fd:events.append(('close',fd))):
            source.close();source.close()
        self.assertEqual(events[0],('restore',7))
        self.assertEqual(events[-1],('close',7))
        self.assertEqual(sum(item[0]=='restore' for item in events),1)

    def test_driver_timestamp_and_close_are_preserved(self):
        class TimedCapture:
            def __init__(self):self.closed=False;self.calls=0;self.stop=threading.Event()
            def read_with_timestamp(self):
                self.calls+=1
                if self.calls==1:return True,'driver-frame',12.5
                self.stop.wait(1)
                return False,None,12.6
            def release(self):self.stop.set()
            def close(self):self.closed=True
        source=TimedCapture();capture=LatestFrameCapture(source)
        deadline=time.monotonic()+1;result=None
        while result is None and time.monotonic()<deadline:
            result=capture.latest_after(0);time.sleep(.005)
        self.assertIsNotNone(result);self.assertEqual(result.captured_at,12.5)
        capture.release();self.assertTrue(source.closed)

    def test_status_publisher_keeps_newest_pending_snapshot(self):
        published=[];gate=threading.Event()
        def publish(status,clear_frame=False):
            if status['sequence']==1:gate.wait(1)
            published.append((status['sequence'],clear_frame))
        publisher=LatestStatusPublisher(publish)
        publisher.submit({'sequence':1});time.sleep(.01)
        publisher.submit({'sequence':2});publisher.submit({'sequence':3},clear_frame=True)
        gate.set();time.sleep(.05);publisher.close()
        self.assertEqual(published,[(1,False),(3,True)])

    def test_status_publisher_surfaces_background_failure(self):
        def fail(_status,clear_frame=False):
            raise RuntimeError('status failed')
        publisher=LatestStatusPublisher(fail)
        publisher.submit({'sequence':1})
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            try:
                publisher.raise_if_failed()
            except RuntimeError as exc:
                self.assertEqual(str(exc),'status failed')
                break
            time.sleep(.005)
        else:self.fail('publisher failure was not surfaced')
        publisher.close()

    def test_capture_trace_records_a_pending_read_and_publication_without_images(self):
        source = QueuedCapture()
        entered = threading.Event()
        original_read = source.read

        def read():
            entered.set()
            return original_read()

        source.read = read
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            trace = DiagnosticTrace(path, "capture", seconds=10)
            with patch.object(DiagnosticTrace, "from_environment", return_value=trace):
                capture = LatestFrameCapture(source)
            try:
                self.assertTrue(entered.wait(3))
                with trace.lock:
                    pending = list(trace.events)
                self.assertEqual([event["event"] for event in pending], ["capture_read_begin"])
                self.assertIsNone(capture.latest_after(0))
                source.frames.put((True, "private-camera-content"))
                deadline = time.monotonic() + 3
                while capture.latest_after(0) is None and time.monotonic() < deadline:
                    time.sleep(.005)
                self.assertEqual(capture.latest_after(0).frame, "private-camera-content")
                self.assertGreaterEqual(
                    capture.latest_after(0).ready_at,
                    capture.latest_after(0).captured_at,
                )
            finally:
                capture.release()
            report = json.loads(path.read_text())
            events = [event for event in report["events"] if event["sequence"] == 1]
            self.assertEqual([event["event"] for event in events],
                             ["capture_read_begin", "capture_read_end", "capture_publication"])
            self.assertLessEqual(events[0]["at_ns"], events[1]["at_ns"])
            self.assertLessEqual(events[1]["at_ns"], events[2]["at_ns"])
            self.assertGreaterEqual(events[1]["thread_cpu_ns"], 0)
            self.assertNotIn("private-camera-content", path.read_text())

    def test_performance_window_reports_tail_latency(self):
        metrics = RollingPerformance(size=4)
        for value in (100, 10, 20, 30, 40):
            metrics.record(inference_ms=value)
        summary = metrics.snapshot()["inference_ms"]
        self.assertEqual(summary, {
            "latest": 40.0, "p50": 20.0, "p95": 40.0,
            "max": 40.0, "samples": 4,
        })
        metrics.record(inference_ms=-1, ignored=None)
        self.assertNotIn("ignored", metrics.snapshot())

    def test_capture_returns_only_the_latest_unprocessed_frame(self):
        source = QueuedCapture()
        capture = LatestFrameCapture(source, "first", metadata={"camera_format": "MJPG"})
        try:
            self.assertEqual(capture.metadata["camera_format"], "MJPG")
            first = capture.latest_after(0)
            self.assertEqual(first.frame, "first")
            source.frames.put((True, "second"))
            source.frames.put((True, "third"))
            deadline = time.monotonic() + 1
            latest = None
            while time.monotonic() < deadline:
                latest = capture.latest_after(first.sequence)
                if latest is not None and latest.frame == "third":
                    break
                time.sleep(0.005)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.frame, "third")
            self.assertGreaterEqual(latest.sequence, 3)
            self.assertIsNone(capture.latest_after(latest.sequence))
        finally:
            capture.release()
        self.assertTrue(source.released)

    def test_capture_exception_becomes_a_reconnectable_failure(self):
        source = QueuedCapture()
        source.frames.put(RuntimeError("camera failed"))
        original_read = source.read

        def read():
            value = original_read()
            if isinstance(value, Exception):
                raise value
            return value

        source.read = read
        capture = LatestFrameCapture(source)
        try:
            deadline = time.monotonic() + 1
            failed = None
            while failed is None and time.monotonic() < deadline:
                failed = capture.latest_after(0)
                time.sleep(0.005)
            self.assertIsNotNone(failed)
            self.assertFalse(failed.ok)
            self.assertIsNone(failed.frame)
        finally:
            capture.release()

    def test_preview_encoder_publishes_without_replacing_status(self):
        shared = SharedDebugState()
        shared.update_status({"sequence": 9})
        published = threading.Event()

        def publish(payload):
            shared.update_frame(payload)
            published.set()

        encoder = LatestPreviewEncoder(publish)
        cv2 = FakeCv2()
        frame = SimpleNamespace(shape=(480, 640, 3))
        try:
            self.assertTrue(encoder.submit(frame, "PROGRAM H", (255, 255, 255), cv2))
            self.assertTrue(published.wait(1))
            self.assertEqual(shared.jpeg, b"jpeg")
            self.assertEqual(shared.status, {"sequence": 9})
            metrics = encoder.metrics()
            self.assertEqual(metrics["preview_submitted"], 1)
            self.assertEqual(metrics["preview_encoded"], 1)
            self.assertIsNone(metrics["preview_error"])
        finally:
            encoder.close()

    def test_preview_failure_is_contained(self):
        encoder = LatestPreviewEncoder(lambda _payload: None)
        cv2 = FakeCv2()
        cv2.imencode = lambda *_args: (_ for _ in ()).throw(RuntimeError("encode failed"))
        try:
            encoder.submit(SimpleNamespace(shape=(480, 640, 3)), "TEST", (0, 0, 0), cv2)
            deadline = time.monotonic() + 1
            while encoder.metrics()["preview_error"] is None and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(encoder.metrics()["preview_error"], "encode failed")
        finally:
            encoder.close()

    def test_preview_encoder_draws_only_landmarks_off_the_gameplay_thread(self):
        published = threading.Event()
        encoder = LatestPreviewEncoder(lambda _payload: published.set())
        cv2 = FakeCv2()
        frame = SimpleNamespace(shape=(480, 640, 3))
        overlay = {
            "landmarks": [(0.25, 0.5), (0.75, 0.5)],
            "connections": ((0, 1),),
            "label": "technical label intentionally ignored",
        }
        try:
            self.assertTrue(encoder.submit(
                frame, "SUPER GLOVE BALL", (255, 255, 255), cv2, overlay
            ))
            self.assertTrue(published.wait(1))
            self.assertIn((frame, "line", (160, 240), (480, 240)), cv2.drawn)
            self.assertIn((frame, "circle", (160, 240)), cv2.drawn)
            self.assertFalse(any(
                item[1] == "technical label intentionally ignored"
                for item in cv2.drawn
            ))
            self.assertFalse(any(item[1] == "SUPER GLOVE BALL" for item in cv2.drawn))
        finally:
            encoder.close()

    def test_gameplay_preview_can_downscale_without_changing_normalized_overlay(self):
        published = threading.Event()
        encoder = LatestPreviewEncoder(lambda _payload: published.set())
        cv2 = FakeCv2()
        source = SimpleNamespace(shape=(480, 640, 3))
        overlay = {"landmarks": [(0.5, 0.5)], "connections": ()}
        try:
            self.assertTrue(encoder.submit(
                source, "SUPER GLOVE BALL", (255, 255, 255), cv2, overlay,
                max_width=320,
            ))
            self.assertTrue(published.wait(1))
            resized = next(item[0] for item in cv2.drawn if item[1] == "resize")
            self.assertEqual(resized.shape, (240, 320, 3))
            self.assertIn((resized, "circle", (160, 120)), cv2.drawn)
        finally:
            encoder.close()

    def test_preview_mirroring_runs_on_encoder_thread(self):
        published = threading.Event()
        encoder = LatestPreviewEncoder(lambda _payload: published.set())
        cv2 = FakeCv2()
        source = SimpleNamespace(shape=(480, 640, 3))
        try:
            self.assertTrue(encoder.submit(
                source, "SUPER GLOVE BALL", (255, 255, 255), cv2,
                {"landmarks": [(0.25, 0.5)]}, mirror=True,
            ))
            self.assertTrue(published.wait(1))
            mirrored = next(item[0] for item in cv2.drawn if item[1] == "flip")
            self.assertIn((mirrored, "circle", (160, 240)), cv2.drawn)
        finally:
            encoder.close()


if __name__ == "__main__":
    unittest.main()
