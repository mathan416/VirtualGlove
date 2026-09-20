#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-post-inference.py
# Purpose: Measure the production-shaped controller send and Dashboard housekeeping boundary.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added repeatable Dashboard-off/on and sustained synthetic lanes.
# Full history: docs/CHANGELOG.md and Git history.

"""Benchmark post-inference work without a camera, emulator, or live controller."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from virtualglove.model import ControllerState
from virtualglove.realtime import (
    DashboardCadence, LatestStatusPublisher, RollingPerformance,
)
from virtualglove.transport import UdpSender


class _Address:
    """Provide a fixed local address without name-resolution work."""

    def current(self):
        """Return the synthetic receiver address and no resolution error."""
        return "127.0.0.1", None

    def close(self):
        """Match the production resolver lifecycle without external resources."""
        pass


class _Socket:
    """Count in-memory datagrams without using a network interface."""

    def __init__(self):
        self.sent = 0

    def setblocking(self, _enabled):
        """Accept the sender's non-blocking configuration request."""
        pass

    def recvfrom(self, _size):
        """Report that the synthetic receiver has no reply pending."""
        raise BlockingIOError

    def sendto(self, payload, _peer):
        """Count and accept one encoded datagram entirely in memory."""
        self.sent += 1
        return len(payload)

    def close(self):
        """Match the production socket lifecycle without external resources."""
        pass


def _percentile(values: list[float], fraction: float) -> float:
    """Return the nearest-rank percentile for one non-empty sample set."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _summary(values: list[float]) -> dict:
    """Summarize the latency distribution used by each benchmark lane."""
    return {
        "p50": round(_percentile(values, 0.50), 4),
        "p95": round(_percentile(values, 0.95), 4),
        "p99": round(_percentile(values, 0.99), 4),
        "max": round(max(values), 4),
        "samples": len(values),
    }


def run_lane(iterations: int, statistics: bool, slow_publish_ms: float) -> dict:
    """Run one established-session lane with newest-only Dashboard publication."""
    sender = UdpSender("127.0.0.1", 55355, "benchmark-secret")
    sender.address.close()
    sender.address = _Address()
    sender.socket.close()
    sender.socket = _Socket()
    sender._peer = ("127.0.0.1", 55355)
    sender.challenge = "a" * 32
    sender._hello_at = float("inf")
    published = [0]

    def publish(_status, clear_frame=False):
        """Simulate optional slow Dashboard work on its newest-only worker."""
        if slow_publish_ms:
            time.sleep(slow_publish_ms / 1000.0)
        published[0] += 1

    publisher = LatestStatusPublisher(publish)
    cadence = DashboardCadence(10.0)
    performance = RollingPerformance()
    send_times, housekeeping_times, iteration_times = [], [], []
    submitted = 0
    warmup = min(1000, max(10, iterations // 20))
    total = iterations + warmup
    try:
        for index in range(total):
            state = ControllerState.released(
                index, index / 60.0, "super_glove_ball", True,
            )
            state.detected = True
            state.axes["x"] = (index % 65535) - 32767
            started = time.perf_counter_ns()
            send_started = time.perf_counter_ns()
            sender.send(state)
            sent = time.perf_counter_ns()
            send_ms = (sent - send_started) / 1e6
            performance.record(send_ms=send_ms)
            virtual_now = index / 60.0
            signature = (state.detected, state.calibrated, False)
            if cadence.due(virtual_now, signature):
                status = state.to_status_dict()
                status["send_ms"] = round(send_ms, 3)
                if statistics:
                    status["performance"] = performance.snapshot()
                publisher.submit(status)
                submitted += 1
            finished = time.perf_counter_ns()
            if index >= warmup:
                send_times.append(send_ms)
                housekeeping_times.append((finished - sent) / 1e6)
                iteration_times.append((finished - started) / 1e6)
    finally:
        publisher.close()
        sender.close()
    return {
        "statistics": statistics,
        "iterations": iterations,
        "udp_send_ms": _summary(send_times),
        "post_send_housekeeping_ms": _summary(housekeeping_times),
        "full_iteration_ms": _summary(iteration_times),
        "dashboard_submitted": submitted,
        "dashboard_published": published[0],
        "udp_datagrams": sender.socket.sent,
        "slow_publisher_ms": slow_publish_ms,
    }


def main() -> int:
    """Run the off/on/off benchmark lanes and emit their JSON report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--slow-publisher-ms", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations < 100:
        parser.error("--iterations must be at least 100")
    lanes = [
        run_lane(args.iterations, False, 0.0),
        run_lane(args.iterations, True, args.slow_publisher_ms),
        run_lane(args.iterations, False, 0.0),
    ]
    report = {
        "format": "virtualglove-post-inference-benchmark/1",
        "scope": "headless established-session synthetic post-inference boundary",
        "lanes": lanes,
        "limitations": [
            "No camera, MediaPipe, network driver, emulator, or display latency is included.",
            "A slow status consumer validates newest-only replacement; it is not production timing.",
        ],
    }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
