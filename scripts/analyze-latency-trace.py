#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/analyze-latency-trace.py
# Purpose: Correlate finite diagnostic samples without subtracting clocks across hosts.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-07 - Measure socket-return to native publication independently.
#   2026-09-06 - Separate processing, publication, and first native consumption evidence.
# Full history: docs/CHANGELOG.md and Git history.

"""Join Controller/receiver sessions, then receiver/core publication identities."""
import argparse
import csv
import json
import math
from pathlib import Path


def summary(values):
    """Report nearest-rank percentiles for individual valid observations."""
    if not values:
        return {'samples': 0}
    values = sorted(values)
    return dict(samples=len(values), min=values[0], p50=values[math.ceil(len(values)*.5)-1],
                p95=values[math.ceil(len(values)*.95)-1], max=values[-1])


def analyze(controller, receiver, core):
    """Never infer network transit or combine percentiles from separate clocks."""
    for report, role in ((controller, 'controller'), (receiver, 'receiver')):
        if report.get('format') != 'virtualglove-diagnostic/1' or report.get('role') != role:
            raise ValueError('Wrong diagnostic format or role')
    metrics = {key: [] for key in ('capture_timestamp_to_processing', 'capture_read_to_processing',
        'processing', 'tracking', 'gesture_and_calibration', 'encode_and_send',
        'capture_timestamp_to_send', 'capture_read_to_send', 'processing_to_send_start',
        'receipt_to_validation', 'validation_to_publication_start',
        'publication', 'receiver_to_native_publication', 'native_write',
        'publication_record_to_first_core_consumption')}
    invalid = 0

    def interval(name, start, end):
        """Exclude malformed/backwards intervals rather than reporting negative latency."""
        nonlocal invalid
        if type(start) is int and type(end) is int and 0 <= start <= end:
            metrics[name].append((end-start)/1e6)
        else:
            invalid += 1

    sends, visions, receives = {}, {}, {}
    for event in controller['events']:
        key = (event['session'], event['sequence'])
        if event['event'] == 'send':
            sends[key] = event
            interval('encode_and_send', event['start_ns'], event['end_ns'])
        elif event['event'] == 'vision':
            visions[key] = event
            interval('capture_timestamp_to_processing', event['capture_ns'], event['start_ns'])
            if event.get('capture_ready_ns') is not None:
                interval('capture_read_to_processing', event['capture_ready_ns'], event['start_ns'])
            interval('processing', event['start_ns'], event['end_ns'])
            if event.get('tracking_end_ns') is not None:
                interval('tracking', event['start_ns'], event['tracking_end_ns'])
                interval('gesture_and_calibration', event['tracking_end_ns'], event['end_ns'])
    for key in sends.keys() & visions.keys():
        interval('capture_timestamp_to_send', visions[key]['capture_ns'], sends[key]['end_ns'])
        if visions[key].get('capture_ready_ns') is not None:
            interval('capture_read_to_send', visions[key]['capture_ready_ns'], sends[key]['end_ns'])
        interval('processing_to_send_start', visions[key]['end_ns'], sends[key]['start_ns'])
    publications = {}
    for event in receiver['events']:
        key = (event['session'], event['sequence'])
        receives[key] = event
        interval('receipt_to_validation', event['received_ns'], event['validated_ns'])
        interval('validation_to_publication_start', event['validated_ns'], event['publication_start_ns'])
        if event['published_ns'] is not None:
            interval('publication', event['publication_start_ns'], event['end_ns'])
            if event.get('native_end_ns'):
                interval('receiver_to_native_publication', event['received_ns'],
                         event['native_end_ns'])
                interval('native_write', event.get('native_start_ns'),
                         event['native_end_ns'])
            publications[(event['sequence'], event['guard'], event['published_ns'])] = event
    consumed, unmatched, invalid_core = set(), 0, 0
    for event in core:
        if not event['valid']:
            invalid_core += 1
            continue
        key = (event['sequence'], event['guard'], event['published_ns'])
        if key in consumed:
            continue
        if key not in publications:
            unmatched += 1
            continue
        consumed.add(key)
        interval('publication_record_to_first_core_consumption', event['published_ns'], event['consumed_ns'])
    return dict(format='virtualglove-latency-analysis/1', timings_ms={k: summary(v) for k,v in metrics.items()},
        correlated_send_receive=len(sends.keys() & receives.keys()),
        sends_without_observed_receipt=len(sends.keys()-receives.keys()),
        publications_without_observed_consumption=len(publications.keys()-consumed),
        unmatched_core_observations=unmatched, invalid_core_callbacks=invalid_core,
        invalid_intervals=invalid, trace_drops=dict(controller=controller['dropped'], receiver=receiver['dropped']),
        network_transit_ms=None, display_latency_ms=None,
        limitations=['Unmatched events include trace-window boundaries and dropped diagnostics, not proven packet loss.',
            'Receipt timestamp is after recvmsg/recvfrom returns, not kernel/NIC arrival.',
            'Publication timestamp is taken at write start; consumption includes coherent-record publication cost.',
            'Core callback pickup is not ROM response or physical display presentation.',
            'Cross-host clocks are deliberately not subtracted; network transit remains unmeasured.',
            'A paired receiver/core capture must come from the same cabinet boot and native-state path.'])


def main():
    """Read bounded temporary traces and create a new aggregate report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller', type=Path, required=True)
    parser.add_argument('--receiver', type=Path, required=True)
    parser.add_argument('--core', type=Path)
    parser.add_argument('--same-cabinet-boot', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.core and not args.same_cabinet_boot:
        parser.error('Confirm receiver and core used the same cabinet boot/path with --same-cabinet-boot')
    core, dropped = [], 0
    if args.core:
        lines = args.core.read_text().splitlines()
        if not lines or not lines[-1].startswith('# dropped='):
            parser.error('Core trace was not finalized by a clean game unload')
        dropped = int(lines[-1].split('=')[1])
        core = [{k:int(v) for k,v in row.items()} for row in csv.DictReader(lines[:-1])]
    report = analyze(json.loads(args.controller.read_text()), json.loads(args.receiver.read_text()), core)
    report['trace_drops']['core'] = dropped
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
