"""Secure, same-origin browser pairing; no credential-bearing browser APIs."""
from __future__ import annotations
import json
import hashlib
import socket
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT = 8444


def lan_addresses():
    """Advertise the LAN route, rather than Docker's internal bridge addresses."""
    import ipaddress
    try:
        routes = json.loads(subprocess.check_output(
            ['ip', '-j', 'route', 'get', '1.1.1.1'], text=True,
            stderr=subprocess.DEVNULL, timeout=3))
        addresses = [route.get('prefsrc', route.get('src', '')) for route in routes]
        return [str(ipaddress.ip_address(value)) for value in addresses
                if value and ipaddress.ip_address(value).is_private
                and not ipaddress.ip_address(value).is_loopback]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def certificates(root):
    root = Path(root) / 'tls'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    cert, key = root / 'controller.crt', root / 'controller.key'
    if not cert.exists() or not key.exists():
        host = socket.gethostname().split('.')[0]
        # The certificate remains stable across upgrades. Its fingerprint is printed by installation.
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', str(key), '-out', str(cert), '-subj', '/CN=Controller Router', '-days', '3650',
            '-addext', ','.join([f'subjectAltName=DNS:{host}.local', f'DNS:{host}'] +
                              ['IP:' + address for address in lan_addresses()])], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    return cert, key


def public_certificate(root):
    """Return only the public certificate and its verification fingerprint."""
    cert = Path(root) / 'tls/controller.crt'
    pem = cert.read_text()
    return {'certificate': pem,
            'fingerprint': hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()}


def serve(manager, root, host='0.0.0.0', port=PORT):
    try:
        from ..shared.pairing import BoundedServer
    except ImportError:
        from shared.pairing import BoundedServer
    cert, key = certificates(root)
    manager.certificate_identity = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()[:7].upper()
    page = Path(__file__).with_name('pairing.html').read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload, kind='application/json'):
            body = json.dumps(payload).encode() if kind == 'application/json' else payload
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/', '/setup', '/setup.html'):
                self.reply(200, page, 'text/html; charset=utf-8')
            elif path == '/certificate.pem':
                self.reply(200, cert.read_bytes(), 'application/x-pem-file')
            elif path == '/api/connections':
                self.reply(200, manager.inspect())
            else: self.reply(404, {'error':'Page not found.'})

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                # Consume bounded requests before rejecting headers so TLS can
                # deliver the error response without a reset from unread data.
                raw = self.rfile.read(size) if 0 < size <= 4097 else b''
                host_header = self.headers.get('Host', '')
                address = urlsplit('https://' + host_header)
                if address.port != PORT or not address.hostname or address.username or address.path:
                    raise ValueError('Open the secure Controller Router Setup page.')
                if (self.headers.get('Origin') != 'https://' + host_header or
                        self.headers.get('Sec-Fetch-Site', '') == 'cross-site' or
                        self.headers.get('X-Controller-Router-Action') != 'pairing' or
                        self.headers.get('Content-Type') != 'application/json'):
                    raise ValueError('Open Pair console from secure Controller Router Setup.')
                if self.path != '/api/pairing' or not 1 <= size <= 4096:
                    raise ValueError('Invalid pairing request.')
                payload = json.loads(raw)
                if not isinstance(payload, dict): raise ValueError('Invalid pairing request.')
                self.reply(200, manager.operation(payload, address.hostname))
            except (ValueError, TypeError, KeyError) as exc:
                # Validation messages contain no credentials or submitted request values.
                self.reply(400, {'error': str(exc) if isinstance(exc, ValueError) else 'Invalid pairing request.'})
            except (OSError, subprocess.SubprocessError):
                self.reply(503, {'error':'The console or controller service is unavailable. Try again when it is ready.'})

        def log_message(self, *_): pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server = BoundedServer((host, port), Handler)
    server.daemon_threads = True
    finish = server.finish_request
    def secured(sock, address):
        sock.settimeout(10)
        try:
            with context.wrap_socket(sock, server_side=True) as connection:
                finish(connection, address)
        except (OSError, ssl.SSLError): sock.close()
    server.finish_request = secured
    server.serve_forever()
