#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/benchmark-diagnostic-overhead.py
# Purpose: Measure local opt-in Python trace costs without camera or controller output.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Add isolated enabled/disabled diagnostic overhead comparison.
# Full history: docs/CHANGELOG.md and Git history.

"""Run on each device; this microbenchmark is not gameplay or end-to-end latency."""
import argparse
import json
import math
import platform
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from powerglove_vision.diagnostic_trace import DiagnosticTrace, session_key


def summarize(values):
    """Report individual microsecond observations including scheduling tails."""
    values.sort()
    return dict(samples=len(values), p50=values[math.ceil(len(values)*.5)-1],
                p95=values[math.ceil(len(values)*.95)-1], max=values[-1])


def main():
    """Compare the disabled guard to hashing/timestamps/event creation/recording."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        for enabled in (False, True):
            trace = DiagnosticTrace(Path(directory)/'trace.json', 'benchmark') if enabled else None
            values = []
            for i in range(5100):
                started = time.perf_counter_ns()
                if trace and trace.enabled:
                    trace.record(dict(event='send', session=session_key('a'*32), sequence=i,
                                      start_ns=time.monotonic_ns(), end_ns=time.monotonic_ns()))
                elapsed = (time.perf_counter_ns()-started)/1000
                if i >= 100:
                    values.append(elapsed)
            if trace:
                trace.close()
            results['enabled' if enabled else 'disabled'] = summarize(values)
    with args.output.open('x') as stream:
        json.dump(dict(format='virtualglove-diagnostic-overhead/1', architecture=platform.machine(),
            python=platform.python_version(), microseconds=results,
            limitations=['One synthetic event per iteration; excludes native C++ trace and disk export.',
                'Run on both devices, then repeat real workload with tracing off/on/off before attributing delays.']),
            stream, indent=2)
        stream.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
