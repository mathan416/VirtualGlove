"""Console-side shared link service; product-specific files are registered at install."""
from __future__ import annotations

import argparse
import base64
import json
import hashlib
import hmac
import os
import secrets
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .pairing import (APPS, MAX_BODY, PORT, BoundedServer, connection_code, fingerprint, legacy_proof,
                      load_json, secret, valid_id, valid_secret, write_json, write_private)


class AdapterFailure(ValueError):
    """Expose fixed app labels, never underlying errors or credentials."""
    def __init__(self, apps):
        names = {'virtualglove': 'VirtualGlove', 'rob_vision': 'R.O.B. Vision'}
        super().__init__('App setup needs attention: ' + ', '.join(names[app] for app in sorted(apps)))


def remove_file(path):
    """Python 3.7-compatible unlink used by legacy RetroPie installations."""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


def default_root():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ControllerRouter/link'
    if Path('/userdata/system/batocera.conf').exists():
        return Path('/userdata/system/controller-router/link')
    if Path('/recalbox/recalbox.version').exists():
        return Path('/recalbox/share/system/controller-router/link')
    return Path('/var/lib/controller-router/link')


def platform_name():
    if os.name == 'nt':
        return 'launchbox'
    if Path('/userdata/system/batocera.conf').exists():
        return 'batocera'
    if Path('/recalbox/recalbox.version').exists():
        return 'recalbox'
    return 'retropie'


