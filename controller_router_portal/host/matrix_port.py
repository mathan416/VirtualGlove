"""Restrict the Matrix service to a loopback-only host port."""
from __future__ import annotations

import re
from contextlib import contextmanager, nullcontext


def _matrix_loopback_compose(source: str) -> tuple[str, bool]:
    """Bind the main Matrix port to loopback in supported App Lab Compose formats."""
    lines = source.splitlines(keepends=True)
    in_services = False
    in_main = False
    ports_start = ports_end = None
    main_line = None
    empty_port_line = None
    for index, line in enumerate(lines):
        if re.match(r"^services:\s*(?:#.*)?$", line):
            in_services = True
            continue
        if in_services and re.match(r"^[^\s#]", line):
            break
        if not in_services:
            continue
        if re.match(r"^  [^\s#][^:]*:\s*(?:#.*)?$", line):
            in_main = bool(re.match(r"^  main:\s*(?:#.*)?$", line))
            if in_main:
                if main_line is not None:
                    raise RuntimeError("Duplicate Matrix main service in App Lab Compose")
                main_line = index
            continue
        if in_main and re.match(r"^    ports:\s*\[\s*\]\s*(?:#.*)?$", line):
            if ports_start is not None or empty_port_line is not None:
                raise RuntimeError("Duplicate Matrix ports in App Lab Compose")
            empty_port_line = index
            continue
        if in_main and re.match(r"^    ports:", line) and not re.match(r"^    ports:\s*(?:#.*)?$", line):
            raise RuntimeError("Unsupported Matrix port format in App Lab Compose")
        if in_main and re.match(r"^    ports:\s*(?:#.*)?$", line):
            if ports_start is not None or empty_port_line is not None:
                raise RuntimeError("Duplicate Matrix ports in App Lab Compose")
            ports_start = index + 1
            ports_end = ports_start
            while ports_end < len(lines) and (not lines[ports_end].strip() or
                    lines[ports_end].startswith("      ")):
                ports_end += 1
    if empty_port_line is not None:
        lines[empty_port_line] = '    ports:\n      - "127.0.0.1:8123:8123"\n'
        return "".join(lines), True
    if ports_start is None:
        if main_line is None:
            raise RuntimeError("App Lab did not create the expected Matrix service")
        lines.insert(main_line + 1, '    ports:\n      - "127.0.0.1:8123:8123"\n')
        return "".join(lines), True
    entries = []
    for index in range(ports_start, ports_end):
        if re.match(r"^      -\s", lines[index]):
            if entries:
                entries[-1][1] = index
            entries.append([index, ports_end])
    # The Matrix app declares a single port. Refuse any extra entry: it could
    # publish the same target through an unsupported or public binding.
    if len(entries) != 1:
        raise RuntimeError("App Lab did not create exactly one Matrix service port")
    matches = []
    for first, end in entries:
        entry = lines[first:end]
        short = re.match(r"^(      - )([\"']?)(?:(127\.0\.0\.1):)?8123:8123(?:/tcp)?\2\s*(?:#.*)?$", entry[0])
        if short:
            matches.append((first, end, "short", bool(short.group(3))))
            continue
        def field(name):
            values = [match.group(1).strip().strip("\"'") for line in entry
                      if (match := re.match(r"^        " + name + r":\s*([^#\n]+)", line))]
            if len(values) > 1:
                raise RuntimeError("Duplicate Matrix port field in App Lab Compose")
            return values[0] if values else None
        if field("target") == "8123" and field("published") == "8123":
            host, protocol = field("host_ip"), field("protocol")
            if host not in (None, "127.0.0.1") or protocol not in (None, "tcp"):
                raise RuntimeError("Unsupported Matrix port binding in App Lab Compose")
            matches.append((first, end, "long", host == "127.0.0.1"))
    if len(matches) != 1:
        raise RuntimeError("App Lab did not create exactly one expected Matrix service port")
    first, end, kind, already = matches[0]
    if already:
        return source, False
    if kind == "short":
        lines[first] = re.sub(r"8123:8123", "127.0.0.1:8123:8123", lines[first], count=1)
    else:
        lines.insert(end, "        host_ip: 127.0.0.1\n")
    return "".join(lines), True



@contextmanager
def matrix_port_lock(lock):
    """Serialize Matrix lifecycle changes with the port watchdog."""
    import fcntl
    import os
    from pathlib import Path

    lock = Path(lock)
    lock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def configure_loopback(compose, lock, runner=None, force=False, safe_to_restart=None, lock_held=False):
    """Bind a generated Matrix Compose file once, serializing our own writers."""
    import os
    import subprocess
    from pathlib import Path

    compose = Path(compose)
    # The installer holds this lock across the full stop/swap/start/rollback.
    # Reacquiring flock on a new fd would deadlock even within one process.
    with (nullcontext() if lock_held else matrix_port_lock(lock)):
        original = compose.read_text()
        updated, changed = _matrix_loopback_compose(original)
        if not changed and not force:
            return False
        if safe_to_restart is not None and not safe_to_restart():
            return False
        temp = compose.with_name('.app-compose.matrix.tmp')
        if changed:
            temp.write_text(updated)
            os.replace(temp, compose)
        try:
            (runner or subprocess.run)(
                ['docker', 'compose', '-p', 'controller-router', '-f', str(compose),
                 'up', '-d', '--force-recreate', 'main'],
                check=True, capture_output=True, text=True, timeout=90)
        except BaseException:
            if changed and compose.read_text() == updated:
                temp.write_text(original)
                os.replace(temp, compose)
            raise
        return True
