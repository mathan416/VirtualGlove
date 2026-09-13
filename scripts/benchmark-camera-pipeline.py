#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-camera-pipeline.py
# Purpose: Measure an isolated Linux camera and recognition pipeline safely.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added benchmark-only process-isolated latest-frame capture.
#   2026-09-09 - Added Linux scheduler and CPU-pressure evidence.
#   2026-09-09 - Added a three-thread scheduling-tail comparison lane.
#   2026-09-09 - Added aggregate sustained-load dequeue, frame-age, and stall evidence.
#   2026-09-07 - Added full-versus-lean MediaPipe graph comparison.
#   2026-09-07 - Added inference-thread and tracking-confidence comparison controls.
#   2026-09-06 - Added exclusive, output-paused camera pipeline measurements.
# Full history: docs/CHANGELOG.md and Git history.

"""Opt-in Linux camera/recognition experiment; never sends controller output.

Run only with the normal camera worker stopped, using its Python environment.
The caller owns stopping/restoring supervision. No camera controls, player files,
or installed sources are changed. Images stay in RAM; only numeric evidence is
exported after capture stops. Native profiler files are temporary and private.
"""

from __future__ import annotations

import argparse
from collections import Counter
import ctypes as C
import errno
import fcntl
import json
import math
import mmap
import multiprocessing
import os
from pathlib import Path
import select
import sys
import tempfile
import threading
import time


class Timeval(C.Structure):
    """Represent the V4L2 timeval fields used in buffer metadata."""
    _fields_ = [('sec', C.c_long), ('usec', C.c_long)]


class Timecode(C.Structure):
    """Represent the fixed-size V4L2 timecode payload."""
    _fields_ = [('type', C.c_uint32), ('flags', C.c_uint32), ('rest', C.c_ubyte * 8)]


class BufferMemory(C.Union):
    """Represent the V4L2 buffer memory offset or pointer union."""
    _fields_ = [('offset', C.c_uint32), ('ptr', C.c_ulong)]


class Buffer(C.Structure):
    """Represent one Linux 64-bit V4L2 capture buffer."""
    _fields_ = [('index', C.c_uint32), ('type', C.c_uint32),
                ('bytesused', C.c_uint32), ('flags', C.c_uint32),
                ('field', C.c_uint32), ('ts', Timeval), ('tc', Timecode),
                ('sequence', C.c_uint32), ('memory', C.c_uint32),
                ('m', BufferMemory), ('length', C.c_uint32),
                ('reserved2', C.c_uint32), ('request_fd', C.c_int32)]


class RequestBuffers(C.Structure):
    """Represent one V4L2 streaming-buffer allocation request."""
    _fields_ = [('count', C.c_uint32), ('type', C.c_uint32),
                ('memory', C.c_uint32), ('capabilities', C.c_uint32),
                ('flags', C.c_uint32)]


REQ, QUERY, QBUF, DQBUF = 0xc0145608, 0xc0585609, 0xc058560f, 0xc0585611
STREAMON, STREAMOFF = 0x40045612, 0x40045613


def task_scheduling_snapshot(pid=None, tid=None):
    """Read cumulative Linux task scheduling counters without changing policy."""
    pid = os.getpid() if pid is None else int(pid)
    tid = getattr(threading, 'get_native_id', threading.get_ident)() if tid is None else int(tid)
    try:
        fields = Path(f'/proc/{pid}/task/{tid}/schedstat').read_text().split()
        status = Path(f'/proc/{pid}/task/{tid}/status').read_text().splitlines()
        switches = {}
        for line in status:
            if line.startswith(('voluntary_ctxt_switches:', 'nonvoluntary_ctxt_switches:')):
                name, value = line.split(':', 1)
                switches[name] = int(value.strip())
        return {
            'runtime_ns': int(fields[0]),
            'runqueue_wait_ns': int(fields[1]),
            'timeslices': int(fields[2]),
            **switches,
        }
    except (OSError, ValueError, IndexError):
        return None


def cpu_pressure_snapshot(path=Path('/proc/pressure/cpu')):
    """Read cumulative Linux CPU pressure totals when PSI is available."""
    try:
        result = {}
        for line in path.read_text().splitlines():
            fields = line.split()
            result[fields[0]] = {
                item.split('=', 1)[0]: float(item.split('=', 1)[1])
                for item in fields[1:]
            }
        return result
    except (OSError, ValueError, IndexError):
        return None


def counter_delta(before, after):
    """Subtract compatible cumulative counter snapshots."""
    if not before or not after:
        return None
    return {
        key: after[key] - before[key]
        for key in before.keys() & after.keys()
        if isinstance(before[key], (int, float)) and isinstance(after[key], (int, float))
    }


