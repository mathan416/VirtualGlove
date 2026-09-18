# Project: VirtualGlove
# File: tests/test_process_capture.py
# Purpose: Verify coherent latest-only process capture and failure publication.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added process-isolated capture contract coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Test the process capture shared slot without camera hardware."""

import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy

from virtualglove.process_capture import (
    ProcessDirectV4L2Capture, ProcessOpenCVCapture, _publish,
    _publish_failure, _publish_opencv, _opencv_capture_worker,
)


class _Source:
    last_metadata = {
        "camera_driver_sequence": 27,
        "camera_driver_timestamp": True,
        "camera_driver_to_dequeue_ms": 3.25,
        "camera_driver_buffers_drained": 1,
    }


class _Process:
    def __init__(self, alive=True):
        self.alive = alive

    def is_alive(self):
        return self.alive


class _Control:
    def poll(self):
        return False


class ProcessCaptureTests(unittest.TestCase):
    def capture(self):
        capture = ProcessDirectV4L2Capture.__new__(ProcessDirectV4L2Capture)
        capture._numpy = numpy
        capture._pixels = bytearray(640 * 480 * 3)
        capture._state = [0] * 7
        capture._lock = threading.Lock()
        capture._process = _Process()
        capture._control = _Control()
        capture._synthetic_sequence = 0
        capture.metadata = {}
        return capture

    def test_publish_and_read_are_coherent_and_latest_only(self):
        capture = self.capture()
        frame = numpy.full((480, 640, 3), 17, dtype=numpy.uint8)
        _publish(frame, 12.5, _Source(), capture._pixels,
                 capture._state, capture._lock, numpy)
        result = capture.latest_after(0)
        self.assertTrue(result.ok)
        self.assertEqual(result.sequence, 1)
        self.assertEqual(result.captured_at, 12.5)
        self.assertTrue(numpy.array_equal(result.frame, frame))
        self.assertIsNone(capture.latest_after(1))
        self.assertEqual(capture.metadata["camera_driver_sequence"], 27)
        frame[:] = 99
        self.assertEqual(result.frame[0, 0, 0], 17)

    def test_dead_child_repeatedly_publishes_failure_for_recovery_timer(self):
        capture = self.capture()
        capture._process.alive = False
        first = capture.latest_after(0)
        second = capture.latest_after(first.sequence)
        self.assertFalse(first.ok)
        self.assertFalse(second.ok)
        self.assertGreater(second.sequence, first.sequence)
        self.assertLess(abs(second.captured_at - time.monotonic()), .1)

    def test_transient_failed_read_can_be_replaced_by_a_valid_frame(self):
        capture = self.capture()
        _publish_failure(capture._state, capture._lock)
        failed = capture.latest_after(0)
        self.assertFalse(failed.ok)
        frame = numpy.full((480, 640, 3), 23, dtype=numpy.uint8)
        _publish(frame, 14.0, _Source(), capture._pixels,
                 capture._state, capture._lock, numpy)
        recovered = capture.latest_after(failed.sequence)
        self.assertTrue(recovered.ok)
        self.assertEqual(recovered.captured_at, 14.0)

    def test_partial_manual_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            ProcessDirectV4L2Capture('/dev/video0', 2, numpy,
                                     manual_exposure=78)

    def test_opencv_publish_carries_no_fabricated_driver_timestamp(self):
        capture = self.capture()
        frame = numpy.full((480, 640, 3), 31, dtype=numpy.uint8)
        _publish_opencv(frame, 20.0, capture._pixels, capture._state,
                        capture._lock, numpy)
        result = capture.latest_after(0)
        self.assertTrue(result.ok)
        self.assertEqual(result.captured_at, 20.0)
        self.assertFalse(capture.metadata["camera_driver_timestamp"])
        self.assertEqual(capture.metadata["camera_driver_sequence"], 0)

    def test_opencv_process_rejects_non_production_frame_size(self):
        with self.assertRaises(ValueError):
            ProcessOpenCVCapture(0, 0, "MJPG", 320, 240, 30, 1, numpy)

    def test_opencv_worker_negotiates_and_publishes_latest_frame(self):
        class Stop:
            stopped = False

            def is_set(self):
                return self.stopped

            def wait(self, _seconds):
                pass

        stop = Stop()

        class Source:
            def __init__(self):
                self.reads = 0
                self.released = False

            def set(self, _key, _value):
                return True

            def get(self, key):
                return {
                    6: int.from_bytes(b"MJPG", "little"),
                    3: 640, 4: 480, 5: 30, 38: 1,
                }[key]

            def isOpened(self):
                return True

            def read(self):
                self.reads += 1
                if self.reads == 2:
                    stop.stopped = True
                return True, numpy.full((480, 640, 3), self.reads, dtype=numpy.uint8)

            def release(self):
                self.released = True

        source = Source()

        class Control:
            def __init__(self):
                self.messages = []

            def send(self, message):
                self.messages.append(message)

            def close(self):
                pass

        control = Control()
        fake_cv2 = SimpleNamespace(
            CAP_PROP_FOURCC=6, CAP_PROP_FRAME_WIDTH=3,
            CAP_PROP_FRAME_HEIGHT=4, CAP_PROP_FPS=5,
            CAP_PROP_BUFFERSIZE=38,
            VideoWriter_fourcc=lambda *letters: int.from_bytes(
                "".join(letters).encode(), "little"
            ),
            VideoCapture=lambda _device, _backend: source,
        )
        pixels = bytearray(640 * 480 * 3)
        state = [0] * 7
        with patch.dict("sys.modules", {"cv2": fake_cv2}):
            _opencv_capture_worker(
                0, 200, "MJPG", 640, 480, 30, 1, pixels, state,
                threading.Lock(), stop, control,
            )
        self.assertTrue(source.released)
        self.assertEqual(source.reads, 2)
        self.assertEqual(state[0], 2)
        self.assertTrue(control.messages[0]["ready"])
        self.assertEqual(control.messages[0]["metadata"]["camera_fps"], 30)
        self.assertEqual(pixels[0], 2)


if __name__ == "__main__":
    unittest.main()
