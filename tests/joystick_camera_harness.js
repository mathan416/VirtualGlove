const vm=require('node:vm'),assert=require('node:assert/strict');
let input='';process.stdin.on('data',s=>input+=s);process.stdin.on('end',async()=>{
const {script,scenario,samples=[]}=JSON.parse(input),nodes={},events={},intervals=[],calls=[];let now=0,count=0,saved=.6,own=false,other=true,vision='starting',fail=false,releaseFail=false,delay=false,resolveEnable=null,statusPatch={},active="default",generation=0,saveFail=false;
function node(){return {value:'.6',textContent:'',disabled:false,hidden:true,attrs:{},children:{},naturalWidth:640,naturalHeight:480,classList:{toggle(){}},querySelector(q){return this.children[q]||(this.children[q]=node());},setAttribute(k,v){this.attrs[k]=v},getAttribute(k){return this.attrs[k]||null},removeAttribute(k){delete this.attrs[k]},set src(v){this.attrs.src=v},get src(){return this.attrs.src}};}
const $=id=>nodes[id]||(nodes[id]=node());
const ctx={JSON,Date,Error,Object,String,Number,Math,Promise,Set,AbortController,performance:{now:()=>now},crypto:{randomUUID:()=> 'joystick-session-'+(++count)},document:{hidden:false,getElementById:$},window:{addEventListener:(key,f)=>events[key]=f},location:{reload(){}},setInterval:(f,ms)=>intervals.push({f,ms}),setTimeout:()=>1,clearTimeout(){},fetch:async(path,options={})=>{
 const data=options.body?JSON.parse(options.body):null;calls.push({path,data,keepalive:options.keepalive});let result={},ok=true;
 if(path==='/api/players'){
  if(data.action==='joystick_deadzone'){if(saveFail)throw Error('Save failed');saved=data.value;generation++;}
  result={active,generation,players:[{id:'default',name:'Player'},{id:'second',name:'Second'}],joystick:{deadzone:saved,effective_deadzone:Math.max(saved,.3),jitter_protected:false,hand_size_protected:saved<.3,hand_size_minimum:.3}};
 }else if(path==='/api/practice'){
  assert.equal(Object.keys(data).sort().join(','),'enabled,session');assert(data.session.startsWith('joystick-session-'));
  if(data.enabled){if(delay){await new Promise(r=>resolveEnable=r);delay=false;}if(fail)throw Error('offline');own=scenario!=='rejected';}
  else{if(releaseFail)throw Error('release offline');own=false;}
  result={practice_mode:other||own,session_active:own};
 }else if(path==='/status'){if(fail)throw Error('status offline');const palm=statusPatch.palm_position||{x:.1,y:.5},effective=Math.max(saved,.3),lo=.5-effective/2,hi=.5+effective/2;result={vision_state:vision,practice_mode:other||own,detected:true,calibrated:true,calibrating:false,player:{active,generation,needs_center:false},dpad:{left:palm.x<lo,right:palm.x>hi,up:palm.y<lo,down:palm.y>hi},palm_position:palm,joystick_grid:{anchor:{x:.5,y:.5},center:{x:.5,y:.5},half_size:effective/2,minimum_size:.3},recognition:{menu_guard:false},buttons:{},menu_gesture:{pose:null}};Object.assign(result,statusPatch);}
 else if(path==='/calibrate'){assert(own&&vision==='active');result={};}
 else throw Error('Unexpected API '+path);
 return {ok,json:async()=>result};
}};
vm.runInNewContext(script,ctx);
const settle=()=>new Promise(r=>setImmediate(r));
async function poll(){now+=500;await intervals.find(x=>x.ms===500).f();await settle();}
async function heartbeat(){now+=2000;await intervals.find(x=>x.ms===2000).f();await settle();}
const image=$('joystick-camera'),button=$('joystick-camera-toggle'),left=()=> $('joystick-directions').querySelector('[data-direction=left]').textContent;
await settle();assert.equal(button.textContent,'Turn on camera');assert.equal($('joystick-center').disabled,true);assert(image.hidden&&!image.src);assert.equal(calls.filter(x=>x.path==='/api/practice').length,0);assert.equal(calls.filter(x=>x.path==='/status').length,0);
if(scenario==='pagehide-pending'){
 delay=true;const opening=button.onclick();await settle();events.pagehide();resolveEnable();await opening;await settle();assert(image.hidden&&!image.src);assert.equal(button.textContent,'Turn on camera');assert(calls.some(x=>x.path==='/api/practice'&&!x.data.enabled&&x.keepalive));process.stdout.write('pending cleanup passed');return;
}
if(scenario==='acquire-failure')fail=true;
await button.onclick();await settle();
if(scenario==='acquire-failure'){assert(image.hidden&&!image.src);assert.equal(left(),'Left: off');fail=false;await heartbeat();}
if(scenario==='rejected'){assert.equal(button.textContent,'Turn on camera');assert(image.hidden&&!image.src);assert.equal(left(),'Left: off');assert.equal(other,true);process.stdout.write('other lease is insufficient');return;}
assert.equal(button.textContent,'Turn off camera');assert(image.hidden&&!image.src);assert(!$('joystick-live').textContent.includes('test active'));
vision='active';await poll();assert(!image.hidden&&image.src.startsWith('/stream'));assert.equal(left(),'Left: pressed');
const id=calls.find(x=>x.path==='/api/practice').data.session;await heartbeat();assert(calls.filter(x=>x.path==='/api/practice'&&x.data.enabled).length>=2);assert(calls.filter(x=>x.path==='/api/practice').every(x=>x.data.session===id));
if(scenario==='center'){
 const center=$('joystick-center'),size=$('joystick-size');image.onload();assert.equal(center.disabled,false);size.value='.4';size.oninput();
 await center.onclick();await settle();assert.equal(calls.filter(x=>x.path==='/calibrate').length,1);assert.equal(button.disabled,true);assert.equal(center.textContent,'Centering…');
 center.onclick();await settle();assert.equal(calls.filter(x=>x.path==='/calibrate').length,1,'centering is single-flight');
 statusPatch={calibrating:true,calibrated:false};await poll();assert.equal(center.textContent,'Centering…');assert($('joystick-center-status').textContent.includes('relaxed open hand'));
 generation++;statusPatch={calibrating:false,calibrated:true,player:{active,generation,needs_center:false},joystick_grid:{anchor:{x:.4,y:.55},center:{x:.4,y:.55},half_size:.3,minimum_size:.3}};await poll();
 assert.equal(center.textContent,'Center saved ✓');assert.equal(center.disabled,false);assert.equal(button.disabled,false);assert.equal(Number(size.value),.4);assert($('joystick-value').textContent.includes('Unsaved preview'));assert(!image.hidden);assert($('joystick-center-status').textContent.includes('grid now uses this position'));
 statusPatch={};
}
if(scenario==='grid'){
 const overlay=$('joystick-grid'),region=$('joystick-region');
 const hidden=n=>Object.prototype.hasOwnProperty.call(n.attrs,'hidden');
 assert(hidden(overlay),'wait for the camera image to load');image.onload();assert(!hidden(overlay));assert.equal(region.attrs['data-region'],'3');
 for(let row=0;row<3;row++)for(let col=0;col<3;col++){
  await heartbeat();statusPatch={palm_position:{x:.5,y:.5},dpad:{left:col===0,right:col===2,up:row===0,down:row===2}};await poll();
  assert.equal(region.attrs['data-region'],String(row*3+col));assert(!hidden(region));
 }
 statusPatch={palm_position:{x:.8,y:.2},dpad:{left:false,right:false,up:false,down:false}};await heartbeat();await poll();assert.equal(region.attrs['data-region'],'4','boundary belongs to center');
 for(const patch of [
  {palm_position:{x:.9,y:.5}},
  {recognition:{menu_guard:true}}, {menu_gesture:{pose:'start'}}, {buttons:{select:true}},
  {detected:false}, {palm_position:null}, {dpad:{left:true,right:true,up:false,down:false}}
 ]){await heartbeat();statusPatch={palm_position:{x:.5,y:.5},dpad:{left:false,right:false,up:false,down:false},...patch};await poll();assert(hidden(region),JSON.stringify(patch));}
 for(const patch of [{calibrated:false},{calibrating:true},{joystick_grid:null},{player:{needs_center:true}},{calibration_save_error:'disk'}]){
  statusPatch=patch;await heartbeat();await poll();assert(hidden(overlay));assert(hidden(region));
 }
 saved=1;statusPatch={palm_position:{x:.02,y:.97}};await heartbeat();await poll();image.onload();
 assert.equal($('joystick-grid-left').attrs.x1,'0');assert.equal($('joystick-grid-bottom').attrs.y1,'1');assert.equal(region.attrs.x,'0');assert.equal(region.attrs.width,'1');assert.equal(region.attrs.height,'1');saved=.6;

 statusPatch={joystick_grid:{anchor:{x:.5,y:.5},center:{x:NaN,y:.5},half_size:.1,minimum_size:.3}};await poll();assert(hidden(overlay));
 statusPatch={};await heartbeat();await poll();image.onload();assert(!hidden(overlay));image.onerror();assert(hidden(overlay)&&hidden(region));
}
if(scenario==='failure'){fail=true;await heartbeat();assert(image.hidden&&!image.src);assert.equal(left(),'Left: off');fail=false;await heartbeat();await poll();assert(!image.hidden);}
if(scenario==='stream'){image.onerror();assert(image.hidden&&!image.src);assert.equal(left(),'Left: off');await poll();assert(!image.src);now+=1600;await poll();assert(image.src.startsWith('/stream'));}
if(scenario==='draft'||scenario==='agreement'){
 const size=$('joystick-size'),overlay=$('joystick-grid'),region=$('joystick-region');
 const hidden=n=>Object.prototype.hasOwnProperty.call(n.attrs,'hidden');
 const pill=k=>$('joystick-directions').querySelector(`[data-direction=${k}]`).textContent;
 function bounds(lo,hi){for(const [id,key,value] of [['left','x1',lo],['right','x1',hi],['top','y1',lo],['bottom','y1',hi]])assert.equal(Number($('joystick-grid-'+id).attrs[key]),value);}
 if(scenario==='agreement'){
  image.onload();
  for(const sample of samples){await heartbeat();statusPatch={palm_position:sample.palm,joystick_grid:sample.grid,dpad:{left:true,right:true,up:true,down:true}};await poll();size.value=String(sample.size);const before=calls.length;size.oninput();assert.equal(calls.length,before);
   for(const key of ['left','right','up','down'])assert.equal(pill(key).endsWith(': pressed'),sample.dpad[key],JSON.stringify(sample));
   assert.equal(region.attrs['data-region'],String((sample.dpad.up?0:sample.dpad.down?2:1)*3+(sample.dpad.left?0:sample.dpad.right?2:1)));
  }
 }else{
 statusPatch={palm_position:{x:.15,y:.15}};await poll();image.onload();assert.equal(region.attrs['data-region'],'0');bounds(.2,.8);
 let before=calls.length;size.value='.8';size.oninput();assert.equal(calls.length,before,'slider redraw must not request data');assert.equal(saved,.6);assert.equal(region.attrs['data-region'],'4');assert.equal(left(),'Left: off');assert.equal(pill('up'),'Up: off');assert($('joystick-live').textContent.includes('Unsaved preview'));
 before=calls.length;$('joystick-default').onclick();assert.equal(calls.length,before);bounds(.2,.8);assert.equal(region.attrs['data-region'],'0');assert.equal(left(),'Left: pressed');assert.equal(pill('up'),'Up: pressed');
 size.value='.8';size.oninput();await button.onclick();await settle();assert(hidden(overlay));assert.equal(Number(size.value),.8);await button.onclick();await settle();await poll();image.onload();assert.equal(Number(size.value),.8);assert.equal(region.attrs['data-region'],'4','camera restart must retain draft');
 size.value='.6';size.oninput();
 for(let row=0;row<3;row++)for(let col=0;col<3;col++){
  await heartbeat();statusPatch={palm_position:{x:[.1,.5,.9][col],y:[.1,.5,.9][row]},dpad:{left:true,right:true,up:true,down:true}};await poll();
  assert.equal(region.attrs['data-region'],String(row*3+col),'draft uses palm, ignoring saved D-pad');
  for(const [k,on] of Object.entries({left:col===0,right:col===2,up:row===0,down:row===2}))assert.equal(pill(k).endsWith(': pressed'),on);
  assert(Math.abs(Number(region.attrs.width)-[.2,.6,.2][col])<1e-12);assert(Math.abs(Number(region.attrs.height)-[.2,.6,.2][row])<1e-12);
 }
 for(const value of [.6,.1]){
  size.value=String(value);before=calls.length;size.oninput();assert.equal(calls.length,before);const lo=value===.6?.2:.35,hi=value===.6?.8:.65;bounds(lo,hi);
  for(const x of [lo,hi])for(const y of [lo,hi]){await heartbeat();statusPatch={palm_position:{x,y}};await poll();assert.equal(region.attrs['data-region'],'4','exact boundary belongs to center');}
 }
 // The calibrated hand floor enlarges a smaller draft without changing its chosen value.
 statusPatch={palm_position:{x:.34,y:.5}};await poll();bounds(.35,.65);assert.equal(left(),'Left: pressed');assert($('joystick-value').textContent.includes('Effective preview size: 30%'));
 for(const patch of [{recognition:{menu_guard:true}},{buttons:{menu_guard:true}},{buttons:{start:true}},{buttons:{select:true}},{menu_gesture:{pose:'select'}},{detected:false},{palm_position:null}]){
  await heartbeat();statusPatch=patch;await poll();assert(hidden(region));assert.equal(left(),'Left: off');before=calls.length;size.oninput();assert.equal(calls.length,before);assert(hidden(region));
 }
 for(const patch of [{calibrated:false},{calibrating:true},{player:{needs_center:true}},{calibration_save_error:'disk'}, {joystick_grid:null}, {joystick_grid:{anchor:{x:.5,y:.5},center:{x:.2,y:.5},half_size:.3,minimum_size:.3}}]){
  await heartbeat();statusPatch=patch;await poll();size.oninput();assert(hidden(overlay));assert.equal(left(),'Left: off');
 }
 statusPatch={palm_position:{x:0,y:1}};await heartbeat();await poll();size.value='1';size.oninput();bounds(0,1);assert.equal(region.attrs['data-region'],'4');assert.equal(region.attrs.width,'1');assert.equal(region.attrs.height,'1');
 for(const value of ['.09','1.01','NaN']){size.value=value;size.oninput();assert(hidden(overlay));assert.equal(left(),'Left: off');}size.value='.6';size.oninput();
 now+=4500;size.oninput();assert(hidden(overlay));assert.equal(left(),'Left: off','draft must not revive expired feedback');
 statusPatch={};await heartbeat();await poll();image.onload();image.onerror();before=calls.length;size.oninput();assert.equal(calls.length,before);assert(hidden(overlay));assert.equal(left(),'Left: off');
 now+=1600;await heartbeat();await poll();image.onload();fail=true;await heartbeat();size.oninput();assert(hidden(overlay));assert.equal(left(),'Left: off');fail=false;await heartbeat();await poll();image.onload();active='second';generation++;await poll();assert.equal(Number(size.value),.6);assert($('joystick-notice').textContent.includes('discarded'));assert(!$('joystick-value').textContent.includes('Unsaved'));assert.equal(saved,.6);
 }
}
if(scenario==='save'){
 const size=$('joystick-size'),region=$('joystick-region');statusPatch={palm_position:{x:.15,y:.5}};await poll();image.onload();size.value='.75';size.oninput();assert.equal(saved,.6);assert.equal(left(),'Left: off');assert.equal(region.attrs['data-region'],'4');assert($('joystick-value').textContent.includes('Unsaved preview'));
 saveFail=true;await $('joystick-form').onsubmit({preventDefault(){}});assert.equal(saved,.6);assert($('joystick-value').textContent.includes('Unsaved preview'));assert.equal(size.disabled,false);saveFail=false;
 await $('joystick-form').onsubmit({preventDefault(){}});assert.equal(saved,.75);assert(!$('joystick-value').textContent.includes('Unsaved'));assert(image.hidden);
 statusPatch={palm_position:{x:.15,y:.5},joystick_grid:{anchor:{x:.5,y:.5},center:{x:.5,y:.5},half_size:.3,minimum_size:.3}};await poll();image.onload();assert(Object.hasOwn($('joystick-grid').attrs,'hidden'),'wait for saved worker bounds');assert.equal(left(),'Left: off');
 statusPatch={palm_position:{x:.15,y:.5}};await poll();assert.equal(region.attrs['data-region'],'4');assert.equal(left(),'Left: off');assert($('joystick-live').textContent.includes('saved dead-zone settings'));
}
if(scenario==='pagehide'){events.pagehide();await settle();assert(image.hidden&&!image.src);assert.equal(left(),'Left: off');assert(calls.some(x=>x.path==='/api/practice'&&!x.data.enabled&&x.keepalive));assert.equal(other,true);process.stdout.write('pagehide passed');return;}
if(scenario==='release-failure')releaseFail=true;
await button.onclick();await settle();assert.equal(button.textContent,'Turn on camera');assert(image.hidden&&!image.src);assert($('joystick-camera-stage').hidden);assert(Object.prototype.hasOwnProperty.call($('joystick-grid').attrs,'hidden'));assert.equal(left(),'Left: off');assert($('joystick-live').textContent.includes('off'));
if(releaseFail){releaseFail=false;await heartbeat();assert.equal(own,false);}
await poll();assert(image.hidden&&!image.src);assert.equal(other,true);assert(calls.some(x=>x.path==='/api/practice'&&!x.data.enabled));
assert(calls.every(x=>x.path!=='/api/controller'&&x.path!=='/api/config'));
assert.equal(calls.filter(x=>x.path==='/calibrate').length,scenario==='center'?1:0);
assert(calls.filter(x=>x.path==='/api/players').every(x=>x.data.action==='read'||scenario==='save'&&x.data.action==='joystick_deadzone'));
process.stdout.write('camera toggle passed');
});