def pressure_delta(before, after):
    """Return only cumulative PSI time deltas; rolling averages cannot be subtracted."""
    if not before or not after:
        return None
    return {
        level: {'total_us': after[level]['total'] - before[level]['total']}
        for level in before.keys() & after.keys()
        if 'total' in before[level] and 'total' in after[level]
    }


def stats(values):
    """Return compact distribution statistics for one numeric sequence."""
    values = sorted(values)
    if not values:
        return {'samples': 0}
    return dict(samples=len(values), mean=sum(values) / len(values), min=values[0],
                p50=values[math.ceil(len(values) * .5) - 1],
                p95=values[math.ceil(len(values) * .95) - 1], max=values[-1])


def driver_age_ms(row, at_ns):
    """Reject unknown/copied clocks, zero timestamps, and impossible future times."""
    if row['flags'] & 0xe000 != 0x2000 or row['driver_ns'] <= 0:
        return None
    delta = at_ns - row['driver_ns']
    return delta / 1e6 if delta >= 0 else None


def interval_ms(rows, field):
    """Return nonnegative intervals between adjacent monotonic timestamps."""
    values = []
    previous = None
    for row in rows:
        current = row.get(field)
        if current is not None and previous is not None and current >= previous:
            values.append((current - previous) / 1e6)
        previous = current
    return values


