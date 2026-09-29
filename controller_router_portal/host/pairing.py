"""UNO Q connection authority. Public views deliberately omit all credentials."""
from __future__ import annotations

import copy
import hmac
import json
import secrets
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

try:
    from ..shared.pairing import Peer, load_json, write_json, secret, parse_code, normalize_host, valid_id, legacy_proof
except ImportError:
    from shared.pairing import Peer, load_json, write_json, secret, parse_code, normalize_host, valid_id, legacy_proof

STATE = Path('/home/arduino/.local/state/controller-router')
PRODUCTS = {'virtualglove': (8100, 'virtualglove'), 'rob_vision': (8101, 'rob-vision')}


class ProductAdapters:
    def installed(self):
        return {app for app, (_, folder) in PRODUCTS.items()
                if Path('/home/arduino/ArduinoApps', folder, 'app.yaml').is_file()}

    def request(self, app, operation, **payload):
        port, folder = PRODUCTS[app]
        token = Path('/home/arduino/ArduinoApps', folder, 'data/router-pairing-adapter-token').read_text().strip()
        request = Request(f'http://127.0.0.1:{port}/api/router-pairing',
                          json.dumps({'operation': operation, **payload}).encode(),
                          {'Content-Type': 'application/json', 'X-Controller-Router-Authorization': token}, method='POST')
        with urlopen(request, timeout=10) as response:
            raw = response.read(32769)
            if len(raw) > 32768:
                raise ValueError('The app connection response is too large.')
            document = json.loads(raw)
        if document.get('error'):
            raise ValueError('The controller app could not update its connection.')
        return document


