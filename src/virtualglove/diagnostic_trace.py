# Project: VirtualGlove
# File: src/virtualglove/diagnostic_trace.py
# Purpose: Retain bounded optional timing evidence without disk I/O in gameplay callbacks.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Start bounded trace duration at the first gameplay event.
#   2026-09-06 - Add opt-in finite diagnostic windows with private asynchronous export.
# Full history: docs/CHANGELOG.md and Git history.

"""Diagnostic evidence only: no images, secrets, input replay, or control queues."""

import hashlib
import json
import os
import threading
import time


def session_key(session):
    """Correlate a transport session without retaining its wire identifier."""
    return hashlib.sha256(session.encode('ascii')).hexdigest()[:32]


class DiagnosticTrace:
    """Drop evidence instead of waiting when a finite diagnostic buffer is full."""

    def __init__(self, path, role, seconds=180, capacity=20000):
        if not 1 <= seconds <= 600 or not 1 <= capacity <= 20000:
            raise ValueError('Trace requires 1-600 seconds and 1-20000 events')
        self.role, self.capacity = role, capacity
        self.duration_ns = int(seconds * 1e9)
        self.events = []
        self.dropped = 0
        self.armed_ns = time.monotonic_ns()
        self.started_ns = None
        self.deadline_ns = None
        self.enabled = True
        self.error = None
        self.stop_reason = "duration"
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.first_event = threading.Event()
        # Reserve privately at startup, never overwrite or follow an existing link.
        self.fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.thread = threading.Thread(target=self._export, name='pgv-diagnostic', daemon=True)
        self.thread.start()

    @classmethod
    def from_environment(cls, role):
        """Opt in with a private output prefix; fail closed for diagnostics only."""
        prefix = os.environ.get('VIRTUALGLOVE_DIAGNOSTIC_TRACE')
        if not prefix:
            return None
        try:
            seconds = float(os.environ.get('VIRTUALGLOVE_DIAGNOSTIC_SECONDS', '180'))
            # Camera recovery may construct the same role more than once inside
            # one long-lived process. A monotonic suffix keeps every bounded
            # trace distinct without overwriting or disabling the later trace.
            return cls('%s.%s.%d.%d.json' % (
                prefix, role, os.getpid(), time.monotonic_ns()
            ), role, seconds)
        except (OSError, ValueError) as exc:
            print('Diagnostic trace disabled: %s' % exc, flush=True)
            return None

    def record(self, event):
        """Accept a caller-owned numeric/allowlisted event without waiting or I/O."""
        if not self.enabled:
            return
        if not self.lock.acquire(False):
            self.dropped += 1
            return
        try:
            if not self.enabled:
                return
            now = time.monotonic_ns()
            if self.started_ns is None:
                self.started_ns = now
                self.deadline_ns = now + self.duration_ns
                self.first_event.set()
            if now >= self.deadline_ns or len(self.events) >= self.capacity:
                self.dropped += 1
                self.stop_reason = "capacity" if len(self.events) >= self.capacity else "duration"
                self.enabled = False
                self.stop.set()
                return
            self.events.append(event)
        finally:
            self.lock.release()

    def _export(self):
        """Freeze one window and serialize off the input-processing thread."""
        while not self.stop.is_set() and not self.first_event.wait(.25):
            pass
        if not self.stop.is_set() and self.deadline_ns is not None:
            self.stop.wait(max(0, (self.deadline_ns - time.monotonic_ns()) / 1e9))
        with self.lock:
            self.enabled = False
            events, self.events = self.events, []
        report = dict(format='virtualglove-diagnostic/1', role=self.role,
                      clock='local CLOCK_MONOTONIC; never subtract across hosts',
                      armed_ns=self.armed_ns, started_ns=self.started_ns,
                      ended_ns=time.monotonic_ns(),
                      capacity=self.capacity, dropped=self.dropped, stop_reason=self.stop_reason, events=events)
        try:
            with os.fdopen(self.fd, 'w') as stream:
                json.dump(report, stream, separators=(',', ':'), allow_nan=False)
                stream.write('\n')
        except (OSError, ValueError) as exc:
            self.error = str(exc)

    def close(self):
        """Finish evidence export after the owning gameplay loop has stopped."""
        if self.enabled:
            self.stop_reason = "closed"
        self.stop.set()
        self.thread.join(timeout=3)
