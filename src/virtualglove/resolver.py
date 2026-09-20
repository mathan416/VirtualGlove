# Project: VirtualGlove
# File: src/virtualglove/resolver.py
# Purpose: Resolve .local names through the host Avahi socket inside App Lab containers.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-03 - Added persistent host mDNS resolution without pinned IP addresses.

"""Use host Avahi for local IPv4 names; retain ordinary DNS elsewhere."""
import ipaddress
import socket
import time
from pathlib import Path

AVAHI_SOCKET = "/run/avahi-daemon/socket"
APP_AVAHI_SOCKET = Path(__file__).resolve().parents[2] / "data/.avahi-resolver.sock"
_cache = {}


def resolve_ipv4(host):
    """Resolve an IPv4 destination, refreshing local addresses every five seconds."""
    name = host.rstrip(".")
    endpoint = str(APP_AVAHI_SOCKET) if APP_AVAHI_SOCKET.exists() else AVAHI_SOCKET
    if not name.lower().endswith(".local") or not Path(endpoint).exists():
        return socket.gethostbyname(host)
    if not name.isascii() or any(c.isspace() for c in name) or len(name) > 253:
        raise socket.gaierror("Invalid local hostname")
    cached = _cache.get(name)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.5)
        connection.connect(endpoint)
        connection.sendall(("RESOLVE-HOSTNAME-IPV4 " + name + "\n").encode("ascii"))
        response = b""
        while b"\n" not in response and len(response) < 1024:
            chunk = connection.recv(1024 - len(response))
            if not chunk:
                break
            response += chunk
    fields = response.decode("ascii", "replace").split()
    if len(fields) != 5 or fields[0] != "+" or fields[3].lower().rstrip(".") != name.lower():
        raise socket.gaierror("Avahi could not resolve " + name)
    try:
        address = str(ipaddress.IPv4Address(fields[4]))
    except ValueError:
        raise socket.gaierror("Avahi returned an invalid IPv4 address") from None
    if len(_cache) >= 256:
        _cache.clear()
    _cache[name] = (now + 5.0, address)
    return address


class BackgroundAddress:
    """Refresh one address without ever retaining or queuing controller states."""
    def __init__(self, host, resolve=resolve_ipv4, refresh_seconds=5.0):
        import threading
        self.host, self.resolve = host, resolve
        self.refresh_seconds = refresh_seconds
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.address = None
        self.expires = 0.0
        self.error = "Resolving console address…"
        self.last_ms = None
        self.thread = None
        try:
            self.address = str(ipaddress.IPv4Address(host))
            self.expires = float("inf")
            self.error = None
        except ipaddress.AddressValueError:
            if host.strip():
                self.thread = threading.Thread(target=self._run, name="controller-address", daemon=True)
                self.thread.start()

    def _run(self):
        """Keep one resolver operation in flight and expire stale answers after ten seconds."""
        while not self.closed.is_set():
            started = time.monotonic()
            try:
                address = self.resolve(self.host)
                address = str(ipaddress.IPv4Address(address))
                with self.lock:
                    self.address, self.expires, self.error = address, time.monotonic() + 10.0, None
                    self.last_ms = (time.monotonic() - started) * 1000
                delay = self.refresh_seconds
            except (OSError, ValueError) as exc:
                with self.lock:
                    self.error = str(exc)
                    self.last_ms = (time.monotonic() - started) * 1000
                delay = 2.0
            self.closed.wait(delay)

    def current(self):
        """Return a fresh cached address immediately; no network operation runs here."""
        with self.lock:
            return (self.address if time.monotonic() < self.expires else None,
                    self.error or "Console address expired; waiting for refresh.")

    def close(self):
        """Stop scheduling work without waiting for a blocked operating-system DNS call."""
        self.closed.set()
