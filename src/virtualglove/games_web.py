# Project: VirtualGlove
# File: src/virtualglove/games_web.py
# Purpose: Render the paired cabinet game registry editor.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Separate maintained web modules without changing rendered pages.

"""Render the paired cabinet game registry editor."""

GAMES_CONTENT = """<section id=games-section style="margin-top:28px;scroll-margin-top:20px"><h2>Games</h2>
<p class=lead>Edit the game mappings installed on your console. Saving affects the next game launch.</p>
<section class=card><p>Use the exact ROM filename, including its extension: <code>Joust (USA).7z</code> and <code>Joust (USA).nes</code> need separate entries. Matching ignores letter case. Only NES and Famicom launches use these mappings.</p>
<details><summary>Available profile identifiers</summary><p id=game-profiles></p><p>Simple mapping: <code>{"games": {"Joust (USA).7z": "program_b"}}</code>. A game can also override the original rapid-fire switches: <code>{"games": {"Blaster Master (USA).nes": {"profile": "program_1", "rapid_a": false}}}</code>. Remove a mapping to leave that game off.</p></details>
<label for=game-json>Game mappings JSON</label><textarea id=game-json spellcheck=false rows=22 style="width:100%;font:14px/1.5 monospace;tab-size:2;background:#090b11;color:#f7f8ff;border:1px solid #303748;border-radius:8px;padding:12px" aria-describedby=games-notice></textarea>
<div class=controls><button id=games-validate>Validate</button><button id=games-format>Format</button><button id=games-save>Save</button><button id=games-reload>Reload</button><button id=games-backup>Download backup</button><button id=games-restore>Restore previous save</button></div>
<p id=games-notice role=status aria-live=polite>Loading the installed console registry…</p></section></section>"""

GAMES_SCRIPT = r"""(()=>{
const editor=document.getElementById('game-json'),notice=document.getElementById('games-notice');
let revision=null,loaded='',backup=false,busy=false;
const buttons=[...document.querySelectorAll('#games-section button')];
function controls(){buttons.forEach(b=>b.disabled=busy||(b.id!=='games-reload'&&!revision)||(b.id==='games-restore'&&!backup))}
async function api(action){const r=await fetch('/api/games',{method:'POST',headers:{'Content-Type':'application/json','X-VirtualGlove-Action':'games'},body:JSON.stringify({action,document:editor.value,revision})});const x=await r.json();if(!r.ok)throw Error(x.error||'Games request failed');return x}
async function run(action){if(busy)return;if(action==='read'&&editor.value!==loaded&&!confirm('Discard your unsaved edits and reload?'))return;if(action==='restore'&&!confirm('Replace the current mappings with the previous save?'))return;busy=true;controls();try{const x=await api(action);if(['read','save','restore'].includes(action)){editor.value=x.document;loaded=x.document;revision=x.revision;backup=x.has_backup;document.getElementById('game-profiles').textContent=x.profiles.join(' · ')}if(action==='format')editor.value=x.document;notice.textContent=action==='save'?'Saved on the console and verified. The next game launch uses these mappings.':action==='restore'?'Previous save restored on the console.':action==='validate'?'Valid JSON and game mappings.':action==='format'?'Formatted. Select Save to apply.':'Installed mappings loaded.'}catch(e){notice.textContent=e.message+' Your draft has been kept.'}finally{busy=false;controls()}}
for(const [id,action] of Object.entries({'games-validate':'validate','games-format':'format','games-save':'save','games-reload':'read','games-restore':'restore'}))document.getElementById(id).onclick=()=>run(action);
document.getElementById('games-backup').onclick=()=>{const url=URL.createObjectURL(new Blob([loaded],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='virtualglove-games-backup.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice.textContent='Downloaded the last verified installed registry.'};
window.addEventListener('beforeunload',e=>{if(editor.value!==loaded){e.preventDefault();e.returnValue=''}});controls();run('read');})();"""
