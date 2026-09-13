# Project: VirtualGlove
# File: src/powerglove_vision/ready_web.py
# Purpose: Render and operate the optional Ready-to-Play browser guide.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-13 - Added the optional, resumable Ready-to-Play guide.
# Full history: docs/CHANGELOG.md and Git history.
"""Optional guided preparation; progress and output authorization are separate."""
from .web_common import _page

READY_ENGINE = r"""
const readyChecks=['neutral','left','right','up','down','a','b','start','select','menu_guard'];
function readyNeutral(s){return !Object.values(s.dpad||{}).some(Boolean)&&!Object.values(s.finger_active||{}).some(Boolean)&&!s.menu_gesture?.pose&&!s.recognition?.menu_guard&&!Object.values(s.buttons||{}).some(Boolean);}
function readyMatch(key,s){
 const direction=Object.values(s.dpad||{}).filter(Boolean).length;
 if(key==='neutral')return readyNeutral(s);
 if(['left','right','up','down'].includes(key))return s.dpad?.[key]===true&&direction===1&&!s.menu_gesture?.pose&&!s.recognition?.menu_guard;
 if(key==='menu_guard')return s.recognition?.menu_guard===true;
 if(direction||s.recognition?.menu_guard)return false;
 if(key==='a'||key==='b')return s.finger_active?.[key==='a'?'index':'thumb']===true&&!s.finger_active?.[key==='a'?'thumb':'index']&&!s.menu_gesture?.pose;
 return s.menu_gesture?.pose===key&&s.menu_gesture?.recognized===true;
}
function readyMatcher(){
 let key=null,phase='neutral',since=null,last=-1,lastAt=null;
 function reset(){phase='neutral';since=null;last=-1;lastAt=null;}
 return {reset, sample(next,s,now){
  if(key!==next){key=next;reset();}
  if(!s.dpad||!s.finger_active||typeof s.finger_active.index!=='boolean'||typeof s.finger_active.thumb!=='boolean'||!s.buttons||!s.recognition||!['left','right','up','down'].every(k=>typeof s.dpad[k]==='boolean')||!s.detected||s.calibrated!==true||s.calibrating||s.calibration_save_error||s.practice_mode!==true||s.worker_controller_enabled!==false||s.vision_state!=='active'||typeof s.sequence!=='number'){reset();return false;}
  if(lastAt!==null&&now-lastAt>500){reset();}
  if(s.sequence<=last)return false;
  last=s.sequence;lastAt=now;
  const target=phase==='hold';
  const matching=target?readyMatch(key,s):readyNeutral(s);
  if(!matching){since=null;return false;}
  if(since===null)since=now;
  if(now-since<(target||key==='neutral'?600:350))return false;
  since=null;
  if(key==='neutral'||phase==='release'){reset();return true;}
  phase=target?'release':'hold';return false;
 }, instruction(){return phase==='neutral'?'Open your hand at center first.':phase==='hold'?'Make the gesture and hold it steadily.':'Return to an open hand at center to finish.'}};
}
function readyGameReason(s){
 if(typeof s.worker_status_age_seconds!=='number'||s.worker_status_age_seconds>=3||s.worker_status_age_seconds<0||s.worker_running!==true)return 'Waiting for fresh tracker status.';
 if(s.practice_mode||s.tuning?.active)return 'Waiting for all practice and tuning sessions to end.';
 if(s.game_session_active!==true)return 'Launch a registered game on RetroPie. Unregistered games cannot complete this guide.';
 const profile=s.active_profile||s.profile,core=s.emulator;
 if(!['super_glove_ball','bad_street_brawler',...Array.from({length:14},(_,i)=>'program_'+(i+1)),...'abcdefghi'.split('').map(x=>'program_'+x)].includes(profile))return 'This game has no supported mapping. Review Games in Setup.';
 if(!core||core==='unknown')return 'Waiting for the game’s emulator identity.';
 const expected=profile==='super_glove_ball'&&['lr-nestopia-powerglove','lr-powerglove-dot'].includes(core)?'native':'joystick';
 if(s.input_mode!==expected)return 'The game profile and input mode disagree. Review Games and the emulator selection.';
 if(profile==='program_14')return s.launch_guard_active||s.controller_context_active!==true?'Waiting for the game’s controller context and launch delay.':null;
 if(s.vision_state!=='active'||s.camera_available!==true)return 'Waiting for the game camera to become ready.';
 if(s.calibrated!==true||s.calibrating||s.player?.needs_center||s.calibration_save_error)return 'Centering is required. Return to safe practice.';
 if(s.launch_guard_active||s.controller_context_active!==true)return 'Waiting for the game’s launch delay and controller context.';
 return null;
}
"""

