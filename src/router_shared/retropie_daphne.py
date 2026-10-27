#!/usr/bin/python3
"""Daphne SDL1 input compatibility: consume only Controller Router outputs."""
from pathlib import Path
import os,sys,json,time,subprocess,signal,select,shlex,fcntl
BASE=Path.home()/'.local/share/controller-router/daphne'
ROOT=Path.home()/'RetroPie/roms/daphne'
BIN='/opt/retropie/emulators/daphne/daphne.bin'

def configure(state_root=None,rom_root=None,binary=None):
 global BASE,ROOT,BIN
 if state_root is not None:BASE=Path(state_root)
 if rom_root is not None:ROOT=Path(rom_root)
 if binary is not None:BIN=str(binary)

def command(p,name,frame):
 params=shlex.split((p/(name+'.commands')).read_text())if(p/(name+'.commands')).is_file()else[]
 return [BIN,name,'vldp','-nohwaccel','-framefile',str(frame),'-homedir',str(Path(BIN).parent),'-fullscreen']+params

def routed_buttons(states):
 out=set()
 for player,(b,x,y)in enumerate(states):
  hot=12 in b or (10 in b and 11 in b)
  if hot and 11 in b:out.add(11)
  if hot and 4 in b:out.add(10)
  if hot and 3 in b:out.add(12)
  if 10 in b and not(hot and 11 in b):out.add(4 if player==0 else 9)
  if not hot:
   if 11 in b:out.add(3 if player==0 else 8)
   for source,target in [(0,0),(1,1),(3,2),(6,5),(4,6),(7,7)]:
    if source in b:out.add(target)
 return out
