"""Optional merged-player bridge for explicitly registered computer emulators.

Reads Router's canonical output, never the physical devices. The parent keeps
stdin open for the session; EOF or SIGTERM closes the virtual output.
"""
import argparse
import os
import select
import signal
import struct
import sys
import time
from pathlib import Path

from .controller_router import PlayerState
from .merged_gamepad import AXIS_CODES, UInputMergedGamepad
from .native_merged_input import discover_merged

PROFILES = {
    'arcem': ('ArcEm Routed Player 1', 0x5752),
    'gsplus': ('GSplus Routed Player 1', 0x5751),
    'simcoupe': ('SAM Routed Player 1', 0x5753),
}


def wait_for_output(name, product, sys_input=Path('/sys/class/input'), dev_input=Path('/dev/input'), timeout=5):
    """Wait for the exact virtual device and joystick node before READY."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = []
        for entry in Path(sys_input).glob('event*'):
            device = entry / 'device'
            try:
                identity = ((device / 'name').read_text().strip(), int((device / 'id/vendor').read_text(), 16), int((device / 'id/product').read_text(), 16))
            except (OSError, ValueError):
                continue
            if identity == (name, 0x1209, product):
                matches.append(device)
        if len(matches) > 1:
            raise RuntimeError('Ambiguous emulator-facing Router device')
        if matches and any((Path(dev_input) / js.name).exists() for js in matches[0].glob('js*')):
            return
        time.sleep(.05)
    raise RuntimeError('Emulator-facing Router joystick did not become ready')


class SamControls:
    """Toggle typing on an unchorded hotkey release; detect the exit chord."""
    def __init__(self):
        self.typing = False
        self.held = False
        self.chord = False

    def apply(self, buttons, axes):
        buttons = set(buttons)
        if {'hotkey', 'start'} <= buttons or {'select', 'start'} <= buttons:
            return set(), {key: 0 for key in axes}, 'EXIT'
        message = None
        if 'hotkey' in buttons:
            if not self.held:
                self.held, self.chord = True, False
            if buttons - {'hotkey'}:
                self.chord = True
        elif self.held:
            self.held = False
            if not self.chord:
                self.typing = not self.typing
                message = 'FOCUS ' + ('ON' if self.typing else 'OFF')
        if self.typing:
            return set(), {key: 0 for key in axes}, message
        return buttons - {'hotkey'}, axes, message


def run(profile, player=1):
    name, product = PROFILES[profile]
    state = PlayerState(player)
    state.active = True
    sink = UInputMergedGamepad(name=name, product=product)
    opened = {}
    event = struct.Struct('llHHi')
    stopped = [False]
    previous = signal.signal(signal.SIGTERM, lambda *_: stopped.__setitem__(0, True))
    sam = SamControls() if profile == 'simcoupe' else None
    try:
        discover_merged(state, opened, (player,))
        if not opened:
            raise RuntimeError('Configured Router merged player is unavailable')
        wait_for_output(name, product)
        print('READY', flush=True)
        next_discovery = time.monotonic() + 1
        while not stopped[0]:
            if time.monotonic() >= next_discovery:
                discover_merged(state, opened, (player,))
                next_discovery = time.monotonic() + 1
            ready, _, _ = select.select([0] + list(opened), [], [], .1)
            if 0 in ready and not os.read(0, 1024):
                break
            for fd in ready:
                if fd == 0:
                    continue
                _, source, mapper = opened[fd]
                try:
                    data = os.read(fd, event.size * 64)
                    if not data:
                        raise OSError('disconnected')
                    for offset in range(0, len(data) - event.size + 1, event.size):
                        _, _, kind, code, value = event.unpack_from(data, offset)
                        if kind in (1, 3):
                            before = dict(source.axes)
                            mapper.event(kind, code, value)
                            for axis in AXIS_CODES:
                                if source.axes[axis] != before[axis]:
                                    source.axis_changed[axis] = time.monotonic()
                except OSError:
                    os.close(fd)
                    opened.pop(fd)
                    source.release()
            buttons, axes = state.desired()
            if sam:
                buttons, axes, message = sam.apply(buttons, axes)
                if message:
                    print(message, flush=True)
                if message == 'EXIT':
                    break
            sink.write(buttons, axes)
    finally:
        for fd in opened:
            os.close(fd)
        sink.close()
        signal.signal(signal.SIGTERM, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=sorted(PROFILES))
    parser.add_argument('--player', type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()
    run(args.profile, args.player)


if __name__ == '__main__':
    main()
