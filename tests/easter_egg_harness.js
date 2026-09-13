const vm=require('node:vm'),assert=require('node:assert/strict');
let input='';process.stdin.on('data',chunk=>input+=chunk);process.stdin.on('end',()=>{
  const {script}=JSON.parse(input),nodes={},timers=[];let now=0,nextTimer=0;
  const node=id=>nodes[id]||(nodes[id]={id,dataset:{},textContent:''});
  const document={hidden:false,getElementById:node};
  const context={window:{},document,Number,Infinity,Date:{now:()=>now},
    setTimeout:(fn,delay)=>{const id=++nextTimer;timers.push({id,fn,delay,cancelled:false});return id},
    clearTimeout:id=>{const timer=timers.find(item=>item.id===id);if(timer)timer.cancelled=true}};
  vm.runInNewContext(script,context);
  const update=context.window.updateEasterEgg,toast=node('spock-toast'),announcement=node('spock-announcement');
  const run=delay=>{for(const timer of timers.filter(item=>item.delay===delay&&!item.cancelled)){timer.cancelled=true;timer.fn()}};
  update({easter_egg:{spock_sequence:0}});
  assert.equal(toast.dataset.visible,undefined);
  now=1000;update({easter_egg:{spock_sequence:1}});assert.equal(toast.dataset.visible,'true');
  run(0);assert.equal(announcement.textContent,'Live long and prosper.');
  run(2500);assert.equal(toast.dataset.visible,undefined);
  now=10000;update({easter_egg:{spock_sequence:2}});assert.equal(toast.dataset.visible,undefined);
  now=31001;update({easter_egg:{spock_sequence:3}});assert.equal(toast.dataset.visible,'true');run(2500);
  document.hidden=true;now=62002;update({easter_egg:{spock_sequence:4}});assert.equal(toast.dataset.visible,undefined);
  document.hidden=false;update({easter_egg:{spock_sequence:4}});assert.equal(toast.dataset.visible,undefined);
  update({easter_egg:{spock_sequence:0}});now=93003;update({easter_egg:{spock_sequence:1}});
  assert.equal(toast.dataset.visible,'true');
  process.stdout.write('easter egg overlay passed');
});
