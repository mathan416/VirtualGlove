"""Private UNO product adapters. Called only with an installer-created capability."""
from __future__ import annotations

import secrets
from pathlib import Path
from .pairing import load_json, write_json, valid_id, valid_secret


def authorized(directory, headers):
    try:
        expected = (Path(directory) / 'router-pairing-adapter-token').read_text().strip()
    except OSError:
        return False
    offered = headers.get('X-Controller-Router-Authorization', '')
    return len(expected) >= 32 and secrets.compare_digest(expected, offered)


def rob_operation(pairings, payload):
    """Update the live credential cache without changing game registries."""
    with pairings.lock:
        operation = payload.get('operation')
        if operation == 'status':
            return {'ready': any(record.get('router_identity') == payload.get('identity')
                                 for record in pairings.records.values())}
        if operation == 'export':
            return {'records': list(pairings.records.values()), 'blocked_legacy': sorted(pairings.blocked_legacy)}
        if operation == 'restore':
            snapshot = payload['snapshot']
            pairings.records = {record['id']: record for record in snapshot['records']}
            pairings.blocked_legacy = set(snapshot['blocked_legacy'])
        elif operation == 'import':
            record = payload['record']
            valid_id(record['console_id']); valid_secret(record['token'])
            if record['platform'] not in ('retropie', 'batocera', 'recalbox'):
                raise ValueError('This console is not supported by R.O.B. Vision.')
            # Identity, rather than hostname, controls replacement.
            for key, previous in list(pairings.records.items()):
                if previous.get('router_identity') == record['identity']:
                    del pairings.records[key]
            pairings.records[record['console_id']] = {'id': record['console_id'], 'token': record['token'],
                'platform': record['platform'], 'host': record['host'], 'router_identity': record['identity']}
            pairings.blocked_legacy.add(record['platform'])
        elif operation == 'remove':
            for key, record in list(pairings.records.items()):
                if record.get('router_identity') == payload['identity']:
                    del pairings.records[key]
        else:
            raise ValueError('Unsupported pairing adapter operation.')
        pairings._save()
        return {'ready': True}


def glove_operation(state, payload):
    """Retain saved camera/player settings and the user's selected console."""
    with state.config_lock:
        operation = payload.get('operation')
        config = state.load_config()
        if operation == 'status':
            return {'ready': payload.get('identity') in config.get('router_connections', {})}
        if operation == 'export':
            return {'config': config}
        if operation == 'restore':
            state._store_config(payload['snapshot']['config'], restart=True)
            return {'ready': True}
        records = config.setdefault('router_connections', {})
        if operation == 'import':
            record = payload['record']
            valid_id(record['console_id']); valid_secret(record['token'])
            previous = records.get(record['identity'], {})
            records[record['identity']] = record
            # A second connection is retained without silently replacing a selected console.
            if (not config.get('receiver') or config.get('receiver') == record['host'] or
                    (previous.get('token') and config.get('token') == previous['token'])):
                config.update(receiver=record['host'], token=record['token'], platform=record['platform'])
        elif operation == 'remove':
            record = records.pop(payload['identity'], None)
            if record and config.get('token') == record['token']:
                config.update(token='', receiver='')
        else:
            raise ValueError('Unsupported pairing adapter operation.')
        state._store_config(config, restart=True)
        return {'ready': True}
