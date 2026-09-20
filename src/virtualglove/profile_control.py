# Project: VirtualGlove
# File: src/virtualglove/profile_control.py
# Purpose: Authenticate profile commands and coordinate per-game profile selection between RetroPie and UNO Q.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Add authenticated Controller discovery for stale RetroPie destinations.
#   2026-09-06 - Address Setup review reliability and private configuration findings.
#   2026-09-05 - Added renewable active-game leases for safe restart recovery.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-04 - Repaired persistent profile transport and asynchronous queue acknowledgements.

"""Authenticate profile commands and coordinate per-game profile selection between RetroPie and UNO Q."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import queue
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gesture import SUPPORTED_PROFILES


PROTOCOL = "virtualglove-profile/1"
MAX_PACKET_BYTES = 4096
DISCOVERY_ADDRESS = "255.255.255.255"
DISCOVERY_CACHE_SECONDS = 30.0
_destination_cache: dict[tuple[str, int, bytes], tuple[str, float]] = {}
_destination_cache_lock = threading.Lock()


def _canonical(data: dict[str, Any]) -> bytes:
    """Serialize a message without its signature for stable HMAC calculation."""
    unsigned = {key: value for key, value in data.items() if key != "signature"}
    return json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode()


def sign_message(data: dict[str, Any], token: str) -> dict[str, Any]:
    """Return a copy of a profile message carrying its SHA-256 HMAC."""
    result = dict(data)
    result["signature"] = hmac.new(token.encode(), _canonical(result), hashlib.sha256).hexdigest()
    return result


def verify_message(data: dict[str, Any], token: str) -> bool:
    """Verify a profile message signature using constant-time comparison."""
    supplied = data.get("signature")
    if not isinstance(supplied, str):
        return False
    expected = hmac.new(token.encode(), _canonical(data), hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def read_token(token: str | None, token_file: Path | None) -> str:
    """Load and validate a token supplied directly or through a protected file."""
    value = token if token is not None else token_file.read_text().strip() if token_file else ""
    if len(value) < 16:
        raise ValueError("profile token must contain at least 16 characters")
    return value


@dataclass(frozen=True)
class ProfileRequest:
    """Represent one validated profile request and its reply address."""
    request_id: str
    profile: str | None
    system: str
    rom: str
    peer: tuple[str, int]
    emulator: str = ""
    session_id: str | None = None
    lease_seconds: float = 0.0
    rapid_a: bool | None = None
    rapid_b: bool | None = None


@dataclass
class ActiveGameLease:
    """Track one renewable registered-game session without replaying transitions."""
    session_id: str | None = None
    profile: str | None = None
    system: str = ""
    rom: str = ""
    emulator: str = ""
    rapid_a: bool | None = None
    rapid_b: bool | None = None
    expires_at: float = 0.0

    def refresh(self, request: ProfileRequest, now: float) -> bool:
        """Refresh a validated session and report whether it is a new game transition."""
        if not request.session_id or request.profile is None or request.lease_seconds <= 0:
            self.clear()
            return True
        same = (
            self.session_id == request.session_id
            and self.profile == request.profile
            and self.system == request.system
            and self.rom == request.rom
            and self.emulator == request.emulator
            and self.rapid_a == request.rapid_a
            and self.rapid_b == request.rapid_b
        )
        self.session_id = request.session_id
        self.profile = request.profile
        self.system = request.system
        self.rom = request.rom
        self.emulator = request.emulator
        self.rapid_a = request.rapid_a
        self.rapid_b = request.rapid_b
        self.expires_at = now + request.lease_seconds
        return not same

    def expire(self, now: float) -> bool:
        """Clear and report a lease whose RetroPie heartbeat has stopped."""
        if self.session_id is None or now < self.expires_at:
            return False
        self.clear()
        return True

    def clear(self) -> None:
        """Forget the current game session and its expiry deadline."""
        self.session_id = None
        self.profile = None
        self.system = ""
        self.rom = ""
        self.emulator = ""
        self.rapid_a = None
        self.rapid_b = None
        self.expires_at = 0.0

    def snapshot(self, now: float) -> dict[str, Any]:
        """Return browser-safe lease state without exposing its session identifier."""
        return {
            "game_session_active": self.session_id is not None,
            "game_session_remaining_ms": max(0, round((self.expires_at - now) * 1000)),
        }


class ProfileCommandServer:
    """Authenticated Pi-to-UNO-Q profile requests with explicit acknowledgements."""

    def __init__(self, host: str, port: int, token: str) -> None:
        self.token = token
        self.requests: queue.SimpleQueue[ProfileRequest] = queue.SimpleQueue()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.bind((host, port))
        except Exception:
            self.socket.close()
            raise
        self.socket.settimeout(0.25)
        self._closed = threading.Event()
        self._seen: set[str] = set()
        self._acks: dict[str, bytes] = {}
        self._thread = threading.Thread(target=self._run, name="profile-control", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Receive, authenticate, deduplicate, and queue profile requests."""
        while not self._closed.is_set():
            try:
                payload, peer = self.socket.recvfrom(MAX_PACKET_BYTES + 1)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                if len(payload) > MAX_PACKET_BYTES:
                    raise ValueError("packet too large")
                data = json.loads(payload)
                if data.get("protocol") != PROTOCOL or not verify_message(data, self.token):
                    raise ValueError("invalid request")
                request_id = str(data["request_id"])
                if data.get("kind") == "discover":
                    if (len(request_id) != 32 or
                            any(character not in "0123456789abcdef" for character in request_id)):
                        raise ValueError("invalid discovery request identifier")
                    if set(data) != {"protocol", "kind", "request_id", "signature"}:
                        raise ValueError("invalid discovery request")
                    reply = sign_message({
                        "protocol": PROTOCOL,
                        "kind": "discover_ack",
                        "request_id": request_id,
                    }, self.token)
                    try:
                        self.socket.sendto(
                            json.dumps(reply, separators=(",", ":")).encode(), peer
                        )
                    except OSError:
                        pass
                    continue
                if data.get("kind") != "set_profile":
                    raise ValueError("invalid request kind")
                if (not request_id.isascii() or not 1 <= len(request_id) <= 128):
                    raise ValueError("invalid request identifier")
                if request_id in self._seen:
                    ack = self._acks.get(request_id)
                    if ack is not None:
                        try:
                            self.socket.sendto(ack, peer)
                        except OSError:
                            pass
                    continue
                profile = data.get("profile")
                if profile is not None and profile not in SUPPORTED_PROFILES:
                    raise ValueError("unknown profile")
                emulator = data.get("emulator", "")
                if (not isinstance(emulator, str) or len(emulator) > 64
                        or not emulator.isascii()
                        or any(not (character.isalnum() or character in "-_.")
                               for character in emulator)):
                    raise ValueError("invalid emulator")
                session_id = data.get("session_id")
                lease_seconds = data.get("lease_seconds", 0.0)
                if session_id is not None:
                    if (not isinstance(session_id, str) or not 16 <= len(session_id) <= 64
                            or not session_id.isascii() or not session_id.isalnum()):
                        raise ValueError("invalid game session")
                    if (type(lease_seconds) not in (int, float)
                            or not 2.0 <= float(lease_seconds) <= 15.0
                            or profile is None):
                        raise ValueError("invalid game lease")
                elif lease_seconds not in (0, 0.0, None):
                    raise ValueError("lease requires a game session")
                rapid_a = data.get("rapid_a")
                rapid_b = data.get("rapid_b")
                if rapid_a is not None and type(rapid_a) is not bool:
                    raise ValueError("invalid rapid A setting")
                if rapid_b is not None and type(rapid_b) is not bool:
                    raise ValueError("invalid rapid B setting")
                self._seen.add(request_id)
                if len(self._seen) > 256:
                    self._seen.clear()
                    self._acks.clear()
                request = ProfileRequest(
                    request_id=request_id,
                    profile=profile,
                    system=str(data.get("system", ""))[:64],
                    rom=Path(str(data.get("rom", ""))).name[:255],
                    peer=peer,
                    emulator=emulator,
                    session_id=session_id,
                    lease_seconds=float(lease_seconds or 0.0),
                    rapid_a=rapid_a,
                    rapid_b=rapid_b,
                )
                self.requests.put(request)
                # Camera/model startup may block the consumer; acknowledge queue admission.
                self.acknowledge(request, True, profile, queued=True)
            except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError, RecursionError):
                continue

    def take(self) -> ProfileRequest | None:
        """Return the next queued request without blocking the vision loop."""
        try:
            return self.requests.get_nowait()
        except queue.Empty:
            return None

    def acknowledge(self, request: ProfileRequest, accepted: bool, profile: str | None, queued: bool = False) -> None:
        """Sign, cache, and send an explicit response to a profile request."""
        data = sign_message({
            "protocol": PROTOCOL,
            "kind": "ack",
            "request_id": request.request_id,
            "accepted": accepted,
            "profile": profile,
            "queued": queued,
        }, self.token)
        payload = json.dumps(data, separators=(",", ":")).encode()
        self._acks[request.request_id] = payload
        try:
            self.socket.sendto(payload, request.peer)
        except OSError:
            # Keep the listener alive; retries can retrieve the cached acknowledgement.
            pass

    def close(self) -> None:
        """Stop the receiver thread and close its socket."""
        self._closed.set()
        self.socket.close()
        self._thread.join(timeout=1)


