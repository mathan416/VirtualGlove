# Project: VirtualGlove
# File: src/virtualglove/player_web.py
# Purpose: Provide player selection, persistent Academy progress, and hand-setting backups.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Add complete hand-setup backups and explicit calibration restoration.
#   2026-09-06 - Add player controls and bounded backup import/export.

"""Browser controls share the Academy's session state without exposing credentials."""

PLAYER_CONTENT = """<style>.player-card a{color:var(--cyan)}.player-card .check{display:flex;align-items:center;gap:12px;min-height:44px}.player-card .check input{flex:0 0 20px;width:20px;height:20px;margin:0}</style><section class="card player-card" aria-labelledby=player-heading id=players>
<h2 id=player-heading>Players</h2><div class=player-row><label>Active player<select id=player-select disabled></select></label></div>
<p id=player-notice role=status aria-live=polite>Loading saved progress…</p>
<details><summary>Players and hand-setup backups</summary>
<label>Player name<input id=player-name maxlength=32 autocomplete=off placeholder="Player name"></label>
<div class=controls><button id=player-create type=button>Add player</button><button id=player-rename type=button>Rename current</button><button id=player-delete type=button>Delete current</button></div>
<p>Each player keeps:</p><ul><li>Name and Academy progress</li><li>Gesture sensitivity and joystick dead zone</li><li>Saved center and movement reach</li></ul>
<p>Hand-setup backups include the player name, recognition sensitivity, center and reach, and software identity. Restore into the player you want to update; reuse calibration only when the camera and playing positions still match.</p>
<div class=controls><button id=player-export type=button>Back up hand setup</button><label class=button for=player-import>Restore hand setup</label><input id=player-import type=file accept=".json,application/json" hidden></div><div id=restore-review hidden><p id=restore-description></p><label class=check><input id=restore-effective type=checkbox> Restore the complete saved sensitivity, including the defaults used when this backup was made.</label><label class=check><input id=restore-reuse type=checkbox> My camera position and playing position match this backup; reuse its calibration.</label><p>Leave calibration reuse unchecked to set a fresh center. Leave complete sensitivity unchecked to restore only personal adjustments with the installed defaults. The current player's Academy progress is kept. Controller output stays paused until you explicitly start it.</p><div class=controls><button id=restore-confirm type=button>Restore this setup</button><button id=restore-cancel type=button>Cancel</button></div></div></details></section>"""

PLAYER_SELECTOR_CONTENT = """<section class=card aria-label="Active player"><label>Active player<select id=player-select disabled></select></label><p id=player-notice role=status aria-live=polite></p><a class=button href=/setup#players>Manage players in Setup</a></section>"""