def lane_summary(lane):
    """Reduce a camera lane to image-free timing and scheduling evidence."""
    samples, capture = lane['samples'], lane['capture']
    capture_intervals = interval_ms(capture, 'dequeued_ns')
    driver_intervals = interval_ms(capture, 'driver_ns')
    recognition_intervals = interval_ms(samples, 'start_ns')
    driver_to_dequeue = [driver_age_ms(row, row['dequeued_ns']) for row in capture]
    driver_to_dequeue = [value for value in driver_to_dequeue if value is not None]
    decode = [(row['decoded_ns'] - row['requeued_ns']) / 1e6 for row in capture]
    decoded_to_recognition = [
        (row['start_ns'] - row['decoded_ns']) / 1e6 for row in samples
        if row['start_ns'] >= row['decoded_ns']
    ]
    sequence_steps = [
        int(current['driver_sequence']) - int(previous['driver_sequence'])
        for previous, current in zip(capture, capture[1:])
        if int(current['driver_sequence']) > int(previous['driver_sequence'])
    ]
    nominal_sequence_step = (
        Counter(sequence_steps).most_common(1)[0][0] if sequence_steps else None
    )
    sequence_nonmodal_steps = sum(
        step != nominal_sequence_step for step in sequence_steps
    ) if nominal_sequence_step is not None else 0
    sequence_forward_skips = sum(
        max(0, step - nominal_sequence_step) for step in sequence_steps
    ) if nominal_sequence_step is not None else 0
    origin_ns = capture[0]['dequeued_ns'] if capture else 0
    tail_events = []
    for previous, current in zip(capture, capture[1:]):
        dequeue_gap = (current['dequeued_ns'] - previous['dequeued_ns']) / 1e6
        dequeue_age = driver_age_ms(current, current['dequeued_ns'])
        decode_ms = (current['decoded_ns'] - current['requeued_ns']) / 1e6
        if (dequeue_gap > 50 or (dequeue_age is not None and dequeue_age > 75)
                or decode_ms > 20):
            tail_events.append({
                'boundary': 'capture',
                'elapsed_s': round((current['dequeued_ns'] - origin_ns) / 1e9, 3),
                'driver_sequence': int(current['driver_sequence']),
                'dequeue_interval_ms': round(dequeue_gap, 3),
                'driver_to_dequeue_ms': (
                    None if dequeue_age is None else round(dequeue_age, 3)
                ),
                'decode_ms': round(decode_ms, 3),
            })
    previous_start = None
    for current in samples:
        recognition_gap = (
            None if previous_start is None
            else (current['start_ns'] - previous_start) / 1e6
        )
        previous_start = current['start_ns']
        pickup_wait = (current['start_ns'] - current['decoded_ns']) / 1e6
        coordinate_age = current['driver_to_coordinates_ms']
        if (pickup_wait > 50 or current['graph_ms'] > 150
                or (recognition_gap is not None and recognition_gap > 150)
                or (coordinate_age is not None and coordinate_age > 220)):
            tail_events.append({
                'boundary': 'recognition',
                'elapsed_s': round((current['start_ns'] - origin_ns) / 1e9, 3),
                'driver_sequence': int(current['driver_sequence']),
                'recognition_interval_ms': (
                    None if recognition_gap is None else round(recognition_gap, 3)
                ),
                'decoded_to_recognition_start_ms': round(pickup_wait, 3),
                'graph_ms': round(current['graph_ms'], 3),
                'tracking_path': current.get('tracking_path'),
                'palm_detector_invoked': current.get('palm_detector_invoked'),
                'palm_detection_count': current.get('palm_detection_count'),
                'driver_to_coordinates_ms': (
                    None if coordinate_age is None else round(coordinate_age, 3)
                ),
            })
    tail_events.sort(key=lambda item: item['elapsed_s'])
    tail_event_count = len(tail_events)
    path_graph_ms = {}
    for row in samples:
        path_graph_ms.setdefault(
            row.get('tracking_path') or 'unavailable', []
        ).append(row['graph_ms'])
    # Attribute latency before and during palm-detector frames. This separates
    # an intrinsically expensive detector from one that merely starts after a
    # late camera dequeue or scheduling stall.
    detector_contexts = []
    for index, current in enumerate(samples):
        if not current.get('palm_detector_invoked'):
            continue
        previous = samples[index - 1] if index else None
        detector_contexts.append({
            'path': current.get('tracking_path') or 'unavailable',
            'previous_path': (
                None if previous is None
                else previous.get('tracking_path') or 'unavailable'
            ),
            'previous_graph_ms': None if previous is None else previous['graph_ms'],
            'recognition_interval_ms': (
                None if previous is None
                else (current['start_ns'] - previous['start_ns']) / 1e6
            ),
            'decoded_to_recognition_start_ms': (
                current['start_ns'] - current['decoded_ns']
            ) / 1e6,
            'driver_to_recognition_ms': current.get('driver_to_recognition_ms'),
            'graph_ms': current['graph_ms'],
            'driver_to_coordinates_ms': current.get('driver_to_coordinates_ms'),
            'skipped_application_frames': current.get(
                'skipped_application_frames', 0
            ),
        })

    def context_stats(field):
        """Summarize one finite numeric detector-context field."""
        values = [
            row[field] for row in detector_contexts
            if row.get(field) is not None and math.isfinite(row[field])
        ]
        return stats(values)

    detector_paths = Counter(row['path'] for row in detector_contexts)
    predecessor_paths = Counter(
        row['previous_path'] for row in detector_contexts
        if row['previous_path'] is not None
    )
    def stalls(values):
        """Count latency-tail samples beyond each diagnostic boundary."""
        return {f'over_{limit}_ms': sum(value > limit for value in values)
                for limit in (50, 75, 100, 150)}
    return {
        'buffers': lane['buffers'],
        'capture_isolation': lane.get('capture_isolation', 'thread'),
        'scheduling': lane.get('scheduling'),
        'recognition_samples': len(samples),
        'detected_samples': sum(bool(row.get('detected')) for row in samples),
        'tracking_paths': dict(Counter(
            row.get('tracking_path') or 'unavailable' for row in samples
        )),
        'captured_frames': len(capture),
        'failed_reads': lane['failed_reads'],
        'errors': lane['errors'],
        'application_skipped_frames': sum(
            max(0, int(row['skipped_application_frames'])) for row in samples
        ),
        'driver_sequence_step': stats(sequence_steps),
        'driver_nominal_sequence_step': nominal_sequence_step,
        # Retain the version-3 field, but count only forward gaps. A step below
        # the modal cadence means the reader captured additional frames.
        'driver_sequence_discontinuities': sequence_forward_skips,
        'driver_sequence_nonmodal_steps': sequence_nonmodal_steps,
        'driver_sequence_forward_skips': sequence_forward_skips,
        'capture_dequeue_interval_ms': stats(capture_intervals),
        'driver_frame_interval_ms': stats(driver_intervals),
        'driver_to_dequeue_ms': stats(driver_to_dequeue),
        'mjpeg_decode_ms': stats(decode),
        'decoded_to_recognition_start_ms': stats(decoded_to_recognition),
        'recognition_start_interval_ms': stats(recognition_intervals),
        'driver_to_recognition_ms': stats([
            row['driver_to_recognition_ms'] for row in samples
            if row['driver_to_recognition_ms'] is not None
        ]),
        'driver_to_coordinates_ms': stats([
            row['driver_to_coordinates_ms'] for row in samples
            if row['driver_to_coordinates_ms'] is not None
        ]),
        'preprocessing_ms': stats([row['preprocessing_ms'] for row in samples]),
        'graph_ms': stats([row['graph_ms'] for row in samples]),
        'tracking_path_graph_ms': {
            path: stats(values) for path, values in sorted(path_graph_ms.items())
        },
        'detector_context': {
            'frames': len(detector_contexts),
            'paths': dict(detector_paths),
            'predecessor_paths': dict(predecessor_paths),
            'previous_graph_ms': context_stats('previous_graph_ms'),
            'recognition_interval_ms': context_stats('recognition_interval_ms'),
            'decoded_to_recognition_start_ms': context_stats(
                'decoded_to_recognition_start_ms'
            ),
            'driver_to_recognition_ms': context_stats(
                'driver_to_recognition_ms'
            ),
            'graph_ms': context_stats('graph_ms'),
            'driver_to_coordinates_ms': context_stats(
                'driver_to_coordinates_ms'
            ),
            'skipped_application_frames': context_stats(
                'skipped_application_frames'
            ),
        },
        'post_graph_ms': stats([
            row['landmark_conversion_and_wrapper_ms'] + row['gesture_and_axes_ms']
            for row in samples
        ]),
        'stalls': {
            'capture_dequeue_interval': stalls(capture_intervals),
            'decoded_to_recognition_start': stalls(decoded_to_recognition),
            'recognition_start_interval': stalls(recognition_intervals),
        },
        'tail_events': tail_events[:100],
        'tail_events_total': tail_event_count,
        'tail_events_truncated': tail_event_count > 100,
    }


