"""Fixed local product APIs for the shared console-assignment page."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ENDPOINTS = {'virtualglove': ('http://127.0.0.1:8100', '/api/controller-router'),
             'rob_vision': ('http://127.0.0.1:8101', '/api/router')}


def product_request(app, path, payload=None):
    base, _ = ENDPOINTS[app]
    headers = {'Content-Type': 'application/json'}
    if app == 'virtualglove':
        headers['X-VirtualGlove-Action'] = 'controller-router'
    request = Request(base + path, headers=headers,
                      data=None if payload is None else json.dumps(payload).encode())
    try:
        with urlopen(request, timeout=18) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            return {'error': json.load(error).get('error', 'Console request failed.')}
        except (ValueError, AttributeError):
            return {'error': 'Console request failed.'}


def targets(state):
    rows = []
    errors = []
    for app, detail in state.get('apps', {}).items():
        if app not in ENDPOINTS or not detail.get('installed'):
            continue
        if app == 'virtualglove':
            try:
                data = product_request(app, '/api/config')
                host = data.get('receiver')
                if host:
                    platform = {'retropie':'RetroPie', 'batocera':'Batocera', 'recalbox':'Recalbox'}.get(data.get('platform'), 'Console')
                    rows.append({'app': app, 'console_id': '', 'name': '%s · %s' % (platform, host)})
            except (OSError, ValueError):
                errors.append('VirtualGlove console connection is unavailable.')
        else:
            try:
                data = product_request(app, '/api/state')
                for console in data.get('link', {}).get('consoles', []):
                    if not console.get('legacy'):
                        rows.append({'app': app, 'console_id': console['id'],
                                     'name': '%s · %s' % (console.get('name', 'Console'), console.get('host', ''))})
            except (OSError, ValueError, KeyError):
                errors.append('R.O.B. Vision console list is unavailable.')
    return {'targets': rows, 'errors': errors}


def routing(message, state):
    action = message.get('operation')
    if action == 'targets':
        return targets(state)
    if action not in ('read', 'save', 'check', 'rollback'):
        raise ValueError('Unknown routing action.')
    app = message.get('app')
    if app not in ENDPOINTS or not state.get('apps', {}).get(app, {}).get('installed'):
        raise ValueError('Install this controller app before configuring its console.')
    if action in ('save', 'rollback') and any(item.get('game_active') for item in state.get('apps', {}).values()):
        raise ValueError('Exit the current game before changing assignments.')
    payload = {'action': action, 'revision': message.get('revision'),
               'config': message.get('config'), 'watch_ms': min(10000, max(0, int(message.get('watch_ms', 0))))}
    if app == 'rob_vision':
        payload['console_id'] = message.get('console_id')
        if not any(row['app'] == app and row['console_id'] == payload['console_id']
                   for row in targets(state)['targets']):
            raise ValueError('Choose a paired console.')
    return product_request(app, ENDPOINTS[app][1], payload)