def main():
 assert os.geteuid()!=0,'RUN_AS_ROUTER_USER';p=Path(sys.argv[1]);assert p.is_absolute()and p.is_dir()and ROOT==p.parent and p.suffix in ['.daphne','.dpahne'];name=p.stem;frame=p/(name+'.txt');assert frame.is_file()
 from router_shared.systems import routes
 from router_shared.native_sessions import launch_policy
 manifest=launch_policy()
 if not routes(manifest,'daphne-native','daphne'):
  args=command(p,name,frame);os.execv(BIN,args)
 assert subprocess.run(['systemctl','is-active','--quiet','virtualglove-controller-router']).returncode==0,'CONTROLLER_ROUTER_REQUIRED'
 BASE.mkdir(parents=True,exist_ok=True);(BASE/'runs').mkdir(exist_ok=True)
 with(BASE/'session.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);return play(p,name,frame)
def play(p,name,frame):
 import evdev
 from evdev import ecodes as E
 devices=[];ui=None;child=None;axes={};keys={};identities=[];seen={};buttons={};last_buttons=set();last_xy=None
 stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid());run=BASE/'runs'/stamp;run.mkdir();log=run/'input.jsonl'
 try:
  for n in [1,2]:
   matches=[]
   for q in Path('/sys/class/input').glob('event*'):
    d=q/'device'
    if(d/'name').read_text().strip()=='VirtualGlove Merged Player '+str(n)and int((d/'id/vendor').read_text(),16)==0x1209 and int((d/'id/product').read_text(),16)==0x5650+n:matches.append(q)
   assert len(matches)==1,'ROUTER_OUTPUT_IDENTITY_NOT_UNIQUE';q=matches[0];dev=evdev.InputDevice('/dev/input/'+q.name);devices.append(dev);keys[dev.fd]=set(dev.active_keys());axes[dev.fd]={code:info.value for code,info in dev.capabilities().get(E.EV_ABS,[])};buttons[dev.fd]=sorted(dev.capabilities(absinfo=False)[E.EV_KEY]);identities.append({'player':n,'name':dev.name,'path':dev.path,'vendor':dev.info.vendor,'product':dev.info.product});seen[dev.fd]=0
  caps={E.EV_KEY:list(range(E.BTN_JOYSTICK,E.BTN_JOYSTICK+13)),E.EV_ABS:[(E.ABS_X,evdev.AbsInfo(0,-32768,32767,0,0,0)),(E.ABS_Y,evdev.AbsInfo(0,-32768,32767,0,0,0))]};ui=evdev.UInput(caps,name='Controller Router Daphne',vendor=0x1209,product=0x5661,version=1,phys='controller-router/daphne/'+str(os.getpid()))
  chosen=[]
  for i in range(120):
   chosen=[q for q in Path('/sys/class/input').glob('js*')if(q/'device/name').read_text().strip()=='Controller Router Daphne'and(q/'device/phys').read_text().strip()=='controller-router/daphne/'+str(os.getpid())]
   if len(chosen)==1:break
   time.sleep(.025)
  assert len(chosen)==1,'DAPHNE_COMPAT_JOYSTICK_NOT_READY';js='/dev/input/'+chosen[0].name
  env=os.environ.copy();env.update(SDL_JOYSTICK_DEVICE=js,CONTROLLER_ROUTER_SYSTEM='daphne',DAPHNE_CONTROLLER_ROUTER='1')
  args=command(p,name,frame)
  receipt={'game':str(p),'command':args,'Router_sources':identities,'SDL1_first_joystick':js,'compat_name':'Controller Router Daphne','physical_device_bypass':False,'started':time.time()};(run/'launch.json').write_text(json.dumps(receipt,indent=2)+'\n');child=subprocess.Popen(args,env=env)
  def forward(sig,frame):
   if child.poll()is None:child.send_signal(sig)
  for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,forward)
  with log.open('w',buffering=1)as trace:
   while child.poll()is None:
    ready,_,_=select.select(devices,[],[],.02)
    for dev in ready:
     for event in dev.read():
      if event.type==E.EV_KEY:
       if event.value:keys[dev.fd].add(event.code)
       else:keys[dev.fd].discard(event.code)
       seen[dev.fd]+=1
      elif event.type==E.EV_ABS:axes[dev.fd][event.code]=event.value;seen[dev.fd]+=1
    states=[]
    for dev in devices:
     b={i for i,code in enumerate(buttons[dev.fd])if code in keys[dev.fd]};a=axes[dev.fd];x=a.get(E.ABS_X,0);y=a.get(E.ABS_Y,0)
     if abs(x)<4000:x=a.get(E.ABS_HAT0X,0)*32767
     if abs(y)<4000:y=a.get(E.ABS_HAT0Y,0)*32767
     states.append((b,x,y))
    out=routed_buttons(states)
    xy=next(((x,y)for b,x,y in states if abs(x)>4000 or abs(y)>4000),(0,0))
    for b in out^last_buttons:ui.write(E.EV_KEY,E.BTN_JOYSTICK+b,int(b in out))
    if xy!=last_xy:ui.write(E.EV_ABS,E.ABS_X,xy[0]);ui.write(E.EV_ABS,E.ABS_Y,xy[1])
    if out!=last_buttons or xy!=last_xy:ui.syn();trace.write(json.dumps({'time':time.time(),'buttons':sorted(out),'xy':xy})+'\n')
    last_buttons=out;last_xy=xy
  receipt.update(returncode=child.returncode,ended=time.time(),Router_events_by_player={str(i+1):seen[d.fd]for i,d in enumerate(devices)});(run/'result.json').write_text(json.dumps(receipt,indent=2)+'\n');return child.returncode
 finally:
  if child and child.poll()is None:child.terminate();child.wait(timeout=10)
  if ui:
   for b in last_buttons:ui.write(E.EV_KEY,E.BTN_JOYSTICK+b,0)
   ui.write(E.EV_ABS,E.ABS_X,0);ui.write(E.EV_ABS,E.ABS_Y,0);ui.syn();ui.close()
  for d in devices:d.close()
  if 'chosen'in locals():
   for i in range(80):
    if not any(q.exists()for q in chosen):break
    time.sleep(.025)
if __name__=='__main__':sys.exit(main())
