# Project: VirtualGlove
# File: src/powerglove_vision/setup_web.py
# Purpose: Present connection, pairing, and idle-display settings with recoverable browser actions.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-12 - Combined console connection and pairing into one guided Setup card.
#   2026-09-11 - Added guided one-time trust for the Controller's local HTTPS authority.
#   2026-09-10 - Use Pixel Pal's thinking and success poses in Setup.
#   2026-09-10 - Added Pixel Pal's camera-settings profiler.
#   2026-09-09 - Distinguished armed idle output from receiver unavailability.
#   2026-09-09 - Made validated fast-sweep tracking standard and removed its switch.
#   2026-09-08 - Replaced free-form camera entry with a live discovered-camera list.
#   2026-09-08 - Added capability-checked manual exposure and gain controls.
#   2026-09-07 - Added advanced camera reader and exposure choices.
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Organize Setup and keep failed requests and unsaved fields recoverable.

"""Setup content is separate from routing so its wording and behavior are reviewable."""

SETUP_CONTENT = """<style>main a{color:var(--cyan)}#players{margin-bottom:14px}#form{margin:0}#form p{margin:0}#notice:empty,#camera-notice:empty,#pair-notice:empty,#attract-notice:empty{display:none}#connection-fields details{margin-top:16px}#attract-form button{justify-self:start}.connection-pairing{margin-top:20px;padding-top:18px;border-top:1px solid var(--line)}.connection-pairing>h3{margin-top:0}.connection-indicators{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;list-style:none;padding:0;margin:0}.connection-indicators li{display:flex;gap:10px;align-items:flex-start;padding:12px;border:1px solid var(--line);border-radius:10px;min-width:0}.connection-indicators .check-dot{flex:0 0 12px;width:12px;height:12px;border-radius:50%;background:#8992a8;margin-top:5px}.connection-indicators [data-state=good] .check-dot{background:var(--green)}.connection-indicators [data-state=bad] .check-dot{background:#ff737c}.connection-indicators strong{display:block;font-size:14px;margin-top:4px}.connection-indicators .check-label{font-size:12px;color:var(--muted)}.setup-status-note{color:var(--muted);font-size:12px;margin-bottom:0}.setup-help{margin-top:12px!important}.compact-guidance{margin:12px 0;padding-left:22px}.compact-guidance li{margin:5px 0}@media(max-width:850px){.connection-indicators{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:360px){.connection-indicators{grid-template-columns:1fr;gap:8px}.connection-indicators li{padding:8px;gap:6px}}#pairing-section [hidden]{display:none!important}#pairing-section fieldset{border:0;padding:0;margin:12px 0}#pairing-section legend{font-weight:bold;margin-bottom:8px}.pair-choice{display:flex;align-items:flex-start;gap:12px;padding:14px;border:1px solid var(--line);border-radius:10px;margin-bottom:10px}.pair-choice input{width:auto;margin-top:5px}.pair-progress{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding-left:0;list-style-position:inside;color:var(--muted);font-size:13px}.pair-progress li{padding:8px 0;border-bottom:1px solid var(--line)}.pair-progress [aria-current=step]{color:var(--cyan);font-weight:bold}.pair-destination{overflow-wrap:anywhere}#pair-change{margin-left:12px}#pairing-section pre{white-space:pre-wrap;overflow-wrap:anywhere}#pair-timer{color:var(--cyan)}#pair-notice{padding:14px;border:1px solid var(--cyan);border-radius:10px}#pairing-section h3:focus,#pair-notice:focus{outline:2px solid var(--cyan);outline-offset:4px}</style><h1>Setup</h1><p>Connect RetroPie, manage players, and choose how the camera and controls behave. For gesture practice and centering, open <a href=/learn>Glove Academy</a>. For a guided walkthrough, see <a href=/help/installation>Installation and setup</a>.</p>
<p><a class=button href=/ready>Get ready to play</a></p>
<section class=card style="margin-bottom:14px" aria-labelledby=connection-status-title><h2 id=connection-status-title>Controller status</h2><ul class=connection-indicators aria-label="Controller status checks" aria-live=polite>
<li id=status-app data-state=unknown><span class=check-dot aria-hidden=true></span><div><span class=check-label>1 · Controller app</span><strong>Checking…</strong></div></li>
<li id=status-console data-state=unknown><span class=check-dot aria-hidden=true></span><div><span class=check-label>2 · Console service</span><strong>Checking…</strong></div></li>
<li id=status-auth data-state=unknown><span class=check-dot aria-hidden=true></span><div><span class=check-label>3 · Authenticated response</span><strong>Checking…</strong></div></li>
<li id=status-wifi data-state=unknown><span class=check-dot aria-hidden=true></span><div><span class=check-label>4 · Networking</span><strong id=wifi-status>Checking…</strong></div></li>
<li id=status-tracking data-state=unknown><span class=check-dot aria-hidden=true></span><div><span class=check-label>Tracking</span><strong>Checking…</strong></div></li>
<li id=status-output data-state=unknown><span class=check-dot aria-hidden=true></span><div><span class=check-label>Controller output</span><strong>Checking…</strong></div></li></ul>
<p class=setup-status-note>Saved console: <strong id=status-destination>Loading…</strong></p>
<p class=setup-status-note>Active controller link: <strong id=status-active-destination>Not active</strong></p>
<p class=setup-status-note id=connection-status-note>Connection checks do not confirm that a game received input.</p><div class=controls><button type=button class=secondary id=support-report>Download system report</button></div><p class=setup-status-note id=support-report-note>A privacy-safe report contains no video, pairing key, player calibration, ROM name, or network address.</p></section>
{{PLAYER_CONTENT}}
{{JOYSTICK_CONTENT}}
<section class=card style="margin-bottom:14px"><h2>Matrix attract mode</h2><form id=attract-form><label>Idle display<select id=matrix-attract><option value=on>On — full animation</option><option value=dim>Dim — gentle animation</option><option value=off>Off — connection pixels only</option></select></label><button type=submit>Save attract mode</button></form><p>Changes only the idle glove animation. Game displays, T, L, startup, errors, and pairing keep their normal brightness. Saves without restarting tracking.</p><details><summary>What the connection pixels mean</summary><p>In Off mode, four faint bottom-left pixels show: app running, console service reachable, authenticated RetroPie response, and a Wi-Fi or Ethernet link connected. The Networking pixel comes from the Controller’s physical network links, including Ethernet through a USB dock, independently of RetroPie. It does not confirm an IP address or Internet access. These indicators do not prove that a game received input.</p></details><p id=attract-notice role=status></p></section>
<section id=connection-section class=card style="margin-bottom:14px" aria-labelledby=connection-title><h2 id=connection-title>Connection and startup</h2><p>Choose your console and startup profile, then save the connection before pairing below.</p><form id=form><p id=paired role=status>Loading saved settings…</p><fieldset id=connection-fields disabled style='border:0;padding:0;margin:0;min-width:0'><div class=formgrid>
<label>RetroPie hostname or IP address<input id=receiver name=receiver placeholder=RETROPIE-NAME.local autocomplete=off></label>
<label>Startup game profile<select id=profile name=profile>{{PROFILE_OPTIONS}}</select></label>
</div><details><summary>Advanced connection</summary><div class=formgrid><label>Receiver UDP port<input id=port name=port type=number min=1 max=65535 required></label></div><label class=check><input id=rotate_token type=checkbox> Replace the pairing key when saving</label><p>Pair with RetroPie again after replacing the key. <a href=/help/configuration#signed-controller-transport-and-upgrades>Learn about pairing keys and coordinated updates</a>.</p></details>
<div class=controls><button type=submit id=connection-save>Save connection</button><button class=secondary type=button id=test>Check console address</button></div><p class=setup-status-note>Checking an address confirms name resolution only—not pairing or gameplay.</p><p class=notice id=notice role=status aria-live=polite></p></fieldset><button id=setup-retry type=button hidden>Reload saved settings</button></form>
</section>
<section id=pairing-card class=card style="margin-bottom:14px"><div id=pairing-section class=connection-pairing role=region aria-labelledby=pair-title><h2 id=pair-title>Pair with RetroPie</h2>
<p id=secure-note></p>
<div id=pair-wizard hidden>
<p class=pair-destination>Saved console: <strong id=pair-destination>Loading…</strong> <a id=pair-change href=#connection-section>Change</a></p>
<p id=pair-prerequisite role=status></p>
<ol class=pair-progress aria-label="Pairing steps"><li id=pair-progress-1>Choose a method</li><li id=pair-progress-2>Confirm your Controller</li><li id=pair-progress-3>Pair with RetroPie</li></ol>
<p id=pair-summary></p><p id=pair-timer role=timer aria-live=off hidden></p>
<div id=pair-step-1><h3 id=pair-heading-1 tabindex=-1>1. Choose a pairing method</h3>
<fieldset id=pair-methods><legend>How will you connect?</legend>
<label class=pair-choice><input type=radio name=pair-method value=code checked><span><strong>One-time code (recommended)</strong><br>Run a command on RetroPie and enter the code it displays.</span></label>
<label class=pair-choice><input type=radio name=pair-method value=ssh><span><strong>SSH password</strong><br>Use your RetroPie username and password. SSH password login must be enabled.</span></label></fieldset>
<button id=pair-begin type=button>Continue</button></div>
<div id=pair-step-2 hidden><h3 id=pair-heading-2 tabindex=-1>2. Confirm your Controller</h3>
<p id=pair-confirmation>Start confirmation to display the matrix ID and approval PIN.</p>
<details><summary>How to compare the certificate</summary><p>Open the browser’s connection or security details for this page, then view its certificate and find the SHA-256 fingerprint. Compare its beginning with the ID displayed on the Controller matrix. Ignore spaces, colons, and letter case. Use the physical matrix as your reference, not just the ID shown on this page.</p><p>In Safari, open the website’s connection details and choose Show Certificate. In Chrome or Edge, use the site controls beside the address, open connection information, then the certificate viewer. The labels vary by browser version.</p><p>If the values differ, stop pairing. Do not enter your PIN, RetroPie code, or password.</p></details>
<fieldset id=pair-confirm-fields disabled><label class=check><input id=verified type=checkbox> I compared the browser certificate fingerprint with the matrix ID and they match</label>
<label>Controller approval PIN<input id=device-code inputmode=numeric maxlength=6 pattern="[0-9]{6}" autocomplete=off placeholder="Six digits shown on the Controller matrix"></label></fieldset>
<div class=controls><button id=pair-confirm-next type=button disabled>Continue</button><button id=pair-restart type=button hidden>Start a new confirmation</button><button id=pair-method-back type=button class=secondary hidden>Change pairing method</button></div></div>
<div id=pair-step-3 hidden><h3 id=pair-heading-3 tabindex=-1>3. Pair with RetroPie</h3>
<fieldset id=pair-credentials disabled>
<div id=pair-code-fields><p>On the RetroPie console named above, open a terminal and run:</p><pre><code>sudo /opt/virtualglove/bin/virtualglove-pair</code></pre><label>RetroPie one-time code<input id=pair-code autocomplete=off placeholder=ABCDE-FGHIJ-23456-7ABCD></label><p>This code comes from that RetroPie console, remains valid for five minutes, and is different from the six-digit Controller approval PIN.</p></div>
<div id=pair-ssh-fields hidden><div class=formgrid><label>RetroPie username<input id=pair-user value=pi autocomplete=username></label><label>RetroPie SSH password<input id=pair-password type=password autocomplete=off disabled></label></div><p>Your password is used for this pairing request and is not saved by the Controller.</p></div>
</fieldset><div class=controls><button id=pair-submit type=button disabled>Pair with RetroPie</button><button id=pair-review type=button class=secondary>Review Controller confirmation</button></div></div>
<div id=pair-pending hidden><h3 id=pair-pending-heading tabindex=-1>Pairing in progress</h3><p>Sending the pairing request to RetroPie. Keep this page open while we wait for its response.</p><p>SSH pairing can take a few minutes. Pairing does not start controller output.</p></div>
<div id=pair-success hidden><img class=setup-pal-success src=/help-assets/gestures/v2/pixel-pal-success.png alt="Pixel Pal gives a thumbs-up"><h3 id=pair-success-heading tabindex=-1>Pairing complete</h3><p>The RetroPie receiver was restarted. The matrix resumes its normal display; when idle, it follows your attract setting. Open Dashboard to start controller output when you are ready. Pairing does not verify that a game received input.</p><a class=button href=/dashboard>Open Dashboard</a></div>
<p id=pair-notice role=status aria-live=polite aria-atomic=true tabindex=-1></p></div></div>
{{DOCTOR_CONTENT}}
</section>
<form id=camera-form><section id=camera-section class=card style="margin-bottom:14px"><h2>Camera</h2><fieldset id=camera-fields disabled style='border:0;padding:0;margin:0;min-width:0'><div class=formgrid><label>Camera<select id=camera name=camera><option value=auto>Automatic — choose the connected camera</option></select></label><label>Camera frame rate<select id=camera_fps name=camera_fps><option value=auto>Automatic — prefer 30 fps</option><option value=30>30 fps</option><option value=60>60 fps</option></select></label><label>Camera buffers<select id=camera_buffers name=camera_buffers><option value=1>1 buffer — lowest queue depth</option><option value=2>2 buffers — steadier camera delivery</option></select></label><label>Camera reader<select id=camera_backend name=camera_backend><option value=opencv>Recommended — OpenCV</option><option value=direct-v4l2>Engineering comparison — Direct V4L2</option></select></label><label>Exposure behavior<select id=camera_exposure name=camera_exposure><option value=auto>Automatic — portable default</option><option value=low-latency>Automatic — fixed frame rate</option><option value=kiyo-low-latency>Automatic — Razer Kiyo Pro tested</option><option value=manual>Manual exposure and gain</option></select></label><label>Hand or glove (diagnostic label)<select id=glove_color name=glove_color><option value=none>Bare hand</option><option value=white>White glove</option><option value=black>Black glove</option></select></label></div><div id=camera-manual-settings class=formgrid hidden><label>Manual exposure<input id=camera_manual_exposure name=camera_manual_exposure type=number min=1 max=10000 step=1 inputmode=numeric></label><label>Manual gain<input id=camera_manual_gain name=camera_manual_gain type=number min=0 max=10000 step=1 inputmode=numeric></label></div>
<p class=setup-status-note id=camera-rate-status role=status>Actual camera behavior appears while tracking is active.</p><ul class=compact-guidance><li>Automatic and OpenCV are the recommended starting point and work when the camera is connected later.</li><li>Direct V4L2 remains available for engineering comparisons and falls back safely when unsupported.</li><li>Manual exposure is optional, camera-dependent, and restored to automatic when tracking closes.</li></ul><p class=setup-help><a href=/help/camera>Open the Camera guide</a> for compatibility, exposure, lighting, and troubleshooting.</p><div class=controls><button type=submit id=camera-save>Save camera settings</button></div><p class=notice id=camera-notice role=status aria-live=polite></p></fieldset></section></form>
<section id=controller-trust class=card style="margin-bottom:14px" aria-labelledby=trust-title><h2 id=trust-title>Trust this Controller</h2>
<p>Optional, one-time setup removes the browser’s privacy warning on this phone or computer. VirtualGlove creates a private authority for this Controller; its private keys never leave the Controller.</p>
<div class=controls><a class=button id=trust-download href=/controller-ca.cer download=virtualglove-controller-ca.cer>Download trust certificate</a></div>
<p id=trust-note class=setup-status-note></p>
<details><summary>Install and trust the certificate</summary><ol class=compact-guidance><li>Before downloading, start Controller confirmation in <strong>Pair with RetroPie</strong> above and compare the browser certificate with the ID on the physical matrix.</li><li>Download the certificate only when those values match.</li><li>Install it as a trusted root on this device, then close and reopen the browser.</li></ol><p><strong>iPhone or iPad:</strong> install the downloaded profile, then open Settings → General → About → Certificate Trust Settings and enable full trust for VirtualGlove. <a href=https://support.apple.com/en-us/102390 rel="noreferrer noopener">Apple’s trust instructions</a> show the current steps.</p><p><strong>Mac:</strong> add it to your login keychain with Keychain Access, open the certificate, and set Secure Sockets Layer trust to Always Trust.</p><p><strong>Windows:</strong> import it for the current user into Trusted Root Certification Authorities.</p><p><strong>Android:</strong> install it as a CA certificate in the device’s security settings. Menu names vary by manufacturer.</p><p>Trust is local to this phone or computer. Repeat it on another device. Firefox may use a separate certificate store and require its own import. Removing or resetting the Controller authority requires trusting the replacement again.</p></details></section>
"""