def _registry_entry(value: Any) -> dict[str, Any]:
    """Normalize one legacy or structured game mapping."""
    if isinstance(value, str):
        entry = {"profile": value}
    elif isinstance(value, dict) and set(value) <= {"profile", "rapid_a", "rapid_b", "four_score"}:
        entry = dict(value)
    else:
        raise ValueError("game mapping must be a profile or settings object")
    profile = entry.get("profile")
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"unknown profile {profile!r}")
    for name in ("rapid_a", "rapid_b"):
        if name in entry and type(entry[name]) is not bool:
            raise ValueError(f"{name} must be a boolean")
    if "four_score" in entry and entry["four_score"] != "force":
        raise ValueError("four_score must be 'force'")
    return entry


def load_registry(path: Path) -> dict[str, str | dict[str, Any]]:
    """Load and validate case-insensitive ROM-to-profile mappings."""
    data = json.loads(path.read_text())
    games = data.get("games")
    if not isinstance(games, dict):
        raise ValueError("profile registry must contain a games object")
    result: dict[str, str | dict[str, Any]] = {}
    for filename, value in games.items():
        try:
            entry = _registry_entry(value)
        except ValueError as exc:
            raise ValueError(f"{exc} for {filename!r}") from exc
        result[Path(filename).name.casefold()] = value if isinstance(value, str) else entry
    return result


