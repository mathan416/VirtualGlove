"""Run an explicitly configured computer emulator with its Router bridge."""
import argparse
import os
import selectors
import signal
import subprocess
import sys
import time


def stop(process, timeout=3):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def launch(profile, command, player=1, timeout=10):
    if not command:
        raise ValueError('An emulator command is required')
    bridge = subprocess.Popen([sys.executable, '-u', '-m', 'router_shared.computer_bridge', profile,
                               '--player', str(player)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              bufsize=0)
    child = None
    previous = {}
    interrupted = [False]
    selector = selectors.DefaultSelector()
    try:
        selector.register(bridge.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        buffer = b''
        ready = False
        while not ready and time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            chunk = os.read(bridge.stdout.fileno(), 4096)
            if not chunk:
                break
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                if line == b'READY':
                    ready = True
                    break
        if not ready:
            raise RuntimeError('Router bridge failed to become ready')
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: interrupted.__setitem__(0, True))
        env = os.environ.copy()
        if profile == 'gsplus':
            env['GSPLUS_ROUTER_NAME'] = 'GSplus Routed Player 1'
        child = subprocess.Popen(command, env=env)
        while child.poll() is None and not interrupted[0]:
            if b'\n' in buffer or selector.select(.1):
                if b'\n' in buffer:
                    chunk = None
                else:
                    chunk = os.read(bridge.stdout.fileno(), 4096)
                if chunk == b'':
                    raise RuntimeError('Router bridge stopped during emulator session')
                if chunk is not None:
                    buffer += chunk
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line == b'EXIT':
                        stop(child)
                        return 0
                    if line.startswith(b'FOCUS '):
                        print(line.decode('ascii'), flush=True)
        if interrupted[0]:
            stop(child)
            return 128 + signal.SIGTERM
        return child.wait()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        stop(child)
        if bridge.stdin:
            bridge.stdin.close()
        try:
            bridge.wait(timeout=3)
        except subprocess.TimeoutExpired:
            stop(bridge)
        selector.close()
        if bridge.stdout:
            bridge.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=('arcem', 'gsplus', 'simcoupe'))
    parser.add_argument('--player', type=int, choices=range(1, 5), default=1)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        return launch(args.profile, command, args.player)
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
