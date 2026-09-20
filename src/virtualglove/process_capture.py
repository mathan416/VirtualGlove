# Project: VirtualGlove
# File: src/virtualglove/process_capture.py
# Purpose: Isolate direct camera capture from long hand-inference calls.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-10 - Added opt-in process-isolated OpenCV capture.
#   2026-09-09 - Added an opt-in Direct V4L2 latest-frame capture process.
# Full history: docs/CHANGELOG.md and Git history.

"""Opt-in process-isolated camera capture with one replaceable frame."""

from __future__ import annotations

import multiprocessing
import signal
import time
from typing import Any

from .realtime import CapturedFrame


def _publish(frame, captured_at, source, pixels, state, lock, numpy) -> None:
    """Atomically replace the shared frame and its non-image metadata."""
    target = numpy.frombuffer(pixels, dtype=numpy.uint8).reshape((480, 640, 3))
    if frame.shape != target.shape or frame.dtype != numpy.uint8:
        raise RuntimeError(f"unexpected camera frame {frame.shape} {frame.dtype}")
    details = source.last_metadata
    with lock:
        target[:] = frame
        state[1] = 1
        state[2] = int(captured_at * 1_000_000_000)
        state[3] = int(details.get("camera_driver_sequence", 0))
        state[4] = int(bool(details.get("camera_driver_timestamp", False)))
        state[5] = int(float(details.get("camera_driver_to_dequeue_ms", 0)) * 1000)
        state[6] = int(details.get("camera_driver_buffers_drained", 0))
        state[0] += 1


def _publish_opencv(frame, captured_at, pixels, state, lock, numpy) -> None:
    """Publish an OpenCV frame without claiming unavailable driver metadata."""
    class _OpenCVSource:
        """Provide explicitly unavailable driver metadata to shared publishing."""

        last_metadata = {
            "camera_driver_sequence": 0,
            "camera_driver_timestamp": False,
            "camera_driver_to_dequeue_ms": 0.0,
            "camera_driver_buffers_drained": 0,
        }

    _publish(frame, captured_at, _OpenCVSource(), pixels, state, lock, numpy)


def _publish_failure(state, lock) -> None:
    """Publish one failed read while allowing the camera child to continue."""
    with lock:
        state[1] = 0
        state[2] = time.monotonic_ns()
        state[0] += 1


def _capture_worker(path, buffers, pixels, state, lock, stop, control,
                    manual_exposure, manual_gain) -> None:
    """Own Direct V4L2 and decoding until the parent requests shutdown."""
    import cv2
    import numpy

    from .camera_controls import configure_manual_on_fd, restore_automatic_on_fd
    from .v4l2_capture import DirectV4L2Capture

    source = None
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    try:
        source = DirectV4L2Capture(path, buffers, cv2, numpy)
        manual_report = None
        first_deadline = time.monotonic() + 5.0
        first = None
        while not stop.is_set() and time.monotonic() < first_deadline:
            try:
                ok, frame, captured_at = source.read_with_timestamp()
            except Exception:
                _publish_failure(state, lock)
                continue
            if ok:
                first = (frame, captured_at)
                break
        if first is None:
            raise RuntimeError("process-isolated camera produced no first frame")
        # Match the proven direct-camera lifecycle: establish a streaming frame
        # before changing controls on the same descriptor.
        if manual_exposure is not None:
            manual_report = configure_manual_on_fd(source.fd, manual_exposure, manual_gain)
            if not manual_report.get("applied"):
                restore_automatic_on_fd(source.fd)
                raise RuntimeError(manual_report.get(
                    "reason", "camera rejected process-isolated manual exposure"
                ))
            source.before_close = restore_automatic_on_fd
        _publish(first[0], first[1], source, pixels, state, lock, numpy)
        control.send({"ready": True, "manual": manual_report})
        while not stop.is_set():
            try:
                ok, frame, captured_at = source.read_with_timestamp()
            except Exception:
                _publish_failure(state, lock)
                stop.wait(0.005)
                continue
            if not ok:
                _publish_failure(state, lock)
                continue
            _publish(frame, captured_at, source, pixels, state, lock, numpy)
    except BaseException as exc:
        _publish_failure(state, lock)
        try:
            control.send({"ready": False, "error": str(exc)})
        except (BrokenPipeError, OSError):
            pass
    finally:
        if source is not None:
            source.close()
        control.close()