class RawCamera:
    """Copy newest available MJPEG buffer, return it, then decode outside ownership."""

    def __init__(self, path, buffers, cv2, np):
        if sys.platform != 'linux' or C.sizeof(Buffer) != 88 or C.sizeof(RequestBuffers) != 20:
            raise RuntimeError('This diagnostic requires the Linux 64-bit V4L2 ABI')
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.maps, self.rows, self.errors = [], [], []
        self.failed_reads = 0
        self.running = False
        self.cv2, self.np = cv2, np
        try:
            # Read only: validate rather than silently changing the camera format.
            fmt = bytearray(208)
            import struct
            struct.pack_into('I', fmt, 0, 1)
            fcntl.ioctl(self.fd, 0xc0d05604, fmt)
            width, height, fourcc = struct.unpack_from('III', fmt, 8)
            if (width, height, fourcc) != (640, 480, int.from_bytes(b'MJPG', 'little')):
                raise RuntimeError('Expected existing MJPG 640x480 camera configuration')
            req = RequestBuffers(buffers, 1, 1, 0, 0)
            fcntl.ioctl(self.fd, REQ, req)
            self.actual_buffers = req.count
            if req.count != buffers:
                raise RuntimeError(f'Driver granted {req.count} buffers, requested {buffers}')
            for index in range(req.count):
                b = self.buffer()
                b.index = index
                fcntl.ioctl(self.fd, QUERY, b)
                self.maps.append(mmap.mmap(self.fd, b.length, flags=mmap.MAP_SHARED,
                    prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=b.m.offset))
                fcntl.ioctl(self.fd, QBUF, b)
            fcntl.ioctl(self.fd, STREAMON, C.c_uint32(1))
            self.running = True
        except BaseException:
            self.close()
            raise

    @staticmethod
    def buffer():
        """Create a zeroed MMAP capture-buffer descriptor."""
        b = Buffer()
        b.type, b.memory = 1, 1
        return b

    def read(self):
        """Return the newest available decoded frame and bounded metadata."""
        try:
            if not self.running or not select.select([self.fd], [], [], 2)[0]:
                self.failed_reads += 1
                return False, None
            b = self.buffer()
            fcntl.ioctl(self.fd, DQBUF, b)
            dropped = 0
            # Bound the drain: at most the originally available driver buffers.
            for _ in range(self.actual_buffers - 1):
                newer = self.buffer()
                try:
                    fcntl.ioctl(self.fd, DQBUF, newer)
                except OSError as exc:
                    if exc.errno == errno.EAGAIN:
                        break
                    raise
                fcntl.ioctl(self.fd, QBUF, b)
                b = newer
                dropped += 1
            dequeued = time.monotonic_ns()
            row = dict(driver_ns=b.ts.sec * 1_000_000_000 + b.ts.usec * 1000,
                       driver_sequence=b.sequence, flags=b.flags,
                       dequeued_ns=dequeued, drained=dropped)
            try:
                if b.bytesused <= 0 or b.bytesused > len(self.maps[b.index]):
                    raise RuntimeError('Invalid camera payload size')
                compressed = self.maps[b.index][:b.bytesused]
            finally:
                fcntl.ioctl(self.fd, QBUF, b)
            row['requeued_ns'] = time.monotonic_ns()
            image = self.cv2.imdecode(self.np.frombuffer(compressed, dtype=self.np.uint8),
                                      self.cv2.IMREAD_COLOR)
            row['decoded_ns'] = time.monotonic_ns()
            if image is None or row['flags'] & 0x40:
                raise RuntimeError('Camera error flag or invalid MJPEG image')
            if len(self.rows) >= 60000:
                raise RuntimeError('Diagnostic capture capacity reached')
            self.rows.append(row)
            return True, (image, row)
        except Exception as exc:
            self.failed_reads += 1
            if len(self.errors) < 20:
                self.errors.append(str(exc))
            return False, None

    def release(self):
        """Leave teardown to close after the capture thread has joined."""
        # LatestFrameCapture first signals its stop event, then calls this.
        # Do not unmap memory concurrently with read/decode; close after join.
        pass

    def close(self):
        """Stop streaming and release every mapped driver resource."""
        if self.running:
            fcntl.ioctl(self.fd, STREAMOFF, C.c_uint32(1))
            self.running = False
        for mapping in self.maps:
            mapping.close()
        self.maps.clear()
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def process_capture_worker(path, buffers, frame_bytes, metadata, lock, stop, report):
    """Own capture/decode in a benchmark-only process and publish one latest frame."""
    import cv2
    import numpy as np
    raw = None
    scheduling_before = task_scheduling_snapshot()
    try:
        raw = RawCamera(path, buffers, cv2, np)
        target = np.frombuffer(frame_bytes, dtype=np.uint8).reshape((480, 640, 3))
        while not stop.is_set():
            ok, payload = raw.read()
            if not ok:
                continue
            frame, row = payload
            if frame.shape != target.shape or frame.dtype != np.uint8:
                raw.failed_reads += 1
                if len(raw.errors) < 20:
                    raw.errors.append(f'Unexpected decoded frame {frame.shape} {frame.dtype}')
                continue
            with lock:
                target[:] = frame
                metadata[1] = 1
                metadata[2] = int(row['driver_ns'])
                metadata[3] = int(row['driver_sequence'])
                metadata[4] = int(row['flags'])
                metadata[5] = int(row['dequeued_ns'])
                metadata[6] = int(row['requeued_ns'])
                metadata[7] = int(row['decoded_ns'])
                metadata[8] = int(row['drained'])
                metadata[0] += 1
    except BaseException as exc:
        with lock:
            metadata[1] = 0
            metadata[0] += 1
        if raw is None:
            rows, errors, failed_reads = [], [str(exc)], 1
        else:
            if len(raw.errors) < 20:
                raw.errors.append(str(exc))
            rows, errors, failed_reads = raw.rows, raw.errors, raw.failed_reads + 1
    else:
        rows, errors, failed_reads = raw.rows, raw.errors, raw.failed_reads
    finally:
        scheduling_after = task_scheduling_snapshot()
        if raw is not None:
            raw.close()
        try:
            report.send({
                'capture': rows,
                'errors': errors,
                'failed_reads': failed_reads,
                'scheduling': counter_delta(scheduling_before, scheduling_after),
            })
        finally:
            report.close()