READY_CONTENT = """<h1>Get ready to play</h1><p>This optional guide remembers each player’s essential checks. Live readiness is checked again every visit. Controller output stays stopped until you explicitly finish practice and advance to a game.</p>
<section class=card><p id=ready-status role=status aria-live=polite>Stopping controller output safely…</p>
<ol class=compact-guidance><li>Choose your player</li><li>Check your console and pairing</li><li>Start safe camera practice and center your hand</li><li>Try the essential controls</li><li>End practice and launch a registered game</li></ol>
<label>Player<select id=ready-player disabled></select></label>
<h2 id=ready-title>Choose your player</h2><p id=ready-cue></p>
<img id=ready-example hidden alt="Gesture example" style="width:180px;height:150px;object-fit:contain">
<img class=camera id=ready-camera hidden alt="Safe practice camera">
<p id=ready-progress></p><div class=controls><button id=ready-next disabled>Confirm player</button><button id=ready-center hidden>Center hand</button><button id=ready-back hidden>Return to safe practice</button><button id=ready-exit disabled class=secondary>Leave guide — keep controls stopped</button></div>
<p><a href=/setup>Setup and connection help</a> · <a href=/learn>Full Glove Academy</a></p>
<p class=setup-status-note>Ready means the reported game mapping and authenticated receiver link are available. It does not confirm that the ROM consumed input. Previous check completion is not a substitute for a working camera and saved center today.</p></section>"""

