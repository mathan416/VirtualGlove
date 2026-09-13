// Execute the real guide without devices or a browser package.
const vm=require('node:vm'),assert=require('node:assert/strict');
let input='';process.stdin.on('data',data=>input+=data);process.stdin.on('end',async()=>{
const {script,scenario}=JSON.parse(input),nodes={},timers=[],calls=[],events={};let now=10000,seq=0;
function node(){return {value:'',disabled:false,hidden:false,textContent:'',children:[],attrs:{},getAttribute(k){return this.attrs[k]||null},removeAttribute(k){delete this.attrs[k]},set src(v){this.attrs.src=v},get src(){return this.attrs.src},replaceChildren(...c){this.children=c}};}
const $=id=>nodes[id]||(nodes[id]=node());
let locked=false,gameStage=false,lease=false,calibrating=false,calibrated=true;
let player={active:'default',generation:0,players:[{id:'default',name:'Existing player'}],needs_center:false,ready_progress:{course:1,completed:scenario==='resumed'?['neutral','left','right','up','down','a','b','start','select','menu_guard']:[],completed_at:null}};
let pose='neutral',game=false,receiver=false,enabled=false,failCalibration=false,pairing=true;
const status=()=>({sequence:seq++,timestamp:now,worker_status_age_seconds:0,worker_running:true,worker_controller_enabled:enabled,controller_enabled:enabled,controller_request_pending:false,practice_mode:lease,vision_state:lease||game?'active':'idle',camera_available:lease||game,calibrating,calibrated,detected:true,player:{active:player.active,generation:player.generation,needs_center:player.needs_center},game_session_active:game,active_profile:game?'super_glove_ball':'off',emulator:game?'lr-nestopia-powerglove':'',input_mode:game?'native':'joystick',controller_context_active:game,receiver_available:receiver,dpad:{left:pose==='left',right:pose==='right',up:pose==='up',down:pose==='down'},finger_active:{thumb:pose==='b',index:pose==='a'},buttons:{},recognition:{menu_guard:pose==='menu_guard'},menu_gesture:{pose:['start','select'].includes(pose)?pose:null,recognized:true}});
const ctx={console,JSON,Date,Error,Object,String,Number,Math,Promise,Set,AbortController,crypto:{randomUUID:()=> 'test-session-123456789'},performance:{now:()=>now},location:{href:'/ready'},document:{getElementById:$,createElement:node},window:{addEventListener:(key,f)=>events[key]=f},setTimeout:(f,delay)=>{const t={f,delay};timers.push(t);return t},clearTimeout:t=>{const i=timers.indexOf(t);if(i>=0)timers.splice(i,1)},fetch:async(path,opts={})=>{
const data=opts.body?JSON.parse(opts.body):null;calls.push({path,data});let result={};let ok=true;
if(path==='/api/ready'){
 if(data.action==='begin'){locked=true;gameStage=false;enabled=false;result={guarded:true}}
 else if(data.action==='status')result={guarded:locked,game_stage:gameStage};
 else if(data.action==='release'){assert(locked);lease=false;if(scenario==='delayed-release'&&!ctx.releasedOnce){ctx.releasedOnce=true;result={released:false,message:'Waiting for practice'};}else{locked=false;gameStage=true;result={released:true};}}
 else if(data.action==='cancel'){lease=false;locked=false;enabled=false;result={released:true}}
 else if(data.action==='arm'){assert(gameStage&&!lease&&!locked&&game);enabled=true;receiver=true;result={armed:true}}
}
else if(path==='/api/players'){
 if(data.action==='select'){assert(locked&&!enabled);player={...player,active:data.id,generation:player.generation+1,needs_center:true,ready_progress:{course:1,completed:[],completed_at:null}};}
 if(data.action==='ready_progress'){assert.equal(data.player,player.active);assert.equal(data.generation,player.generation);assert(!data.progress.completed_at||gameStage);player={...player,ready_progress:data.progress};}
 result=structuredClone(player);
}
else if(path==='/status')result=status();
else if(path==='/api/config')result={receiver:'private.local',port:55355,connection_configured:true};
else if(path==='/api/connection-status')result={console_service:true,console_authenticated:pairing,checked_seconds_ago:0};
else if(path==='/api/practice'){assert(!data.reset);if(data.enabled)assert(locked&&!enabled);lease=data.enabled;result={practice_mode:lease};}
else if(path==='/calibrate'){assert(locked&&lease&&!enabled);if(failCalibration){ok=false;}else{calibrating=true;calibrated=false;}}
else if(path!=='/api/test-connection')throw Error('Unexpected '+path);
return {ok,status:ok?200:503,json:async()=>result};
}};
vm.runInNewContext(script,ctx);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
async function tick(count=1){for(let i=0;i<count;i++){await settle();now+=200;const i=timers.findIndex(t=>t.delay===150);if(i>=0){const t=timers.splice(i,1)[0];await t.f();}await settle();}}
async function click(id){assert.equal($(id).disabled,false,id+' disabled');$(id).onclick();await settle();await tick();}
await settle();await tick(2);
assert.equal(calls[0].path,'/api/ready');assert.equal(calls[0].data.action,'begin');assert(locked&&!enabled&&!lease);
await click('ready-next');await tick(2);assert.equal($('ready-title').textContent,'Console and pairing');
await click('ready-next');await tick(2);assert(lease&&!enabled);
if(scenario==='calibration-failure'){
 failCalibration=true;await click('ready-center');await tick(110);assert.equal($('ready-title').textContent,'Safe camera practice');assert.equal($('ready-next').disabled,true);assert(!enabled);process.stdout.write('calibration failure safe');return;
}
await click('ready-next');
if(scenario==='switch'){
 player={...player,active:'other',generation:1,needs_center:true,ready_progress:{course:1,completed:[],completed_at:null}};await tick(3);assert.equal($('ready-title').textContent,'Choose your player');assert(!enabled);assert.equal(player.ready_progress.completed.length,0);process.stdout.write('switch safe');return;
}
if(scenario!=='resumed'){
 for(const key of ['neutral','left','right','up','down','a','b','start','select','menu_guard']){
  pose='neutral';await tick(5);if(key!=='neutral'){pose=key;await tick(5);pose='neutral';await tick(4);}
 }
}
assert.equal(player.ready_progress.completed.length,10);
assert(!enabled);await click('ready-next');await tick(2);
if(scenario==='delayed-release'){assert.equal($('ready-title').textContent,'Ending practice');assert(!enabled);await click('ready-next');}
assert(!lease&&gameStage);await tick(3);assert.equal($('ready-title').textContent,'Launch a registered game');assert.equal($('ready-next').disabled,true);
game=true;await tick(3);await click('ready-next');await tick(3);
assert.equal($('ready-title').textContent,'Ready to play');assert(player.ready_progress.completed_at);
const release=calls.findIndex(c=>c.path==='/api/ready'&&c.data.action==='release'),arm=calls.findIndex(c=>c.path==='/api/ready'&&c.data.action==='arm');assert(release>=0&&arm>release);
assert(calls.filter(c=>c.path==='/api/players'&&c.data.action!=='read').every(c=>['select','ready_progress'].includes(c.data.action)));
pairing=false;await tick(12);assert.equal($('ready-title').textContent,'Launch a registered game');
process.stdout.write('guide flow safe');
});
