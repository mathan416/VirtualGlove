"""Shared device-pairing primitives. No product credentials enter public responses."""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

PORT = 55359  # 55358 remains VirtualGlove's existing game registry / Router API.
APPS = frozenset({'virtualglove', 'rob_vision'})
MAX_BODY = 32768


class BoundedServer(ThreadingHTTPServer):
    """Limit concurrent TLS handshakes and HTTP work on a small controller."""
    daemon_threads = True
    def __init__(self, *args, **kwargs):
        self.capacity = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)
    def process_request(self, request, address):
        if not self.capacity.acquire(blocking=False):
            self.close_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.capacity.release()
            raise
    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.capacity.release()


def secret() -> str:
    return secrets.token_urlsafe(48)


def valid_secret(value):
    if not isinstance(value, str) or not 32 <= len(value) <= 256 or any(c.isspace() for c in value):
        raise ValueError('Invalid connection credential.')
    return value


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise ValueError('Invalid device identity.')
    return value


def write_private(path: Path, content: bytes):
    """Replace atomically, preserving an existing file's owner and permissions."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    previous = path.stat() if path.exists() else None
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            if hasattr(os, 'fchmod'):
                os.fchmod(out.fileno(), previous.st_mode & 0o777 if previous else 0o600)
            if hasattr(os, 'geteuid') and os.geteuid() == 0:
                owner = previous or path.parent.stat()
                os.fchown(out.fileno(), owner.st_uid, owner.st_gid)
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        if os.name == 'nt':
            import subprocess
            identity = subprocess.check_output(['whoami'], text=True).strip()
            subprocess.run(['icacls', name, '/inheritance:r', '/grant:r', identity + ':F', 'SYSTEM:F'],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value):
    write_private(path, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())


def load_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {} if default is None else default


def fingerprint(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def certificate_code(der: bytes) -> str:
    return base64.b32encode(hashlib.sha256(der).digest()).decode()[:20]


def connection_code(der: bytes, authorization: str) -> str:
    return 'CR1-' + certificate_code(der) + '-' + authorization


def parse_code(code: str):
    if not isinstance(code, str):
        raise ValueError('Paste the connection code printed by the console.')
    match = re.fullmatch(r'CR1-([A-Z2-7]{20})-([A-Z2-7]{12})', code.strip().upper())
    if not match:
        raise ValueError('Paste the complete CR1 connection code printed by the console.')
    return match.groups()


def normalize_host(value):
    if not isinstance(value, str) or len(value) > 253:
        raise ValueError('Enter the console hostname or LAN IP address.')
    value = value.strip().lower().rstrip('.')
    if not value or not re.fullmatch(r'[a-z0-9][a-z0-9.:-]*', value) or value == 'localhost':
        raise ValueError('Enter the console hostname or LAN IP address, without a URL or port.')
    return value


def lan_address(host: str):
    """Resolve on the host, including mDNS; reject public and loopback targets."""
    for family, _, _, _, address in socket.getaddrinfo(normalize_host(host), PORT, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(address[0])
        if ip.is_private and not (ip.is_loopback or ip.is_multicast or ip.is_unspecified or ip.is_link_local):
            return str(ip)
    raise ValueError('The console name does not resolve to a LAN address.')


class Peer:
    """Pinned TLS: inspect the certificate before sending a credential or code."""
    def __init__(self, host, pin=None, code_pin=None, port=PORT, resolve=lan_address):
        self.host = normalize_host(host)
        self.address = resolve(self.host)
        self.port = port
        self.pin = pin
        self.code_pin = code_pin
        self.last_fingerprint = None

    def request(self, path, payload=None, token=None):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # Explicit certificate pinning below.
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        connection = http.client.HTTPSConnection(self.address, self.port, context=context, timeout=10)
        try:
            connection.connect()
            der = connection.sock.getpeercert(binary_form=True)
            actual = fingerprint(der)
            if self.pin and not hmac.compare_digest(self.pin, actual):
                raise ValueError('Console certificate changed. Repair the connection before continuing.')
            if self.code_pin and not hmac.compare_digest(self.code_pin, certificate_code(der)):
                raise ValueError('Connection code does not match this console. No credentials were sent.')
            if token and not (self.pin or self.code_pin):
                raise ValueError('A verified console certificate is required.')
            self.last_fingerprint = actual
            body = None if payload is None else json.dumps(payload).encode()
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = 'Bearer ' + valid_secret(token)
            connection.request('GET' if body is None else 'POST', path, body, headers)
            response = connection.getresponse()
            raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ValueError('Console response is too large.')
            result = json.loads(raw)
            if not isinstance(result, dict) or response.status != 200 or result.get('error'):
                raise ValueError(result.get('error', 'Console request failed.') if isinstance(result, dict) else 'Invalid console response.')
            return result
        finally:
            connection.close()


def legacy_proof(token, nonce, console_id, cert_fingerprint):
    """Authenticate a migrated peer without sending its existing secret."""
    message = '\n'.join([nonce, console_id, cert_fingerprint]).encode()
    return hmac.new(token.encode(), message, hashlib.sha256).hexdigest()