def select_profile_settings(
    registry: dict[str, str | dict[str, Any]], system: str, rom: str
) -> dict[str, Any] | None:
    """Select normalized profile settings for one registered NES/Famicom ROM."""
    if system.casefold() not in {"nes", "famicom"}:
        return None
    value = registry.get(Path(rom).name.casefold())
    return None if value is None else _registry_entry(value)


def local_broadcast_addresses() -> tuple[str, ...]:
    """Return physical IPv4 broadcast targets without shelling out or scanning."""
    try:
        import fcntl
    except ImportError:
        return (DISCOVERY_ADDRESS,)
    targets: list[str] = []
    sysfs = Path("/sys/class/net")
    try:
        interfaces = socket.if_nameindex()
    except OSError:
        return (DISCOVERY_ADDRESS,)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        for _index, name in interfaces:
            if name == "lo" or name.startswith(("docker", "veth", "br-")):
                continue
            device = sysfs / name / "device"
            if sysfs.exists() and not device.exists():
                continue
            carrier = sysfs / name / "carrier"
            try:
                if carrier.exists() and carrier.read_text().strip() != "1":
                    continue
                request = struct.pack("256s", name[:15].encode())
                address = socket.inet_ntoa(
                    fcntl.ioctl(probe.fileno(), 0x8915, request)[20:24]
                )
                netmask = socket.inet_ntoa(
                    fcntl.ioctl(probe.fileno(), 0x891B, request)[20:24]
                )
                interface = ipaddress.IPv4Interface(address + "/" + netmask)
                if (interface.ip.is_loopback or interface.ip.is_link_local or
                        interface.network.prefixlen >= 31):
                    continue
                target = str(interface.network.broadcast_address)
                if target not in targets:
                    targets.append(target)
            except (OSError, ValueError):
                continue
    return tuple(targets) or (DISCOVERY_ADDRESS,)