READY_SCRIPT = READY_ENGINE + r"""
(()=>{
const $=id=>document.getElementById(id),session=crypto.randomUUID(),matcher=readyMatcher();
const cues={neutral:['Neutral','Open your hand at the saved center.','find-neutral.png'],left:['Left','Move your hand left.','move-left.png'],right:['Right','Move your hand right.','move-right.png'],up:['Up','Move your hand up.','move-up.png'],down:['Down','Move your hand down.','move-down.png'],a:['A','Curl your index finger.','finger-curl.png'],b:['B','Curl your thumb.','thumb-curl.png'],start:['Start','Make the V sign and hold it.','v-sign.png'],select:['Select','Give a thumbs-up and hold it.','thumbs-up.png'],menu_guard:['Menu Guard','Curl thumb and ring; extend index, middle, and pinky.','menu-guard.png']};
let stage='player',player=null,guarded=false,busy=false,practice=false,alive=true,connected=false,lastConnection=0,lastLease=0,centerStarted=null,centerSeen=false,centerRequired=false,identity=null,status={},connectionSignature=null,connectionRun=0;
function tell(text){$('ready-status').textContent=text;}
async function api(path,data){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),4500);try{const r=await fetch(path,{method:data===undefined?'GET':'POST',cache:'no-store',headers:data===undefined?{}:{'Content-Type':'application/json','X-VirtualGlove-Action':path==='/api/players'?'players':'ready'},body:data===undefined?undefined:JSON.stringify(data),signal:controller.signal});if(!r.ok)throw Error('The Controller could not complete this step. Retry when it reconnects.');return r.status===204?{}:await r.json();}finally{clearTimeout(timer)}}
const who=()=>({player:player.active,generation:player.generation});
const guide=(action,extra={})=>api('/api/ready',{action,session,...extra});
const fresh=()=>typeof status.worker_status_age_seconds==='number'&&status.worker_status_age_seconds>=0&&status.worker_status_age_seconds<3;
const stopped=()=>guarded&&fresh()&&status.worker_controller_enabled===false&&status.controller_enabled===false&&!status.controller_request_pending;
const camera=()=>stopped()&&practice&&status.practice_mode===true&&status.vision_state==='active'&&status.camera_available===true;
const calibratedNow=()=>camera()&&status.calibrated===true&&!status.calibrating&&!player?.needs_center&&!player?.restoring_calibration&&!status.calibration_save_error;
const centered=()=>calibratedNow()&&!centerRequired;
function resetLive(){matcher.reset();centerStarted=null;centerSeen=false;centerRequired=false;connected=false;lastConnection=0;connectionSignature=null;connectionRun++;}
function progress(){return player?.ready_progress||{course:1,completed:[],completed_at:null};}
function draw(){
 $('ready-player').disabled=busy||!stopped()||stage!=='player';$('ready-exit').disabled=busy||!guarded&&stage!=='game'&&stage!=='done';
 const done=progress().completed;$('ready-progress').textContent=`Essential checks saved: ${done.length} of ${readyChecks.length}.`;
 $('ready-center').hidden=!['camera','checks'].includes(stage);$('ready-center').disabled=busy||!camera()||centerStarted!==null;
 $('ready-back').hidden=!['game','done'].includes(stage);$('ready-back').disabled=busy;
 const key=readyChecks.find(k=>!done.includes(k));
 $('ready-example').hidden=stage!=='checks'||!key;
 if(stage==='checks'&&key){$('ready-example').src='/help-assets/gestures/actions/'+cues[key][2];$('ready-title').textContent=cues[key][0];$('ready-cue').textContent=cues[key][1]+' '+matcher.instruction();}
 else{$('ready-title').textContent=({player:'Choose your player',connection:'Console and pairing',camera:'Safe camera practice',checks:'Essential checks complete',release:'Ending practice',game:'Launch a registered game',done:'Ready to play'})[stage];$('ready-cue').textContent=({player:'Confirm the player who will use this Controller.',connection:'We check the saved address, console service, and authenticated pairing. Use Setup to save or pair if needed.',camera:'Show one open hand. Center it if required, or set a fresh center if the camera or your position moved.',checks:'Your checks are saved. The next action ends practice and allows controls for a registered game.',release:'Waiting for practice to stop completely. Other Academy or tuning tabs may keep practice active.',game:'Launch a game registered in Games on RetroPie. Controls can start only after practice ends and the reported mapping is consistent.',done:'The camera, saved center, registered-game mapping, and authenticated receiver link are available. Game-side input receipt is not verified.'})[stage];}
 $('ready-next').textContent=({player:'Confirm player',connection:'Start safe practice',camera:'Continue to essential checks',checks:key?'Follow the gesture above':'End practice and enable registered-game controls',release:'Finish ending practice',game:'Check game and enable controls',done:'Keep playing'})[stage];
 $('ready-next').hidden=stage==='done';
 $('ready-next').disabled=busy||!player||({player:!stopped(),connection:!stopped()||!connected,camera:!centered()||centerStarted!==null,checks:!!key||!centered(),release:false,game:!!readyGameReason(status)||!connected,done:true})[stage];
 const view=camera();$('ready-camera').hidden=!view;if(view){if(!$('ready-camera').getAttribute('src'))$('ready-camera').src='/stream';}else $('ready-camera').removeAttribute('src');
}
async function connect(){
 const revision=++connectionRun;connected=false;lastConnection=performance.now();
 try{const c=await api('/api/config');if(!c.receiver||c.connection_configured!==true){tell('Save your console and pair this Controller in Setup, then return here.');return;}
 const signature=JSON.stringify([c.receiver,c.port]);
 if(signature!==connectionSignature){await api('/api/test-connection',{receiver:c.receiver});connectionSignature=signature;}
 const health=await api('/api/connection-status');
 if(revision!==connectionRun)return;
 connected=typeof health.checked_seconds_ago==='number'&&health.checked_seconds_ago>=0&&health.checked_seconds_ago<30&&health.console_service===true&&health.console_authenticated===true;
 tell(connected?'Saved address, console service, and authenticated pairing checked.':'Waiting for a recent authenticated console check. Use Connection Doctor in Setup if this persists.');
 }catch(e){if(revision===connectionRun)tell('Could not verify the console connection. Check Setup and retry.');}
 lastConnection=performance.now();
}
async function saveCheck(key,complete=false){
 const before=identity,p=progress(),completed=key?[...new Set([...p.completed,key])]:p.completed;
 const result=await api('/api/players',{action:'ready_progress',...who(),progress:{course:1,completed,completed_at:complete?new Date().toISOString().slice(0,19)+'Z':p.completed_at}});
 if(before!==identity)throw Error('Player changed. Confirm the active player again.');player=result;matcher.reset();
}
async function releasePractice(){const result=await guide('release',{confirmed:true,...who()});if(!result.released){tell(result.message);return;}guarded=false;stage='game';tell('Practice has ended. Launch a registered game on RetroPie.');lastConnection=0;}
async function work(fn){if(busy)return;busy=true;draw();try{await fn();}catch(e){matcher.reset();tell(e.message);}finally{busy=false;draw();}}
$('ready-player').onchange=()=>work(async()=>{if(!stopped())throw Error('Wait for output to stop first.');player=await api('/api/players',{action:'select',...who(),id:$('ready-player').value});identity=null;resetLive();stage='player';});
$('ready-center').onclick=()=>work(async()=>{if(!camera())throw Error('Wait for safe practice and the camera.');matcher.reset();centerRequired=true;centerStarted=performance.now();centerSeen=false;try{await api('/calibrate',{});}catch(e){centerStarted=null;throw e;}tell('Centering: hold one open hand still.');});
$('ready-next').onclick=()=>work(async()=>{
 if(stage==='player'){if(!stopped())throw Error('Waiting for output to stop.');stage='connection';await connect();}
 else if(stage==='connection'){if(!stopped()||!connected)throw Error('Recheck connection first.');const result=await api('/api/practice',{session,enabled:true});practice=result.practice_mode===true;lastLease=performance.now();stage='camera';tell('Starting safe practice. Controller output remains stopped.');}
 else if(stage==='camera'){if(!centered()||centerStarted!==null)throw Error('Finish centering first.');stage='checks';matcher.reset();}
 else if(stage==='checks'){
  if(!readyChecks.every(k=>progress().completed.includes(k))||!centered())throw Error('Finish essential checks and centering first.');
  practice=false;matcher.reset();stage='release';await releasePractice();
 }else if(stage==='release'){await releasePractice();
 }else if(stage==='game'){
  if(!connected||readyGameReason(status))throw Error(readyGameReason(status)||'Recheck authenticated pairing.');
  await guide('arm',who());tell('Waiting for the authenticated receiver link…');
 }
});
$('ready-back').onclick=()=>work(async()=>{await guide('begin');guarded=true;practice=false;stage='player';resetLive();tell('Output is stopping. Confirm your player again.');});
$('ready-exit').onclick=()=>work(async()=>{
 if(!guarded){await guide('begin');guarded=true;}
 practice=false;const result=await guide('cancel',{confirmed:true});if(!result.released){tell(result.message);return;}
 alive=false;location.href='/dashboard';
});
async function poll(){
 if(!alive)return;
 if(document.hidden){matcher.reset();setTimeout(poll,300);return;}
 if(busy){setTimeout(poll,150);return;}
 busy=true;
 try{
  const lease=await guide('status');guarded=lease.guarded;
  if(!guarded&&!lease.game_stage){practice=false;stage='player';resetLive();tell('Another guide visit took over. Reload this page to begin safely.');draw();return;}
  const next=await api('/api/players',{action:'read'}),id=next.active+':'+next.generation;
  if(identity!==id){const changed=identity!==null;player=next;identity=id;resetLive();if(changed){await guide('begin');guarded=true;practice=false;stage='player';tell('Player changed. Confirm the active player again.');}const selected=$('ready-player');selected.replaceChildren(...next.players.map(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.name;return o}));selected.value=next.active;}else player=next;
  status=await api('/status');window.updateEasterEgg?.(status);
  if(practice&&performance.now()-lastLease>1500){const result=await api('/api/practice',{session,enabled:true});practice=result.practice_mode===true;lastLease=performance.now();}
  if(!fresh()||!status.detected)matcher.reset();
  if(centerStarted!==null){if(status.calibrating)centerSeen=true;if(centerSeen&&calibratedNow()){centerStarted=null;centerSeen=false;centerRequired=false;tell('Center saved.');}else if(status.calibration_save_error||performance.now()-centerStarted>20000){centerStarted=null;centerSeen=false;stage='camera';tell('Centering did not finish. Hold an open hand and select Center hand to retry.');}}
  if(['connection','game','done'].includes(stage)&&performance.now()-lastConnection>2000)await connect();
  if(stage==='checks'){
   if(!centered()){matcher.reset();stage='camera';tell('Tracking or calibration needs attention. Restore the camera and center before continuing.');}
   else {const key=readyChecks.find(k=>!progress().completed.includes(k));if(key&&matcher.sample(key,status,performance.now()))await saveCheck(key);}
  }
  if(['game','done'].includes(stage)){
   const reason=readyGameReason(status),linked=status.receiver_available===true&&status.controller_enabled===true&&status.worker_controller_enabled===true&&!status.controller_request_pending;
   if(!reason&&connected&&linked){if(stage!=='done'){await saveCheck(null,true);stage='done';}tell('Ready to play. The ROM’s input consumption is not verified.');}
   else{stage='game';tell(reason||(!connected?'Waiting for authenticated console pairing.':'Waiting for the receiver link. Select Check game and enable controls when the game is ready.'));}
  }
 }catch(e){matcher.reset();connected=false;tell('Connection interrupted. Progress already saved is kept. Reconnecting safely…');}
 finally{busy=false;draw();if(alive)setTimeout(poll,150);}
}
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
window.addEventListener('pagehide',()=>{alive=false;practice=false;fetch('/api/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session,enabled:false}),keepalive:true}).catch(()=>{});});
async function begin(){busy=true;draw();try{await guide('begin');guarded=true;tell('Output stopped. Waiting for fresh player and tracker status.');}catch(e){tell('Could not secure the output pause. Reload this guide when the Controller reconnects.');return;}finally{busy=false;draw();}poll();}
begin();
})();
"""
READY = _page('Get ready to play', READY_CONTENT, READY_SCRIPT)