PLAYER_SCRIPT = r"""(()=>{
let context=null,busy=false,loading=false,pending=null,saving=null,listKey='',importBackup=null,importIdentity=null;
const el=id=>document.getElementById(id);
const academy=!!el('practice-lessons');
const notice=text=>{el('player-notice').textContent=text};
async function api(action,extra={}){const r=await fetch('/api/players',{method:'POST',headers:{'Content-Type':'application/json','X-VirtualGlove-Action':'players'},body:JSON.stringify({action,player:context?.active,generation:context?.generation,...extra}),keepalive:action==='progress'});const s=await r.json();if(!r.ok)throw Error(s.error||'Player request failed.');return s}
function apply(s,restore=false){if(!s||!Array.isArray(s.players)||!s.progress)throw Error('Player settings are unavailable.');const changed=!context||s.active!==context.active||s.generation!==context.generation;context=s;const key=JSON.stringify(s.players);if(key!==listKey){el('player-select').replaceChildren(...s.players.map(p=>new Option(p.name,p.id)));listKey=key;el('player-select').value=s.active}if(changed||restore){el('player-select').value=s.active;const name=el('player-name'),active=s.players.find(p=>p.id===s.active);if(name)name.value=active?.name||''}el('player-select').disabled=busy;if(academy){if(changed||restore){beginTransition();completed=new Set(s.progress.completed);index=s.progress.lesson;trainingComplete=completed.size===lessons.length;pending=null;draw()}else{for(const n of s.progress.completed)completed.add(n);if(completed.size===lessons.length&&!trainingComplete){beginTransition();trainingComplete=true;draw()}}playerReady=!s.error;}notice(s.error||(s.restoring_calibration?'Applying restored calibration; controller output is paused.':s.needs_center?'Player ready. Set your center before starting controller output.':academy&&trainingComplete?'Glove Master saved. Your award will be here when you return.':academy?'Progress saves automatically on this Controller.':'Player settings loaded.'));}
async function load(){if(loading||busy||saving)return;loading=true;try{apply(await api('read'))}catch(e){if(academy)playerReady=false;notice(e.message+' Retrying…')}finally{loading=false}}
function save(){if(!context||!playerReady||busy)return;pending={course:1,completed:[...completed],lesson:index};flush()}
function flush(){if(saving||!pending)return saving;const value=pending;pending=null;saving=api('progress',{progress:value}).then(s=>{if(context&&s.active===context.active&&s.generation===context.generation)context=s}).catch(e=>{if(academy)playerReady=false;notice('Progress could not be saved. '+e.message)}).finally(()=>{saving=null;if(pending&&playerReady)flush()});return saving}
if(academy)window.saveAcademyProgress=save;
window.playerIdentity=()=>context?{player:context.active,generation:context.generation}:{};
async function command(action,extra={}){if(busy)return;busy=true;el('player-select').disabled=true;if(academy)playerReady=false;try{while(saving)await saving;pending=null;apply(await api(action,extra),true);return true}catch(e){notice(e.message);if(academy)playerReady=!!context&&!context.error;return false}finally{busy=false;el('player-select').disabled=false;if(context)el('player-select').value=context.active}}
if(academy)window.resetAcademyProgress=()=>command('reset_progress');
el('player-select').onchange=()=>command('select',{id:el('player-select').value});
if(el('player-create'))el('player-create').onclick=()=>command('create',{name:el('player-name').value});
if(el('player-rename'))el('player-rename').onclick=()=>command('rename',{name:el('player-name').value});
if(el('player-delete'))el('player-delete').onclick=()=>{if(confirm('Delete this player, their sensitivity settings, and Academy progress?'))command('delete')};
if(el('player-export'))el('player-export').onclick=async()=>{try{const s=await api('export'),raw=String(s.backup?.name||context?.players?.find(p=>p.id===context.active)?.name||'player'),slug=raw.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,40)||'player';const blob=new Blob([JSON.stringify(s.backup,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=slug+'-virtualglove-hand-setup.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){notice(e.message)}};
if(el('player-import'))el('player-import').onchange=async()=>{const file=el('player-import').files?.[0];if(!file)return;try{if(file.size>8192)throw Error('Choose a hand-setup JSON file smaller than 8 KB.');const backup=JSON.parse(await file.text()),current=backup?.format==='virtualglove-hand-setup'&&backup?.version===4;if(!backup||typeof backup!=='object'||!current)throw Error('Choose a current VirtualGlove hand-setup backup. Older PowerGlove backups are not supported.');importBackup=backup;importIdentity={player:context?.active,generation:context?.generation};const hasCalibration=backup.calibration!=null;el('restore-description').textContent='Restore '+(typeof backup.name==='string'?backup.name:'this backup')+' to the current player: replace sensitivity, center-box size and player name. '+(hasCalibration?'A saved calibration is available.':'No saved calibration is included; set a fresh center.');el('restore-description').textContent+=' Software: '+(backup.source?.version||'not recorded')+' · '+(backup.source?.commit||'commit not recorded')+'.';el('restore-effective').checked=false;el('restore-effective').disabled=!backup.effective_thresholds;el('restore-reuse').checked=false;el('restore-reuse').disabled=!hasCalibration;el('restore-review').hidden=false}catch(e){notice(e.message)}finally{el('player-import').value=''}};
if(el('restore-confirm'))el('restore-confirm').onclick=async()=>{if(!importBackup)return;const ok=await command('restore',{backup:importBackup,...importIdentity,reuse_calibration:el('restore-reuse').checked,use_effective_thresholds:el('restore-effective').checked});if(ok){importBackup=null;el('restore-review').hidden=true}};
if(el('restore-cancel'))el('restore-cancel').onclick=()=>{importBackup=null;el('restore-review').hidden=true};
window.addEventListener('pagehide',()=>{if(pending&&!saving)flush()});
load();setInterval(load,2000);
})();"""
