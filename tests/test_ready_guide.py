# Project: VirtualGlove
# SPDX-License-Identifier: MIT
"""Ready-guide migration, isolation, safe output transitions and live gates."""
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from powerglove_vision.players import READY_CHECKS, blank_ready_progress
from powerglove_vision.tuning import TuningManager
from powerglove_vision.control_server import ControlState
from powerglove_vision.ready_guide import game_gate
from powerglove_vision.ready_web import READY, READY_ENGINE, READY_SCRIPT


class ReadyPlayersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'gesture-tuning.json'
        self.manager = TuningManager(self.path)

    def command(self, action, **values):
        p = self.manager.player_snapshot()
        return self.manager.player_command(dict(action=action, player=p['active'], generation=p['generation'], **values))

    def test_version_five_migration_is_lossless_and_backed_up_on_first_write(self):
        original = copy.deepcopy(self.manager.players.data)
        original['version'] = 5
        item = original['players']['default']; item.pop('ready_progress')
        item.update(name='Existing player', joystick_deadzone=.42, progress={'course':1,'completed':[1,4],'lesson':5},
                    calibration={'version':2,'neutral':dict(palm_x=.5,palm_y=.5,palm_scale=.2,roll=0,noise_x=.01,noise_y=.02,reach_left=0,reach_right=0,reach_up=0,reach_down=0)})
        self.path.write_text(json.dumps(original))
        self.manager = TuningManager(self.path)
        self.assertIsNone(self.manager.players.error)
        self.assertEqual(json.loads(self.path.read_text()), original)
        self.command('ready_progress', progress={'course':1,'completed':['neutral'],'completed_at':None})
        saved = json.loads(self.path.read_text()); saved['version']=5
        ready = saved['players']['default'].pop('ready_progress')
        self.assertEqual(ready['completed'], ['neutral'])
        self.assertEqual(saved, original)
        self.assertEqual(json.loads(self.path.with_name('gesture-tuning-v5-backup.json').read_text()), original)

    def test_optional_independent_resumable_and_academy_isolation(self):
        first = self.manager.player_snapshot()['active']
        self.command('progress', progress={'course':1,'completed':[2],'lesson':3})
        self.command('ready_progress', progress={'course':1,'completed':['neutral','left'],'completed_at':None})
        second = self.command('create', name='Second')
        self.assertEqual(second['ready_progress'], blank_ready_progress())
        self.command('select', id=first)
        self.assertEqual(self.manager.player_snapshot()['ready_progress']['completed'], ['neutral','left'])
        self.assertEqual(self.manager.player_snapshot()['progress'], {'course':1,'completed':[2],'lesson':3})
        self.command('reset_progress')
        self.assertEqual(self.manager.player_snapshot()['ready_progress']['completed'], ['neutral','left'])
        reloaded = TuningManager(self.path)
        self.assertEqual(reloaded.player_snapshot()['ready_progress']['completed'], ['neutral','left'])
        self.assertNotIn('ready_progress', self.command('export')['backup'])

    def test_bad_updates_leave_file_unchanged(self):
        self.command('ready_progress', progress={'course':1,'completed':['neutral'],'completed_at':None})
        before = self.path.read_bytes()
        for value in [dict(course=True,completed=[],completed_at=None),dict(course=2,completed=[],completed_at=None),
                      dict(course=1,completed=['nope'],completed_at=None),dict(course=1,completed=['neutral']*11,completed_at=None),
                      dict(course=1,completed=['neutral'],completed_at='2026-01-01T00:00:00Z'),
                      dict(course=1,completed=list(READY_CHECKS),completed_at='2026-02-30T00:00:00Z'),
                      dict(course=1,completed=list(READY_CHECKS),completed_at=123),
                      dict(course=1,completed=[],completed_at=None,landmarks=[])]:
            with self.assertRaises(ValueError): self.command('ready_progress',progress=value)
            self.assertEqual(self.path.read_bytes(), before)
        stale = self.manager.player_snapshot(); self.command('create',name='Other')
        with self.assertRaises(ValueError):
            self.manager.player_command(dict(action='ready_progress',player=stale['active'],generation=stale['generation'],progress=blank_ready_progress()))

    def test_completion_is_bounded_and_monotonic(self):
        self.command('ready_progress', progress={'course':1,'completed':list(READY_CHECKS),'completed_at':'2026-09-12T12:00:00Z'})
        result=self.command('ready_progress',progress=blank_ready_progress())
        self.assertEqual(result['ready_progress']['completed'],list(READY_CHECKS))
        self.assertEqual(result['ready_progress']['completed_at'],'2026-09-12T12:00:00Z')


def game_status():
    return dict(worker_status_age_seconds=0,worker_running=True,practice_mode=False,game_session_active=True,
                active_profile='super_glove_ball',emulator='lr-nestopia-powerglove',input_mode='native',
                vision_state='active',camera_available=True,calibrated=True,calibrating=False,
                player={'active':'default','generation':0,'needs_center':False},controller_context_active=True,
                controller_enabled=True,worker_controller_enabled=True,receiver_available=True)


class ReadyGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'device.json';self.path.write_text(json.dumps(dict(receiver='console.local',token='x'*24,profile='off')))
        self.state=ControlState(self.path);self.session='ready-session-123456789';self.practice=False;self.calls=[]
        self.player=dict(active='default',generation=0,needs_center=False,ready_progress=dict(course=1,completed=list(READY_CHECKS),completed_at=None))
        self.state.update_worker(game_status())
        self.mock=patch('powerglove_vision.control_server.urllib.request.urlopen',side_effect=self.urlopen);self.mock.start();self.addCleanup(self.mock.stop)
        self.state.connection_probe=lambda *a,**k:dict(console_service=True,console_authenticated=True,checked_seconds_ago=0)

    def urlopen(self, request, **kwargs):
        self.calls.append((request.full_url,json.loads(request.data)))
        if request.full_url.endswith('/players'): result=self.player
        elif request.full_url.endswith('/practice'):result={'practice_mode':self.practice}
        elif request.full_url.endswith('/controller'):result={'controller_enabled':json.loads(request.data)['enabled']}
        else:raise AssertionError(request.full_url)
        return io.BytesIO(json.dumps(result).encode())

    def guide(self,action,**extra):
        return self.state.ready_request(dict(action=action,session=self.session,**extra))

    def test_begin_persists_pause_and_rejects_manual_and_automatic_start(self):
        self.state.set_controller_enabled(True)
        self.guide('begin')
        self.assertFalse(self.state.controller_enabled())
        with self.assertRaises(ValueError):self.state.set_controller_enabled(True)
        with self.assertRaises(ValueError):self.state._set_controller_enabled(True,automatic=True)
        reloaded=ControlState(self.path)
        self.assertFalse(reloaded.controller_enabled())
        with self.assertRaises(ValueError):reloaded.set_controller_enabled(True)
        self.assertTrue(all(not body['enabled'] for path,body in self.calls if path.endswith('/controller')))

    def test_only_current_visit_can_release_and_practice_must_end(self):
        self.guide('begin');self.practice=True
        self.assertFalse(self.guide('release',confirmed=True,player='default',generation=0)['released'])
        self.assertTrue(self.state._ready_marker.exists())
        with self.assertRaises(ValueError):self.guide('arm',player='default',generation=0)
        with self.assertRaises(ValueError):self.state.ready_request(dict(action='release',session='stale-session-12345678',confirmed=True))
        self.practice=False
        self.assertTrue(self.guide('release',confirmed=True,player='default',generation=0)['released'])
        self.assertFalse(self.state.controller_enabled())
        self.guide('arm',player='default',generation=0)
        self.assertTrue(self.state.controller_enabled())
        kinds=[path.rsplit('/',1)[-1] for path,_ in self.calls]
        self.assertLess(kinds.index('practice'),len(kinds)-1)

    def test_incomplete_and_stale_player_cannot_release(self):
        self.guide('begin')
        self.player['ready_progress']['completed']=[]
        with self.assertRaises(ValueError):self.guide('release',confirmed=True,player='default',generation=0)
        with self.assertRaises(ValueError):self.guide('release',confirmed=True,player='other',generation=0)
        self.assertTrue(self.state._ready_marker.exists())

    def test_cancel_does_not_arm_and_takeover_revokes_old_game_visit(self):
        self.guide('begin');self.guide('release',confirmed=True,player='default',generation=0)
        self.state.ready_request(dict(action='begin',session='second-session-12345678'))
        with self.assertRaises(ValueError):self.guide('arm',player='default',generation=0)
        self.state.ready_request(dict(action='cancel',session='second-session-12345678',confirmed=True))
        self.assertFalse(self.state.controller_enabled())

    def test_game_gate_all_final_states(self):
        good=game_status();self.assertIsNone(game_gate(good))
        for changes in [dict(game_session_active=False),dict(active_profile='off'),dict(receiver_available=False),
                        dict(input_mode='joystick'),dict(emulator=''),dict(vision_state='error'),dict(calibrated=False),
                        dict(calibration_save_error='failed'),dict(worker_status_age_seconds=3),dict(practice_mode=True),
                        dict(worker_controller_enabled=False),dict(launch_guard_active=True)]:
            self.assertIsNotNone(game_gate(dict(good,**changes)),changes)
        self.assertIsNone(game_gate(dict(good,emulator='lr-fceumm',input_mode='joystick')))
        numeric = dict(good, active_profile='program_1', emulator='lr-fceumm',
                       input_mode='joystick')
        self.assertIsNone(game_gate(numeric))
        manual = dict(good, active_profile='program_14', emulator='lr-fceumm',
                      input_mode='joystick', vision_state='idle',
                      camera_available=False, calibrated=False,
                      receiver_available=False, controller_enabled=False,
                      worker_controller_enabled=False)
        self.assertIsNone(game_gate(manual))