def _opencv_capture_worker(device, backend, camera_format, width, height,
                           requested_rate, buffers, pixels, state, lock, stop,
                           control) -> None:
    """Own OpenCV capture in a child and publish only its newest decoded frame."""
    import cv2
    import numpy

    from .diagnostic_trace import DiagnosticTrace

    source = None
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    trace = DiagnosticTrace.from_environment("capture")
    sequence = 0
    try:
        source = cv2.VideoCapture(device, backend)
        source.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*camera_format))
        source.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        source.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        rate_accepted = (
            source.set(cv2.CAP_PROP_FPS, requested_rate)
            if requested_rate is not None else None
        )
        buffers_accepted = source.set(cv2.CAP_PROP_BUFFERSIZE, buffers)
        if not source.isOpened():
            raise RuntimeError("process-isolated OpenCV camera did not open")

        first_deadline = time.monotonic() + 5.0
        ready = False
        while not stop.is_set() and time.monotonic() < first_deadline:
            sequence += 1
            traced = trace is not None and trace.enabled
            if traced:
                started_ns = time.monotonic_ns()
                cpu_started_ns = time.thread_time_ns()
                trace.record({"event": "capture_read_begin", "sequence": sequence,
                              "at_ns": started_ns})
            ok, frame = source.read()
            captured_at = time.monotonic()
            if traced:
                ended_ns = time.monotonic_ns()
                trace.record({
                    "event": "capture_read_end", "sequence": sequence,
                    "at_ns": ended_ns, "ok": bool(ok),
                    "thread_cpu_ns": time.thread_time_ns() - cpu_started_ns,
                })
            if ok:
                _publish_opencv(frame, captured_at, pixels, state, lock, numpy)
                if traced:
                    trace.record({"event": "capture_publication", "sequence": sequence,
                                  "at_ns": time.monotonic_ns(), "ok": True})
                ready = True
                break
            _publish_failure(state, lock)
            if traced:
                trace.record({"event": "capture_publication", "sequence": sequence,
                              "at_ns": time.monotonic_ns(), "ok": False})
            stop.wait(0.005)
        if not ready:
            raise RuntimeError("process-isolated OpenCV camera produced no first frame")

        fourcc = int(source.get(cv2.CAP_PROP_FOURCC))
        negotiated_format = "".join(
            chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)
        ).rstrip("\x00")
        control.send({
            "ready": True,
            "metadata": {
                "camera_format": negotiated_format or camera_format,
                "camera_width": round(source.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "camera_height": round(source.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "camera_fps_preferred": requested_rate,
                "camera_fps_request_accepted": rate_accepted,
                "camera_fps": round(source.get(cv2.CAP_PROP_FPS), 1),
                "camera_buffers_requested": buffers,
                "camera_buffers": source.get(cv2.CAP_PROP_BUFFERSIZE),
                "camera_buffers_accepted": buffers_accepted,
            },
        })
        while not stop.is_set():
            sequence += 1
            traced = trace is not None and trace.enabled
            if traced:
                started_ns = time.monotonic_ns()
                cpu_started_ns = time.thread_time_ns()
                trace.record({"event": "capture_read_begin", "sequence": sequence,
                              "at_ns": started_ns})
            try:
                ok, frame = source.read()
            except Exception:
                ok, frame = False, None
            captured_at = time.monotonic()
            if traced:
                trace.record({
                    "event": "capture_read_end", "sequence": sequence,
                    "at_ns": time.monotonic_ns(), "ok": bool(ok),
                    "thread_cpu_ns": time.thread_time_ns() - cpu_started_ns,
                })
            if ok:
                _publish_opencv(frame, captured_at, pixels, state, lock, numpy)
            else:
                _publish_failure(state, lock)
            if traced:
                trace.record({"event": "capture_publication", "sequence": sequence,
                              "at_ns": time.monotonic_ns(), "ok": bool(ok)})
            if not ok:
                stop.wait(0.005)
    except BaseException as exc:
        _publish_failure(state, lock)
        try:
            control.send({"ready": False, "error": str(exc)})
        except (BrokenPipeError, OSError):
            pass
    finally:
        if source is not None:
            source.release()
        if trace is not None:
            trace.close()
        control.close()


class ProcessDirectV4L2Capture:
    """Publish the newest direct camera frame from an isolated child process."""

    def __init__(self, path: str, buffers: int, numpy: Any, *,
                 metadata: dict | None = None, manual_exposure: int | None = None,
                 manual_gain: int | None = None) -> None:
        if (manual_exposure is None) != (manual_gain is None):
            raise ValueError("manual exposure and gain must be supplied together")
        context = multiprocessing.get_context("spawn")
        self._numpy = numpy
        self._pixels = context.RawArray("B", 640 * 480 * 3)
        self._state = context.RawArray("q", 7)
        self._lock = context.Lock()
        self._stop = context.Event()
        parent, child = context.Pipe(duplex=False)
        self._control = parent
        self._process = context.Process(
            target=_capture_worker,
            args=(str(path), int(buffers), self._pixels, self._state, self._lock,
                  self._stop, child, manual_exposure, manual_gain),
            name="virtualglove-camera-sidecar", daemon=True,
        )
        self.metadata = dict(metadata or {})
        self.metadata.update({
            "capture_isolation_requested": "process",
            "capture_isolation": "process",
            "capture_isolation_fallback": None,
        })
        self._closed = False
        self._synthetic_sequence = 0
        self._process.start()
        child.close()
        if not self._control.poll(7.0):
            self.release()
            raise RuntimeError("process-isolated camera startup timed out")
        message = self._control.recv()
        if not message.get("ready"):
            self.release()
            raise RuntimeError(message.get("error", "process-isolated camera failed"))
        manual = message.get("manual")
        if manual:
            self.metadata.update({
                "camera_exposure_supported": bool(manual.get("supported")),
                "camera_exposure_applied": bool(manual.get("applied")),
                "camera_manual_limits": manual.get("limits", {}),
            })

    def latest_after(self, sequence: int) -> CapturedFrame | None:
        """Return a coherent copy only when a newer shared frame exists."""
        try:
            if self._control.poll():
                message = self._control.recv()
                if message.get("error"):
                    self.metadata["capture_process_error"] = message["error"]
        except (EOFError, OSError):
            pass
        with self._lock:
            current = int(self._state[0])
            if current <= sequence:
                if self._process.is_alive():
                    return None
                self._synthetic_sequence = max(self._synthetic_sequence, sequence) + 1
                return CapturedFrame(
                    self._synthetic_sequence, time.monotonic(), False, None,
                    time.monotonic(),
                )
            ok = bool(self._state[1])
            captured_at = self._state[2] / 1_000_000_000
            driver_sequence = int(self._state[3])
            timestamp_valid = bool(self._state[4])
            driver_to_dequeue_ms = self._state[5] / 1000
            drained = int(self._state[6])
            frame = None
            if ok:
                frame = self._numpy.frombuffer(
                    self._pixels, dtype=self._numpy.uint8
                ).reshape((480, 640, 3)).copy()
        self.metadata.update({
            "camera_driver_sequence": driver_sequence,
            "camera_driver_timestamp": timestamp_valid,
            "camera_driver_to_dequeue_ms": driver_to_dequeue_ms,
            "camera_driver_buffers_drained": drained,
        })
        return CapturedFrame(current, captured_at, ok, frame if ok else None,
                             time.monotonic())

    def release(self) -> None:
        """Stop capture and reap the camera-owning child process."""
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self._process.join(timeout=2.0)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2.0)
        self._control.close()


class ProcessOpenCVCapture(ProcessDirectV4L2Capture):
    """Publish the newest OpenCV frame from an isolated child process."""

    def __init__(self, device: Any, backend: int, camera_format: str,
                 width: int, height: int, requested_rate: int | None,
                 buffers: int, numpy: Any, *, metadata: dict | None = None) -> None:
        if (width, height) != (640, 480):
            raise ValueError("process-isolated OpenCV requires 640x480")
        context = multiprocessing.get_context("spawn")
        self._numpy = numpy
        self._pixels = context.RawArray("B", width * height * 3)
        self._state = context.RawArray("q", 7)
        self._lock = context.Lock()
        self._stop = context.Event()
        parent, child = context.Pipe(duplex=False)
        self._control = parent
        self._process = context.Process(
            target=_opencv_capture_worker,
            args=(device, backend, camera_format, width, height, requested_rate,
                  buffers, self._pixels, self._state, self._lock, self._stop,
                  child),
            name="virtualglove-opencv-camera-sidecar", daemon=True,
        )
        self.metadata = dict(metadata or {})
        self.metadata.update({
            "capture_backend_requested": "opencv",
            "capture_backend": "opencv",
            "capture_backend_fallback": None,
            "capture_isolation_requested": "process",
            "capture_isolation": "process",
            "capture_isolation_fallback": None,
        })
        self._closed = False
        self._synthetic_sequence = 0
        self._process.start()
        child.close()
        if not self._control.poll(7.0):
            self.release()
            raise RuntimeError("process-isolated OpenCV startup timed out")
        message = self._control.recv()
        if not message.get("ready"):
            self.release()
            raise RuntimeError(message.get("error", "process-isolated OpenCV failed"))
        self.metadata.update(message.get("metadata", {}))
