#!/usr/bin/env python3
"""Observe saved Player 1 sources for Hotkey/Select+Start; do not grab or inject input.

Protocol: print READY at startup, print EXIT once on a same-source chord, and
exit on stdin EOF or SIGTERM. Device reconnects are rediscovered from stable
saved identities. This helper does not configure or drive an emulator.
"""
import argparse
import os
from pathlib import Path
import select
import signal
import struct
import sys
import time

from router_shared.controller_router import SourceState, _MapperState, load_config, session_mapping
from router_shared.merged_gamepad import (
    PhysicalMapper, controller_candidates, find_saved_controller,
    input_axis_ranges, translate_es_mapping,
)

EV_SYN = 0
SYN_REPORT = 0
SYN_DROPPED = 3


class ChordTracker:
    """Keep each source separate and require a new press after state loss."""
    def __init__(self, mapping, axis_ranges=None):
        self.state = SourceState()
        self.mapper = PhysicalMapper(mapping, _MapperState(self.state), axis_ranges)
        self.latched = False
        self.desynchronized = False

    def release(self):
        self.state.release()
        self.latched = False
        self.desynchronized = False

    def event(self, kind, code, value):
        if kind == EV_SYN and code == SYN_DROPPED:
            self.release()
            self.desynchronized = True
            return False
        if self.desynchronized:
            if kind == EV_SYN and code == SYN_REPORT:
                self.desynchronized = False
            return False
        self.mapper.event(kind, code, value)
        active = ('start' in self.state.buttons and
                  bool({'hotkey', 'select'} & self.state.buttons))
        fired = active and not self.latched
        self.latched = active
        return fired


def distinct_chord(mapping):
    """A single button must never count as both sides of the exit chord."""
    starts = {(x['type'], x['code']) for x in mapping if x['name'] == 'start'}
    triggers = {(x['type'], x['code']) for x in mapping if x['name'] in ('hotkey', 'select')}
    return bool(starts and (triggers - starts))


def open_saved_sources(saved, es_inputs, opened):
    """Open only known Player 1 sources read-only and nonexclusively."""
    if not saved:
        return
    try:
        candidates = controller_candidates(es_inputs)
    except (OSError, ValueError):
        return
    for source in saved:
        if any(row[0] == source['id'] for row in opened.values()):
            continue
        candidate = find_saved_controller(source, candidates)
        if candidate is None or any(row[1] == candidate['event'] for row in opened.values()):
            continue
        joystick = event_fd = None
        try:
            joystick = os.open(candidate['joystick'], os.O_RDONLY | os.O_NONBLOCK)
            mapping = translate_es_mapping(session_mapping(source, candidate), joystick)
            # Exit chords use button mappings only: raw unsigned axes may be
            # nonzero at rest and must not be mistaken for held buttons.
            mapping = [row for row in mapping if row['name'] in ('hotkey', 'select', 'start')
                       and row['type'] == 'button']
            if not distinct_chord(mapping):
                continue
            starts = {(row['type'], row['code']) for row in mapping if row['name'] == 'start'}
            mapping = [row for row in mapping if row['name'] == 'start' or
                       (row['type'], row['code']) not in starts]
            event_fd = os.open(candidate['event'], os.O_RDONLY | os.O_NONBLOCK)
            tracker = ChordTracker(mapping, input_axis_ranges(event_fd, mapping))
            opened[event_fd] = (source['id'], candidate['event'], tracker)
            event_fd = None
        except (OSError, ValueError, KeyError):
            continue
        finally:
            if joystick is not None:
                os.close(joystick)
            if event_fd is not None:
                os.close(event_fd)


def run(config_path, es_inputs, stdin_fd=0):
    config = load_config(Path(config_path))
    saved = next((entry['sources'] for entry in config['players'] if entry['player'] == 1), [])
    if not saved:
        raise ValueError('No Player 1 physical sources are assigned')
    opened = {}
    event = struct.Struct('llHHi')
    stopped = [False]
    previous = signal.signal(signal.SIGTERM, lambda *_: stopped.__setitem__(0, True))
    try:
        open_saved_sources(saved, Path(es_inputs), opened)
        if not opened:
            print('Exit watcher: no assigned Player 1 source is currently available; retrying', file=sys.stderr, flush=True)
        print('READY', flush=True)
        next_discovery = time.monotonic() + 1
        while not stopped[0]:
            if time.monotonic() >= next_discovery:
                open_saved_sources(saved, Path(es_inputs), opened)
                next_discovery = time.monotonic() + 1
            ready, _, _ = select.select([stdin_fd] + list(opened), [], [], .2)
            if stdin_fd in ready and not os.read(stdin_fd, 1024):
                break
            for fd in ready:
                if fd == stdin_fd:
                    continue
                _, _, tracker = opened[fd]
                try:
                    data = os.read(fd, event.size * 64)
                    if not data or len(data) % event.size:
                        raise OSError('disconnected or malformed event read')
                    for offset in range(0, len(data), event.size):
                        _, _, kind, code, value = event.unpack_from(data, offset)
                        if tracker.event(kind, code, value):
                            print('EXIT', flush=True)
                            return 0
                except OSError:
                    os.close(fd)
                    opened.pop(fd)
                    tracker.release()
    finally:
        for fd, (_, _, tracker) in opened.items():
            tracker.release()
            os.close(fd)
        signal.signal(signal.SIGTERM, previous)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--es-inputs', type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args.config, args.es_inputs)
    except (OSError, ValueError) as exc:
        print('Exit watcher: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
