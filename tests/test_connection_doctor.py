# Project: VirtualGlove
# File: tests/test_connection_doctor.py
# Purpose: Verify Connection Doctor browser logic and safe diagnostic behavior.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-13 - Added Connection Doctor coverage.
# Full history: docs/CHANGELOG.md and Git history.
"""Execute the Doctor's real JavaScript with isolated API/DOM fixtures in Node."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from powerglove_vision.connection_doctor_web import DOCTOR_SCRIPT
from powerglove_vision.control_server import SETUP

HARNESS = r"""
const vm=require('node:vm');
let input='';process.stdin.on('data',s=>input+=s);process.stdin.on('end',async()=>{
const {script,scenario}=JSON.parse(input),nodes={},calls=[];let downloaded=null,configReads=0,probeReads=0;
function node(){return {value:'',checked:false,disabled:false,textContent:'',children:[],listeners:{},
addEventListener(k,f){this.listeners[k]=f},replaceChildren(...rows){this.children=rows},append(...rows){this.children.push(...rows)},setAttribute(){},click(){}}}
const $=id=>nodes[id]||(nodes[id]=node());
const config={receiver:'private-console.local',port:55355,profile:'super_glove_ball',connection_configured:true,token:'secret-token',player:{name:'private-player'},calibration:{x:123}};
if(scenario==='empty')config.receiver='';
for(const k of ['receiver','port','profile'])$(k).value=String(config[k]);
if(scenario==='unsaved')$('receiver').value='draft.local';
const status={worker_running:true,controller_enabled:true,controller_context_active:true,vision_state:'active',receiver_available:true,game_session_active:true,profile:'super_glove_ball',emulator:'lr-nestopia-powerglove',input_mode:'native',events:['private-event'],receiver_active_address:'10.20.30.40'};
if(scenario==='idle')status.controller_enabled=false;
if(scenario==='mismatch')status.input_mode='joystick';
if(scenario==='launch')status.launch_guard_active=true;
if(scenario==='unknown-profile')status.profile='unsupported';
const context={$,settingsBusy:scenario==='busy',pairingBusy:false,windowActive:()=>false,Date,JSON,Error,String,Object,Promise,
document:{createElement:()=>node(),createTextNode:text=>({textContent:text})},
setTimeout:f=>{f();return 1},Blob:class{constructor(parts){this.parts=parts}},URL:{createObjectURL:b=>{downloaded=JSON.parse(b.parts.join(''));return 'blob:test'},revokeObjectURL(){}},
api:async(path,payload)=>{calls.push({path,payload});
if(scenario==='offline')throw Error('private exception secret-token');
if(path==='/api/config'){configReads++;return {...config,receiver:scenario==='external-change'&&configReads>1?'changed.local':config.receiver}}
if(path==='/api/test-connection'){if(scenario==='dns')throw Error('private DNS details');return {address:'10.20.30.40'}}
if(path==='/api/connection-status'){probeReads++;return {console_service:scenario!=='service-down',console_authenticated:!['unpaired','service-down'].includes(scenario),checked_seconds_ago:scenario==='stale'?60:scenario==='pending'&&probeReads<3?null:1}}
if(path==='/status'){if(scenario==='edit-during'){$('receiver').value='changed.local';$('receiver').listeners.input();}if(scenario==='worker-offline')throw Error('private worker detail');return status}
throw Error('Unexpected API '+path);
}};
vm.runInNewContext(script,context);
await $('doctor-run').onclick();
if(!$('doctor-download').disabled)$('doctor-download').onclick();
process.stdout.write(JSON.stringify({downloaded,calls,probeReads,disabled:$('doctor-run').disabled,notice:$('doctor-notice').textContent}));
});
"""

@unittest.skipUnless(shutil.which('node'), 'Node is required for JavaScript behavior checks')
class ConnectionDoctorTests(unittest.TestCase):
    def run_doctor(self, scenario='success'):
        result = subprocess.run(['node', '-e', HARNESS], input=json.dumps(dict(script=DOCTOR_SCRIPT, scenario=scenario)), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data['disabled'])
        self.assertTrue(all(c['path'] in ['/api/config','/api/test-connection','/api/connection-status','/status'] for c in data['calls']))
        self.assertTrue(all(not c.get('payload') or c['path']=='/api/test-connection' for c in data['calls']))
        return data

    def states(self, result):
        return {c['id']: c['state'] for c in result['downloaded']['checks']}

    def test_success_is_limited_and_download_is_sanitized(self):
        result = self.run_doctor()
        states = self.states(result)
        self.assertEqual(states['pairing'], 'pass')
        self.assertEqual(states['receiver'], 'pass')
        self.assertEqual(states['mapping'], 'pass')
        self.assertEqual(states['device'], 'unknown')
        report = json.dumps(result['downloaded'])
        for private in ['private-', 'secret-token', '10.20.30.40', '55355', 'calibration', 'super_glove_ball']:
            self.assertNotIn(private, report)

    def test_unsaved_and_missing_console_do_not_probe(self):
        for scenario in ['unsaved','empty']:
            result = self.run_doctor(scenario)
            self.assertEqual([c['path'] for c in result['calls']], ['/api/config'])
            self.assertEqual(self.states(result)['saved'], 'attention')
            self.assertEqual(self.states(result)['pairing'], 'unknown')

    def test_busy_pairing_or_save_does_not_start_checks(self):
        self.assertEqual(self.run_doctor('busy')['calls'], [])

    def test_stale_and_failed_auth_never_pass_pairing(self):
        for scenario in ['stale','unpaired','service-down']:
            self.assertEqual(self.states(self.run_doctor(scenario))['pairing'], 'unknown')

    def test_pending_probe_is_retried(self):
        result = self.run_doctor('pending')
        self.assertEqual(result['probeReads'], 3)
        self.assertEqual(self.states(result)['pairing'], 'pass')

    def test_dns_failure_is_distinct_from_cached_service(self):
        self.assertEqual(self.states(self.run_doctor('dns'))['address'], 'attention')

    def test_idle_and_launch_guard_never_claim_receiver_ready(self):
        for scenario in ['idle','launch','worker-offline']:
            self.assertEqual(self.states(self.run_doctor(scenario))['receiver'], 'unknown')

    def test_mapping_mismatch_and_unknown_profile(self):
        self.assertEqual(self.states(self.run_doctor('mismatch'))['mapping'], 'attention')
        self.assertEqual(self.states(self.run_doctor('unknown-profile'))['mapping'], 'unknown')

    def test_changes_during_check_invalidate_download(self):
        for scenario in ['edit-during','external-change','offline']:
            self.assertIsNone(self.run_doctor(scenario)['downloaded'])

    def test_setup_scripts_parse_and_doctor_is_inside_pairing_card(self):
        from html.parser import HTMLParser
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(); self.scripts=[]; self.in_script=False; self.stack=[]; self.doctor_parent=None; self.pairing_closed=False; self.doctor_after_pairing=False; self.doctor_links=0
            def handle_starttag(self, tag, attrs):
                attrs=dict(attrs)
                if attrs.get('id')=='connection-doctor':
                    self.doctor_parent=self.stack[-1][1]
                    self.doctor_after_pairing=self.pairing_closed
                if tag=='a' and any(identity=='connection-doctor' for _,identity in self.stack):
                    self.doctor_links+=1
                if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
                    self.stack.append((tag,attrs.get('id')))
                if tag=='script': self.in_script=True
            def handle_endtag(self, tag):
                if tag=='script': self.in_script=False
                if self.stack and self.stack[-1][0]==tag:
                    _,identity=self.stack.pop()
                    if identity=='pairing-section': self.pairing_closed=True
            def handle_data(self, data):
                if self.in_script:self.scripts.append(data)
        parser=Parser();parser.feed(SETUP.decode())
        self.assertEqual(parser.doctor_parent,'pairing-card')
        self.assertTrue(parser.doctor_after_pairing)
        self.assertEqual(parser.doctor_links,0)
        self.assertNotIn(b'{{DOCTOR_', SETUP)
        for script in parser.scripts:
            parsed=subprocess.run(['node','--check'],input=script,text=True,capture_output=True)
            self.assertEqual(parsed.returncode,0,parsed.stderr)