_CAMERA_PROFILE_STYLE = """.camera-profiler{margin-top:18px;padding:14px;border:1px solid var(--line);border-radius:12px}.camera-profiler h3{margin-top:0}.camera-profile-coach{display:flex;align-items:center;gap:14px}.camera-profile-coach img{width:72px;height:80px;object-fit:contain}.camera-profile-progress{width:100%;height:12px}.camera-profile-results{padding-left:22px}.camera-profile-results li{margin:7px 0}.camera-profile-good{color:var(--green)}.camera-profile-view{position:relative;max-width:640px;margin:12px auto;background:#050608;border:1px solid var(--line);border-radius:12px;overflow:hidden;aspect-ratio:4/3}.camera-profile-view[hidden]{display:none}.camera-profile-view>img{display:block;width:100%;height:100%;object-fit:contain}.camera-profile-guide{position:absolute;inset:7%;pointer-events:none;border:2px solid rgba(73,231,183,.7);border-radius:8px}.camera-profile-guide:before,.camera-profile-guide:after{content:'';position:absolute;background:rgba(73,231,183,.8)}.camera-profile-guide:before{left:50%;top:42%;width:2px;height:16%;transform:translateX(-1px)}.camera-profile-guide:after{top:50%;left:44%;height:2px;width:12%;transform:translateY(-1px)}.camera-profile-cue{position:absolute;left:50%;bottom:8%;transform:translateX(-50%);width:max-content;max-width:88%;padding:8px 12px;border:1px solid #ffffff55;border-radius:9px;background:rgba(5,6,8,.86);color:#fff;font:800 15px/1.3 system-ui;text-align:center}.camera-profile-countdown{position:absolute;right:4%;top:4%;display:grid;place-items:center;width:58px;height:58px;border:2px solid var(--cyan);border-radius:50%;background:rgba(5,6,8,.88);color:#fff;font:900 25px/1 system-ui}.camera-profile-time{min-height:24px;color:var(--muted);text-align:center}.camera-profile-view[data-cue=sweep] .camera-profile-guide{border-style:dashed}.camera-profile-view[data-cue=edge] .camera-profile-guide{border-color:#ffd359;box-shadow:inset 0 0 0 4px rgba(255,211,89,.28)}.camera-profile-view[data-cue=ready] .camera-profile-guide{border-color:var(--cyan)}"""
_CAMERA_PROFILE_STYLE = ".setup-pal-success{float:right;width:96px;height:104px;object-fit:contain;margin:0 0 8px 16px}" + _CAMERA_PROFILE_STYLE
SETUP_CONTENT = SETUP_CONTENT.replace("</style>", _CAMERA_PROFILE_STYLE + "</style>", 1)
SETUP_CONTENT = SETUP_CONTENT.replace(
    "<div class=controls><button type=submit id=camera-save>Save camera settings</button></div><p class=notice id=camera-notice role=status aria-live=polite></p>",
    """<div class=controls><button type=submit id=camera-save>Save camera settings</button></div><p class=notice id=camera-notice role=status aria-live=polite></p>
<div class=camera-profiler><div class=camera-profile-coach><img src=/help-assets/gestures/v2/pixel-pal-thinking.png alt=\"Pixel Pal inspects the camera settings\"><div><h3>Find the best camera settings</h3><p>Pixel Pal can compare safe settings for this camera. Keep one hand visible and follow the short movement cues. No video or images are saved.</p></div></div>
<div class=controls><button type=button id=camera-profile-start>Start camera test</button><button type=button class=secondary id=camera-profile-cancel hidden>Stop test</button></div>
<div id=camera-profile-panel hidden aria-live=polite><p><strong id=camera-profile-step></strong></p><p id=camera-profile-instruction></p><div class=camera-profile-view id=camera-profile-view hidden><img id=camera-profile-frame data-src=/stream alt="Live mirrored camera view with hand tracking"><div class=camera-profile-guide aria-hidden=true></div><div class=camera-profile-countdown id=camera-profile-countdown role=timer aria-live=off>3</div><div class=camera-profile-cue id=camera-profile-cue>Get ready</div></div><p class=camera-profile-time id=camera-profile-time role=timer aria-live=off></p><progress class=camera-profile-progress id=camera-profile-progress max=1 value=0></progress><ul class=camera-profile-results id=camera-profile-results></ul><p id=camera-profile-recommendation></p><button type=button id=camera-profile-apply hidden>Use recommended settings</button></div></div>""",
    1,
)

