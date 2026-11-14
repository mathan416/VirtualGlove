#!/usr/bin/env python3
"""Run one emulator and a passive exit watcher without changing game input."""
import argparse
import ctypes
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time


def stop(process, timeout=5):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()



def linux_parent_death(expected_parent):
    """Terminate the emulator if its supervisor dies, including the setup race."""
    # Popen forks after this supervisor has installed a SIGTERM handler.
    # Reset the inherited handler before arming or checking parent death.
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Could not configure parent-death signal')
    if os.getppid() != expected_parent:
        os.kill(os.getpid(), signal.SIGTERM)


def launch(watcher, config, es_inputs, command, workdir=None, use_sudo=False, timeout=10):
    if not command or not Path(command[0]).is_absolute():
        raise ValueError('The emulator command must use an absolute executable path')
    watcher_args = [sys.executable, '-u', str(watcher), '--config', str(config), '--es-inputs', str(es_inputs)]
    if use_sudo:
        watcher_args = ['/usr/bin/sudo', '-n'] + watcher_args
    observer = subprocess.Popen(watcher_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    child = None
    selector = selectors.DefaultSelector()
    handlers = {}
    interrupted = [None]
    try:
        selector.register(observer.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        pending = b''
        ready = False
        while time.monotonic() < deadline and not ready:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            data = os.read(observer.stdout.fileno(), 4096)
            if not data:
                break
            pending += data
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                if line == b'READY':
                    ready = True
                    break
        if not ready:
            raise RuntimeError('Passive exit watcher did not become ready')
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[sig] = signal.signal(sig, lambda number, _frame: interrupted.__setitem__(0, number))
        parent_pid = os.getpid()
        parent_death = (lambda: linux_parent_death(parent_pid)) if sys.platform.startswith('linux') else None
        child = subprocess.Popen(command, cwd=str(workdir) if workdir else None, preexec_fn=parent_death)
        while child.poll() is None and interrupted[0] is None:
            if b'\n' not in pending:
                if not selector.select(.1):
                    continue
                data = os.read(observer.stdout.fileno(), 4096)
                if not data:
                    raise RuntimeError('Passive exit watcher stopped unexpectedly')
                pending += data
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                if line == b'EXIT':
                    stop(child)
                    return 0
        if interrupted[0] is not None:
            stop(child)
            return 128 + interrupted[0]
        return child.wait()
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        stop(child)
        if observer.stdin:
            observer.stdin.close()
        try:
            observer.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # A normal watcher reads stdin EOF and exits promptly. Do not use
            # broad process-name killing if an elevated watcher misbehaves.
            try:
                stop(observer)
            except PermissionError:
                print('Passive exit watcher did not stop; inspect its process', file=sys.stderr)
        selector.close()
        if observer.stdout:
            observer.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watcher', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--es-inputs', type=Path, required=True)
    parser.add_argument('--workdir', type=Path)
    parser.add_argument('--sudo', action='store_true', help='Start the read-only watcher using sudo -n')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        return launch(args.watcher, args.config, args.es_inputs, command, args.workdir, args.sudo)
    except (OSError, ValueError, RuntimeError) as exc:
        print('Native exit launcher: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
