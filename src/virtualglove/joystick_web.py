# Project: VirtualGlove
# File: src/virtualglove/joystick_web.py
# Purpose: Render per-player digital joystick dead-zone controls and status.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Simplified camera-test guidance and hid redundant direction text.
#   2026-09-12 - Preview unsaved grid bounds and directions immediately during practice.
#   2026-09-12 - Made 60% the standard centre-box size for new players.
#   2026-09-06 - Added Setup dead-zone controls with per-player persistence.
# Full history: docs/CHANGELOG.md and Git history.
"""Per-player Setup controls for the nine-region digital joystick layout."""

JOYSTICK_CONTENT = """<section class=card id=joystick-settings style="margin-top:14px" aria-labelledby=joystick-title>
<h2 id=joystick-title>Joystick dead zone</h2>
<p id=joystick-player>Loading player…</p>
<form id=joystick-form><label for=joystick-size>Center box size: Small ↔ Large</label>
<input id=joystick-size type=range min=0.10 max=1 step=0.01 value=0.60 disabled aria-describedby=joystick-value>
<p id=joystick-value></p><div class=controls><button id=joystick-save type=submit disabled>Save dead zone</button><button id=joystick-default type=button disabled>Use standard size</button><button id=joystick-camera-toggle type=button aria-pressed=false>Turn on camera</button><button id=joystick-center type=button disabled>Center hand</button></div></form>
<style>#joystick-camera-stage{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:14px;margin-top:14px}#joystick-camera-stage .camera{display:block;width:100%;height:auto;aspect-ratio:auto;border:0;border-radius:0;margin:0}#joystick-grid{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:hidden}#joystick-grid line{stroke:rgba(255,255,255,.55);stroke-width:1;vector-effect:non-scaling-stroke}#joystick-region{fill:rgba(54,219,232,.16)}</style>
<div id=joystick-camera-stage hidden><img class=camera id=joystick-camera hidden alt="Mirrored camera view for the dead-zone test">
<svg id=joystick-grid hidden aria-hidden=true viewBox="0 0 1 1" preserveAspectRatio=none><rect id="joystick-region" hidden /><line id="joystick-grid-left" /><line id="joystick-grid-right" /><line id="joystick-grid-top" /><line id="joystick-grid-bottom" /></svg></div>
<div id=joystick-directions class=controls hidden aria-hidden=true><span class=bit data-direction=left>Left: off</span><span class=bit data-direction=up>Up: off</span><span class=bit data-direction=down>Down: off</span><span class=bit data-direction=right>Right: off</span></div>
<p id=joystick-live role=status aria-live=polite></p><p id=joystick-center-status role=status aria-live=polite></p><p id=joystick-notice role=status aria-live=polite></p>
<div id=joystick-camera-help hidden><p>The live box is anchored to the hand center saved with <strong>Center hand</strong>. The chosen percentage sets its width and height, but the box is never smaller than 1.5 times your calibrated hand size. Near an edge, the whole box moves inward so it stays full-size. Inside the box stops movement; moving beyond an edge or corner selects a direction. Native Super Glove Ball X/Y reach is separate.</p>
<p>Slider changes preview immediately. Select <strong>Save dead zone</strong> to use them in gameplay.</p></div></section>"""