SETUP_SCRIPT = r"""(()=>{
const $=id=>document.getElementById(id), secure=location.protocol==='https:';
let prepared=null, savedConfig=null, settingsBusy=false, pairingBusy=false,cameraProfileActive=false,cameraProfileTimer=null;
let pairStep=1, lockedUntil=0, retryConfirmation=false;
const settingsFields=['receiver','port','profile','glove_color','camera','camera_fps','camera_buffers','camera_backend','camera_exposure','camera_manual_exposure','camera_manual_gain'];
function syncCameraOptions(options,selected){const menu=$('camera'),wanted=String(selected??menu.value??'auto'),items=Array.isArray(options)?options:[];menu.replaceChildren();for(const item of items){if(!item||typeof item.value!=='string'||typeof item.label!=='string')continue;const option=document.createElement('option');option.value=item.value;option.textContent=item.label;menu.append(option)}if(!menu.options.length){const option=document.createElement('option');option.value='auto';option.textContent='Automatic — choose the connected camera';menu.append(option)}if(!Array.from(menu.options).some(option=>option.value===wanted)){const option=document.createElement('option');option.value=wanted;option.textContent=`Saved camera ${wanted} — currently unavailable`;menu.append(option)}menu.value=wanted}
function syncExposureFields(){const manual=$('camera_exposure').value==='manual';$('camera-manual-settings').hidden=!manual;$('camera_manual_exposure').required=manual;$('camera_manual_gain').required=manual}
async function api(path,payload,timeoutMs=0){
  const options=payload===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
  if(path==='/api/attract')options.headers['X-VirtualGlove-Action']='attract';
  if(path==='/api/camera-profile'&&payload!==undefined)options.headers['X-VirtualGlove-Action']='camera-profile';
  const controller=timeoutMs?new AbortController():null;
  const timer=controller?setTimeout(()=>controller.abort(),timeoutMs):null;
  if(controller)options.signal=controller.signal;
  try{const response=await fetch(path,options);let result;
  try{result=await response.json()}catch(e){throw Error('The Controller returned an unreadable response. Try again.')}
  if(!response.ok)throw Error(result.error||'The request could not be completed.');
  return result;}finally{if(timer!==null)clearTimeout(timer)}
}
async function action(button,notice,work){
  button.disabled=true;$(notice).textContent='Working…';
  try{await work()}catch(e){$(notice).textContent=e.message||'Connection lost. Try again.'}finally{button.disabled=false}
}
async function load(updateFields=false){
  const c=await api('/api/config');
  if(c.camera_manual_exposure==null)c.camera_manual_exposure=78;if(c.camera_manual_gain==null)c.camera_manual_gain=96;
  if(updateFields){syncCameraOptions(c.camera_options,c.camera);for(const k of settingsFields)$(k).value=String(c[k]??'');syncExposureFields();$('matrix-attract').value=c.matrix_attract||'on';$('connection-fields').disabled=false;$('camera-fields').disabled=false;}
  $('paired').textContent=c.connection_configured?'Connection and pairing key saved. Use pairing below if RetroPie has not received this key.':'Enter your console address and pair with RetroPie. Local play and Glove Academy work without pairing.';
  $('status-destination').textContent=c.receiver||'Not configured';
  savedConfig=c;
  renderPairing();
  $('setup-retry').hidden=true;
}
async function initialLoad(){$('notice').textContent='Loading saved settings…';$('camera-notice').textContent='';try{await load(true);$('notice').textContent=''}catch(e){$('notice').textContent='Could not load saved settings. '+e.message;$('setup-retry').hidden=false}}
$('setup-retry').onclick=initialLoad;initialLoad();
function indicator(id,state,label){const item=$(id);item.dataset.state=state;item.querySelector('strong').textContent=label}
function controllerOutputStatus(w){
  const waitingForGame=w.controller_enabled&&!w.controller_context_active,outputPaused=w.practice_mode||w.profile==='off'||w.vision_profile==='off';
  const label=w.controller_request_pending?'Request pending':w.practice_mode?'Paused for practice':!w.controller_enabled?'Stopped':waitingForGame?'Armed — waiting for game':outputPaused?'Ready when gestures resume':w.receiver_available===false?'Receiver unavailable':w.receiver_available===true?'Delivering':'Starting';
  const state=w.controller_enabled&&(w.receiver_available===true||waitingForGame||outputPaused)?'good':w.controller_enabled&&w.receiver_available===false?'bad':'unknown';
  return {label,state};
}
async function refreshStatus(){
  if(document.hidden)return;
  const [connections,worker,cameras]=await Promise.allSettled([api('/api/connection-status',undefined,3500),api('/status',undefined,3500),api('/api/config',undefined,3500)]);
  if(cameras.status==='fulfilled')syncCameraOptions(cameras.value.camera_options,$('camera').value);
  if(connections.status==='fulfilled'){
    const c=connections.value,unknown=c.console_configured?'Checking…':'Not configured';
    indicator('status-app','good','Running');
    indicator('status-console',c.console_service===true?'good':c.console_service===false?'bad':'unknown',c.console_service===true?'Reachable':c.console_service===false?'Unreachable':unknown);
    indicator('status-auth',c.console_authenticated===true?'good':c.console_authenticated===false?'bad':'unknown',c.console_authenticated===true?'Confirmed':c.console_authenticated===false?'Not confirmed':unknown);
    indicator('status-wifi',c.networking==='connected'?'good':c.networking==='disconnected'?'bad':'unknown',({connected:'Connected',disconnected:'Disconnected',unavailable:'Unavailable'}[c.networking]||'Unavailable'));
    $('connection-status-note').textContent=(c.checked_seconds_ago==null?'Console check pending. ':'Console checked '+Math.round(c.checked_seconds_ago)+' seconds ago. ')+'These checks do not confirm that a game received input.';
  }else{
    indicator('status-app',worker.status==='fulfilled'?'good':'bad',worker.status==='fulfilled'?'Running':'Check failed');
    for(const id of ['status-console','status-auth','status-wifi'])indicator(id,'unknown','Unavailable');
    $('connection-status-note').textContent='Could not refresh connection checks. Retrying automatically; no settings were changed.';
  }
  if(worker.status==='fulfilled'){
    const w=worker.value;
    $('status-active-destination').textContent=w.receiver_available===true&&w.receiver_active_address?`Authenticated at ${w.receiver_active_address}`:w.controller_enabled&&w.controller_context_active?'Searching for the paired console':'Not active';
    const trackingLabel=({active:'Active',starting:'Starting',idle:'Idle',error:'Needs attention'}[w.vision_state]||(w.worker_running?'Starting':'Unavailable'));
    indicator('status-tracking',w.vision_state==='active'?'good':w.vision_state==='error'||!w.worker_running?'bad':'unknown',trackingLabel);
    const output=controllerOutputStatus(w);
    indicator('status-output',output.state,output.label);
    const actual=Number(w.camera_fps),requested=w.camera_fps_requested;
    const backend=w.capture_backend==='direct-v4l2'?'Direct V4L2':w.capture_backend==='opencv'?'OpenCV':'—',fallback=w.capture_backend_fallback?` Direct mode fell back safely: ${w.capture_backend_fallback}.`:'';
    let exposure;if(w.camera_exposure_mode==='manual'||w.camera_exposure_mode==='manual-test')exposure=w.camera_exposure_applied?`manual exposure ${w.camera_manual_exposure}, gain ${w.camera_manual_gain} applied`:`manual settings unavailable; automatic fallback${w.camera_control_error?` (${w.camera_control_error})`:''}`;else exposure=w.camera_exposure_mode==='auto'?'automatic exposure':w.camera_exposure_applied?'automatic fixed-rate exposure applied':'automatic fixed-rate exposure unavailable';
    const buffers=Number(w.camera_buffers_requested),bufferText=Number.isFinite(buffers)?` Buffers: ${buffers}.`:'';
    $('camera-rate-status').textContent=(Number.isFinite(actual)&&actual>0?(requested!=='auto'&&Number(requested)!==actual?`Requested ${requested} fps; this camera is delivering ${actual} fps.`:`Camera is delivering ${actual} fps.`):'Camera rate is unavailable.')+bufferText+` Reader: ${backend}; ${exposure}.`+fallback;
  }else{$('status-active-destination').textContent='Unavailable';indicator('status-tracking','bad','Unavailable');indicator('status-output','bad','Unavailable')}
}
async function statusLoop(){try{await refreshStatus()}finally{setTimeout(statusLoop,5000)}}statusLoop();
$('support-report').onclick=async()=>{const button=$('support-report');button.disabled=true;$('support-report-note').textContent='Preparing system report…';try{const report=await api('/api/support-report',undefined,5000),blob=new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'}),link=document.createElement('a'),day=new Date().toISOString().slice(0,10);link.href=URL.createObjectURL(blob);link.download=`virtualglove-system-report-${day}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);$('support-report-note').textContent='System report downloaded. It contains no video, secrets, personal hand data, ROM name, or network address.'}catch(e){$('support-report-note').textContent='Could not prepare the report. '+e.message}finally{button.disabled=false}};
function method(){return document.querySelector('input[name="pair-method"]:checked').value}
function methodLabel(){return method()==='ssh'?'SSH password':'One-time code'}
function dirtySettings(){return !savedConfig||settingsFields.some(k=>String($(k).value).trim()!==String(savedConfig[k]))||$('rotate_token').checked}
function windowActive(){return performance.now()<lockedUntil}
function validConfirmation(){return !!prepared&&windowActive()&&$('verified').checked&&/^[0-9]{6}$/.test($('device-code').value)}
function clearSecrets(){for(const id of ['device-code','pair-code','pair-password'])$(id).value='';$('verified').checked=false}
function focusPairing(id){$(id).focus();$(id).scrollIntoView({block:'center'})}
function pairNotice(message,focus=false){$('pair-notice').textContent=message;if(focus)focusPairing('pair-notice')}
function moveTo(step){pairStep=step;renderPairing();focusPairing(step===4?'pair-success-heading':'pair-heading-'+step)}
function renderPairing(){
 const active=windowActive(),blocked=!savedConfig?.connection_configured||dirtySettings()||settingsBusy;
 $('pair-destination').textContent=savedConfig?.receiver||'Not configured';
 $('pair-prerequisite').textContent=!savedConfig?'Load your saved settings before pairing.':!savedConfig.connection_configured?'Enter your console address above and select Save connection before pairing.':dirtySettings()?'You have unsaved changes. Save them above before pairing.':'';
 $('pair-change').hidden=active||pairingBusy;
 $('connection-fields').disabled=!savedConfig||active||pairingBusy||settingsBusy;$('camera-fields').disabled=!savedConfig||active||pairingBusy||settingsBusy;
 $('pair-methods').disabled=!secure||active||pairingBusy||blocked;
 for(let n=1;n<=3;n++){$('pair-step-'+n).hidden=pairStep!==n||(n===3&&pairingBusy);$('pair-progress-'+n).toggleAttribute('aria-current',pairStep===n);if(pairStep===n)$('pair-progress-'+n).setAttribute('aria-current','step')}
 $('pair-success').hidden=pairStep!==4;
 $('pair-pending').hidden=!(pairingBusy&&pairStep===3);
 $('pair-summary').textContent=pairStep>1?(savedConfig?.receiver||'Not configured')+' · '+methodLabel()+(pairStep>=3?' · Controller confirmation entered':''):'';
 $('pair-timer').hidden=!active||pairStep===4||pairingBusy;
 if(active)$('pair-timer').textContent='Confirmation window: '+Math.ceil((lockedUntil-performance.now())/1000)+' seconds remaining. Console and method are fixed until it ends.';
 $('pair-begin').disabled=!secure||blocked||pairingBusy;
 $('pair-confirm-fields').disabled=!prepared||!active||pairingBusy;
 $('pair-confirm-next').hidden=retryConfirmation;
 $('pair-confirm-next').disabled=!validConfirmation()||pairingBusy||blocked;
 $('pair-restart').hidden=!retryConfirmation;
 $('pair-restart').disabled=pairingBusy||blocked;
 $('pair-method-back').hidden=!retryConfirmation||active;
 $('pair-method-back').disabled=pairingBusy;
 $('pair-credentials').disabled=pairStep!==3||!validConfirmation()||pairingBusy;
 $('pair-password').disabled=method()!=='ssh'||pairStep!==3||!validConfirmation()||pairingBusy;
 $('pair-code-fields').hidden=method()!=='code';$('pair-ssh-fields').hidden=method()!=='ssh';
 $('pair-submit').disabled=pairStep!==3||!validConfirmation()||blocked||pairingBusy;
 const submitLabel=pairingBusy&&pairStep===3?'Pairing…':'Pair with RetroPie';
 if($('pair-submit').textContent!==submitLabel)$('pair-submit').textContent=submitLabel;
 $('pair-review').disabled=pairingBusy;
 // Keep the live status outside any aria-busy region so progress is announced immediately.
 for(const id of ['camera','camera_fps','camera_buffers','camera_backend','camera_exposure','camera_manual_exposure','camera_manual_gain','glove_color','camera-save'])$(id).disabled=cameraProfileActive;
}
function expirePairing(){
 if(pairingBusy)return;
 if(prepared&&!windowActive()){
  prepared=null;clearSecrets();retryConfirmation=true;
  $('pair-notice').textContent='Controller confirmation expired. Start a new confirmation to try again.';moveTo(2);
 }else renderPairing();
}
async function beginPairing(){
 if(pairingBusy||settingsBusy||!secure||!savedConfig?.connection_configured||dirtySettings())return;
 pairingBusy=true;clearSecrets();prepared=null;renderPairing();$('pair-notice').textContent='Displaying the Controller ID and PIN…';
 const host=savedConfig.receiver,chosen=method();
 try{
  const started=performance.now(),x=await api('/api/pair/begin',{host,method:chosen});
  if(!Number.isFinite(x.expires_in)||x.expires_in<=0||!x.certificate_id)throw Error('Confirmation is unavailable. Try again.');
  lockedUntil=started+x.expires_in*1000;prepared={host,method:chosen};retryConfirmation=false;
  $('pair-confirmation').textContent='The Controller matrix shows ID '+x.certificate_id+', then a six-digit approval PIN. Compare the browser certificate with the physical matrix before entering that PIN.';
  $('pair-notice').textContent='';moveTo(2);
 }catch(e){retryConfirmation=pairStep===2;$('pair-notice').textContent=e.message||'Could not start confirmation. Try again.'}
 finally{pairingBusy=false;expirePairing()}
}
$('secure-note').textContent=secure?'Pair this Controller with your saved RetroPie console. Both methods use a physical confirmation on the Controller matrix.':'Pairing requires the secure Setup page.';
$('pair-wizard').hidden=!secure;
if(!secure){const target='https://'+location.hostname+':8443/setup',a=document.createElement('a');a.href=target;a.textContent='Open secure Setup';a.className='button';$('secure-note').append(' ',a);$('trust-download').href=target;$('trust-download').removeAttribute('download');$('trust-download').textContent='Open secure Setup first';$('trust-note').textContent='The trust certificate is available only through secure Setup.'}else $('trust-note').textContent='After trusting it, reopen https://'+location.hostname+':8443/setup.';
$('pair-change').onclick=()=>{$('receiver').focus()};
for(const id of settingsFields.concat('rotate_token'))$(id).addEventListener('input',()=>{if(id==='camera_exposure')syncExposureFields();if(pairStep===4){pairStep=1;clearSecrets()}renderPairing()});
for(const el of document.querySelectorAll('input[name="pair-method"]'))el.onchange=()=>{clearSecrets();renderPairing()};
$('pair-begin').onclick=beginPairing;$('pair-restart').onclick=beginPairing;
$('pair-method-back').onclick=()=>{if(!windowActive()&&!pairingBusy){retryConfirmation=false;clearSecrets();moveTo(1)}};
$('verified').onchange=()=>{if(!$('verified').checked)$('pair-password').value='';renderPairing();if($('verified').checked)$('device-code').focus()};
for(const id of ['device-code','pair-code','pair-user','pair-password'])$(id).oninput=()=>{if(pairStep===3)pairNotice('');renderPairing()};
$('pair-confirm-next').onclick=()=>{if(validConfirmation()){moveTo(3);$(method()==='ssh'?'pair-password':'pair-code').focus()}};
$('pair-review').onclick=()=>{if(!pairingBusy){$('pair-password').value='';moveTo(2)}};
$('pair-submit').onclick=async()=>{
 if($('pair-submit').disabled||pairingBusy||!validConfirmation()||dirtySettings())return;
 const chosen=prepared.method;
 if(chosen==='code'&&!$('pair-code').value.trim()){pairNotice('Enter the RetroPie one-time code from the command shown above, then select Pair with RetroPie.',true);return}
 if(chosen==='ssh'&&(!$('pair-user').value.trim()||!$('pair-password').value)){pairNotice('Enter your RetroPie username and SSH password, then select Pair with RetroPie.',true);return}
 const payload={host:prepared.host,device_code:$('device-code').value};
 if(chosen==='ssh'){payload.username=$('pair-user').value.trim();payload.password=$('pair-password').value}else payload.code=$('pair-code').value.trim();
 pairingBusy=true;renderPairing();pairNotice('Pairing in progress. Waiting for RetroPie…');focusPairing('pair-pending-heading');
 try{const result=await api('/api/pair/'+chosen,payload);if(result.paired!==true)throw Error('The Controller did not confirm pairing.');prepared=null;lockedUntil=0;clearSecrets();$('pair-notice').textContent='Pairing complete. The RetroPie receiver was restarted.';moveTo(4)}
 catch(e){prepared=null;clearSecrets();retryConfirmation=true;$('pair-notice').textContent=(e.message||'Connection lost. Pairing could not be confirmed.')+' Start a new Controller confirmation before retrying.';moveTo(2);focusPairing('pair-notice')}
 finally{payload.password='';payload.code='';payload.device_code='';pairingBusy=false;expirePairing()}
};
window.addEventListener('pagehide',()=>{clearSecrets();prepared=null;retryConfirmation=true;pairStep=2});
window.addEventListener('pageshow',()=>{expirePairing()});
setInterval(expirePairing,500);
function cameraResultText(result){
 const age=Number.isFinite(result.sample_age_p95_ms)?`${result.sample_age_p95_ms} ms response`:'response unavailable',continuity=Math.round((result.continuity||0)*100);
 const weak=result.valid&&continuity<80;
 return `${result.name}: ${continuity}% hand continuity, ${age}${result.valid&&!weak?'':` — not recommended${result.error?`: ${result.error}`:weak?': hand visibility was too low':''}`}`;
}
function renderCameraProfile(state){
 const panel=$('camera-profile-panel'),results=$('camera-profile-results'),recommendation=state.recommendation;
 const running=state.active===true,needsStop=running||state.phase==='restoring'||state.phase==='error';
 cameraProfileActive=needsStop;panel.hidden=state.phase==='idle';$('camera-profile-start').hidden=needsStop;$('camera-profile-cancel').hidden=!needsStop;
 $('camera-profile-step').textContent=running?`Camera test ${state.candidate||0} of ${state.total||0}`:state.phase==='complete'?'Camera test complete':state.phase==='cancelled'?'Camera test cancelled':state.phase==='error'?'Camera test needs attention':'';
 $('camera-profile-instruction').textContent=state.error||state.instruction||'';
 const view=$('camera-profile-view'),frame=$('camera-profile-frame'),showView=running&&['countdown','measuring'].includes(state.phase);
 view.hidden=!showView;
 if(showView&&!frame.getAttribute('src'))frame.src=frame.dataset.src+'?t='+Date.now();
 if(!showView&&frame.getAttribute('src'))frame.removeAttribute('src');
 const cue=String(state.cue||'ready');view.dataset.cue=cue;
 $('camera-profile-cue').textContent=cue==='sweep'?'Sweep smoothly between opposite corners':cue==='edge'?'Touch an edge, then return to centre':cue==='centre'?'Keep your whole hand near the centre':'Get ready';
 const cueRemaining=Math.max(0,Number(state.cue_remaining)||0),candidateRemaining=Math.max(0,Number(state.candidate_remaining)||0);
 $('camera-profile-countdown').textContent=String(cueRemaining);
 $('camera-profile-time').textContent=showView?(state.phase==='countdown'?'Starting in '+cueRemaining+'…':cueRemaining+' second'+(cueRemaining===1?'':'s')+' left for this step · '+candidateRemaining+' seconds left in this camera setting'):'';
 const total=Math.max(1,Number(state.total)||1),candidate=Math.max(0,Number(state.candidate)||0),candidateProgress=Math.max(0,Math.min(1,Number(state.candidate_progress)||0));$('camera-profile-progress').value=state.phase==='complete'?1:Math.min(1,(Math.max(0,candidate-1)+candidateProgress)/total);
 results.replaceChildren();for(const result of state.results||[]){const item=document.createElement('li');item.textContent=cameraResultText(result);if(result.valid&&(result.continuity||0)>=.8)item.className='camera-profile-good';results.append(item)}
 $('camera-profile-recommendation').textContent=recommendation?`Pixel Pal recommends ${recommendation.name}. Your previous settings are still active until you choose Use recommended settings.`:state.phase==='complete'?'Pixel Pal did not find a safe improvement. Your camera settings were left unchanged.':'';
 $('camera-profile-apply').hidden=!(state.phase==='complete'&&recommendation);renderPairing();
}
async function pollCameraProfile(){
 if(cameraProfileTimer!==null){clearTimeout(cameraProfileTimer);cameraProfileTimer=null}
 try{const state=await api('/api/camera-profile');renderCameraProfile(state);if(state.active)cameraProfileTimer=setTimeout(pollCameraProfile,600)}catch(e){$('camera-profile-instruction').textContent='Camera test status is temporarily unavailable. Your saved settings are protected.'}
}
$('camera-profile-start').onclick=async()=>{
 if(cameraProfileActive||settingsBusy||!confirm('Start a camera test? Controller output will stop while Pixel Pal compares settings for about three minutes.'))return;
 try{renderCameraProfile(await api('/api/camera-profile',{action:'begin'}));cameraProfileTimer=setTimeout(pollCameraProfile,600)}catch(e){$('camera-profile-panel').hidden=false;$('camera-profile-instruction').textContent=e.message||'The camera test could not start.'}
};
$('camera-profile-cancel').onclick=async()=>{const button=$('camera-profile-cancel');button.disabled=true;try{renderCameraProfile(await api('/api/camera-profile',{action:'stop'}));cameraProfileTimer=setTimeout(pollCameraProfile,600)}catch(e){$('camera-profile-instruction').textContent=e.message||'The camera test could not be stopped.'}finally{button.disabled=false}};
$('camera-profile-apply').onclick=async()=>{try{await api('/api/camera-profile',{action:'apply'});$('camera-profile-recommendation').textContent='Recommended settings saved. Tracking is restarting.';$('camera-profile-apply').hidden=true;await load(true)}catch(e){$('camera-profile-recommendation').textContent=e.message||'The recommendation could not be saved.'}};
pollCameraProfile();
const saveSettings=e=>{e.preventDefault();if(settingsBusy||pairingBusy||windowActive())return;if($('rotate_token').checked&&!confirm('Replace the pairing key and stop controller output? You must pair with RetroPie again.'))return;const noticeId=e.submitter?.id==='camera-save'?'camera-notice':'notice';$(noticeId==='notice'?'camera-notice':'notice').textContent='';settingsBusy=true;action(e.submitter,noticeId,async()=>{
 try{const payload={receiver:$('receiver').value.trim(),port:Number($('port').value),profile:$('profile').value,glove_color:$('glove_color').value,camera:$('camera').value.trim(),camera_fps:$('camera_fps').value,camera_buffers:$('camera_buffers').value,camera_backend:$('camera_backend').value,camera_exposure:$('camera_exposure').value,camera_manual_exposure:Number($('camera_manual_exposure').value),camera_manual_gain:Number($('camera_manual_gain').value),rotate_token:$('rotate_token').checked};
 renderPairing();await api('/api/config',payload);$('rotate_token').checked=false;$(noticeId).textContent=noticeId==='camera-notice'?'Camera settings saved. Tracking is restarting.':'Connection saved. Tracking is restarting.';await load(true);
 }finally{settingsBusy=false;renderPairing()}
})};
$('form').onsubmit=saveSettings;$('camera-form').onsubmit=saveSettings;
$('test').onclick=()=>action($('test'),'notice',async()=>{const x=await api('/api/test-connection',{receiver:$('receiver').value.trim()});$('notice').textContent=`Address resolved: ${x.receiver} → ${x.address}. Pairing and controller delivery have not been tested.`});
$('attract-form').onsubmit=e=>{e.preventDefault();action(e.submitter,'attract-notice',async()=>{await api('/api/attract',{mode:$('matrix-attract').value});$('attract-notice').textContent='Attract mode saved. Tracking was not restarted.'})};
{{DOCTOR_SCRIPT}}
renderPairing();
})();"""


from .player_web import PLAYER_CONTENT, PLAYER_SCRIPT

SETUP_CONTENT = SETUP_CONTENT.replace("{{PLAYER_CONTENT}}", PLAYER_CONTENT)
SETUP_SCRIPT += "\n" + PLAYER_SCRIPT

from .joystick_web import JOYSTICK_CONTENT, JOYSTICK_SCRIPT

SETUP_CONTENT = SETUP_CONTENT.replace("{{JOYSTICK_CONTENT}}", JOYSTICK_CONTENT)
SETUP_SCRIPT += "\n" + JOYSTICK_SCRIPT


from .connection_doctor_web import DOCTOR_CONTENT, DOCTOR_SCRIPT

SETUP_CONTENT = SETUP_CONTENT.replace("{{DOCTOR_CONTENT}}", DOCTOR_CONTENT)
SETUP_SCRIPT = SETUP_SCRIPT.replace("{{DOCTOR_SCRIPT}}", DOCTOR_SCRIPT)