def _cache_key(host: str, port: int, token: str) -> tuple[str, int, bytes]:
    """Build a destination-cache key without retaining the pairing token."""
    return host, port, hashlib.sha256(token.encode()).digest()


def _cached_destination(key: tuple[str, int, bytes], now: float) -> str | None:
    """Return one unexpired authenticated destination from the process cache."""
    with _destination_cache_lock:
        item = _destination_cache.get(key)
        if item is None:
            return None
        address, expires_at = item
        if now >= expires_at:
            _destination_cache.pop(key, None)
            return None
        return address


def _remember_destination(
    key: tuple[str, int, bytes], address: str, now: float
) -> None:
    """Cache one validated IPv4 destination within the bounded expiry table."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return
    if not isinstance(parsed, ipaddress.IPv4Address) or parsed.is_unspecified:
        return
    with _destination_cache_lock:
        expired = [item_key for item_key, item in _destination_cache.items()
                   if now >= item[1]]
        for item_key in expired:
            _destination_cache.pop(item_key, None)
        if key not in _destination_cache and len(_destination_cache) >= 16:
            oldest = min(_destination_cache, key=lambda item_key: _destination_cache[item_key][1])
            _destination_cache.pop(oldest, None)
        _destination_cache[key] = (address, now + DISCOVERY_CACHE_SECONDS)


def _receive_reply(
    sock: socket.socket, token: str, request_id: str, kind: str
) -> tuple[dict[str, Any], tuple[str, int]] | None:
    """Accept only a signed, request-matched reply and return its UDP peer."""
    timeout = sock.gettimeout()
    deadline = time.monotonic() + (float(timeout) if timeout is not None else 0.0)
    while True:
        try:
            if timeout is not None:
                sock.settimeout(max(0.001, deadline - time.monotonic()))
            response, peer = sock.recvfrom(MAX_PACKET_BYTES + 1)
            if len(response) > MAX_PACKET_BYTES:
                continue
            ack = json.loads(response)
            if (not isinstance(ack, dict) or ack.get("protocol") != PROTOCOL or
                    ack.get("kind") != kind or ack.get("request_id") != request_id or
                    not verify_message(ack, token)):
                continue
            sock.settimeout(timeout)
            return ack, peer
        except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
            continue
        except OSError:
            try:
                sock.settimeout(timeout)
            except OSError:
                pass
            return None


def _exchange(
    sock: socket.socket, payload: bytes, destination: tuple[str, int], token: str,
    request_id: str, kind: str, attempts: int
) -> tuple[dict[str, Any], tuple[str, int]] | None:
    """Send a bounded request and accept only its authenticated matching reply."""
    for _attempt in range(attempts):
        try:
            sock.sendto(payload, destination)
        except OSError:
            return None
        reply = _receive_reply(sock, token, request_id, kind)
        if reply is not None:
            return reply
    return None


def send_request(host: str, port: int, token: str, profile: str | None,
                 system: str, rom: str, timeout: float, *,
                 session_id: str | None = None, lease_seconds: float = 0.0,
                 emulator: str = "", rapid_a: bool | None = None,
                 rapid_b: bool | None = None,
                 discovery_addresses=None) -> dict[str, Any]:
    """Send a signed profile request, discovering the paired Controller if needed."""
    request_id = uuid.uuid4().hex
    message = {
        "protocol": PROTOCOL,
        "kind": "set_profile",
        "request_id": request_id,
        "profile": profile,
        "system": system,
        "rom": Path(rom).name,
        "emulator": emulator,
    }
    if session_id is not None:
        message["session_id"] = session_id
        message["lease_seconds"] = lease_seconds
    if rapid_a is not None:
        message["rapid_a"] = rapid_a
    if rapid_b is not None:
        message["rapid_b"] = rapid_b
    message = sign_message(message, token)
    payload = json.dumps(message, separators=(",", ":")).encode()
    key = _cache_key(host, port, token)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        cached = _cached_destination(key, time.monotonic())
        if cached is not None:
            result = _exchange(
                sock, payload, (cached, port), token, request_id, "ack", 1
            )
            if result is not None:
                ack, peer = result
                _remember_destination(key, peer[0], time.monotonic())
                return ack
        result = _exchange(sock, payload, (host, port), token, request_id, "ack", 3)
        if result is not None:
            ack, peer = result
            _remember_destination(key, peer[0], time.monotonic())
            return ack

        discover_id = uuid.uuid4().hex
        discover = sign_message({
            "protocol": PROTOCOL,
            "kind": "discover",
            "request_id": discover_id,
        }, token)
        discover_payload = json.dumps(discover, separators=(",", ":")).encode()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        targets = (
            tuple(discovery_addresses()) if discovery_addresses is not None
            else local_broadcast_addresses()
        )
        for target in targets[:8]:
            try:
                sock.sendto(discover_payload, (target, port))
            except OSError:
                continue
        discovered = _receive_reply(sock, token, discover_id, "discover_ack")
        if discovered is not None:
            _discovery_ack, peer = discovered
            _remember_destination(key, peer[0], time.monotonic())
            result = _exchange(
                sock, payload, (peer[0], port), token, request_id, "ack", 3
            )
            if result is not None:
                ack, response_peer = result
                _remember_destination(key, response_peer[0], time.monotonic())
                return ack
    raise TimeoutError("UNO Q did not acknowledge the profile change")


def build_parser() -> argparse.ArgumentParser:
    """Create the profile-control command-line parser."""
    parser = argparse.ArgumentParser(description="Select the UNO Q gesture profile for a launched ROM")
    parser.add_argument("--uno-q", required=True, help="UNO Q hostname or address")
    parser.add_argument("--port", type=int, default=55356)
    tokens = parser.add_mutually_exclusive_group(required=True)
    tokens.add_argument("--token")
    tokens.add_argument("--token-file", type=Path)
    parser.add_argument("--registry", type=Path, default=Path("/etc/virtualglove/games.json"))
    parser.add_argument("--system", default="nes")
    parser.add_argument("--rom", default="Manual selection")
    parser.add_argument("--profile", choices=(*SUPPORTED_PROFILES, "off"),
                        help="manual override; otherwise select from the ROM registry")
    parser.add_argument("--timeout", type=float, default=0.4)
    return parser


def main() -> int:
    """Resolve a profile, request the change, and return a meaningful exit status."""
    args = build_parser().parse_args()
    token = read_token(args.token, args.token_file)
    settings = None if args.profile else select_profile_settings(
        load_registry(args.registry), args.system, args.rom
    )
    profile = ((None if args.profile == "off" else args.profile)
               if args.profile else settings["profile"] if settings else None)
    try:
        ack = send_request(
            args.uno_q, args.port, token, profile, args.system, args.rom, args.timeout,
            rapid_a=settings.get("rapid_a") if settings else None,
            rapid_b=settings.get("rapid_b") if settings else None,
        )
    except TimeoutError as exc:
        print(str(exc))
        return 2
    label = profile or "off"
    print(f"VirtualGlove profile: {label} ({'accepted' if ack.get('accepted') else 'rejected'})")
    return 0 if ack.get("accepted") else 3


if __name__ == "__main__":
    raise SystemExit(main())
