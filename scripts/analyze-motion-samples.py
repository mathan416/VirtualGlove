#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/analyze-motion-samples.py
# Purpose: Analyze saved native-motion samples and smoothing step response.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Exercised the real latest-coordinate lane in unsmoothed simulations.
#   2026-09-07 - Updated ideal steps for the bounded native speed curve.
#   2026-09-06 - Added offline motion-sample analysis for latency tuning.
# Full history: docs/CHANGELOG.md and Git history.

"""Summarize saved telemetry and model smoothing only; never replay controller input."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from virtualglove.gesture import GestureConfig, GestureEngine
from virtualglove.model import Calibration, HandObservation


def step_response(distance, hz=60, unsmoothed=False):
    """Exercise the actual engine with an ideal instantaneous measured-position step."""
    config = GestureConfig()
    if unsmoothed:
        config = replace(config, motion_noise_multiplier=0., motion_noise_floor=0.,
                         motion_slow_follow=1.)
    engine = GestureEngine('super_glove_ball', config=config,
                           calibration=Calibration(.5, .5, .2, 0))
    initial = HandObservation(10., True, .95, .5, .5, .2)
    engine.update_native_motion(initial, initial, bounded=not unsmoothed)
    rows = []
    for i in range(1, int(hz) + 1):
        pose = replace(initial, timestamp=10+i/hz, palm_x=.5+distance)
        engine.update_native_motion(pose, pose, bounded=not unsmoothed)
        rows.append({'ms_after_first_step_sample': (i-1)*1000/hz,
                     'selected_x': pose.palm_x, 'filtered_x': engine._filtered_palm_x})
    settled = next((r['ms_after_first_step_sample'] for r in rows
                    if abs(r['filtered_x']-(.5+distance)) <= .05*abs(distance)), None)
    return {'distance_camera_units': distance, 'hz': hz, 'unsmoothed': unsmoothed,
            'noise_multiplier': config.motion_noise_multiplier,
            'slow_follow': config.motion_slow_follow,
            'full_speed': config.motion_full_speed,
            'time_to_95_percent_ms': settled, 'samples': rows}


def summarize(directory):
    """Return aggregate evidence for saved status samples in one directory."""
    result = {}
    for name in ('game1-uno.json', 'xy2-movement-uno.json', 'xy3-movement-uno.json'):
        p = directory/name
        if not p.exists():
            continue
        source = json.loads(p.read_text())
        if 'segments' in source:
            n = sum(s['observed_samples'] for s in source['segments'])
            valid = sum(s['detected_samples'] for s in source['segments'])
            losses = sum(s['tracking_losses'] for s in source['segments'])
        else:
            rows = source['rows']; n = len(rows)
            valid = sum(r['motion_valid'] is True for r in rows)
            losses = sum(a['motion_valid'] is True and b['motion_valid'] is False
                         for a, b in zip(rows, rows[1:]))
        result[name] = {'samples': n, 'detected_samples': valid,
                        'detected_percent': round(100*valid/n, 2) if n else None,
                        'observed_losses': losses,
                        'per_move_coordinate_replay_available': False}
    return result


def main():
    """Parse arguments and create a new aggregate motion-analysis report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'telemetry': summarize(args.samples_dir),
              'simulation': [step_response(d, unsmoothed=u)
                             for d in (.01, .025, .05, .10, .20) for u in (False, True)],
              'limitations': [
                  'Step model uses code defaults and 60 Hz, not a recorded hand trajectory.',
                  'Smoothing response excludes capture, recognition, transport, game, and display delay.',
                  'Saved telemetry cannot identify intermediate images, settling time, or overshoot per move.',
                  'No prediction accuracy or end-to-end latency can be established without time-aligned reference motion.',
                  'Separate sessions contain different physical movements; percentages are descriptive, not a controlled comparison.']}
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    for row in report['simulation']:
        if not row['unsmoothed']:
            print('Step %.3f: %.1f ms to 95%% (bounded speed-curve model)' %
                  (row['distance_camera_units'], row['time_to_95_percent_ms']))


if __name__ == '__main__':
    main()