class PairingManager:
    def __init__(self, matrix, game_active, root=STATE, adapters=None, peer=Peer, clock=time.time):
        self.root, self.matrix, self.game_active = Path(root), matrix, game_active
        self.adapters, self.peer, self.clock = adapters or ProductAdapters(), peer, clock
        self.lock = threading.RLock()
        self.document = load_json(self.root / 'connections.json',
                                  {'schema': 1, 'uno_id': secrets.token_hex(16), 'consoles': {}, 'conflicts': []})
        self.window = None
        self.locked_until = 0
        self.certificate_identity = None
        self._save()

    def _save(self):
        write_json(self.root / 'connections.json', self.document)

    def _idle(self):
        if self.game_active():
            self.matrix.clear_pairing()
            self.window = None
            raise ValueError('Finish the game before changing console connections.')

    def inspect(self):
        with self.lock:
            consoles = []
            for identity, item in self.document['consoles'].items():
                consoles.append({'id': identity, 'host': item['host'], 'platform': item['platform'],
                    'status': item.get('status', 'Unavailable'), 'apps': {
                        app: {'status': value.get('status', 'Needs attention'), 'enabled': value.get('enabled', True)}
                        for app, value in item.get('apps', {}).items()}, 'message': item.get('message', '')})
            return {'consoles': consoles, 'conflicts': self.document['conflicts'],
                    'pairing': bool(self.window and self.window['expires'] > self.clock())}

    def begin(self, host, code, uno_host):
        with self.lock:
            self._idle()
            if self.clock() < self.locked_until:
                raise ValueError('Too many confirmation attempts. Wait for the pairing window to expire.')
            if self.window and self.window['expires'] > self.clock():
                raise ValueError('Finish or cancel the current pairing first.')
            host, uno_host = normalize_host(host), normalize_host(uno_host)
            code_pin, authorization = parse_code(code)
            peer = self.peer(host, code_pin=code_pin)
            remote = peer.request('/identity')
            valid_id(remote['console_id'])
            if remote.get('game_active'):
                raise ValueError('Finish the console game before pairing.')
            pin = f'{secrets.randbelow(1_000_000):06d}'
            session = secrets.token_hex(16)
            if not self.certificate_identity or not self.matrix.begin_pairing(self.certificate_identity, pin):
                raise ValueError('The UNO Q Matrix is unavailable. Pairing needs its confirmation code.')
            self.window = {'session': session, 'expires': self.clock() + 120, 'attempts': 0,
                'pin': pin, 'host': host, 'uno_url': 'http://' + uno_host, 'authorization': authorization,
                'fingerprint': peer.last_fingerprint, 'remote': remote}
            return {'session': session, 'expires_in': 120, 'certificate_id': self.certificate_identity}

    def cancel(self):
        with self.lock:
            self.window = None
            self.matrix.clear_pairing()
            return {'cancelled': True}

    def confirm(self, session, pin):
        with self.lock:
            self._idle()
            window = self.window
            if not window or window['session'] != session or self.clock() >= window['expires']:
                self.cancel()
                raise ValueError('Confirmation expired. Start pairing again.')
            if not isinstance(pin, str) or not hmac.compare_digest(pin, window['pin']):
                window['attempts'] += 1
                if window['attempts'] >= 5:
                    self.locked_until = window['expires']
                    self.cancel()
                raise ValueError('Confirmation code did not match the Matrix.')
            self.window = None
            try:
                identity = window['remote']['console_id']
                old = self.document['consoles'].get(identity, {})
                record = {'host': window['host'], 'platform': window['remote']['platform'],
                    'fingerprint': window['fingerprint'], 'token': secret(), 'uno_url': window['uno_url'],
                    'apps': copy.deepcopy(old.get('apps', {}))}
                available = set(window['remote']['apps']) & self.adapters.installed()
                for app in available:
                    if record['apps'].get(app, {}).get('enabled') is False:
                        continue
                    record['apps'][app] = {'token': secret(), 'console_id': secrets.token_hex(16),
                                            'enabled': True, 'status': 'Ready'}
                peer = self.peer(record['host'], pin=record['fingerprint'])
                self._provision(identity, record, peer, authorization=window['authorization'])
                return self.inspect()
            finally:
                self.matrix.clear_pairing()

    def _payload(self, record):
        return {'uno_id': self.document['uno_id'], 'uno_url': record['uno_url'], 'token': record['token'],
                'credentials': {app: {'token': value['token'], 'console_id': value['console_id']}
                    for app, value in record['apps'].items() if value.get('enabled', True)}}

    def _provision(self, identity, record, peer, authorization=None, migration=None):
        self._idle()
        payload = self._payload(record)
        if authorization is not None:
            pending = peer.request('/pair', {**payload, 'authorization': authorization})
        elif migration:
            transcript = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            pending = peer.request('/adopt', {'connection': payload, 'proofs': [
                {'nonce': nonce, 'proof': legacy_proof(token, nonce + '\n' + transcript,
                    identity, record['fingerprint'])} for nonce, token in migration.values()]})
        else:
            pending = peer.request('/manage', {**payload, 'operation': 'prepare'}, token=record['token'])
        transaction = pending['transaction']
        snapshots = {}
        previous = copy.deepcopy(self.document)
        journal = {'identity': identity, 'record': record, 'transaction': transaction, 'snapshots': snapshots,
                   'previous': previous}
        write_json(self.root / 'pending-connection.json', journal)
        current_app = None
        try:
            for app, credentials in record['apps'].items():
                if app not in self.adapters.installed():
                    continue
                current_app = app
                snapshots[app] = self.adapters.request(app, 'export')
                write_json(self.root / 'pending-connection.json', journal)
                if credentials.get('enabled', True):
                    self.adapters.request(app, 'import', record={**credentials, 'identity': identity,
                        'host': record['host'], 'platform': record['platform']})
                else:
                    self.adapters.request(app, 'remove', identity=identity)
            self._idle()
            current_app = None
            peer.request('/manage', {'operation': 'commit', 'transaction': transaction}, token=record['token'])
            record['status'] = 'Connected'
            self.document['consoles'][identity] = record
            self._save()
            peer.request('/manage', {'operation': 'finalize', 'transaction': transaction}, token=record['token'])
            write_json(self.root / ('before-connection-' + transaction + '.json'), journal)
            (self.root / 'pending-connection.json').unlink()
        except Exception as error:
            self._rollback(journal, peer)
            names = {'virtualglove': 'VirtualGlove', 'rob_vision': 'R.O.B. Vision'}
            if current_app:
                message = names[current_app] + ' needs attention.'
            elif str(error) in ('App setup needs attention: VirtualGlove',
                                'App setup needs attention: R.O.B. Vision',
                                'App setup needs attention: R.O.B. Vision, VirtualGlove'):
                message = str(error) + '.'
            else:
                message = 'The console connection needs attention.'
            recovery = ('Recovery will retry when its service is available.'
                        if (self.root / 'pending-connection.json').exists()
                        else 'The previous connection was restored.')
            raise ValueError(message + ' ' + recovery + ' Check the app services and try again.') from None

    def _rollback(self, journal, peer):
        failures = []
        for app, snapshot in journal['snapshots'].items():
            try:
                self.adapters.request(app, 'restore', snapshot=snapshot)
            except Exception:
                failures.append(app)
        try:
            peer.request('/manage', {'operation': 'abort', 'transaction': journal['transaction']},
                         token=journal['record']['token'])
        except Exception:
            # The console may have independently recovered its expired journal.
            previous = journal['previous']['consoles'].get(journal['identity'])
            try:
                if previous:
                    restored = peer.request('/manage', {'operation': 'status'}, token=previous['token'])
                    if restored.get('uno_id') != journal['previous']['uno_id']:
                        raise ValueError('Recovery identity mismatch.')
                else:
                    restored = peer.request('/identity')
                    if restored.get('paired'):
                        raise ValueError('Console recovery is incomplete.')
                if restored.get('console_id') != journal['identity']:
                    raise ValueError('Recovery identity mismatch.')
            except Exception:
                failures.append('console')
        self.document = journal['previous']
        self._save()
        if not failures:
            (self.root / 'pending-connection.json').unlink(missing_ok=True)

    def reconcile(self):
        """Repair interrupted work, refresh links, and provision newly installed adapters."""
        with self.lock:
            journal = load_json(self.root / 'pending-connection.json')
            if journal:
                record = journal['record']
                self._rollback(journal, self.peer(record['host'], pin=record['fingerprint']))
                return
            if not self.game_active():
                self.import_legacy()
            for identity, record in list(self.document['consoles'].items()):
                try:
                    peer = self.peer(record['host'], pin=record['fingerprint'])
                    remote = peer.request('/manage', {'operation': 'status'}, token=record['token'])
                    if remote['console_id'] != identity or remote['uno_id'] != self.document['uno_id']:
                        raise ValueError('Console identity needs review.')
                    new_apps = (set(remote['apps']) & self.adapters.installed()) - set(record['apps'])
                    if new_apps and not self.game_active() and not remote.get('game_active'):
                        candidate = copy.deepcopy(record)
                        for app in new_apps:
                            candidate['apps'][app] = {'enabled': True, 'token': secret(),
                                'console_id': secrets.token_hex(16), 'status': 'Ready'}
                        self._provision(identity, candidate, peer)
                    current = self.document['consoles'][identity]
                    current['status'] = 'Connected'
                    for app, value in current['apps'].items():
                        value['status'] = ('Disabled' if not value.get('enabled', True) else
                                          'Ready' if app in remote['apps'] and app in self.adapters.installed() else 'Needs attention')
                        if value['status'] == 'Ready':
                            try:
                                if not self.adapters.request(app, 'status', identity=identity).get('ready'):
                                    value['status'] = 'Needs attention'
                            except (OSError, ValueError):
                                value['status'] = 'Needs attention'
                except ValueError:
                    record['status'] = 'Needs attention'
                except OSError:
                    record['status'] = 'Unavailable'
            self._save()

    def import_legacy(self):
        """Prove possession of existing app credentials before consolidating identities."""
        groups = {}
        conflicts = []
        for app in self.adapters.installed():
            existing_host = None
            try:
                exported = self.adapters.request(app, 'export')
                if app == 'virtualglove':
                    config = exported['config']
                    records = [{'host': config.get('receiver'), 'token': config.get('token'),
                                'platform': config.get('platform'), 'id': None}]
                else:
                    records = exported['records']
                for existing in records:
                    existing_host = existing.get('host')
                    if not existing.get('host') or not existing.get('token') or existing.get('router_identity'):
                        continue
                    if any(existing['host'] == record['host'] and app in record['apps']
                           for record in self.document['consoles'].values()):
                        continue
                    peer = self.peer(existing['host'])
                    nonce = secrets.token_hex(32)
                    proof = peer.request('/legacy-proof', {'app': app, 'nonce': nonce})
                    identity = valid_id(proof['console_id'])
                    if not hmac.compare_digest(proof.get('proof', ''),
                            legacy_proof(existing['token'], nonce, identity, peer.last_fingerprint)):
                        raise ValueError('Existing console credentials did not prove its identity.')
                    if proof.get('paired') or identity in self.document['consoles']:
                        conflicts.append({'host': existing['host'], 'message':
                            'An existing connection needs review. Pair this console explicitly to choose this UNO Q.'})
                        continue
                    group = groups.setdefault(identity, {'peer': peer, 'proof': proof, 'records': {}})
                    if group['peer'].last_fingerprint != peer.last_fingerprint:
                        raise ValueError('Console certificate identities conflict.')
                    group['records'][app] = (existing, nonce)
            except OSError:
                # Preserve the legacy link while making the pending migration visible.
                names = {'virtualglove': 'VirtualGlove', 'rob_vision': 'R.O.B. Vision'}
                notice = {'message': names[app] +
                    ' has an existing connection awaiting import. Bring the console online and upgrade its software, then check again.'}
                if existing_host:
                    notice['host'] = existing_host
                conflicts.append(notice)
            except (ValueError, KeyError):
                conflicts.append({'message': 'An existing app connection needs review. Its saved settings remain intact.'})
        for identity, group in groups.items():
            unproved = set(group['proof'].get('legacy_paired_apps', [])) - set(group['records'])
            if unproved:
                conflicts.append({'host': group['peer'].host, 'message':
                    'This console has another existing app connection. Pair it explicitly to choose this UNO Q; its current settings remain intact.'})
                continue
            # Preserve the UNO's hostname rather than using the loopback adapter address.
            hostname_file = Path('/home/arduino/ArduinoApps/virtualglove/data/controller-hostname')
            import socket
            hostname = hostname_file.read_text().strip() if hostname_file.exists() else socket.gethostname().split('.')[0] + '.local'
            peer, remote = group['peer'], group['proof']
            record = {'host': peer.host, 'platform': remote['platform'], 'fingerprint': peer.last_fingerprint,
                      'token': secret(), 'uno_url': 'http://' + normalize_host(hostname), 'apps': {}}
            for app, (existing, _) in group['records'].items():
                record['apps'][app] = {'enabled': True, 'token': secret(),
                    'console_id': existing.get('id') or secrets.token_hex(16), 'status': 'Ready'}
            # Provision installed adapters not previously paired to either product automatically.
            for app in (set(remote['apps']) & self.adapters.installed()) - set(record['apps']):
                record['apps'][app] = {'enabled': True, 'token': secret(),
                    'console_id': secrets.token_hex(16), 'status': 'Ready'}
            try:
                self._provision(identity, record, self.peer(peer.host, pin=peer.last_fingerprint),
                    migration={app: (nonce, existing['token'])
                               for app, (existing, nonce) in group['records'].items()})
            except ValueError:
                conflicts.append({'host': peer.host, 'message': 'Migration could not complete. The previous app connection was retained.'})
        self.document['conflicts'] = conflicts

    def access(self, identity, app, enabled):
        with self.lock:
            self._idle()
            record = copy.deepcopy(self.document['consoles'][identity])
            if app not in record['apps'] or type(enabled) is not bool:
                raise ValueError('Choose an installed app and its access setting.')
            record['apps'][app]['enabled'] = enabled
            record['apps'][app]['status'] = 'Ready' if enabled else 'Disabled'
            if enabled:
                record['apps'][app]['token'] = secret()
            self._provision(identity, record, self.peer(record['host'], pin=record['fingerprint']))
            return self.inspect()

    def remove(self, identity):
        with self.lock:
            self._idle()
            record = copy.deepcopy(self.document['consoles'][identity])
            for item in record['apps'].values():
                item.update(enabled=False, status='Disabled')
            peer = self.peer(record['host'], pin=record['fingerprint'])
            self._provision(identity, record, peer)
            peer.request('/manage', {'operation': 'remove'}, token=record['token'])
            del self.document['consoles'][identity]
            self._save()
            return self.inspect()

    def operation(self, payload, uno_host=None):
        action = payload.get('operation')
        if action == 'inspect': return self.inspect()
        if action == 'begin': return self.begin(payload.get('host'), payload.get('code'), uno_host)
        if action == 'confirm': return self.confirm(payload.get('session'), payload.get('pin'))
        if action == 'cancel': return self.cancel()
        if action == 'remove': return self.remove(payload.get('id'))
        if action == 'access': return self.access(payload.get('id'), payload.get('app'), payload.get('enabled'))
        if action == 'repair':
            self._idle(); self.reconcile(); return self.inspect()
        raise ValueError('Unknown connection action.')

    def routing(self, message):
        action = message.get('operation')
        if action == 'targets':
            return {'targets': [{'app': 'router', 'console_id': identity,
                'name': record['platform'].title() + ' · ' + record['host']}
                for identity, record in self.document['consoles'].items()], 'errors': []}
        if action not in ('read', 'save', 'check', 'rollback'):
            raise ValueError('Unknown routing action.')
        if action in ('save', 'rollback'): self._idle()
        record = self.document['consoles'].get(message.get('console_id'))
        if not record: raise ValueError('Choose a paired console.')
        peer = self.peer(record['host'], pin=record['fingerprint'])
        return peer.request('/router', {'action': action, 'revision': message.get('revision'),
            'config': message.get('config'), 'watch_ms': min(10000, max(0, int(message.get('watch_ms', 0))))},
            token=record['token'])