def ensure_certificate(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    cert, key = root / 'certificate.pem', root / 'private-key.pem'
    if not cert.exists() or not key.exists():
        try:
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(key), '-out', str(cert), '-subj', '/CN=Controller-Router-Console',
                            '-days', '3650'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            if os.name != 'nt': raise
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import NameOID
            from datetime import datetime, timedelta, timezone
            private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Controller Router Console')])
            now = datetime.now(timezone.utc)
            leaf = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key())
                    .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
                    .not_valid_after(now + timedelta(days=3650)).sign(private, hashes.SHA256()))
            write_private(key, private.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            write_private(cert, leaf.public_bytes(serialization.Encoding.PEM))
    key.chmod(0o600)
    return cert, key


class LinkStore:
    def __init__(self, root, clock=time.time, restart=None, game_active=None):
        self.root = Path(root)
        self.clock = clock
        self.lock = threading.RLock()
        self.restart = restart or self._restart
        self.game_active = game_active or live_game
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.marker = (Path('/run/controller-router/pairing.pending') if os.name != 'nt' and
                       self.root == default_root() else self.root / 'pairing.pending')
        identity = self.root / 'console-id'
        if not identity.exists():
            write_private(identity, (secrets.token_hex(16) + '\n').encode())
        self.console_id = valid_id(identity.read_text().strip())
        self.adapters = load_json(self.root / 'adapters.json')
        self.connection = load_json(self.root / 'connection.json')
        self.challenges = {}
        # An interrupted transaction must not leave partially activated credentials.
        if (self.root / 'pending.json').exists():
            self._restore(load_json(self.root / 'pending.json'))
            (self.root / 'pending.json').unlink()
        else:
            remove_file(self.marker)

    def public(self):
        self.adapters = load_json(self.root / 'adapters.json')
        legacy_apps = []
        if not self.connection:
            for app, descriptor in self.adapters.items():
                try:
                    if len(Path(descriptor['token_file']).read_text().strip()) >= 16:
                        legacy_apps.append(app)
                except OSError:
                    continue
        return {'schema': 1, 'console_id': self.console_id, 'platform': platform_name(),
                'apps': sorted(self.adapters), 'paired': bool(self.connection),
                'legacy_paired_apps': sorted(legacy_apps),
                'uno_id': self.connection.get('uno_id'), 'game_active': self.game_active()}

    def expire(self):
        with self.lock:
            pending = load_json(self.root / 'pending.json')
            if pending and self.clock() >= pending.get('expires', 0):
                self._restore(pending)
                (self.root / 'pending.json').unlink()

    def register(self, app, descriptor):
        if app not in APPS or descriptor.get('kind') not in ('json', 'env', 'text'):
            raise ValueError('Unsupported controller adapter.')
        for key in ('token_file', 'target_file'):
            if not Path(descriptor[key]).is_absolute():
                raise ValueError('Adapter paths must be absolute.')
        with self.lock:
            self.expire()
            self.public()
            self.adapters[app] = descriptor
            write_json(self.root / 'adapters.json', self.adapters)

    def authorize(self, token, transaction=None):
        expected = self.connection.get('token', '')
        if transaction:
            pending = load_json(self.root / 'pending.json')
            if pending.get('transaction') == transaction:
                expected = pending.get('connection', {}).get('token', '')
        if not expected or not secrets.compare_digest(expected, token or ''):
            raise ValueError('Connection authorization was rejected.')

    def prepare(self, payload, token=None, authorization=None):
        with self.lock:
            self.expire()
            self.public()
            if self.game_active():
                raise ValueError('Exit the game before changing a console connection.')
            if (self.root / 'pending.json').exists():
                raise ValueError('Another connection change is pending.')
            if authorization is not None:
                window = load_json(self.root / 'window.json')
                if self.clock() >= window.get('expires', 0) or window.get('attempts', 0) >= 5 or window.get('used'):
                    raise ValueError('Connection code expired. Open a new pairing window on the console.')
                if not secrets.compare_digest(window.get('authorization', ''), authorization):
                    window['attempts'] = window.get('attempts', 0) + 1
                    write_json(self.root / 'window.json', window)
                    raise ValueError('Connection code was rejected.')
            else:
                self.authorize(token)
            uno_id = valid_id(payload.get('uno_id'))
            url = payload.get('uno_url')
            parsed = urlsplit(url) if isinstance(url, str) else None
            if not parsed or parsed.scheme != 'http' or not parsed.hostname or parsed.path or parsed.username or parsed.port:
                raise ValueError('Invalid UNO Q address.')
            credentials = payload.get('credentials', {})
            if not isinstance(credentials, dict) or not set(credentials) <= self.adapters.keys():
                raise ValueError('Install the requested controller software on this console first.')
            for app, credential in credentials.items():
                valid_secret(credential.get('token'))
                valid_id(credential.get('console_id'))
            new_connection = {'schema': 1, 'uno_id': uno_id, 'uno_url': url,
                              'token': valid_secret(payload.get('token')), 'apps': credentials}
            files = {}
            affected = set(self.adapters)
            for app in affected:
                descriptor = self.adapters[app]
                for name in ('token_file', 'target_file', 'identity_file'):
                    if descriptor.get(name):
                        path = Path(descriptor[name])
                        files[str(path)] = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
                for name in descriptor.get('backup_files', []):
                    path = Path(name)
                    files[str(path)] = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
            pending = {'transaction': secrets.token_hex(16), 'expires': self.clock() + 120,
                       'connection': new_connection, 'previous': self.connection, 'files': files,
                       'affected': sorted(affected)}
            write_json(self.root / ('before-connection-' + pending['transaction'] + '.json'), pending)
            write_json(self.root / 'pending.json', pending)
            write_private(self.marker, b'Connection change in progress\n')
            if self.marker.parent != self.root:
                self.marker.parent.chmod(0o755)
            if authorization is not None:
                window['used'] = True
                write_json(self.root / 'window.json', window)
            return {'transaction': pending['transaction'], **self.public()}

    def _apply(self, app, credential, url):
        descriptor = self.adapters[app]
        token_file = Path(descriptor['token_file'])
        write_private(token_file, (credential['token'] + '\n').encode())
        target = Path(descriptor['target_file'])
        if descriptor['kind'] == 'json':
            document = load_json(target)
            document[descriptor.get('target_key', 'uno_q')] = urlsplit(url).hostname
            write_json(target, document)
        elif descriptor['kind'] == 'env':
            import re
            source = target.read_text()
            source, count = re.subn(r'(?m)^ROB_VISION_URL=.*$', 'ROB_VISION_URL=' + url + ':8766', source)
            if count != 1:
                raise ValueError('Receiver configuration is missing its UNO Q address.')
            write_private(target, source.encode())
        else:
            write_private(target, (url + ':8766\n').encode())
        if descriptor.get('identity_file'):
            write_private(Path(descriptor['identity_file']), (credential['console_id'] + '\n').encode())

    def commit(self, transaction, token):
        with self.lock:
            self.authorize(token, transaction)
            pending = load_json(self.root / 'pending.json')
            if pending.get('transaction') != transaction or self.clock() >= pending.get('expires', 0):
                raise ValueError('Connection change expired. Try again.')
            if self.game_active():
                raise ValueError('Exit the game before activating the connection.')
            failed_app = None
            try:
                affected = set(pending.get('affected', pending['connection']['apps']))
                changed = {app for app in affected if
                    pending['connection']['apps'].get(app) != pending['previous'].get('apps', {}).get(app) or
                    (app in pending['connection']['apps'] and pending['connection']['uno_url'] != pending['previous'].get('uno_url'))}
                for app in affected - set(pending['connection']['apps']):
                    if Path(self.adapters[app]['token_file']).exists() and Path(self.adapters[app]['token_file']).read_text().strip():
                        changed.add(app)
                pending['changed'] = sorted(changed)
                write_json(self.root / 'pending.json', pending)
                for app in changed:
                    failed_app = app
                    if app in pending['connection']['apps']:
                        self._apply(app, pending['connection']['apps'][app], pending['connection']['uno_url'])
                    else:
                        write_private(Path(self.adapters[app]['token_file']), b'')
                for app in changed:
                    failed_app = app
                    self.restart(app, self.adapters[app])
                self.connection = pending['connection']
                write_json(self.root / 'connection.json', self.connection)
                pending['committed'] = True
                write_json(self.root / 'pending.json', pending)
                return {'connected': True, **self.public()}
            except Exception:
                self._restore(pending)
                if failed_app:
                    raise AdapterFailure([failed_app]) from None
                raise ValueError('Connection could not be saved; the previous connection was restored.') from None

    def finalize(self, transaction, token):
        with self.lock:
            self.authorize(token, transaction)
            pending = load_json(self.root / 'pending.json')
            if pending.get('transaction') != transaction or not pending.get('committed'):
                raise ValueError('Connection change has not completed.')
            (self.root / 'pending.json').unlink()
            remove_file(self.marker)
            return {'connected': True}

    def abort(self, transaction, token):
        with self.lock:
            self.authorize(token, transaction)
            pending = load_json(self.root / 'pending.json')
            if pending.get('transaction') == transaction:
                self._restore(pending)
                (self.root / 'pending.json').unlink()
            return {'restored': True}

    def _restore(self, pending):
        for name, content in pending.get('files', {}).items():
            path = Path(name)
            if content is None:
                remove_file(path)
            else:
                write_private(path, base64.b64decode(content))
        self.connection = pending.get('previous', {})
        write_json(self.root / 'connection.json', self.connection)
        failures = []
        for app in pending.get('changed', pending.get('affected', set(pending.get('connection', {}).get('apps', {})) |
                               set(pending.get('previous', {}).get('apps', {})))):
            try:
                self.restart(app, self.adapters[app])
            except (OSError, ValueError, subprocess.SubprocessError):
                failures.append(app)
        if failures:
            raise AdapterFailure(failures)
        remove_file(self.marker)

    def revoke(self, app, token):
        with self.lock:
            self.authorize(token)
            if self.game_active():
                raise ValueError('Exit the game before removing a connection.')
            credentials = dict(self.connection.get('apps', {}))
            if app is None:
                credentials.clear()
            elif app in credentials:
                credentials.pop(app)
            else:
                raise ValueError('Unknown controller app.')
            transaction = self.prepare({**self.connection, 'credentials': credentials}, token=token)['transaction']
            self.commit(transaction, token)
            self.finalize(transaction, token)
            if app is None:
                self.connection = {}
                write_json(self.root / 'connection.json', {})
            return {'removed': True}

    def proof(self, app, nonce, cert_fingerprint):
        if app not in self.adapters or not isinstance(nonce, str) or not 16 <= len(nonce) <= 128:
            raise ValueError('Invalid migration request.')
        token = Path(self.adapters[app]['token_file']).read_text().strip()
        if len(token) < 16:
            raise ValueError('This app has no existing pairing.')
        with self.lock:
            self.challenges = {key: value for key, value in self.challenges.items() if value['expires'] > self.clock()}
            if len(self.challenges) >= 32:
                raise ValueError('Migration request limit reached.')
            self.challenges[nonce] = {'app': app, 'expires': self.clock() + 60, 'fingerprint': cert_fingerprint}
        return {**self.public(), 'proof': legacy_proof(token, nonce, self.console_id, cert_fingerprint)}

    def adopt(self, payload):
        """Every legacy app must authorize the same fresh migration transcript."""
        with self.lock:
            if self.connection:
                raise ValueError('Migration needs review or a new proof.')
            document = payload.get('connection', {})
            transcript = json.dumps(document, sort_keys=True, separators=(',', ':'))
            claims = payload.get('proofs', [{'nonce': payload.get('nonce'), 'proof': payload.get('proof')}])
            if not isinstance(claims, list) or not 1 <= len(claims) <= len(APPS):
                raise ValueError('Migration proof rejected.')
            proved = set()
            for claim in claims:
                if not isinstance(claim, dict):
                    raise ValueError('Migration proof rejected.')
                nonce = claim.get('nonce')
                challenge = self.challenges.pop(nonce, None)
                if not challenge or challenge['expires'] <= self.clock() or challenge['app'] in proved:
                    raise ValueError('Migration needs review or a new proof.')
                token = Path(self.adapters[challenge['app']]['token_file']).read_text().strip()
                expected = legacy_proof(token, nonce + '\n' + transcript, self.console_id, challenge['fingerprint'])
                if not hmac.compare_digest(expected, str(claim.get('proof', ''))):
                    raise ValueError('Migration proof rejected.')
                proved.add(challenge['app'])
            if proved != set(self.public()['legacy_paired_apps']):
                raise ValueError('Every existing app connection must authorize migration.')
            # Reuse the complete transaction validation without opening a public pairing window.
            previous = self.connection
            self.connection = {'token': document.get('token')}
            try:
                result = self.prepare(document, token=document.get('token'))
                pending = load_json(self.root / 'pending.json')
                pending['previous'] = previous
                write_json(self.root / 'pending.json', pending)
                write_json(self.root / ('before-connection-' + pending['transaction'] + '.json'), pending)
                return result
            finally:
                self.connection = previous

    @staticmethod
    def _restart(app, descriptor):
        enabled = bool(Path(descriptor['token_file']).read_text().strip())
        command = descriptor.get('restart' if enabled else 'stop', [])
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ValueError('The controller restart adapter is unavailable.')
        subprocess.run(command, check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if enabled and descriptor.get('setup'):
            subprocess.run(descriptor['setup'], check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def live_game():
    if os.name == 'nt':
        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq retroarch.exe'],
                                capture_output=True, text=True, timeout=5)
        return 'retroarch.exe' in result.stdout.lower()
    for path in Path('/proc').glob('[0-9]*/comm'):
        try:
            if path.read_text().strip().lower() in ('retroarch', 'retroarch.bin'):
                return True
        except OSError:
            continue
    return False


def serve(root, host='0.0.0.0', port=PORT):
    cert, key = ensure_certificate(Path(root))
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    store = LinkStore(root)
    write_private(Path(root) / 'service.pid', (str(os.getpid()) + '\n').encode())

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, result):
            body = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.reply(200, store.public()) if self.path == '/identity' else self.reply(404, {'error': 'Unknown request.'})

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= MAX_BODY or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('Invalid connection request.')
                self.connection.settimeout(5)
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError('Invalid connection request.')
                authorization = self.headers.get('Authorization', '')
                token = authorization[7:] if authorization.startswith('Bearer ') else ''
                if self.path == '/pair':
                    result = store.prepare(payload, authorization=str(payload.get('authorization', '')))
                elif self.path == '/legacy-proof':
                    result = store.proof(payload.get('app'), payload.get('nonce'), fingerprint(der))
                elif self.path == '/adopt':
                    result = store.adopt(payload)
                elif self.path == '/router':
                    store.authorize(token)
                    from .controller_router import RouterStore, _paths
                    config, inputs, *_ = _paths(platform_name())
                    router = RouterStore(config, platform_name(), inputs)
                    if payload.get('action') == 'save' and 'rob_vision' in store.connection.get('apps', {}):
                        proposed = router._materialize(payload.get('config'))
                        players = [row['player'] for row in proposed['players'] for source in row['sources']
                                   if source['name'] == 'R.O.B. Vision Controller 2']
                        if players != [2]:
                            raise ValueError('Buddy must remain assigned to Player 2.')
                    result = router.operate(payload.get('action'), payload)
                elif self.path == '/manage':
                    operation = payload.get('operation')
                    if operation == 'prepare':
                        result = store.prepare(payload, token=token)
                    elif operation in ('commit', 'finalize', 'abort'):
                        result = getattr(store, operation)(payload.get('transaction'), token)
                    elif operation == 'remove':
                        result = store.revoke(payload.get('app'), token)
                    elif operation == 'status':
                        store.authorize(token)
                        result = store.public()
                    else:
                        raise ValueError('Unknown connection operation.')
                else:
                    raise ValueError('Unknown connection request.')
                self.reply(200, result)
            except AdapterFailure as error:
                self.reply(400, {'error': str(error)})
            except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
                self.reply(400, {'error': 'Connection request failed. Check the code, finish any game, or reopen pairing.'})

        def log_message(self, *_args):
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server = BoundedServer((host, port), Handler)
    server.daemon_threads = True
    # Complete TLS handshakes in bounded worker threads rather than blocking accept.
    original_finish = server.finish_request
    def finish_request(sock, address):
        sock.settimeout(5)
        try:
            with context.wrap_socket(sock, server_side=True) as secured:
                original_finish(secured, address)
        except (OSError, ssl.SSLError):
            sock.close()
    server.finish_request = finish_request
    def expiry():
        while True:
            time.sleep(2)
            try:
                store.expire()
            except (OSError, ValueError, subprocess.SubprocessError):
                pass  # Keep the pending journal and retry recovery; never expose credentials in logs.
    threading.Thread(target=expiry, daemon=True).start()
    server.serve_forever()


def open_window(root, timeout=300):
    if live_game():
        raise ValueError('Exit the game before opening pairing.')
    cert, _ = ensure_certificate(Path(root))
    authorization = base64.b32encode(secrets.token_bytes(16)).decode()[:12]
    write_json(Path(root) / 'window.json', {'authorization': authorization,
               'expires': time.time() + timeout, 'attempts': 0, 'used': False})
    code = connection_code(ssl.PEM_cert_to_DER_cert(cert.read_text()), authorization)
    print('Controller Router connection code: ' + code, flush=True)
    print('Open Pair console in UNO Q Setup. This code expires in five minutes and can be used once.', flush=True)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('serve', 'pair'))
    parser.add_argument('--root', type=Path, default=default_root())
    args = parser.parse_args()
    serve(args.root) if args.action == 'serve' else open_window(args.root)


if __name__ == '__main__':
    main()