class ProcessLatestCapture:
    """Expose a process-isolated camera through the LatestFrameCapture contract."""

    def __init__(self, path, buffers, np):
        from powerglove_vision.realtime import CapturedFrame
        self._captured_frame = CapturedFrame
        self._np = np
        context = multiprocessing.get_context('spawn')
        self._frame = context.RawArray('B', 640 * 480 * 3)
        self._metadata = context.RawArray('q', 9)
        self._lock = context.Lock()
        self._stop = context.Event()
        self._parent_report, child_report = context.Pipe(duplex=False)
        self._process = context.Process(
            target=process_capture_worker,
            args=(path, buffers, self._frame, self._metadata, self._lock,
                  self._stop, child_report),
            name='virtualglove-camera-sidecar', daemon=True,
        )
        self._process.start()
        child_report.close()
        self.report = None

    def latest_after(self, sequence):
        """Copy a coherent newest frame only when its shared sequence advances."""
        with self._lock:
            current = int(self._metadata[0])
            if current <= sequence:
                return None
            ok = bool(self._metadata[1])
            values = tuple(int(self._metadata[index]) for index in range(2, 9))
            frame = None
            if ok:
                frame = self._np.frombuffer(self._frame, dtype=self._np.uint8).reshape(
                    (480, 640, 3)
                ).copy()
        driver_ns, driver_sequence, flags, dequeued_ns, requeued_ns, decoded_ns, drained = values
        metadata = dict(driver_ns=driver_ns, driver_sequence=driver_sequence,
                        flags=flags, dequeued_ns=dequeued_ns,
                        requeued_ns=requeued_ns, decoded_ns=decoded_ns,
                        drained=drained)
        captured_at = decoded_ns / 1e9 if decoded_ns else time.monotonic()
        return self._captured_frame(current, captured_at, ok,
                                    (frame, metadata) if ok else None,
                                    time.monotonic())

    def release(self):
        """Stop the child, receive its bounded numeric/capture report, and join."""
        self._stop.set()
        if self._parent_report.poll(5):
            self.report = self._parent_report.recv()
        self._process.join(timeout=3)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2)
            raise RuntimeError('Camera sidecar did not stop cleanly')
        if self.report is None:
            raise RuntimeError(f'Camera sidecar exited without a report ({self._process.exitcode})')
        self._parent_report.close()


