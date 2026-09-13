# Project: VirtualGlove
# File: src/powerglove_vision/realtime.py
# Purpose: Keep camera capture and diagnostic JPEG work off the gameplay loop.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added transition-aware 10 Hz Dashboard cadence.
#   2026-09-07 - Accepted driver timestamps and safely closed direct capture backends.
#   2026-09-07 - Kept optional trace thread identifiers compatible with Python 3.7.
#   2026-09-05 - Added latest-frame capture and asynchronous preview encoding.
# Full history: docs/CHANGELOG.md and Git history.

"""Low-latency camera and preview helpers for the vision worker."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from math import ceil
from typing import Any, Callable, Optional

from .diagnostic_trace import DiagnosticTrace


@dataclass(frozen=True)
class CapturedFrame:
    """Describe one camera read and when it completed."""

    sequence: int
    captured_at: float
    ok: bool
    frame: Any
    ready_at: float | None = None


class RollingPerformance:
    """Summarize recent timing samples without retaining camera content."""

    def __init__(self, size: int = 300) -> None:
        if size <= 0:
            raise ValueError("performance window size must be positive")
        self.size = size
        self._values: dict[str, deque[float]] = {}

    def record(self, **measurements: float | None) -> None:
        """Append finite non-negative millisecond measurements."""
        for name, value in measurements.items():
            if value is None:
                continue
            number = float(value)
            if number < 0 or number != number or number in (float("inf"), float("-inf")):
                continue
            self._values.setdefault(name, deque(maxlen=self.size)).append(number)

    @staticmethod
    def _percentile(ordered: list[float], percentile: float) -> float:
        """Return the nearest-rank item from an already sorted window."""
        return ordered[max(0, ceil(len(ordered) * percentile) - 1)]

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        """Return rounded latest, median, tail, maximum, and sample count."""
        summary = {}
        for name, values in self._values.items():
            ordered = sorted(values)
            summary[name] = {
                "latest": round(values[-1], 1),
                "p50": round(self._percentile(ordered, 0.50), 1),
                "p95": round(self._percentile(ordered, 0.95), 1),
                "max": round(ordered[-1], 1),
                "samples": len(ordered),
            }
        return summary


class DashboardCadence:
    """Throttle routine UI snapshots while publishing state transitions promptly."""

    def __init__(self, hz: float = 10.0) -> None:
        if hz <= 0:
            raise ValueError("Dashboard cadence must be positive")
        self.interval = 1.0 / hz
        self.next_at = 0.0
        self.last_signature = None

    def due(self, now: float, signature, *, force: bool = False) -> bool:
        """Return true for the next interval, a transition, or an explicit force."""
        if force or now >= self.next_at or signature != self.last_signature:
            self.next_at = now + self.interval
            self.last_signature = signature
            return True
        return False


class LatestFrameCapture:
    """Continuously drain a camera while retaining only its newest frame."""

    def __init__(
        self,
        capture: Any,
        first_frame: Any | None = None,
        *,
        first_captured_at: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._capture = capture
        self._clock = clock
        self.metadata = dict(metadata or {})
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sequence = 0
        self._latest: CapturedFrame | None = None
        self._trace = DiagnosticTrace.from_environment("capture")
        if first_frame is not None:
            self._sequence = 1
            self._latest = CapturedFrame(
                1, clock() if first_captured_at is None else first_captured_at,
                True, first_frame, clock(),
            )
        self._thread = threading.Thread(
            target=self._run, name="virtualglove-camera", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        """Read continuously so slow inference can never build a frame queue."""
        while not self._stop.is_set():
            trace = self._trace
            traced = trace is not None and trace.enabled
            attempt = self._sequence + 1
            if traced:
                started_ns = time.monotonic_ns()
                cpu_started_ns = time.thread_time_ns()
                thread_id = getattr(threading, "get_native_id", threading.get_ident)()
                trace.record(dict(event="capture_read_begin", sequence=attempt,
                                  at_ns=started_ns, thread_id=thread_id))
            try:
                timed_read = getattr(self._capture, "read_with_timestamp", None)
                if timed_read is None:
                    ok, frame = self._capture.read()
                    captured_at = self._clock()
                else:
                    ok, frame, captured_at = timed_read()
            except Exception:
                # Publish failure so the main loop can apply its timed reconnect.
                ok, frame, captured_at = False, None, self._clock()
            ready_at = self._clock()
            if traced:
                ended_ns = time.monotonic_ns()
                cpu_ended_ns = time.thread_time_ns()
                trace.record(dict(event="capture_read_end", sequence=attempt,
                                  at_ns=ended_ns, ok=bool(ok),
                                  thread_cpu_ns=cpu_ended_ns - cpu_started_ns))
            with self._lock:
                self._sequence += 1
                capture_metadata = getattr(self._capture, "last_metadata", None)
                if isinstance(capture_metadata, dict):
                    self.metadata.update(capture_metadata)
                self._latest = CapturedFrame(
                    self._sequence, captured_at, bool(ok), frame if ok else None,
                    ready_at,
                )
            if traced:
                trace.record(dict(event="capture_publication", sequence=attempt,
                                  at_ns=time.monotonic_ns(), ok=bool(ok)))
            if not ok:
                self._stop.wait(0.005)

    def latest_after(self, sequence: int) -> CapturedFrame | None:
        """Return a newer camera result without waiting or replaying an old frame."""
        with self._lock:
            if self._latest is None or self._latest.sequence <= sequence:
                return None
            return self._latest

    def release(self) -> None:
        """Stop capture and unblock the camera driver where supported."""
        self._stop.set()
        try:
            self._capture.release()
        finally:
            if threading.current_thread() is not self._thread:
                self._thread.join(timeout=1.0)
            close = getattr(self._capture, "close", None)
            if close is not None and not self._thread.is_alive():
                close()
            if self._trace is not None:
                self._trace.close()


@dataclass(frozen=True)
class _PreviewJob:
    """Hold one replaceable browser-preview encoding request."""

    frame: Any
    label: str
    color: tuple[int, int, int]
    cv2: Any
    overlay: dict
    max_width: Optional[int]
    mirror: bool


class LatestPreviewEncoder:
    """Encode only the latest requested browser preview on a daemon thread."""

    def __init__(self, publish: Callable[[bytes], None]) -> None:
        self._publish = publish
        self._jobs: queue.Queue[_PreviewJob | None] = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._closed = False
        self._submitted = 0
        self._dropped = 0
        self._encoded = 0
        self._last_encode_ms: float | None = None
        self._last_error: str | None = None
        self._thread = threading.Thread(
            target=self._run, name="virtualglove-preview", daemon=True
        )
        self._thread.start()

    def submit(
        self,
        frame: Any,
        label: str,
        color: tuple[int, int, int],
        cv2: Any,
        overlay: Optional[dict] = None,
        max_width: Optional[int] = None,
        mirror: bool = False,
    ) -> bool:
        """Queue a preview, replacing pending work rather than delaying gameplay."""
        with self._lock:
            if self._closed:
                return False
            self._submitted += 1
        job = _PreviewJob(
            frame, label, color, cv2, dict(overlay or {}), max_width, bool(mirror)
        )
        try:
            self._jobs.put_nowait(job)
            return True
        except queue.Full:
            try:
                self._jobs.get_nowait()
            except queue.Empty:
                pass
            with self._lock:
                self._dropped += 1
            try:
                self._jobs.put_nowait(job)
                return True
            except queue.Full:
                with self._lock:
                    self._dropped += 1
                return False

    def _run(self) -> None:
        """Draw and encode previews independently of controller publication."""
        while True:
            job = self._jobs.get()
            if job is None:
                return
            started = time.monotonic()
            try:
                frame = job.cv2.flip(job.frame, 1) if job.mirror else job.frame
                height, width = frame.shape[:2]
                if job.max_width and width > job.max_width:
                    output_height = max(1, round(height * job.max_width / width))
                    frame = job.cv2.resize(
                        frame, (job.max_width, output_height),
                        interpolation=job.cv2.INTER_AREA,
                    )
                    height, width = frame.shape[:2]
                landmarks = job.overlay.get("landmarks", ())
                for start, end in job.overlay.get("connections", ()):
                    if start >= len(landmarks) or end >= len(landmarks):
                        continue
                    a, b = landmarks[start], landmarks[end]
                    job.cv2.line(
                        frame,
                        (int(a[0] * width), int(a[1] * height)),
                        (int(b[0] * width), int(b[1] * height)),
                        (255, 180, 30), 2,
                    )
                for point in landmarks:
                    job.cv2.circle(
                        frame,
                        (int(point[0] * width), int(point[1] * height)),
                        3, (20, 255, 120), -1,
                    )
                encoded, jpeg = job.cv2.imencode(
                    ".jpg", frame, [job.cv2.IMWRITE_JPEG_QUALITY, 78]
                )
                if encoded:
                    self._publish(jpeg.tobytes())
                    with self._lock:
                        self._encoded += 1
                        self._last_error = None
            except Exception as exc:
                # A diagnostic preview failure must never stop controller output.
                with self._lock:
                    self._last_error = str(exc)
            finally:
                elapsed = (time.monotonic() - started) * 1000
                with self._lock:
                    self._last_encode_ms = elapsed

    def metrics(self) -> dict[str, int | float | str | None]:
        """Return non-blocking diagnostics for the Dashboard status payload."""
        with self._lock:
            return {
                "preview_submitted": self._submitted,
                "preview_encoded": self._encoded,
                "preview_dropped": self._dropped,
                "preview_encode_ms": (
                    None if self._last_encode_ms is None else round(self._last_encode_ms, 1)
                ),
                "preview_error": self._last_error,
            }

    def close(self) -> None:
        """Stop after discarding any preview that has not started encoding."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._jobs.get_nowait()
        except queue.Empty:
            pass
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=1.0)


