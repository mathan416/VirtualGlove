#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/calibrate-reach.py
# Purpose: Record per-player comfortable reach through the existing calibration APIs.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Port guided reach calibration with raw palm samples and practice isolation.
# Full history: docs/CHANGELOG.md and Git history.

"""Run begin, center, left, right, up, down, apply as separate, player-cued steps.

Run inside the Controller container with its worker Python environment. No images
are saved. Output stays paused after apply/cancel; do not launch games or change
players during a session. Cancel restores the original complete hand setup.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import json
import math
from pathlib import Path
import statistics
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from virtualglove.game_registry import atomic_write
from virtualglove.gesture import load_calibration
from virtualglove.players import calibration_value

DIRECTIONS = ('left', 'right', 'up', 'down')


def measure_span(direction, positions, center, observed_count):
    """Reject insufficient, unstable, clipped, or wrong-side raw-palm holds."""
    if direction not in DIRECTIONS:
        raise ValueError('Choose left, right, up, or down.')
    if len(positions) < 12 or len(positions) < .8 * observed_count:
        raise ValueError('Insufficient reliable tracking; retry this pose.')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
           for v in positions):
        raise ValueError('Invalid camera positions; retry this pose.')
    values = sorted(positions)
    median = statistics.median(values)
    spread = values[int((len(values)-1)*.9)] - values[int((len(values)-1)*.1)]
    sign = -1 if direction in ('left', 'up') else 1
    span = sign * (median - center)
    if span < .05:
        raise ValueError('Move farther in the requested on-screen direction and retry.')
    if median <= .025 or median >= .975:
        raise ValueError('Too close to the camera boundary; use a closer comfortable reach.')
    if spread > min(.03, .12 * span):
        raise ValueError('Pose varied too much; hold steady and retry.')
    return dict(span=span, samples=len(values), position_median=median,
                position_p10_p90_span=spread)


class ReachSession:
    """Use existing generation-checked restore and persistent controller-stop APIs."""

    def __init__(self, root=ROOT, clock=time.monotonic, sleep=time.sleep):
        self.root, self.clock, self.sleep = root, clock, sleep
        self.path = root / 'data/reach-calibration-session.json'
        self.center_path = root / 'data/calibration.json'
        self.last_renewed = float('-inf')

    def get(self):
        """Read uncached worker status so repeated polls cannot inflate samples."""
        with urllib.request.urlopen('http://127.0.0.1:8089/status', timeout=3) as response:
            return json.load(response)

    def post(self, endpoint, data):
        """Route mutations through the supervisor to persist output stops."""
        request = urllib.request.Request('http://127.0.0.1:8088/' + endpoint,
            data=json.dumps(data).encode(), headers={'Content-Type': 'application/json',
                'X-VirtualGlove-Action': endpoint.rsplit('/', 1)[-1]})
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read()
            return json.loads(body) if body else None

    def persist(self, session):
        """Atomically retain progress and rollback metadata with private permissions."""
        atomic_write(self.path, json.dumps(session, indent=2, allow_nan=False) + '\n')

    @staticmethod
    def player_args(session):
        """Bind each operation to the same active player generation."""
        return {key: session['player'][source] for key, source in
                (('player', 'active'), ('generation', 'generation'))}

    def check(self, session, status):
        """Reject identity changes, tuning, or re-enabled delivery before accepting data."""
        player = status.get('player', {})
        if any(player.get(key) != session['player'][key] for key in ('active', 'generation')):
            raise ValueError('Player changed; calibration not applied. Restore the saved backup for its original player.')
        if status.get('controller_enabled') or status.get('tuning', {}).get('active'):
            raise ValueError('Output or gesture tuning was enabled; pause it before continuing.')

    def renew(self, session):
        """Keep practice active during a step; optical flow and delivery stay bypassed."""
        if self.clock() - self.last_renewed >= 1:
            self.post('api/practice', {'session': session['lease'], 'enabled': True})
            self.last_renewed = self.clock()

    def wait_practice(self, session):
        """Wait for synchronous camera recognition without changing the game profile."""
        deadline = self.clock() + 30
        while self.clock() < deadline:
            self.renew(session)
            status = self.get()
            # The persisted stop may still be crossing the supervisor boundary.
            self.check(session, dict(status, controller_enabled=False))
            if (not status.get('controller_enabled') and status.get('practice_mode')
                    and status.get('vision_state') == 'active'):
                return
            self.sleep(.1)
        raise ValueError('Camera practice did not become ready; check Dashboard.')

    def center(self, session):
        """Recenter normally, clear previous reach, and verify the saved player identity."""
        before = self.center_path.stat().st_mtime_ns
        self.post('calibrate', {})
        deadline = self.clock() + 30
        while self.clock() < deadline:
            self.renew(session)
            status = self.get()
            self.check(session, status)
            if (self.center_path.stat().st_mtime_ns != before and status.get('calibrated')
                    and not status.get('calibrating')):
                reference = load_calibration(self.center_path)
                if reference is not None and all(getattr(reference, 'reach_' + d) == 0 for d in DIRECTIONS):
                    session.update(center=asdict(reference), samples={})
                    self.persist(session)
                    return 'Center saved. Next, hold your comfortable left position.'
            self.sleep(.1)
        raise ValueError('Center not completed; hold a steady visible open hand and retry.')

    def hold(self, session, direction):
        """Sample three seconds of independent, confident raw palm positions."""
        if 'center' not in session:
            raise ValueError('Record center first.')
        reference = load_calibration(self.center_path)
        if reference is None or asdict(reference) != session['center']:
            raise ValueError('Center changed; record center again before measuring reach.')
        axis = 'x' if direction in ('left', 'right') else 'y'
        values, seen = [], set()
        deadline = self.clock() + 3
        while self.clock() < deadline:
            self.renew(session)
            status = self.get()
            self.check(session, status)
            if not status.get('practice_mode'):
                raise ValueError('Practice was interrupted; retry this pose.')
            identity = (status.get('timestamp'), status.get('capture_sequence'))
            if None not in identity and identity not in seen:
                seen.add(identity)
                position = status.get('palm_position') or {}
                if (status.get('detected') and status.get('confidence', 0) >= .75
                        and status.get('calibrated') and not status.get('calibrating')
                        and axis in position and status.get('sample_age_ms', 1000) < 250):
                    values.append(position[axis])
            self.sleep(.02)
        current = load_calibration(self.center_path)
        if current is None or asdict(current) != session['center']:
            raise ValueError('Center changed during this hold; retry after recentering.')
        measured = measure_span(direction, values, session['center']['palm_' + axis], len(seen))
        session['samples'][direction] = measured
        self.persist(session)
        return json.dumps({direction: measured})

    def restore(self, session, apply):
        """Apply reach or roll back through the existing durable player restore path."""
        backup = copy.deepcopy(session['backup'])
        if apply:
            if set(session['samples']) != set(DIRECTIONS):
                raise ValueError('Record all four reach positions first.')
            current = load_calibration(self.center_path)
            if current is None or asdict(current) != session.get('center'):
                raise ValueError('Center changed; not applying reach.')
            neutral = dict(session['center'])
            neutral.update({'reach_' + k: v['span'] for k, v in session['samples'].items()})
            backup['calibration'] = calibration_value({'version': 2, 'neutral': neutral})
        previous_player = session['player']
        result = self.post('api/players', dict(action='restore', backup=backup,
            reuse_calibration=True, **self.player_args(session)))
        session['player'] = result
        session['state'] = 'restoring'
        self.persist(session)
        deadline = self.clock() + 10
        while self.clock() < deadline:
            self.renew(session)
            status = self.get()
            if all(status.get('player', {}).get(k) == previous_player[k] for k in ('active', 'generation')):
                self.sleep(.1)
                continue
            self.check(session, status)
            actual = load_calibration(self.center_path)
            if (not status['player'].get('restoring_calibration')
                    and not status['player'].get('needs_center') and actual is not None
                    and asdict(actual) == calibration_value(backup['calibration'])['neutral']):
                session['state'] = 'applied' if apply else 'cancelled'
                self.persist(session)
                self.post('api/practice', {'session': session['lease'], 'enabled': False})
                return ('Reach saved.' if apply else 'Original setup restored.') + ' Output remains paused.'
            self.sleep(.1)
        raise ValueError('Restore pending; verify player status before resuming. The rollback backup remains available.')

    def run(self, step):
        """Perform exactly one player-cued step, leaving pauses under user control."""
        if step == 'begin':
            if self.path.exists() and json.loads(self.path.read_text())['state'] in ('active', 'restoring'):
                raise ValueError('A reach session already exists; finish/cancel it or inspect its pending restore.')
            status = self.get()
            player = status['player']
            if player.get('needs_center') or status.get('tuning', {}).get('active'):
                raise ValueError('Finish player centering/tuning first.')
            session = dict(state='active', player=player, samples={}, lease='reach-' + uuid.uuid4().hex)
            backup = self.post('api/players', dict(action='export', **self.player_args(session)))['backup']
            if backup['calibration'] is None:
                raise ValueError('Set your hand center first.')
            folder = self.root / 'data/backups' / session['lease']
            folder.mkdir(mode=0o700, parents=True)
            backup_path = folder / 'hand-setup.json'
            atomic_write(backup_path, json.dumps(backup, indent=2) + '\n')
            session.update(backup=backup, backup_path=str(backup_path))
            self.persist(session)
            self.post('api/controller', {'enabled': False})
            self.wait_practice(session)
            return 'Output paused. Hold a relaxed center pose, then run center. Backup: ' + str(backup_path)
        session = json.loads(self.path.read_text())
        if session['state'] != 'active':
            raise ValueError('No active reach session; inspect Dashboard if a restore is pending.')
        self.check(session, self.get())
        if step == 'cancel':
            return self.restore(session, False)
        self.wait_practice(session)
        if step == 'center':
            return self.center(session)
        if step in DIRECTIONS:
            return self.hold(session, step)
        return self.restore(session, step == 'apply')


def main():
    """Expose explicit steps without recording hand positions before a player cue."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=('begin', 'center', *DIRECTIONS, 'apply', 'cancel'))
    args = parser.parse_args()
    try:
        print(ReachSession().run(args.step))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