class TimedCalls:
    """Measure selected calls without copying the tracker implementation."""

    def __init__(self, target, names):
        self.target, self.names, self.times = target, names, {}

    def __getattr__(self, name):
        """Wrap selected callables and accumulate their execution time."""
        value = getattr(self.target, name)
        if name not in self.names:
            return value

        def call(*args, **kwargs):
            """Invoke one wrapped callable and record elapsed monotonic time."""
            started = time.monotonic_ns()
            try:
                return value(*args, **kwargs)
            finally:
                self.times[name] = self.times.get(name, 0) + time.monotonic_ns() - started
        return call


def measure_frame(tracker, engine, frame):
    """Measure recognition, conversion, and gesture work for one frame."""
    tracker.cv2.times.clear()
    tracker.hands.times.clear()
    begin = time.monotonic_ns()
    result = tracker.process(frame)
    tracked = time.monotonic_ns()
    engine.update(result.observation)
    end = time.monotonic_ns()
    prep = sum(tracker.cv2.times.values())
    graph = sum(tracker.hands.times.values())
    return result, dict(start_ns=begin, end_ns=end, detected=result.observation.detected,
                       tracking_path=result.diagnostics.get('tracking_path'),
                       palm_detector_invoked=result.diagnostics.get('palm_detector_invoked'),
                       palm_detection_count=result.diagnostics.get('palm_detection_count'),
                       hand_presence_score=result.diagnostics.get('hand_presence_score'),
                       preprocessing_ms=prep / 1e6, graph_ms=graph / 1e6,
                       landmark_conversion_and_wrapper_ms=(tracked - begin - prep - graph) / 1e6,
                       gesture_and_axes_ms=(end - tracked) / 1e6,
                       total_ms=(end - begin) / 1e6)


def wrap_tracker(tracker):
    """Disable preview work and time selected tracker calls in place."""
    tracker.preview_enabled = tracker.diagnostics_enabled = False
    tracker.cv2 = TimedCalls(tracker.cv2, {'flip', 'cvtColor'})
    tracker.hands = TimedCalls(tracker.hands, {'process'})


def camera_lane(path, buffers, seconds, tracker, engine, isolation='thread'):
    """Measure one exclusive live-camera lane with selected capture isolation."""
    from powerglove_vision.realtime import LatestFrameCapture
    import cv2
    import numpy as np
    if isolation == 'process':
        raw = None
        capture = ProcessLatestCapture(path, buffers, np)
    else:
        raw = RawCamera(path, buffers, cv2, np)
        capture = LatestFrameCapture(raw)
    rows, selected, last_detected = [], 0, None
    psi_before = cpu_pressure_snapshot()
    inference_before = task_scheduling_snapshot()
    capture_before = None
    if isolation == 'thread':
        capture_before = task_scheduling_snapshot(
            os.getpid(), getattr(capture._thread, 'native_id', None)
        )
    started = time.monotonic()
    warmup_until, deadline = started + 2, started + 2 + seconds
    try:
        while time.monotonic() < deadline:
            latest = capture.latest_after(selected)
            if latest is None:
                time.sleep(.001)
                continue
            skipped = latest.sequence - selected - 1
            selected = latest.sequence
            if not latest.ok:
                continue
            frame, metadata = latest.frame
            result, timing = measure_frame(tracker, engine, frame)
            if result.observation.detected:
                last_detected = frame
            if time.monotonic() >= warmup_until:
                rows.append(dict(metadata, **timing, capture_sequence=selected,
                    skipped_application_frames=skipped,
                    driver_to_recognition_ms=driver_age_ms(metadata, timing['start_ns']),
                    driver_to_coordinates_ms=driver_age_ms(metadata, timing['end_ns'])))
    finally:
        inference_after = task_scheduling_snapshot()
        capture_after = None
        if isolation == 'thread':
            capture_after = task_scheduling_snapshot(
                os.getpid(), getattr(capture._thread, 'native_id', None)
            )
        capture.release()
        if isolation == 'thread':
            capture._thread.join(timeout=3)
            if capture._thread.is_alive():
                raise RuntimeError('Capture thread did not stop; process exit must release camera')
            raw.close()
            captured, errors, failed_reads = raw.rows, raw.errors, raw.failed_reads
            capture_scheduling = counter_delta(capture_before, capture_after)
        else:
            captured = capture.report['capture']
            errors = capture.report['errors']
            failed_reads = capture.report['failed_reads']
            capture_scheduling = capture.report['scheduling']
    capture_rows = [r for r in captured if r['decoded_ns'] >= int(warmup_until * 1e9)]
    return dict(buffers=buffers, capture_isolation=isolation,
                samples=rows, capture=capture_rows, errors=errors,
                failed_reads=failed_reads,
                scheduling={
                    'inference_task': counter_delta(inference_before, inference_after),
                    'capture_task': capture_scheduling,
                    'system_cpu_pressure': pressure_delta(psi_before, cpu_pressure_snapshot()),
                }), last_detected