@dataclass(frozen=True)
class _StatusJob:
    """Hold one replaceable Dashboard status publication."""

    status: dict
    clear_frame: bool


class LatestStatusPublisher:
    """Publish only the newest prepared status without blocking inference."""

    def __init__(self, publish: Callable[..., None]) -> None:
        self._publish = publish
        self._jobs: queue.Queue[_StatusJob | None] = queue.Queue(maxsize=1)
        self._closed = False
        self._lock = threading.Lock()
        self._failure: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run, name="virtualglove-status", daemon=True,
        )
        self._thread.start()

    def submit(self, status: dict, *, clear_frame: bool = False) -> bool:
        """Replace pending housekeeping while preserving the newest state."""
        self.raise_if_failed()
        with self._lock:
            if self._closed:
                return False
        job = _StatusJob(dict(status), bool(clear_frame))
        try:
            self._jobs.put_nowait(job)
            return True
        except queue.Full:
            try:
                self._jobs.get_nowait()
            except queue.Empty:
                pass
            try:
                self._jobs.put_nowait(job)
                return True
            except queue.Full:
                return False

    def _run(self) -> None:
        """Publish newest-only status work outside the inference thread."""
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self._publish(job.status, clear_frame=job.clear_frame)
            except BaseException as exc:
                with self._lock:
                    self._failure = exc
                return

    def raise_if_failed(self) -> None:
        """Surface publisher failures on the owning control thread."""
        with self._lock:
            failure = self._failure
            self._failure = None
        if failure is not None:
            raise failure

    def close(self) -> None:
        """Discard pending housekeeping and stop the publisher thread."""
        with self._lock:
            self._closed = True
        try:
            self._jobs.get_nowait()
        except queue.Empty:
            pass
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=1.0)
