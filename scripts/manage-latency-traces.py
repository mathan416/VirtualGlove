#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/manage-latency-traces.py
# Purpose: Enable and restore bounded Controller/receiver timing traces safely.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Addressed the renamed virtualglove App Lab container.
#   2026-09-08 - Added reversible two-device trace session management.
#   2026-09-08 - Require an emulator-free start and flush receiver traces gracefully.
# Full history: docs/CHANGELOG.md and Git history.

"""Restart only the measured services, then restore production and collect traces."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path


CONTROLLER_START = r'''
import hashlib, json, os, subprocess, sys, time, urllib.request
from pathlib import Path
session, duration = sys.argv[1], int(sys.argv[2])
if not __import__('re').fullmatch(r'[0-9a-f]{32}', session) or not 30 <= duration <= 600:
    raise SystemExit('invalid session or duration')
base = Path('/home/arduino/ArduinoApps/virtualglove')
def controller_enabled():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8088/status', timeout=2) as response:
            return bool(json.load(response).get('controller_enabled'))
    except Exception:
        return False
was_enabled = controller_enabled()
folder = base/'data'/'latency-traces'/session
folder.mkdir(mode=0o700, parents=True, exist_ok=False)
override = folder/'trace-compose.yaml'
override.write_text('services:\n  main:\n    environment:\n'
    '      VIRTUALGLOVE_DIAGNOSTIC_TRACE: /app/data/latency-traces/%s/controller\n'
    '      VIRTUALGLOVE_DIAGNOSTIC_SECONDS: "%d"\n' % (session, duration))
command = ['docker','compose','--project-directory',str(base/'.cache'),
    '-f',str(base/'.cache/app-compose.yaml'),'-f',str(base/'.cache/app-compose-overrides.yaml'),
    '-f',str(override),'up','-d','--force-recreate','main']
compose_environment = dict(os.environ, APP_HOME=str(base))
subprocess.run(command, check=True, stdout=subprocess.DEVNULL,
               env=compose_environment)
inspect = subprocess.check_output(['docker','inspect','virtualglove-main-1',
    '--format','{{json .Config.Env}}'], text=True)
env = json.loads(inspect)
expected = 'VIRTUALGLOVE_DIAGNOSTIC_TRACE=/app/data/latency-traces/%s/controller' % session
if expected not in env:
    raise SystemExit('Controller trace environment was not applied')
rearmed = False
if was_enabled:
    body = json.dumps({'enabled':True}).encode()
    for _ in range(40):
        try:
            request = urllib.request.Request('http://127.0.0.1:8088/api/controller',
                data=body, headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(request, timeout=2) as response:
                rearmed = bool(json.load(response).get('controller_enabled'))
            if rearmed: break
        except Exception: pass
        time.sleep(.5)
    if not rearmed:
        raise SystemExit('Controller tracing started but armed delivery was not restored')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps({'boot_id_sha256':hashlib.sha256(boot.encode()).hexdigest(),
                  'folder':str(folder),'trace_environment':True,
                  'controller_was_enabled':was_enabled,'controller_rearmed':rearmed}))
'''

RETROPIE_START = r'''
import hashlib, json, re, subprocess, sys
from pathlib import Path
session, duration = sys.argv[1], int(sys.argv[2])
if not re.fullmatch(r'[0-9a-f]{32}', session) or not 30 <= duration <= 600:
    raise SystemExit('invalid session or duration')
folder = '/var/tmp/virtualglove-latency/%s' % session
drop = '/run/systemd/system/virtualglove-receiver.service.d/latency-trace.conf'
subprocess.run(['sudo','-n','mkdir','-p',folder,drop.rsplit('/',1)[0]],check=True)
subprocess.run(['sudo','-n','chmod','700',folder],check=True)
content = ('[Service]\nKillSignal=SIGINT\n'
    'Environment=VIRTUALGLOVE_DIAGNOSTIC_TRACE=%s/receiver\n'
    'Environment=VIRTUALGLOVE_DIAGNOSTIC_SECONDS=%d\n' % (folder,duration))
subprocess.run(['sudo','-n','tee',drop],input=content,text=True,stdout=subprocess.DEVNULL,check=True)
subprocess.run(['sudo','-n','systemctl','daemon-reload'],check=True)
subprocess.run(['sudo','-n','systemctl','restart','virtualglove-receiver.service'],check=True)
shown = subprocess.check_output(['systemctl','show','virtualglove-receiver.service','-p','Environment'],text=True)
if 'VIRTUALGLOVE_DIAGNOSTIC_TRACE=%s/receiver' % folder not in shown:
    raise SystemExit('Receiver trace environment was not applied')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps({'boot_id_sha256':hashlib.sha256(boot.encode()).hexdigest(),
                  'folder':folder,'trace_environment':True}))
'''

RETROPIE_PREFLIGHT = r'''
import json
from pathlib import Path

running = []
for process in Path('/proc').glob('[0-9]*'):
    try:
        command = (process/'comm').read_text().strip().casefold()
    except OSError:
        continue
    if command.startswith('retroarch'):
        running.append(int(process.name))
print(json.dumps({'retroarch_running':bool(running),'pids':sorted(running)[:8]}))
'''

CONTROLLER_STOP = r'''
import base64, hashlib, json, os, subprocess, sys, time, urllib.request
from pathlib import Path
session = sys.argv[1]
base = Path('/home/arduino/ArduinoApps/virtualglove')
def controller_enabled():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8088/status', timeout=2) as response:
            return bool(json.load(response).get('controller_enabled'))
    except Exception:
        return False
was_enabled = controller_enabled()
folder = base/'data'/'latency-traces'/session
subprocess.run(['docker','compose','--project-directory',str(base/'.cache'),
    '-f',str(base/'.cache/app-compose.yaml'),'-f',str(base/'.cache/app-compose-overrides.yaml'),
    'up','-d','--force-recreate','main'],check=True,stdout=subprocess.DEVNULL,
    env=dict(os.environ, APP_HOME=str(base)))
inspect = subprocess.check_output(['docker','inspect','virtualglove-main-1',
    '--format','{{json .Config.Env}}'],text=True)
env = json.loads(inspect)
expected = 'VIRTUALGLOVE_DIAGNOSTIC_TRACE=/app/data/latency-traces/%s/controller' % session
clean = expected not in env
rearmed = False
if was_enabled:
    body = json.dumps({'enabled':True}).encode()
    for _ in range(40):
        try:
            request = urllib.request.Request('http://127.0.0.1:8088/api/controller',
                data=body, headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(request, timeout=2) as response:
                rearmed = bool(json.load(response).get('controller_enabled'))
            if rearmed: break
        except Exception: pass
        time.sleep(.5)
    if not rearmed:
        raise SystemExit('Production Controller restored but armed delivery was not restored')
files = {}
for path in folder.glob('controller.*.*.json'):
    data = path.read_bytes()
    if len(data) > 16*1024*1024: raise SystemExit('Controller trace too large')
    files[path.name] = base64.b64encode(data).decode()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps({'boot_id_sha256':hashlib.sha256(boot.encode()).hexdigest(),
                  'trace_environment_removed':clean,'files':files,
                  'controller_was_enabled':was_enabled,'controller_rearmed':rearmed}))
'''

RETROPIE_STOP = r'''
import base64, hashlib, json, subprocess, sys
from pathlib import Path
session = sys.argv[1]
folder = Path('/var/tmp/virtualglove-latency')/session
drop = '/run/systemd/system/virtualglove-receiver.service.d/latency-trace.conf'
# Stop while the temporary SIGINT policy is still loaded so Python reaches its
# normal cleanup path and closes the bounded trace before production returns.
subprocess.run(['sudo','-n','systemctl','stop','virtualglove-receiver.service'],check=True)
subprocess.run(['sudo','-n','rm','-f',drop],check=True)
subprocess.run(['sudo','-n','systemctl','daemon-reload'],check=True)
subprocess.run(['sudo','-n','systemctl','start','virtualglove-receiver.service'],check=True)
shown = subprocess.check_output(['systemctl','show','virtualglove-receiver.service','-p','Environment'],text=True)
files = {}
listing = subprocess.check_output(['sudo','-n','find',str(folder),'-maxdepth','1','-type','f','-name','receiver.receiver.*.json','-print'],text=True)
for name in listing.splitlines():
    data = subprocess.check_output(['sudo','-n','cat',name])
    if len(data) > 16*1024*1024: raise SystemExit('Receiver trace too large')
    if not data: raise SystemExit('Receiver trace did not flush during graceful shutdown')
    try:
        report = json.loads(data.decode())
    except (UnicodeError, ValueError):
        raise SystemExit('Receiver trace is not valid JSON')
    if report.get('role') != 'receiver':
        raise SystemExit('Receiver trace has the wrong role')
    files[Path(name).name] = base64.b64encode(data).decode()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps({'boot_id_sha256':hashlib.sha256(boot.encode()).hexdigest(),
    'trace_environment_removed':
        ('VIRTUALGLOVE_DIAGNOSTIC_TRACE=%s/receiver' % folder) not in shown,
    'files':files}))
'''


def ssh_command(target, identity=None, host_key_alias=None):
    """Build one noninteractive SSH command without invoking a shell."""
    command = ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10']
    if identity:
        command += ['-i', str(identity)]
    if host_key_alias:
        command += ['-o', 'HostKeyAlias='+host_key_alias]
    return command + [target]


def remote(target, script, arguments, identity=None, host_key_alias=None, timeout=120):
    """Run one fixed Python program remotely and decode its JSON response."""
    command = ssh_command(target, identity, host_key_alias) + ['python3','-',*arguments]
    result = subprocess.run(command,input=script,text=True,stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-800:] or 'remote command failed')
    return json.loads(result.stdout)


def connection_from(args, role):
    """Return the selected target, identity, and host-key alias for one role."""
    return (getattr(args, role+'_ssh'), getattr(args, role+'_identity'),
            getattr(args, role+'_host_key_alias'))


def save_state(path, state):
    """Create a private, non-overwriting restoration state file."""
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with path.open('x') as stream:
        json.dump(state,stream,indent=2,allow_nan=False);stream.write('\n')
    os.chmod(path,0o600)


def start(args):
    """Enable finite tracing on both devices, rolling back on partial failure."""
    if args.state.exists():
        raise RuntimeError('State file already exists; stop or choose a new session')
    session = uuid.uuid4().hex
    controller_target, controller_identity, controller_alias = connection_from(args, 'controller')
    retropie_target, retropie_identity, retropie_alias = connection_from(args, 'retropie')
    readiness = remote(retropie_target, RETROPIE_PREFLIGHT, [],
                       retropie_identity, retropie_alias)
    if readiness.get('retroarch_running'):
        raise RuntimeError(
            'Close RetroArch before tracing so the custom core opens the traced native-state file'
        )
    controller = remote(controller_target, CONTROLLER_START,
                        [session, str(args.duration)], controller_identity, controller_alias)
    try:
        retropie = remote(retropie_target, RETROPIE_START,
                          [session, str(args.duration)], retropie_identity, retropie_alias)
    except Exception:
        remote(controller_target, CONTROLLER_STOP, [session],
               controller_identity, controller_alias)
        raise
    state = {'format':'virtualglove-latency-trace-session/1','session':session,
             'started_unix':time.time(),'duration_seconds':args.duration,
             'controller':{'target':args.controller_ssh,'identity':str(args.controller_identity or ''),
                           'host_key_alias':args.controller_host_key_alias,**controller},
             'retropie':{'target':args.retropie_ssh,'identity':str(args.retropie_identity or ''),
                         'host_key_alias':args.retropie_host_key_alias,**retropie},
             'diagnostic_core':'not selected by this tool; use the separately named core for core timing'}
    save_state(args.state,state)
    print('Tracing active for session %s; production services were restarted.' % session)
    print('State: %s' % args.state)


def stop(args):
    """Restore production processes before collecting finalized trace files."""
    state=json.loads(args.state.read_text())
    if state.get('format')!='virtualglove-latency-trace-session/1' or not re.fullmatch(r'[0-9a-f]{32}',state.get('session','')):
        raise RuntimeError('Invalid trace-session state file')
    session=state['session']; results={}
    for role,script in (('controller',CONTROLLER_STOP),('retropie',RETROPIE_STOP)):
        info=state[role]
        results[role]=remote(info['target'],script,[session],Path(info['identity']) if info['identity'] else None,
                             info.get('host_key_alias'))
    export=args.output_dir
    export.mkdir(mode=0o700,parents=True,exist_ok=False)
    for role,result in results.items():
        for name,encoded in result['files'].items():
            path=export/name;path.write_bytes(base64.b64decode(encoded,validate=True));os.chmod(path,0o600)
    same_boot=all(results[role]['boot_id_sha256']==state[role]['boot_id_sha256'] for role in results)
    restored=all(results[role]['trace_environment_removed'] for role in results)
    report={'format':'virtualglove-latency-trace-export/1','session':session,
            'same_boot':same_boot,'production_environment_restored':restored,
            'files':sorted(path.name for path in export.iterdir()),
            'core_trace_required_for_core_consumption':True}
    (export/'export.json').write_text(json.dumps(report,indent=2)+'\n');os.chmod(export/'export.json',0o600)
    if not restored:
        raise RuntimeError('Trace files were collected but production environment restoration failed')
    print('Tracing stopped and production services restored. Export: %s' % export)
    if not same_boot: print('WARNING: a device rebooted; do not correlate these traces as one session')


def add_connection(parser, role):
    """Add one device's noninteractive SSH options to a command parser."""
    parser.add_argument('--'+role+'-ssh',required=True)
    parser.add_argument('--'+role+'-identity',type=Path)
    parser.add_argument('--'+role+'-host-key-alias')


def main():
    """Parse a start/stop operation and report recoverable command errors."""
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='action',required=True)
    begin=commands.add_parser('start',help='restart services with bounded tracing enabled')
    add_connection(begin,'controller');add_connection(begin,'retropie')
    begin.add_argument('--duration',type=int,default=180,choices=range(30,601))
    begin.add_argument('--state',type=Path,required=True)
    finish=commands.add_parser('stop',help='restore production, then collect finalized traces')
    finish.add_argument('--state',type=Path,required=True)
    finish.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    try:
        start(args) if args.action=='start' else stop(args)
    except (OSError,ValueError,subprocess.SubprocessError,RuntimeError) as error:
        parser.error(str(error))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