def lane_matrix(buffers, isolations):
    """Broadcast one selector or pair equal-length selectors deterministically."""
    buffers, isolations = list(buffers), list(isolations)
    if len(buffers) == 1:
        buffers *= len(isolations)
    if len(isolations) == 1:
        isolations *= len(buffers)
    if len(buffers) != len(isolations):
        raise ValueError('buffers and capture-isolation must have equal lengths or one value')
    return list(zip(buffers, isolations))


def native_profile_summary(folder):
    """Summarize selected calculator durations from a native profiler trace."""
    from mediapipe.framework import calculator_profile_pb2
    groups = {}
    for path in Path(folder).glob('*.binarypb'):
        report = calculator_profile_pb2.GraphProfile()
        report.ParseFromString(path.read_bytes())
        for trace in report.graph_trace:
            for event in trace.calculator_trace:
                if event.event_type != calculator_profile_pb2.GraphTrace.PROCESS:
                    continue
                if not event.HasField('start_time') or not event.HasField('finish_time'):
                    continue
                if not 0 <= event.node_id < len(trace.calculator_name):
                    continue
                name = trace.calculator_name[event.node_id]
                duration = event.finish_time - event.start_time
                if duration >= 0:
                    groups.setdefault(name, []).append(duration / 1000)
    return {name: stats(values) for name, values in groups.items()}


def replay_lane(frame, profiled, tracker_class, engine_class, calibration_class,
                inference_threads=2, tracking_confidence=.55, graph_mode="full"):
    """Replay one in-memory frame with optional native graph profiling."""
    from google.protobuf import text_format
    from mediapipe.framework import calculator_pb2
    from mediapipe.python.solution_base import SolutionBase
    with tempfile.TemporaryDirectory(prefix='pgv-native-profile-') as folder:
        tracker = tracker_class(inference_threads=inference_threads,
                                tracking_confidence=tracking_confidence,
                                graph_mode=graph_mode)
        if profiled:
            config = calculator_pb2.CalculatorGraphConfig()
            text_format.Parse(tracker.hands._graph.text_config, config)
            tracker.hands.close()
            p = config.profiler_config
            p.enable_profiler = p.trace_enabled = True
            p.trace_log_capacity = 131072
            p.trace_log_interval_usec = -1  # export only after graph stops
            p.trace_log_margin_usec = 0
            p.trace_log_path = folder + '/'
            outputs = ["multi_hand_landmarks"] if graph_mode == "lean-image" else [
                "multi_hand_landmarks", "multi_hand_world_landmarks", "multi_handedness"
            ]
            tracker.hands = SolutionBase(graph_config=config,
                side_inputs={'model_complexity': 0, 'num_hands': 1, 'use_prev_landmarks': True},
                outputs=outputs)
        wrap_tracker(tracker)
        engine = engine_class('super_glove_ball', calibration=calibration_class(.5, .5, .2, 0))
        rows = []
        try:
            for index in range(45):
                _, timing = measure_frame(tracker, engine, frame)
                timing['warmup'] = index < 10
                rows.append(timing)
        finally:
            tracker.close()
        native = native_profile_summary(folder) if profiled else {}
    landmark_calls = sum(value['samples'] for name, value in native.items()
                         if 'handlandmarkcpu__' in name and 'InferenceCalculator' in name)
    return dict(profiled=profiled, samples=rows, native_calculators_ms=native,
                native_trace_complete=(landmark_calls == len(rows)) if profiled else None)


