#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/run-native-latency-session.py
# Purpose: Guide repeatable stationary and movement windows with read-only status collection.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Added FCEUmm labeling and removed redundant full-session neutral holds.
#   2026-09-08 - Added smoke/full protocols, cue logs, and video annotation templates.
#   2026-09-06 - Add operator-paced native latency session evidence.
# Full history: docs/CHANGELOG.md and Git history.

"""Coordinate an external recording; never start controls, change settings, or open a camera."""
import argparse
import importlib.util
import json
import os
import threading
import time
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('status_measurement', Path(__file__).with_name('measure-vision-status.py'))
measurement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measurement)


def record_cue(stream, event, **fields):
    """Write local pacing evidence without claiming synchronization to the video."""
    item = {"event": event, "local_monotonic": time.monotonic(),
            "local_unix": time.time(), **fields}
    stream.write(json.dumps(item, allow_nan=False) + "\n")
    stream.flush()


def collect_window(url, output, label, phase, seconds, test='native', cue_stream=None,
                   trials=10, poll_interval=.25):
    """Keep operator cues separate from telemetry and from the video's clock."""
    print('\n%s: %d seconds. Start external recording before continuing.' % (label, seconds))
    input('Press Enter when framed and ready (Ctrl-C cancels): ')
    for remaining in (3, 2, 1):
        print(remaining, flush=True)
        if cue_stream:
            record_cue(cue_stream, "countdown", window=label, remaining=remaining)
        time.sleep(1)
    result = []
    thread = threading.Thread(
        target=lambda: result.append(measurement.collect(url, seconds, poll_interval, phase))
    )
    thread.start()
    started = time.monotonic()
    if cue_stream:
        record_cue(cue_stream, "window_start", window=label, phase=phase,
                   duration_seconds=seconds)
    if phase == 'movement':
        interval = seconds / trials
        for trial in range(trials):
            time.sleep(max(0, started + trial * interval - time.monotonic()))
            size = 'SHORT' if trial < max(1, trials // 2) else 'LONG'
            print('%s %d/%d: %s step, then hold' % (label, trial+1, trials, size), flush=True)
            if cue_stream:
                record_cue(cue_stream, "move", window=label, trial=trial + 1,
                           direction=label, size=size.lower())
            time.sleep(max(0, started + trial * interval + interval / 2 - time.monotonic()))
            print('Return to center and hold', flush=True)
            if cue_stream:
                record_cue(cue_stream, "return", window=label, trial=trial + 1)
    else:
        print('Hold an open hand still; support your forearm if practical.', flush=True)
    thread.join()
    if cue_stream:
        record_cue(cue_stream, "window_end", window=label)
    report = result[0]
    report['window_label'] = label
    report['test'] = test
    report['cue_clock'] = 'Mac local pacing only; not synchronized to video or device clocks'
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print('Finished: %d fresh samples, %d request errors.' % (report['observed_samples'], report['request_errors']))
    if not report['observed_samples']:
        raise RuntimeError('No active samples; verify delivery and status before continuing')
    if phase == 'neutral' and (len(report['segments']) != 1 or not report['segments'][0]['stationary_candidate']):
        print('REPEAT NEEDED: tracking/calibration/conditions or gesture checks failed. Video review is also required.')


def main():
    """Create one new local session directory and ask before each physical window."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status-url', type=measurement.status_url, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--test', choices=('native', 'dot', 'fceumm'), default='native',
                        help='Label evidence and show the matching preflight; does not launch an emulator')
    parser.add_argument('--protocol', choices=('smoke', 'full'), default='full',
                        help='smoke checks framing in about 45 seconds; full collects the baseline')
    parser.add_argument('--preflight', type=Path,
                        help='Optional preflight.json copied by digest into the session manifest')
    parser.add_argument('--poll-interval', type=float, default=.25,
                        help='Read-only status observation interval, 0.1-1.0 seconds (default: 0.25)')
    args = parser.parse_args()
    if not .1 <= args.poll_interval <= 1:
        parser.error('--poll-interval must be between 0.1 and 1.0 seconds')
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    cue_path = args.output_dir / 'cues.jsonl'
    preflight_digest = None
    if args.preflight:
        import hashlib
        preflight_digest = hashlib.sha256(args.preflight.read_bytes()).hexdigest()
    session = {"format": "virtualglove-guided-latency-session/3", "test": args.test,
               "protocol": args.protocol, "created_unix": time.time(),
               "preflight_sha256": preflight_digest,
               "cue_clock": "Mac local pacing only; not synchronized to video or device clocks"}
    (args.output_dir / 'session.json').write_text(json.dumps(session, indent=2) + '\n')
    os.chmod(args.output_dir / 'session.json', 0o600)
    directions = ('left', 'right') if args.protocol == 'smoke' else ('left', 'right', 'up', 'down')
    trials = 2 if args.protocol == 'smoke' else 10
    annotation = {"video_sha256": "REPLACE_AFTER_INDEXING", "timing_verified": False,
                  "seconds_per_pts_second": 1.0,
                  "trials": [{"label": "%s-%02d" % (direction, index + 1),
                              "direction": direction, "unoccluded": False,
                              "hand_onset": None, "game_onset": None}
                             for direction in directions for index in range(trials)],
                  "stationary": []}
    (args.output_dir / 'video-annotations.template.json').write_text(
        json.dumps(annotation, indent=2) + '\n')
    os.chmod(args.output_dir / 'video-annotations.template.json', 0o600)
    if args.test == 'dot':
        print('Preflight: launch Super Glove Ball with lr-powerglove-dot for this launch;')
        print('UNO Q MediaPipe baseline; active player and calibration; yellow dot and TRACKING;')
        print('The inset canvas is x=16..239, y=24..207. NO INPUT must remove the dot.')
        print('The installed wrapper traces for 300 seconds from launch; relaunch for later trace windows.')
    elif args.test == 'native':
        print('Preflight: native core/device 517; active player and calibration; Robo-Glove follows hand;')
    else:
        print('Preflight: launch a listed game with FCEUmm; active player and calibration;')
        print('Controller mode must show joystick output, with native X/Y inactive.')
    print('preview CLOSED; stable lighting; same game conditions; original hand+screen video framing checked.')
    print('Verify software identities and effective per-game video overrides separately. No configuration is changed.')
    with cue_path.open('x') as cues:
        os.chmod(cue_path, 0o600)
        record_cue(cues, "session_start", protocol=args.protocol, test=args.test)
        # One supported neutral window is sufficient. Additional neutral windows
        # are repeats only when that first sample is invalid, never routine work.
        neutral_count = 1
        neutral_seconds = 8 if args.protocol == 'smoke' else 20
        movement_seconds = 16 if args.protocol == 'smoke' else 60
        for index in range(1, neutral_count + 1):
            label = 'neutral-%d' % index
            collect_window(args.status_url, args.output_dir / (label+'.json'), label,
                           'neutral', neutral_seconds, args.test, cues,
                           poll_interval=args.poll_interval)
        for direction in directions:
            collect_window(args.status_url, args.output_dir / (direction+'.json'), direction,
                           'movement', movement_seconds, args.test, cues, trials=trials,
                           poll_interval=args.poll_interval)
        record_cue(cues, "session_end", protocol=args.protocol, test=args.test)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
