# Project: VirtualGlove
# SPDX-License-Identifier: MIT
"""Read-only connection guidance using existing Setup and runtime APIs."""

DOCTOR_CONTENT = """<div id=connection-doctor class=connection-pairing role=region aria-labelledby=doctor-title>
<h3 id=doctor-title>Connection Doctor</h3><p>Let’s check the saved console connection. Your settings and controller output stay as they are.</p>
<div class=controls><button type=button id=doctor-run>Check connection</button><button type=button class=secondary id=doctor-download disabled>Download connection report</button></div>
<p id=doctor-notice role=status aria-live=polite>Run a check for results and next steps.</p><ol id=doctor-checks class=compact-guidance></ol>
<p class=setup-status-note>These checks cannot prove that a game received input. The report contains only checklist results, with no addresses, credentials, player data, calibration, or hand measurements.</p>
</div>"""

# Installed inside Setup's existing closure to share its save/pair busy guards.
DOCTOR_SCRIPT = r"""(()=>{
const names={saved:'Saved console',address:'Address resolution',service:'Console service',pairing:'Secure pairing',receiver:'Controller receiver link',device:'Virtual controller readiness',mapping:'Game input mode'};
let report=null,epoch=0,running=false;
const signature=c=>JSON.stringify([String(c.receiver||'').trim(),String(c.port??''),String(c.profile??''),c.connection_configured]);
function matches(c){return ['receiver','port','profile'].every(k=>String($(k).value).trim()===String(c[k]??'').trim())&&!$('rotate_token').checked;}
function invalidate(){epoch++;report=null;$('doctor-download').disabled=true;$('doctor-checks').replaceChildren();$('doctor-notice').textContent='Connection or pairing changed. Save any edits, then run a new check.';}
for(const id of ['receiver','port','profile','rotate_token'])$(id).addEventListener('input',invalidate);
$('form').addEventListener('submit',invalidate);
$('camera-form').addEventListener('submit',invalidate);
$('pair-submit').addEventListener('click',invalidate);
function draw(checks){$('doctor-checks').replaceChildren(...checks.map(c=>{const row=document.createElement('li'),title=document.createElement('strong');title.textContent=names[c.id]+': '+({pass:'Checked',attention:'Needs attention',unknown:'Not verified',pending:'Checking…'}[c.state]);row.append(title,document.createTextNode(' — '+c.message));return row}));}
$('doctor-run').onclick=async()=>{
 if(running)return;
 if(settingsBusy||pairingBusy||windowActive()){$('doctor-notice').textContent='Finish saving or pairing, then run the connection check.';return;}
 running=true;const run=++epoch,checks=Object.keys(names).map(id=>({id,state:'pending',message:'Waiting for this check.'}));
 report=null;$('doctor-download').disabled=true;$('doctor-run').disabled=true;$('connection-doctor').setAttribute('aria-busy','true');draw(checks);
 const current=()=>run===epoch;
 const put=(id,state,message)=>{if(!current())return;Object.assign(checks.find(c=>c.id===id),{state,message});draw(checks);};
 async function get(path,payload){const result=await api(path,payload,4500);if(!current())throw Error('changed');return result;}
 try{
  $('doctor-notice').textContent='Checking the saved console…';
  const config=await get('/api/config');
  if(!matches(config)){put('saved','attention','The selected console or startup profile has unsaved changes. Select Save connection, then check again.');}
  else if(!config.receiver){put('saved','attention','Enter the RetroPie address above and select Save connection.');}
  else{
   put('saved','pass','The selected address, port, and startup profile match the saved settings.');
   try{await get('/api/test-connection',{receiver:config.receiver});put('address','pass','The saved address resolves. Resolution alone does not prove the console is online.');}
   catch(e){put('address','attention','The saved address could not be resolved in time. Check the spelling, console power, and network connection; then retry.');}
   if(!current())return;
   $('doctor-notice').textContent='Checking the console service and pairing…';
   try{
    let c=await get('/api/connection-status');
    for(let i=0;i<4&&c.checked_seconds_ago==null;i++){await new Promise(resolve=>setTimeout(resolve,750));if(!current())throw Error('changed');c=await get('/api/connection-status');}
    const fresh=typeof c.checked_seconds_ago==='number'&&c.checked_seconds_ago>=0&&c.checked_seconds_ago<30;
    put('service',fresh&&c.console_service===true?'pass':fresh&&c.console_service===false?'attention':'unknown',fresh&&c.console_service===true?'A console check from the last 30 seconds found the Games service reachable. This is separate from the controller receiver.':fresh&&c.console_service===false?'The console Games service did not respond. Check console power, networking, and the RetroPie installation.':'No recent console-service result is available. Wait a moment and check again.');
    put('pairing',config.connection_configured&&fresh&&c.console_authenticated===true?'pass':'unknown',config.connection_configured&&fresh&&c.console_authenticated===true?'A console check from the last 30 seconds received an authenticated Games response using the saved pairing key.':!config.connection_configured?'No saved connection key is available. Save the connection, then use Pair this Controller.':'Pairing could not be confirmed. If the console service is reachable, use Pair this Controller; otherwise restore connectivity first.');
   }catch(e){put('service','unknown','The console check is unavailable. Retry once the Controller connection returns.');put('pairing','unknown','No authenticated result is available. A saved key alone does not confirm pairing.');}
   if(!current())return;
   $('doctor-notice').textContent='Checking reported controller and game status…';
   try{
    const s=await get('/status');
    const active=s.worker_running===true&&s.controller_enabled===true&&s.controller_context_active===true&&!s.controller_request_pending&&!s.practice_mode&&!s.launch_guard_active&&s.profile!=='off'&&s.vision_profile!=='off'&&s.vision_state==='active';
    put('receiver',active&&s.receiver_available===true?'pass':active&&s.receiver_available===false?'attention':'unknown',active&&s.receiver_available===true?'The running tracker reports an authenticated receiver handshake and packet sending. Game input delivery is not acknowledged.':active&&s.receiver_available===false?'The running tracker has no receiver link. Check the RetroPie receiver service, pairing, and UDP port.':'No active receiver-link check is available. When ready, use Dashboard to start controls with a game or manual profile, then check again.');
    const profile=s.active_profile||s.profile,core=s.emulator,mode=s.input_mode;
    if(s.worker_running===true&&s.game_session_active===true&&['super_glove_ball','bad_street_brawler',...Array.from({length:14},(_,i)=>'program_'+(i+1)),...'abcdefghi'.split('').map(x=>'program_'+x)].includes(profile)&&typeof core==='string'&&core&&core!=='unknown'&&['native','joystick'].includes(mode)){
     const expected=profile==='super_glove_ball'&&['lr-nestopia-powerglove','lr-powerglove-dot'].includes(core)?'native':'joystick';
     put('mapping',mode===expected?'pass':'attention',mode===expected?'The reported active game profile, emulator, and input mode agree. Installed core files and game-side input are not verified.':'The reported game profile and input mode disagree. Review Games and the RetroPie emulator selection, then restart the game.');
    }else put('mapping','unknown','No complete active-game report is available. Start a registered game, then check again; review its mapping in Games.');
   }catch(e){put('receiver','unknown','Tracker status is unavailable. Open Dashboard and retry when the Controller reconnects.');put('mapping','unknown','Game status is unavailable. No mapping or native-core success can be confirmed.');}
   put('device','unknown','The current protocol does not report virtual-gamepad creation or native-core consumption. Verify input in the game on RetroPie.');
   const latest=await get('/api/config');if(signature(latest)!==signature(config)||!matches(latest)){invalidate();return;}
  }
  if(!current())return;
  for(const c of checks)if(c.state==='pending'){c.state='unknown';c.message='Save the selected console first, then run the checks again.';}
  draw(checks);report={format:'virtualglove-connection-report',version:1,checked_at_utc:new Date().toISOString(),checks};
  $('doctor-download').disabled=false;$('doctor-notice').textContent='Check complete. Follow the items marked Needs attention or Not verified. These results are a snapshot, not a gameplay test.';
 }catch(e){if(current()){$('doctor-notice').textContent='The check could not finish. Restore the Controller connection and try again.';for(const c of checks)if(c.state==='pending'){c.state='unknown';c.message='Check did not finish.';}draw(checks);}}
 finally{running=false;$('doctor-run').disabled=false;$('connection-doctor').setAttribute('aria-busy','false');}
};
$('doctor-download').onclick=()=>{if(!report)return;const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='virtualglove-connection-report.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
})();"""