JOYSTICK_SCRIPT = r"""(()=>{
const el=id=>document.getElementById(id), directions=['left','right','up','down'];
let player=null, dirty=false, busy=false, polling=false;
const notice=text=>el('joystick-notice').textContent=text;
async function api(payload){return request('/api/players',{method:'POST',headers:{'Content-Type':'application/json','X-VirtualGlove-Action':'players'},body:JSON.stringify(payload)});}
function describe(){const v=Number(el('joystick-size').value),minimum=player?.joystick?.hand_size_minimum,effective=typeof minimum==='number'&&Number.isFinite(minimum)?Math.max(v,minimum):(dirty?v:player?.joystick?.effective_deadzone);let text=`Chosen size: ${Math.round(v*100)}% of camera frame width and height.`;
 if(typeof effective==='number'&&Number.isFinite(effective)&&effective>v+1e-9)text+=` Effective ${dirty?'preview':'saved'} size: ${Math.round(effective*100)}% (minimum 1.5× your calibrated hand size).`;
 if(dirty)text+=' Unsaved preview — Save dead zone to apply this size to gameplay.';
 el('joystick-value').textContent=text}
function controls(){el('joystick-size').disabled=busy||!player;el('joystick-save').disabled=busy||!player||!dirty;el('joystick-default').disabled=busy||!player;cameraControls()}
function apply(s){if(!s.joystick||!s.players)throw Error('Joystick settings unavailable. Reload after updating the Controller.');
 const changed=player&&(player.active!==s.active||player.generation!==s.generation);
 const samePlayer=player&&player.active===s.active;
 if(changed&&!(centering&&samePlayer)){if(dirty)notice('Player settings changed. Unsaved dead-zone edits were discarded.');dirty=false;hideCamera()}
 if(changed&&!samePlayer)cancelCenter('Centering stopped because the active player changed.');
 player=s;el('joystick-player').textContent='Player: '+(s.players.find(p=>p.id===s.active)?.name||s.active);
 if(!dirty){const value=s.joystick.deadzone;
 el('joystick-size').value=Math.max(.10,Math.min(1,value));describe(s);
 }controls();}
el('joystick-size').oninput=()=>{dirty=true;redraw();controls()};
el('joystick-default').onclick=()=>{el('joystick-size').value=.60;dirty=true;redraw();controls();notice('Standard size selected for preview. Save to apply to gameplay.')};
el('joystick-form').onsubmit=async e=>{e.preventDefault();if(busy||!player||!dirty)return;busy=true;controls();notice('Saving…');
 const identity={player:player.active,generation:player.generation};
 try{const s=await api({action:'joystick_deadzone',...identity,value:Number(el('joystick-size').value)});dirty=false;hideCamera();apply(s);if(cameraWanted)el('joystick-live').textContent='Dead zone saved. Waiting for updated camera test feedback…';notice('Dead zone saved for this player. Center and reach are unchanged.')}
 catch(e){notice(e.message)}finally{busy=false;controls()}};
let cameraWanted=false, cameraBusy=false, leaseBusy=false, session=null, leaseAt=null, viewReady=false, alive=true, retryAt=0, cameraRevision=0, imageLoaded=false, gridStatus=null;
let centering=false, centerSeen=false, centerStarted=0, centerDoneUntil=0;
const releases=new Set();
const clock=()=>performance.now();
function ownsPractice(){return cameraWanted&&leaseAt!==null&&clock()-leaseAt<4500&&gridStatus?.practice_mode===true&&gridStatus?.vision_state==='active'&&viewReady&&imageLoaded;}
function cameraControls(){const toggle=el('joystick-camera-toggle'),center=el('joystick-center');toggle.textContent=cameraWanted?'Turn off camera':'Turn on camera';toggle.disabled=cameraBusy||centering;toggle.setAttribute('aria-pressed',String(cameraWanted));el('joystick-camera-help').hidden=!cameraWanted;center.disabled=busy||centering||!ownsPractice();center.classList.toggle('danger',centering);center.setAttribute('aria-busy',String(centering));center.textContent=centering?'Centering…':clock()<centerDoneUntil?'Center saved ✓':'Center hand';}
function cancelCenter(message=''){centering=false;centerSeen=false;centerStarted=0;if(message)el('joystick-center-status').textContent=message;cameraControls();}
function updateCenter(s){if(!centering){cameraControls();return;}if(s.calibrating)centerSeen=true;
 if(s.calibration_save_error){cancelCenter('The hand center could not be saved. Try again.');return;}
 if(centerSeen&&s.calibrated===true&&!s.calibrating&&!s.player?.needs_center){centering=false;centerSeen=false;centerStarted=0;centerDoneUntil=clock()+1800;el('joystick-center-status').textContent='Hand center saved. The grid now uses this position and hand size.';cameraControls();return;}
 if(clock()-centerStarted>20000){cancelCenter('Centering did not finish. Show one relaxed open hand and try again.');return;}
 el('joystick-center-status').textContent=s.calibrating?'Keep one relaxed open hand in your normal playing position.':'Waiting for centering to begin…';cameraControls();}
function directionsOff(){for(const d of directions){const node=el('joystick-directions').querySelector(`[data-direction=${d}]`);node.classList.toggle('on',false);node.textContent=d[0].toUpperCase()+d.slice(1)+': off';}}
function hideCamera(){viewReady=false;imageLoaded=false;gridStatus=null;clearGrid();el('joystick-camera-stage').hidden=true;el('joystick-camera').removeAttribute('src');el('joystick-camera').hidden=true;directionsOff();cameraControls();}
async function request(path,options={}){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),3000);try{const r=await fetch(path,{...options,signal:controller.signal});const data=await r.json();if(!r.ok)throw Error(data.error||'Request failed.');return data;}finally{clearTimeout(timer)}}
async function practiceLease(id,enabled){return request('/api/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session:id,enabled}),keepalive:!enabled});}
async function release(id){if(!id)return;releases.add(id);try{await practiceLease(id,false);releases.delete(id);}catch(e){if(alive&&!cameraWanted)el('joystick-live').textContent='Camera shutdown is still being confirmed; retrying safely.';}}
async function renew(){if(leaseBusy||!cameraWanted||!alive)return;leaseBusy=true;const id=session,revision=cameraRevision,started=clock();
 try{const result=await practiceLease(id,true);if(!alive||revision!==cameraRevision){await release(id);return;}
 if(result.session_active!==true||result.practice_mode!==true){cameraWanted=false;cameraRevision++;leaseAt=null;hideCamera();cameraControls();await release(id);el('joystick-live').textContent='Camera test stopped: this practice lease was not accepted. Turn on the camera to retry after updating the Controller or closing the conflicting session.';return;}
 leaseAt=started;
 }catch(e){if(alive&&revision===cameraRevision){leaseAt=null;hideCamera();el('joystick-live').textContent='Camera test connection interrupted. Retrying safely…';}}
 finally{leaseBusy=false;}
}
el('joystick-camera-toggle').onclick=async()=>{if(cameraBusy)return;cameraBusy=true;cameraRevision++;leaseAt=null;hideCamera();
 if(cameraWanted){const old=session;cameraWanted=false;cameraControls();el('joystick-live').textContent='';await release(old);}
 else{session=globalThis.crypto?.randomUUID?.()||`joystick-${Date.now()}-${Math.random().toString(36).slice(2)}`;cameraWanted=true;retryAt=0;cameraControls();el('joystick-live').textContent='Starting safe camera practice…';await renew();}
 cameraBusy=false;cameraControls();if(alive)poll();
};
el('joystick-center').onclick=async()=>{if(centering||!ownsPractice())return;centering=true;centerSeen=false;centerStarted=clock();centerDoneUntil=0;clearGrid();directionsOff();cameraControls();el('joystick-center-status').textContent='Keep one relaxed open hand in your normal playing position.';
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),3000);
 try{const response=await fetch('/calibrate',{method:'POST',signal:controller.signal});if(!response.ok)throw Error('Centering request failed.');}
 catch(error){cancelCenter(error.name==='AbortError'?'Centering request timed out. Try again.':error.message||'Centering could not start. Try again.');}
 finally{clearTimeout(timer)}
};
function clearGrid(){el('joystick-grid').setAttribute('hidden','');el('joystick-region').setAttribute('hidden','');el('joystick-region').removeAttribute('data-region');}
// One geometry and direction calculation drives both the overlay and direction pills.
function geometry(s){
 const grid=s?.joystick_grid,anchor=grid?.anchor,savedCenter=grid?.center;
 if(!s||!alive||!viewReady||!cameraWanted||leaseAt===null||clock()-leaseAt>=4500||s.practice_mode!==true||s.vision_state!=='active'||s.calibrated!==true||s.calibrating||s.calibration_save_error||s.player?.needs_center)return null;
 if(s.player?.active&&player&&(s.player.active!==player.active||s.player.generation!==player.generation))return null;
 const values=[anchor?.x,anchor?.y,savedCenter?.x,savedCenter?.y,grid?.half_size,grid?.minimum_size];
 if(!values.every(v=>typeof v==='number'&&Number.isFinite(v))||anchor.x<0||anchor.x>1||anchor.y<0||anchor.y>1||grid.minimum_size<=0||grid.minimum_size>1)return null;
 const chosen=Number(el('joystick-size').value),effective=dirty?Math.max(chosen,grid.minimum_size):grid.half_size*2,h=effective/2;
 if(!Number.isFinite(chosen)||chosen<.10||chosen>1||h<.05||h>.5)return null;
 const clamp=(v,low,high)=>Math.max(low,Math.min(high,v));
 const expectedSaved={x:clamp(anchor.x,grid.half_size,1-grid.half_size),y:clamp(anchor.y,grid.half_size,1-grid.half_size)};
 if(Math.abs(savedCenter.x-expectedSaved.x)>1e-9||Math.abs(savedCenter.y-expectedSaved.y)>1e-9)return null;
 const c=dirty?{x:clamp(anchor.x,h,1-h),y:clamp(anchor.y,h,1-h)}:savedCenter;
 if(c.x<h||c.x>1-h||c.y<h||c.y>1-h)return null;
 // A settings save can arrive before the worker's updated geometry. Wait for it.
 if(!dirty&&player?.joystick&&Math.abs(h-player.joystick.effective_deadzone/2)>1e-9)return null;
 return {c,h,effective};
}
function directionState(s,g){
 const palm=s?.palm_position;
 if(!g||s.detected!==true||!palm||![palm.x,palm.y].every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1)||s.recognition?.menu_guard||s.buttons?.menu_guard||s.menu_gesture?.pose||s.buttons?.start||s.buttons?.select)return null;
 const left=g.c.x-g.h,right=g.c.x+g.h,top=g.c.y-g.h,bottom=g.c.y+g.h;
 if(dirty)return {left:palm.x<left,right:palm.x>right,up:palm.y<top,down:palm.y>bottom};
 const d=s.dpad;
 if(!d||!directions.every(k=>typeof d[k]==='boolean')||d.left&&d.right||d.up&&d.down)return null;
 if(!directions.some(k=>d[k])&&(palm.x<left||palm.x>right||palm.y<top||palm.y>bottom))return null;
 return d;
}
function drawGrid(g,d){
 clearGrid();if(!imageLoaded||!g)return;
 const {c,h}=g,clip=v=>Math.max(0,Math.min(1,v)),xs=[0,clip(c.x-h),clip(c.x+h),1],ys=[0,clip(c.y-h),clip(c.y+h),1];
 for(const [id,x1,y1,x2,y2] of [['left',xs[1],0,xs[1],1],['right',xs[2],0,xs[2],1],['top',0,ys[1],1,ys[1]],['bottom',0,ys[2],1,ys[2]]]){const line=el('joystick-grid-'+id);for(const [key,value] of Object.entries({x1,y1,x2,y2}))line.setAttribute(key,String(value));}
 el('joystick-grid').removeAttribute('hidden');if(!d)return;
 const col=d.left?0:d.right?2:1,row=d.up?0:d.down?2:1;
 const x=xs[col],y=ys[row],width=xs[col+1]-x,height=ys[row+1]-y;if(width<=0||height<=0)return;
 const region=el('joystick-region');for(const [key,value] of Object.entries({x,y,width,height}))region.setAttribute(key,String(value));region.setAttribute('data-region',String(row*3+col));region.removeAttribute('hidden');
}
function redraw(){
 const g=geometry(gridStatus),d=directionState(gridStatus,g);
 for(const key of directions){const node=el('joystick-directions').querySelector(`[data-direction=${key}]`),on=d?.[key]===true;node.classList.toggle('on',on);node.textContent=key[0].toUpperCase()+key.slice(1)+(on?': pressed':': off');}
 drawGrid(g,d);describe(player);
 if(viewReady)el('joystick-live').textContent=d?(dirty?'Camera test active. Unsaved preview — Save dead zone to apply to gameplay.':'Camera test active. Directions use your saved dead-zone settings.'):'Camera test active. Waiting for a visible, calibrated hand and current practice feedback.';
}
function feedback(s){
 window.updateEasterEgg?.(s);
 const own=cameraWanted&&leaseAt!==null&&clock()-leaseAt<4500;
 const ready=own&&s.practice_mode===true&&s.vision_state==='active';
 gridStatus=s;updateCenter(s);
 if(!ready){hideCamera();if(!cameraWanted)return;el('joystick-live').textContent=!own?'Waiting for this panel’s practice lease…':s.vision_state==='error'?'Camera unavailable. Check its connection; the test will retry.':'Starting safe camera practice…';return;}
 if(clock()<retryAt){hideCamera();return;}
 const image=el('joystick-camera');viewReady=true;image.hidden=false;el('joystick-camera-stage').hidden=false;gridStatus=s;cameraControls();
 if(!image.getAttribute('src'))image.src='/stream?t='+Date.now();
 redraw();
}
el('joystick-camera').onload=()=>{if(!viewReady||!cameraWanted)return;imageLoaded=el('joystick-camera').naturalWidth>0&&el('joystick-camera').naturalHeight>0;redraw();cameraControls();};
el('joystick-camera').onerror=()=>{if(!cameraWanted||!viewReady)return;retryAt=clock()+1500;hideCamera();el('joystick-live').textContent='Camera image unavailable. Reconnecting…';};
async function poll(){if(polling||busy||document.hidden||!alive)return;polling=true;const revision=cameraRevision;try{const settings=await api({action:'read'});if(busy||!alive)return;apply(settings);if(!cameraWanted)return;
 const s=await request('/status',{cache:'no-store'});if(alive&&revision===cameraRevision)feedback(s);
 }catch(e){if(alive&&revision===cameraRevision){hideCamera();if(cameraWanted)el('joystick-live').textContent='Camera test feedback unavailable. Retrying…';notice(e.message);}}
 finally{polling=false;if(centering&&clock()-centerStarted>20000)cancelCenter('Centering did not finish. Show one relaxed open hand and try again.');}}
async function heartbeat(){if(!alive)return;await renew();for(const id of [...releases])await release(id);if(!cameraWanted&&releases.size===0)el('joystick-live').textContent='';}
window.addEventListener('pagehide',()=>{alive=false;cameraWanted=false;cameraRevision++;leaseAt=null;centering=false;hideCamera();cameraControls();el('joystick-live').textContent='';
 for(const id of new Set([session,...releases]))if(id)fetch('/api/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session:id,enabled:false}),keepalive:true}).catch(()=>{});
});
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
describe();controls();cameraControls();hideCamera();poll();setInterval(poll,500);setInterval(heartbeat,2000);
})();"""