def main():
    """Run bounded camera lanes and print a numeric report without images."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', required=True)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--seconds', type=int, choices=range(5, 601), default=10)
    parser.add_argument('--buffers', nargs='+', type=int, choices=(1, 2),
                        default=(1, 2, 1))
    parser.add_argument('--capture-isolation', nargs='+',
                        choices=('thread', 'process'), default=('thread',),
                        help='benchmark-only latest-frame capture ownership')
    parser.add_argument('--aggregate-only', action='store_true',
                        help='retain compact summaries instead of per-frame rows')
    parser.add_argument('--skip-replay', action='store_true',
                        help='skip the fixed detected-hand profiler replay')
    parser.add_argument('--tracking-evidence', action='store_true',
                        help='expose lightweight palm/landmark path evidence')
    parser.add_argument('--output', type=Path,
                        help='write the report to this path instead of standard output')
    parser.add_argument('--inference-threads', type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument('--tracking-confidence', type=float,
                        choices=(.30, .35, .40, .45, .50, .55, .60),
                        default=.55)
    parser.add_argument('--graph-mode', choices=('full', 'lean-image'), default='full')
    parser.add_argument('--worker-stopped', action='store_true', required=True,
                        help='Acknowledge exclusive camera ownership; caller restores the worker')
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root / 'src'))
    from powerglove_vision.tracker import MediaPipeTracker
    from powerglove_vision.gesture import GestureEngine
    from powerglove_vision.model import Calibration
    import cv2
    import mediapipe as mp
    tracker = MediaPipeTracker(inference_threads=args.inference_threads,
                               tracking_confidence=args.tracking_confidence,
                               graph_mode=args.graph_mode,
                               tracking_evidence=args.tracking_evidence)
    wrap_tracker(tracker)
    # Synthetic center for cost measurement only. Never reads or changes player setup.
    engine = GestureEngine('super_glove_ball', calibration=Calibration(.5, .5, .2, 0))
    report = dict(format='virtualglove-camera-pipeline/3', opencv=cv2.__version__,
        mediapipe=mp.__version__, inference_threads=args.inference_threads,
        tracking_confidence=args.tracking_confidence, graph_mode=args.graph_mode,
        seconds_per_lane=args.seconds, requested_buffers=list(args.buffers),
        requested_capture_isolation=list(args.capture_isolation),
        aggregate_only=args.aggregate_only,
        tracking_evidence=args.tracking_evidence,
        lanes=[], replay=[], limitations=[
            'Isolated capture/recognition; no gameplay transmission or supervisor workload.',
            'Driver timestamps are not validated physical exposure timestamps.',
            'Coordinates use a synthetic calibration solely for computation cost.',
            'Native graph process durations include scheduling; they are not CPU-only time.',
            'Native replay timings include warmup; Python replay samples label warmup.',
            'Fixed-frame replay measures profiling overhead, not live tracking reliability.',
            'Finite native trace capacity 131072 events; missing traces invalidate native attribution.',
        ])
    replay_frame = None
    try:
        for buffers, isolation in lane_matrix(args.buffers, args.capture_isolation):
            lane, frame = camera_lane(args.camera, buffers, args.seconds, tracker, engine,
                                      isolation=isolation)
            report['lanes'].append(lane_summary(lane) if args.aggregate_only else lane)
            if frame is not None:
                replay_frame = frame
            print(json.dumps({'completed_buffers': buffers,
                              'capture_isolation': isolation}), flush=True)
    finally:
        tracker.close()
    if replay_frame is not None and not args.skip_replay:
        for profiled in (False, True, False):
            report['replay'].append(replay_lane(replay_frame, profiled, MediaPipeTracker,
                                                GestureEngine, Calibration,
                                                args.inference_threads,
                                                args.tracking_confidence,
                                                args.graph_mode))
            print(json.dumps({'completed_profiled_replay': profiled}), flush=True)
    elif not args.skip_replay:
        report['recognition_profile_error'] = 'No detected-hand frame; repeat with visible hand'
    rendered = json.dumps(report, allow_nan=False,
                          indent=2 if args.output else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + '\n')
        print(json.dumps({'output': str(args.output),
                          'lanes': len(report['lanes'])}), flush=True)
    else:
        print(rendered, flush=True)


if __name__ == '__main__':
    main()
