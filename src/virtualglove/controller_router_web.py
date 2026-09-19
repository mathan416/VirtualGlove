# Project: VirtualGlove
# File: src/virtualglove/controller_router_web.py
# Purpose: Setup UI for authenticated Player 1-4 controller routing.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Reloaded assignments after Setup restores the saved platform.
#   2026-09-19 - Added authenticated Controller Router Setup card.
# Full history: docs/CHANGELOG.md and Git history.

"""Controller Router card kept separate so its security boundary is reviewable."""

ROUTER_CONTENT = r"""
<section id=controller-router class=card style="margin-bottom:14px" aria-labelledby=router-title>
<h2 id=router-title>Controller Router</h2>
<p>Choose which configured joypads share each FCEUmm player. Your original controllers keep working in the console menus; the merged players become active only during compatible NES gameplay.</p>
<p id=router-prerequisite class=setup-status-note>Loading console controller assignments…</p>
<div id=router-panel hidden>
<div class=table-scroll><table><thead><tr><th>Configured controller</th><th>Connection</th><th>Assignment</th></tr></thead><tbody id=router-sources></tbody></table></div>
<label>VirtualGlove player<select id=router-virtual><option value="">Unassigned</option><option value=1>Player 1</option><option value=2>Player 2</option><option value=3>Player 3</option><option value=4>Player 4</option></select></label>
<p class=setup-status-note>Only one player can receive this VirtualGlove. Player 1 alone carries the physical controller’s console hotkey; VirtualGlove Select never becomes a hotkey.</p>
<div class=controls><button type=button id=router-save>Save assignments</button><button type=button class=secondary id=router-check>Check controllers</button><button type=button class=secondary id=router-rollback hidden>Restore previous assignments</button></div>
<p id=router-notice role=status aria-live=polite></p>
</div></section>
"""

ROUTER_SCRIPT = r"""(()=>{
const byId=id=>document.getElementById(id),card=byId('controller-router');
if(!card)return;
let snapshot=null,busy=false;
async function request(action,payload={}){
 const response=await fetch('/api/controller-router',{method:'POST',headers:{'Content-Type':'application/json','X-VirtualGlove-Action':'controller-router'},body:JSON.stringify({action,...payload})});
 let result;try{result=await response.json()}catch(_error){throw Error('The Controller returned an unreadable response.')}
 if(!response.ok)throw Error(result.error||'Controller Router request failed.');return result;
}
function selectFor(source){const select=document.createElement('select');select.dataset.source=source.id;
 for(const [value,label] of [['','Unassigned'],['1','Player 1'],['2','Player 2'],['3','Player 3'],['4','Player 4']]){const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option)}
 const suggested=source.assigned_player||source.suggested_player;select.value=suggested?String(suggested):'';return select}
function render(data){snapshot=data;const body=byId('router-sources');body.replaceChildren();
 for(const source of data.inventory||[]){const row=document.createElement('tr'),name=document.createElement('td'),state=document.createElement('td'),assignment=document.createElement('td');name.textContent=`${source.name} · ${source.identity_suffix}`;state.textContent=source.connected?'Connected':'Unavailable';assignment.append(selectFor(source));row.append(name,state,assignment);body.append(row)}
 if(!(data.inventory||[]).length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=3;cell.textContent='No configured gamepads are currently connected.';row.append(cell);body.append(row)}
 byId('router-virtual').value=data.config?.virtualglove_player?String(data.config.virtualglove_player):'';byId('router-rollback').hidden=!data.has_backup;byId('router-panel').hidden=false;byId('router-prerequisite').textContent='Review assignments before saving. Suggested frontend order is never saved automatically.'}
async function load(){const platform=byId('platform')?.value;if(!['retropie','recalbox','batocera'].includes(platform)){byId('router-panel').hidden=true;byId('router-prerequisite').textContent=platform==='launchbox'?'LaunchBox keeps its separate Network RetroPad route.':'Select and save a supported console platform to manage its controllers.';return}
 try{render(await request('read'))}catch(error){byId('router-panel').hidden=true;byId('router-prerequisite').textContent=error.message}}
async function work(button,fn){if(busy)return;busy=true;button.disabled=true;try{await fn()}catch(error){byId('router-notice').textContent=error.message}finally{button.disabled=false;busy=false}}
byId('router-save').onclick=()=>work(byId('router-save'),async()=>{const players=[];for(let player=1;player<=4;player++){const sources=[...card.querySelectorAll('select[data-source]')].filter(item=>item.value===String(player)).map(item=>item.dataset.source);if(sources.length)players.push({player,sources})}const virtual=byId('router-virtual').value;render(await request('save',{revision:snapshot.revision,config:{players,virtualglove_player:virtual?Number(virtual):null}}));byId('router-notice').textContent='Controller Router assignments saved. They will apply to the next FCEUmm launch.'});
byId('router-check').onclick=()=>work(byId('router-check'),async()=>{byId('router-notice').textContent='Press a button or direction on a controller…';const result=await request('check',{watch_ms:750});const connected=new Map((result.inventory||[]).map(item=>[item.id,item.connected]));for(const select of card.querySelectorAll('select[data-source]'))select.closest('tr').children[1].textContent=connected.get(select.dataset.source)?'Connected':'Unavailable';const active=Object.entries(result.activity||{}).map(([id,controls])=>`${id.slice(-6)}: ${controls.join(', ')}`).join(' · ');byId('router-notice').textContent=active?`Input received — ${active}`:result.safe?'Controllers are connected; no input was pressed during the test.':`${result.missing_sources.length} assigned controller${result.missing_sources.length===1?' is':'s are'} unavailable.`});
byId('router-rollback').onclick=()=>work(byId('router-rollback'),async()=>{if(!confirm('Restore the previous Controller Router assignments?'))return;render(await request('rollback',{revision:snapshot.revision}));byId('router-notice').textContent='Previous Controller Router assignments restored.'});
byId('platform')?.addEventListener('change',load);window.addEventListener('virtualglove-config-loaded',load);window.addEventListener('virtualglove-paired',load);setTimeout(load,0);
})();"""
