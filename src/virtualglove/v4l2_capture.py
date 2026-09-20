# Project: VirtualGlove
# File: src/virtualglove/v4l2_capture.py
# Purpose: Read the newest Linux MJPEG camera buffer with driver timestamps.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Restore temporary active-stream controls before camera close.
#   2026-09-07 - Promoted the measured direct-V4L2 experiment as an optional backend.
# Full history: docs/CHANGELOG.md and Git history.

"""Optional Linux capture backend; callers retain an OpenCV fallback."""

from __future__ import annotations

import ctypes as C
import errno
import fcntl
import mmap
import os
import select
import struct
import sys
import time


class Timeval(C.Structure):
    """Mirror the Linux timeval structure used in V4L2 buffers."""

    _fields_ = [("sec", C.c_long), ("usec", C.c_long)]


class Timecode(C.Structure):
    """Mirror the fixed-size V4L2 timecode structure."""

    _fields_ = [("type", C.c_uint32), ("flags", C.c_uint32),
                ("rest", C.c_ubyte * 8)]


class BufferMemory(C.Union):
    """Represent the V4L2 buffer memory offset or pointer union."""

    _fields_ = [("offset", C.c_uint32), ("ptr", C.c_ulong)]


class Buffer(C.Structure):
    """Mirror the Linux 64-bit V4L2 buffer ABI."""

    _fields_ = [("index", C.c_uint32), ("type", C.c_uint32),
                ("bytesused", C.c_uint32), ("flags", C.c_uint32),
                ("field", C.c_uint32), ("ts", Timeval), ("tc", Timecode),
                ("sequence", C.c_uint32), ("memory", C.c_uint32),
                ("m", BufferMemory), ("length", C.c_uint32),
                ("reserved2", C.c_uint32), ("request_fd", C.c_int32)]


class RequestBuffers(C.Structure):
    """Mirror the V4L2 buffer-allocation request structure."""

    _fields_ = [("count", C.c_uint32), ("type", C.c_uint32),
                ("memory", C.c_uint32), ("capabilities", C.c_uint32),
                ("flags", C.c_uint32)]


REQ, QUERY, QBUF, DQBUF = 0xC0145608, 0xC0585609, 0xC058560F, 0xC0585611
STREAMON, STREAMOFF = 0x40045612, 0x40045613
G_FMT = 0xC0D05604
MONOTONIC_TIMESTAMP = 0x2000
TIMESTAMP_MASK = 0xE000
ERROR_FLAG = 0x40


class DirectV4L2Capture:
    """Decode only the newest queued 640x480 MJPEG driver buffer."""

    def __init__(self, path, buffers, cv2, numpy):
        if not sys.platform.startswith("linux") or C.sizeof(Buffer) != 88:
            raise RuntimeError("direct V4L2 requires the Linux 64-bit ABI")
        self.path = str(path)
        self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        self.cv2, self.numpy = cv2, numpy
        self.maps = []
        self.running = False
        self.last_metadata = {}
        self.before_close = None
        try:
            fmt = bytearray(208)
            struct.pack_into("I", fmt, 0, 1)
            fcntl.ioctl(self.fd, G_FMT, fmt)
            width, height, fourcc = struct.unpack_from("III", fmt, 8)
            if (width, height, fourcc) != (640, 480, int.from_bytes(b"MJPG", "little")):
                raise RuntimeError("direct V4L2 requires negotiated MJPG 640x480")
            request = RequestBuffers(int(buffers), 1, 1, 0, 0)
            fcntl.ioctl(self.fd, REQ, request)
            self.actual_buffers = int(request.count)
            if self.actual_buffers != int(buffers):
                raise RuntimeError("camera did not grant the requested direct buffers")
            for index in range(self.actual_buffers):
                buffer = self._buffer()
                buffer.index = index
                fcntl.ioctl(self.fd, QUERY, buffer)
                self.maps.append(mmap.mmap(
                    self.fd, buffer.length, flags=mmap.MAP_SHARED,
                    prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=buffer.m.offset,
                ))
                fcntl.ioctl(self.fd, QBUF, buffer)
            fcntl.ioctl(self.fd, STREAMON, C.c_uint32(1))
            self.running = True
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _buffer():
        """Create an MMAP video-capture buffer descriptor."""
        buffer = Buffer()
        buffer.type, buffer.memory = 1, 1
        return buffer

    def isOpened(self):
        """Return whether streaming is active, matching OpenCV's interface."""
        return self.running

    def read_with_timestamp(self):
        """Return a decoded newest frame and its best monotonic driver timestamp."""
        if not self.running or not select.select([self.fd], [], [], 0.25)[0]:
            return False, None, time.monotonic()
        buffer = self._buffer()
        try:
            fcntl.ioctl(self.fd, DQBUF, buffer)
        except OSError as exc:
            if exc.errno == errno.EAGAIN:
                return False, None, time.monotonic()
            raise
        drained = 0
        for _ in range(self.actual_buffers - 1):
            newer = self._buffer()
            try:
                fcntl.ioctl(self.fd, DQBUF, newer)
            except OSError as exc:
                if exc.errno == errno.EAGAIN:
                    break
                fcntl.ioctl(self.fd, QBUF, buffer)
                raise
            fcntl.ioctl(self.fd, QBUF, buffer)
            buffer = newer
            drained += 1
        dequeued = time.monotonic()
        try:
            if buffer.bytesused <= 0 or buffer.bytesused > len(self.maps[buffer.index]):
                raise RuntimeError("invalid direct camera payload")
            compressed = self.maps[buffer.index][:buffer.bytesused]
            flags = int(buffer.flags)
            sequence = int(buffer.sequence)
            driver_at = buffer.ts.sec + buffer.ts.usec / 1_000_000.0
        finally:
            fcntl.ioctl(self.fd, QBUF, buffer)
        frame = self.cv2.imdecode(
            self.numpy.frombuffer(compressed, dtype=self.numpy.uint8),
            self.cv2.IMREAD_COLOR,
        )
        if frame is None or flags & ERROR_FLAG:
            raise RuntimeError("camera marked the direct MJPEG frame invalid")
        timestamp_valid = (
            flags & TIMESTAMP_MASK == MONOTONIC_TIMESTAMP
            and 0 < driver_at <= dequeued
        )
        captured_at = driver_at if timestamp_valid else dequeued
        self.last_metadata = {
            "camera_driver_sequence": sequence,
            "camera_driver_timestamp": bool(timestamp_valid),
            "camera_driver_to_dequeue_ms": round(max(0.0, dequeued - captured_at) * 1000, 2),
            "camera_driver_buffers_drained": drained,
        }
        return True, frame, captured_at

    def read(self):
        """Return an OpenCV-compatible frame tuple without its timestamp."""
        ok, frame, _timestamp = self.read_with_timestamp()
        return ok, frame

    def release(self):
        """The owning latest-frame reader stops before close tears down mappings."""
        return None

    def close(self):
        """Restore controls and release streaming, mappings, and the device."""
        callback, self.before_close = self.before_close, None
        if callback is not None and self.fd >= 0:
            try:
                callback(self.fd)
            except Exception:
                # Camera teardown must continue even when a disconnected device
                # can no longer acknowledge restoration.
                pass
        if self.running:
            try:
                fcntl.ioctl(self.fd, STREAMOFF, C.c_uint32(1))
            finally:
                self.running = False
        for mapping in self.maps:
            mapping.close()
        self.maps.clear()
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
