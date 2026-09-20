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
<style>
#controller-router .router-table-scroll{overflow-x:auto;margin:16px 0 18px}
#controller-router table{width:100%;min-width:620px;border-collapse:separate;border-spacing:0;table-layout:fixed;border:1px solid var(--line);border-radius:10px;overflow:hidden}
#controller-router th,#controller-router td{padding:13px 16px;text-align:left;vertical-align:middle;border-bottom:1px solid var(--line)}
#controller-router th{background:#090b11;color:var(--muted);font:800 12px/1.35 system-ui;text-transform:uppercase;letter-spacing:.7px}
#controller-router tbody tr:last-child td{border-bottom:0}
#controller-router th:nth-child(1){width:52%}#controller-router th:nth-child(2){width:20%}#controller-router th:nth-child(3){width:28%}
#controller-router td:nth-child(1){overflow-wrap:anywhere}#controller-router td:nth-child(2){white-space:nowrap}#controller-router td select{min-width:150px}
#controller-router .router-hotkey-warning{margin:14px 0;padding:12px 14px;border:1px solid #ff737c;border-radius:9px;background:#e6404718;color:#ff9da3;font-weight:800}
</style>
<section id=controller-router class=card style="margin-bottom:14px" aria-labelledby=router-title>
<h2 id=router-title>Controller Router</h2>
<p>Choose which configured joypads share each FCEUmm player. Your original controllers keep working in the console menus; the merged players become active only during compatible NES gameplay.</p>
<p id=router-prerequisite class=setup-status-note>Loading console controller assignments…</p>
<div id=router-panel hidden>
<div class=router-table-scroll><table><thead><tr><th>Configured controller</th><th>Connection status</th><th>Player assignment</th></tr></thead><tbody id=router-sources></tbody></table></div>
<label>VirtualGlove player<select id=router-virtual><option value="">Unassigned</option><option value=1>Player 1</option><option value=2>Player 2</option><option value=3>Player 3</option><option value=4>Player 4</option></select></label>
<p class=setup-status-note>Only one player can receive this VirtualGlove. Player 1 alone carries the physical controller’s console hotkey; VirtualGlove Select never becomes a hotkey.</p>
<p id=router-hotkey-warning class=router-hotkey-warning role=alert hidden>No physical controller is assigned to Player 1. RetroArch menu and exit hotkeys may be unavailable during FCEUmm gameplay. Keep a keyboard available or assign a physical controller to Player 1.</p>
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
function updateHotkeyWarning(){byId('router-hotkey-warning').hidden=[...card.querySelectorAll('select[data-source]')].some(item=>item.value==='1')}
function render(data){snapshot=data;const body=byId('router-sources');body.replaceChildren();
 for(const source of data.inventory||[]){const row=document.createElement('tr'),name=document.createElement('td'),state=document.createElement('td'),assignment=document.createElement('td');name.textContent=`${source.name} · ${source.identity_suffix}`;state.textContent=source.connected?'Connected':'Unavailable';assignment.append(selectFor(source));row.append(name,state,assignment);body.append(row)}
 if(!(data.inventory||[]).length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=3;cell.textContent='No configured gamepads are currently connected.';row.append(cell);body.append(row)}
 byId('router-virtual').value=data.config?.virtualglove_player?String(data.config.virtualglove_player):'';byId('router-rollback').hidden=!data.has_backup;byId('router-panel').hidden=false;byId('router-prerequisite').textContent='Review assignments before saving. Suggested frontend order is never saved automatically.';updateHotkeyWarning()}
async function load(){const platform=byId('platform')?.value;if(!['retropie','recalbox','batocera'].includes(platform)){byId('router-panel').hidden=true;byId('router-prerequisite').textContent=platform==='launchbox'?'LaunchBox keeps its separate Network RetroPad route.':'Select and save a supported console platform to manage its controllers.';return}
 try{render(await request('read'))}catch(error){byId('router-panel').hidden=true;byId('router-prerequisite').textContent=error.message}}
async function work(button,fn){if(busy)return;busy=true;button.disabled=true;try{await fn()}catch(error){byId('router-notice').textContent=error.message}finally{button.disabled=false;busy=false}}
byId('router-save').onclick=()=>work(byId('router-save'),async()=>{const players=[];for(let player=1;player<=4;player++){const sources=[...card.querySelectorAll('select[data-source]')].filter(item=>item.value===String(player)).map(item=>item.dataset.source);if(sources.length)players.push({player,sources})}const virtual=byId('router-virtual').value;render(await request('save',{revision:snapshot.revision,config:{players,virtualglove_player:virtual?Number(virtual):null}}));byId('router-notice').textContent='Controller Router assignments saved. They will apply to the next FCEUmm launch.'});
byId('router-check').onclick=()=>work(byId('router-check'),async()=>{byId('router-notice').textContent='Press a button or direction on a controller…';const result=await request('check',{watch_ms:750});const connected=new Map((result.inventory||[]).map(item=>[item.id,item.connected]));for(const select of card.querySelectorAll('select[data-source]'))select.closest('tr').children[1].textContent=connected.get(select.dataset.source)?'Connected':'Unavailable';const active=Object.entries(result.activity||{}).map(([id,controls])=>`${id.slice(-6)}: ${controls.join(', ')}`).join(' · ');byId('router-notice').textContent=active?`Input received — ${active}`:result.safe?'Controllers are connected; no input was pressed during the test.':`${result.missing_sources.length} assigned controller${result.missing_sources.length===1?' is':'s are'} unavailable.`});
byId('router-rollback').onclick=()=>work(byId('router-rollback'),async()=>{if(!confirm('Restore the previous Controller Router assignments?'))return;render(await request('rollback',{revision:snapshot.revision}));byId('router-notice').textContent='Previous Controller Router assignments restored.'});
card.addEventListener('change',event=>{if(event.target.matches('select[data-source]'))updateHotkeyWarning()});
byId('platform')?.addEventListener('change',load);window.addEventListener('virtualglove-config-loaded',load);window.addEventListener('virtualglove-paired',load);setTimeout(load,0);
})();"""