@unittest.skipUnless(shutil.which('node'), 'Node needed for guide JavaScript checks')
class ReadyJavaScriptTests(unittest.TestCase):
    def test_all_gestures_require_holds_release_and_safe_fresh_samples(self):
        script=READY_ENGINE+r"""
const assert=require('node:assert/strict');
let now=0,seq=0;
const base=()=>({detected:true,calibrated:true,practice_mode:true,worker_controller_enabled:false,vision_state:'active',sequence:seq++,dpad:{left:false,right:false,up:false,down:false},finger_active:{index:false,thumb:false},buttons:{a:false,b:false},recognition:{menu_guard:false},menu_gesture:{pose:null}});
function frame(key){const s=base();if(['left','right','up','down'].includes(key))s.dpad[key]=true;else if(key==='a')s.finger_active.index=true;else if(key==='b')s.finger_active.thumb=true;else if(['start','select'].includes(key))s.menu_gesture={pose:key,recognized:true};else if(key==='menu_guard')s.recognition.menu_guard=true;return s;}
function feed(m,key,pose,n=5,change={}){let completed=false;for(let i=0;i<n;i++){now+=200;completed=m.sample(key,Object.assign(frame(pose),change),now)||completed;}return completed;}
for(const key of readyChecks){
 const m=readyMatcher();
 if(key==='neutral'){assert.equal(feed(m,key,'left'),false);assert.equal(feed(m,key,'neutral'),true);continue;}
 assert.equal(feed(m,key,key),false,'must start neutral');
 assert.equal(feed(m,key,'neutral',3),false);
 assert.equal(feed(m,key,key,3),false,'short hold');
 assert.equal(feed(m,key,key,2),false,'must release');
 assert.equal(feed(m,key,'neutral',3),true,key);
 const lost=readyMatcher();feed(lost,key,'neutral',3);feed(lost,key,key,5);feed(lost,key,key,1,{detected:false});
 assert.equal(feed(lost,key,'neutral',3),false,'loss cancels pending gesture');
 const out=readyMatcher();feed(out,key,'neutral',3);assert.equal(feed(out,key,key==='left'?'right':'left',6),false);
}
for(const change of [{detected:false},{calibrated:false},{calibrating:true},{calibration_save_error:'disk'},{practice_mode:false},{worker_controller_enabled:true},{vision_state:'error'},{dpad:null}]){
 assert.equal(feed(readyMatcher(),'neutral','neutral',8,change),false);
}
const stale=readyMatcher(),s=base();assert.equal(stale.sample('neutral',s,0),false);assert.equal(stale.sample('neutral',s,1000),false);
const gap=readyMatcher();feed(gap,'left','neutral',3);feed(gap,'left','left',3);now+=1000;assert.equal(feed(gap,'left','left',6),false,'gap requires neutral again');
"""
        r=subprocess.run(['node','-e',script],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_full_guide_workflow_and_failures(self):
        harness = Path(__file__).with_name('ready_browser_harness.js')
        for scenario in ['normal', 'resumed', 'delayed-release', 'calibration-failure', 'switch']:
            with self.subTest(scenario=scenario):
                result = subprocess.run(['node', str(harness)], input=json.dumps(dict(script=READY_SCRIPT, scenario=scenario)), text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_page_and_scripts_parse(self):
        from html.parser import HTMLParser
        class Parser(HTMLParser):
            def __init__(self):super().__init__();self.script=False;self.scripts=[];self.ids=[]
            def handle_starttag(self,tag,attrs):
                if tag=='script':self.script=True
                if 'id' in dict(attrs):self.ids.append(dict(attrs)['id'])
            def handle_endtag(self,tag):
                if tag=='script':self.script=False
            def handle_data(self,data):
                if self.script:self.scripts.append(data)
        p=Parser();p.feed(READY.decode());self.assertEqual(len(p.ids),len(set(p.ids)))
        for script in p.scripts:
            r=subprocess.run(['node','--check'],input=script,text=True,capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr)


class ReadyRouteTests(unittest.TestCase):
    def test_page_route_and_action_safeguard(self):
        import http.client
        from powerglove_vision.control_server import start_control_server
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'device.json';path.write_text(json.dumps(dict(receiver='',profile='off')))
            servers,state=start_control_server(path,'127.0.0.1',0,0)
            try:
                connection=http.client.HTTPConnection('127.0.0.1',servers.servers[0].server_port,timeout=3)
                connection.request('GET','/ready');response=connection.getresponse()
                self.assertEqual(response.status,200);self.assertIn(b'Get ready to play',response.read())
                data=json.dumps(dict(action='begin',session='test-session-123456789'))
                for headers in [{'Content-Type':'application/json'}, {'Content-Type':'application/json','X-VirtualGlove-Action':'ready','Origin':'https://elsewhere.test'}]:
                    connection.request('POST','/api/ready',data,headers);response=connection.getresponse()
                    self.assertEqual(response.status,403);response.read();self.assertFalse(state._ready_marker.exists())
                with patch.object(state,'flush_controller_request',return_value=False):
                    connection.request('POST','/api/ready',data,{'Content-Type':'application/json','X-VirtualGlove-Action':'ready'})
                    response=connection.getresponse();self.assertEqual(response.status,200);self.assertTrue(json.loads(response.read())['guarded'])
                self.assertFalse(state.controller_enabled());connection.close()
            finally:
                servers.shutdown()
