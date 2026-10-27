#!/usr/bin/python3
"""Host-only native Controller Router adapter; saved input configurations are never rewritten."""
from pathlib import Path
import os,sys,json,time,subprocess,signal,hashlib,shlex,argparse,ctypes,select
BASE=Path.home()/'.local/share/controller-router/native'
USER=os.environ.get('USER','pi')
HOME=Path.home()
UID=os.getuid()
GID=os.getgid()
REGISTRY=Path('/opt/retropie/support/launchers/native-router-registry.json')
SELF='/opt/controller-router/bin/native-route'

def configure(registry_path=None):
 global BASE,REGISTRY,SELF,USER,UID,GID,HOME
 import pwd
 REGISTRY=Path(registry_path or os.environ.get('CONTROLLER_ROUTER_NATIVE_REGISTRY',REGISTRY))
 data=json.loads(REGISTRY.read_text()).get('runtime',{})
 account=pwd.getpwnam(data.get('user',USER if UID else 'pi'))
 USER,UID,GID=account.pw_name,account.pw_uid,account.pw_gid
 HOME=Path(account.pw_dir)
 BASE=Path(data.get('state_root',str(Path(account.pw_dir)/'.local/share/controller-router/native')))
 SELF=data.get('launcher',SELF)
 if not BASE.is_absolute() or not Path(SELF).is_absolute():raise ValueError('Native paths must be absolute')


def native_session(proc_root=Path('/proc'), registry_path=None):
 """Recognize only a registered worker, never a shell substring or inspection."""
 try:
  registry_file=Path(registry_path or REGISTRY)
  data=json.loads(registry_file.read_text());runtime=data.get('runtime',{})
  import pwd
  account=pwd.getpwnam(runtime.get('user','pi'))
  base=Path(runtime.get('state_root',str(Path(account.pw_dir)/'.local/share/controller-router/native')))
  launcher=runtime.get('launcher','/opt/controller-router/bin/native-route')
  processes=list(Path(proc_root).iterdir())
 except(OSError,ValueError,KeyError,TypeError):return None,None
 for process in processes:
  if not process.name.isdigit():continue
  try:
   args=[os.fsdecode(x)for x in(process/'cmdline').read_bytes().split(b'\0')if x]
   executable=Path(os.readlink(str(process/'exe'))).name
   if len(args)!=4 or args[1]!=launcher or args[2]!='--worker' or not executable.startswith('python3'):continue
   run=Path(args[3])
   if run.parent!=base/'runs' or run.is_symlink() or (run/'request.json').is_symlink():continue
   if run.stat().st_uid!=account.pw_uid or (process/'cmdline').stat().st_uid!=account.pw_uid:continue
   request=json.loads((run/'request.json').read_text())
   entry=data['entries'][request['entry']]
   if not request.get('inspect') and request['system']==entry['system']:
    from .systems import system_id
    return 'native-merged',system_id(entry['system'])
  except(OSError,ValueError,KeyError,TypeError):continue
 return None,None

def registry():return json.loads(REGISTRY.read_text())['entries']
def needs_exit_keyboard(entry):return any(binary in entry['command']for binary in ['/opt/retropie/emulators/mame/mame','/opt/retropie/emulators/advmame/bin/advmame'])
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def identity(d):
 try:return((d/'name').read_text().strip(),int((d/'id/vendor').read_text(),16),int((d/'id/product').read_text(),16))
 except(OSError,ValueError):return None

def inputs():
 rows=[]
 for p in Path('/sys/class/input').glob('event*'):
  ident=identity(p/'device')
  if ident and ident[0].startswith('VirtualGlove Merged Player ')and ident[1]==0x1209 and ident[2]in [0x5651,0x5652,0x5653,0x5654]:
   player=ident[2]-0x5650
   if ident[0]=='VirtualGlove Merged Player '+str(player):
    js=[x.name for x in(p/'device').glob('js*')]
    rows.append(dict(player=player,event=p.name,js=js,name=ident[0],vendor=ident[1],product=ident[2]))
 assert rows and len({x['player']for x in rows})==len(rows),'ROUTER_IDENTITIES_MISSING_OR_DUPLICATE'
 return sorted(rows,key=lambda x:x['player'])

def pointer_bridge(rows):
 from evdev import InputDevice,UInput,ecodes as E
 import threading
 row=next(r for r in rows if r['player']==1)
 pad=InputDevice('/dev/input/'+row['event'])
 ui=UInput({E.EV_REL:[E.REL_X,E.REL_Y],E.EV_KEY:[E.BTN_LEFT,E.BTN_RIGHT,E.KEY_SPACE,E.KEY_ENTER,E.KEY_ESC]},name='Controller Router Native Pointer',vendor=0x1209,product=0x5760)
 stop=threading.Event()
 def loop():
  held_before=set()
  try:
   while not stop.wait(.02):
    b=set(pad.active_keys());hot=E.BTN_MODE in b or(E.BTN_SELECT in b and E.BTN_START in b)
    held=set()if hot else{target for source,target in[(E.BTN_SOUTH,E.BTN_LEFT),(E.BTN_EAST,E.BTN_RIGHT),(E.BTN_NORTH,E.KEY_SPACE),(E.BTN_WEST,E.KEY_ENTER),(E.BTN_START,E.KEY_ENTER),(E.BTN_SELECT,E.KEY_ESC)]if source in b}
    for key in held^held_before:ui.write(E.EV_KEY,key,int(key in held))
    for axis,hat,rel in[(E.ABS_X,E.ABS_HAT0X,E.REL_X),(E.ABS_Y,E.ABS_HAT0Y,E.REL_Y)]:
     value=pad.absinfo(axis).value;digital=pad.absinfo(hat).value
     motion=int(value/32767*16)if abs(value)>6000 else digital*8
     if motion and not hot:ui.write(E.EV_REL,rel,motion)
    ui.syn();held_before=held
  finally:
   for key in held_before:ui.write(E.EV_KEY,key,0)
   ui.syn()
 thread=threading.Thread(target=loop,daemon=True);thread.start();time.sleep(.2)
 def close():stop.set();thread.join(2);ui.close();pad.close()
 return close


def expand_command(args,entry):
 quake_dir=Path(args.rom).parent.name if Path(args.rom).suffix.lower()=='.pak'else 'id1'
 values={'%QUAKEDIR%':quake_dir,'%ROM%':args.rom,'%BASENAME%':args.basename,'%XRES%':args.xres,'%YRES%':args.yres}
 command=entry['command']
 for key,value in values.items():command=command.replace(key,shlex.quote(value))
 assert not any(x in command for x in values),'UNRESOLVED_PLACEHOLDER'
 return command

def passthrough(args,entry):
 command=expand_command(args,entry)
 os.execv('/bin/bash',['bash','-c',command])

def prepare(args):
 assert os.geteuid()==UID and UID!=0,'RUN_AS_ROUTER_USER'
 entries=registry();entry=entries[args.entry]
 from router_shared.systems import routes
 from router_shared.native_sessions import launch_policy
 manifest=launch_policy()
 if not routes(manifest,'native-routed',entry['system']):
  return passthrough(args,entry)
 BASE.mkdir(parents=True,exist_ok=True);(BASE/'runs').mkdir(exist_ok=True)
 import fcntl
 lock=(BASE/'native-session.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if not args.test_seconds:args.test_seconds=int(os.environ.get('CONTROLLER_ROUTER_QUALIFY_SECONDS','0'))
 assert 0<=args.test_seconds<=30,'QUALIFICATION_LIMIT_OUT_OF_RANGE'
 assert subprocess.run(['systemctl','is-active','--quiet','virtualglove-controller-router']).returncode==0,'ROUTER_SERVICE_REQUIRED'
 rows=inputs();stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid());run=BASE/'runs'/stamp;run.mkdir(parents=True)
 command=expand_command(args,entry)
 if entry['system']=='atarist'and '/emulators/hatari/'in command and '--joy1'not in command and '--joystick'not in command:command+=' --joy1 real'
 environment={k:v for k,v in os.environ.items()if k.startswith(('SDL_','SDL1_','XDG_'))or k in ['DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','TERM','AUDIODEV','ALSA_CONFIG_PATH','LD_LIBRARY_PATH']}
 request=dict(test_seconds=args.test_seconds,environment=environment,entry=args.entry,system=entry['system'],command=command,controllers=rows,created=time.time(),inspect=args.inspect)
 write(run/'request.json',request)
 cmd=['sudo','-n','unshare','--mount','--propagation','private','--fork','/usr/bin/python3',SELF,'--namespace',str(run)]
 close_pointer=pointer_bridge(rows)if entry.get('pointer_bridge')and not args.inspect else None
 exit_ui=None
 if needs_exit_keyboard(entry)and not args.inspect:
  from evdev import UInput,ecodes as E
  exit_ui=UInput({E.EV_KEY:[E.KEY_ESC]},name='Controller Router Native Exit',vendor=0x1209,product=0x5763);time.sleep(.2)
 child=subprocess.Popen(cmd)
 def forward(sig,frame):
  try:child.send_signal(sig)
  except ProcessLookupError:pass
 for sig in(signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,forward)
 try:
  escape_sent=False
  while child.poll()is None:
   if exit_ui and not escape_sent and(run/'exit-request').exists():
    exit_ui.write(E.EV_KEY,E.KEY_ESC,1);exit_ui.syn();time.sleep(.12);exit_ui.write(E.EV_KEY,E.KEY_ESC,0);exit_ui.syn();escape_sent=True
   time.sleep(.02)
  result=child.returncode
 finally:
  if close_pointer:close_pointer()
  if exit_ui:exit_ui.close()
 if(run/'result.json').exists():return result
 write(run/'result.json',dict(error='Native namespace helper failed',returncode=result));return result

def load_run(name):
 run=Path(name);assert run.parent==BASE/'runs' and run.is_dir()and not run.is_symlink(),'INVALID_SESSION_PATH'
 req=json.loads((run/'request.json').read_text());entry=registry()[req['entry']]
 assert entry['system']==req['system'],'REGISTRY_MISMATCH'
 return run,req,entry

def namespace(name):
 assert os.geteuid()==0,'NAMESPACE_REQUIRES_ROOT';run,req,entry=load_run(name)
 if not entry.get('private_bridge'):
  # Bind the original input tree before replacing this namespace's view.
  source=run/'original-input';source.mkdir(exist_ok=True)
  def mount(*args):subprocess.run(['mount']+list(args),check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  mount('--bind','/dev/input',str(source));mount('-t','tmpfs','-o','mode=755','tmpfs','/dev/input')
  merged={r['event']for r in req['controllers']};kept=[];hidden=[]
  for p in source.iterdir():
   if not p.is_char_device()or p.name.startswith('js'):continue
   keep=True
   if p.name.startswith('event')and p.name not in merged:
    dev=Path('/sys/class/input')/p.name/'device';has_js=any(dev.glob('js*'))
    udev=Path('/run/udev/data/c%d:%d'%(os.major(p.stat().st_rdev),os.minor(p.stat().st_rdev)))
    data=udev.read_text()if udev.exists()else''
    # Pointer/keyboard combo devices are preserved even if they also advertise joystick inputs.
    pointer=any('E:ID_INPUT_'+kind+'=1'in data for kind in ['MOUSE','TOUCHPAD','TABLET','TOUCHSCREEN'])
    keep=not(has_js or 'E:ID_INPUT_JOYSTICK=1'in data)or pointer
   if keep:
    dest=Path('/dev/input')/p.name;dest.touch();mount('--bind',str(p),str(dest));kept.append(p.name)
   else:hidden.append(p.name)
  for dirname in ['by-id','by-path']:
   p=source/dirname
   if p.is_dir():
    target=Path('/dev/input')/dirname;target.mkdir();mount('--bind',str(p),str(target))
  for index,row in enumerate(req['controllers']):
   assert len(row['js'])==1,'ROUTER_JOYSTICK_NODE_REQUIRED'
   dest=Path('/dev/input')/('js'+str(index));dest.touch();mount('--bind',str(source/row['js'][0]),str(dest));row['namespace_js']=str(dest)
  write(run/'devices.json',dict(controllers=req['controllers'],preserved_nodes=sorted(kept),hidden_raw_joysticks=sorted(hidden),global_devices_unchanged=True))
 else:
  write(run/'devices.json',dict(controllers=req['controllers'],existing_private_bridge=True,global_devices_unchanged=True))
 if req['system']=='n64'and not req.get('test_seconds'):
  # The legacy launcher rewrites runtime hotkeys/resolution. Keep those writes session-local.
  import shutil
  target=Path('/opt/retropie/configs/n64');copy=run/'native-n64-config';copy.mkdir();os.chown(str(copy),UID,GID)
  for source in target.iterdir():
   if source.is_file():
    dest=copy/source.name;shutil.copy2(str(source),str(dest));os.chown(str(dest),UID,GID)
  subprocess.run(['mount','--bind',str(copy),str(target)],check=True)
 if req.get('test_seconds'):
  # Qualification runs write only to copied configuration directories.
  import shutil
  targets=[Path('/opt/retropie/configs')/req['system']]
  if req['system']in ['mame','arcade','mame-advmame','mame-libretro']:
   for system in ['mame','arcade','mame-advmame','mame-libretro']:
    targets += [HOME/'RetroPie/roms'/system/sub for sub in ['cfg','nvram','hi','memcard']]
  overlays=[]
  for index,target in enumerate(targets):
   if not target.is_dir():continue
   dest=run/('test-config-'+str(index));shutil.copytree(str(target),str(dest),symlinks=True)
   for root,dirs,files in os.walk(str(dest)):
    os.chown(root,UID,GID)
    for name in files:
     q=Path(root)/name
     if not q.is_symlink():os.chown(str(q),UID,GID)
   subprocess.run(['mount','--bind',str(dest),str(target)],check=True);overlays.append(str(target))
  home=run/'test-home';home.mkdir();os.chown(str(home),UID,GID)
  (home/'.mame').symlink_to('/opt/retropie/configs/mame',target_is_directory=True)
  if (HOME/'.asoundrc').is_file():
   shutil.copy2(str(HOME/'.asoundrc'),str(home/'.asoundrc'));os.chown(str(home/'.asoundrc'),UID,GID)
  req['environment']['HOME']=str(home);write(run/'test-overlays.json',overlays)
 details=json.loads((run/'devices.json').read_text());details['mount_namespace_private']=os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt');write(run/'devices.json',details)
 # Execute the actual command without root privileges, retaining the frontend's display/audio environment.
 os.setgroups(os.getgrouplist(USER,GID));os.setgid(GID);os.setuid(UID)
 os.environ.update(req.get('environment',{}))
 os.environ.update(HOME=req.get('environment',{}).get('HOME',str(HOME)),USER=USER,LOGNAME=USER,CONTROLLER_ROUTER_SYSTEM=req['system'],NATIVE_CONTROLLER_ROUTER='1',CONTROLLER_ROUTER_RUN=str(run))
 ctypes.CDLL(None).prctl(1,signal.SIGTERM,0,0,0)
 os.execv('/usr/bin/python3',['/usr/bin/python3',SELF,'--worker',str(run)])

def sdl_report(rows,prefer_sdl1=True):
 result={};sdl=ctypes.CDLL('libSDL2-2.0.so.0');sdl.SDL_Init.argtypes=[ctypes.c_uint32];sdl.SDL_GetError.restype=ctypes.c_char_p
 assert sdl.SDL_Init(0x200)==0,'SDL2_INIT_FAILED';sdl.SDL_JoystickNameForIndex.restype=ctypes.c_char_p
 for fn in ['SDL_JoystickGetDeviceVendor','SDL_JoystickGetDeviceProduct']:getattr(sdl,fn).restype=ctypes.c_uint16
 class GUID(ctypes.Structure):_fields_=[('data',ctypes.c_ubyte*16)]
 sdl.SDL_JoystickGetDeviceGUID.restype=GUID;sdl.SDL_JoystickGetGUIDString.argtypes=[GUID,ctypes.c_char_p,ctypes.c_int]
 devices=[];maps=[]
 try:
  for index in range(sdl.SDL_NumJoysticks()):
   n=sdl.SDL_JoystickNameForIndex(index);name=n.decode()if n else'';vendor=sdl.SDL_JoystickGetDeviceVendor(index);product=sdl.SDL_JoystickGetDeviceProduct(index)
   if (name,vendor,product)not in[(r['name'],r['vendor'],r['product'])for r in rows]:
    devices.append(dict(index=index,name=name,vendor=vendor,product=product,retained_pointer=True));continue
   guid=ctypes.create_string_buffer(33);sdl.SDL_JoystickGetGUIDString(sdl.SDL_JoystickGetDeviceGUID(index),guid,33)
   mapping=guid.value.decode()+','+name+',a:b0,b:b1,x:b3,y:b4,back:b10,start:b11,guide:b12,leftshoulder:b6,rightshoulder:b7,lefttrigger:b8,righttrigger:b9,leftstick:b13,rightstick:b14,leftx:a0,lefty:a1,rightx:a2,righty:a3,dpup:h0.1,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,platform:Linux,'
   maps.append(mapping);devices.append(dict(index=index,name=name,vendor=vendor,product=product,mapping=mapping))
  assert len(maps)==len(rows),'SDL_MERGED_OUTPUTS_NOT_RESOLVED'
 finally:sdl.SDL_Quit()
 os.environ['SDL_GAMECONTROLLERCONFIG']=os.environ.get('SDL_GAMECONTROLLERCONFIG','')+'\n'+'\n'.join(maps)
 # SDL1 otherwise lists the preferred js device AND its evdev counterpart twice.
 # The filtered event tree already contains only the intended merged joysticks.
 if prefer_sdl1:
  os.environ.pop('SDL_JOYSTICK_DEVICE',None);os.environ['SDL_JOYSTICK_HIDAPI']='0'
 return dict(devices=devices,mappings=len(maps))

def opened_input_devices(pid):
 pending=[pid];rows=[]
 while pending:
  current=pending.pop();proc=Path('/proc')/str(current)
  try:pending.extend(int(x)for x in(proc/'task'/str(current)/'children').read_text().split())
  except OSError:pass
  for fd in(proc/'fd').glob('*'):
   try:
    target=os.readlink(str(fd))
    if target.startswith('/dev/input/'):
     st=fd.stat();node=Path('/sys/dev/char')/('%d:%d'%(os.major(st.st_rdev),os.minor(st.st_rdev)));name=(node/'device/name').read_text().strip()
     rows.append(dict(pid=current,path=target,name=name,major=os.major(st.st_rdev),minor=os.minor(st.st_rdev)))
   except OSError:pass
 return rows

def child_probe():
 from router_shared.native_sessions import running_native_session
 context=running_native_session();assert context[0]is not None,context
 s=ctypes.CDLL('libSDL-1.2.so.0');s.SDL_JoystickName.restype=ctypes.c_char_p;assert s.SDL_Init(0x200)==0
 names=[s.SDL_JoystickName(i).decode()for i in range(s.SDL_NumJoysticks())];s.SDL_Quit();assert names[:2]==['VirtualGlove Merged Player 1','VirtualGlove Merged Player 2'],names
 print(json.dumps(dict(native_context=context,SDL1=names,namespace_is_private=json.loads((Path(os.environ['CONTROLLER_ROUTER_RUN'])/'devices.json').read_text())['mount_namespace_private'])));return 0

def worker(name):
 assert os.geteuid()==UID and UID!=0,'WORKER_MUST_BE_ROUTER_USER';run,req,entry=load_run(name);rows=req['controllers'];report=sdl_report(rows,not entry.get('private_bridge'))
 write(run/'sdl.json',report)
 if req['inspect']:
  write(run/'result.json',dict(returncode=0,inspection_only=True,SDL=report,system=req['system']));print(json.dumps(report));return 0
 from evdev import InputDevice,ecodes as E
 console_group=None;old_ttou=None
 pads=[InputDevice('/dev/input/'+r['event'])for r in rows];counts={str(r['player']):0 for r in rows};child=None;reason='normal';requested=False;deadline=None;started=time.monotonic();device_opens=[];last_device_scan=0
 try:
  console=entry.get('prefix')=='CON:'and os.isatty(0)
  if console:
   console_group=os.tcgetpgrp(0);old_ttou=signal.signal(signal.SIGTTOU,signal.SIG_IGN)
   child=subprocess.Popen(['bash','-c',req['command']],preexec_fn=os.setpgrp)
   os.tcsetpgrp(0,child.pid)
  else:child=subprocess.Popen(['bash','-c',req['command']],start_new_session=True)
  def request_exit(sig=None,frame=None):
   nonlocal requested,deadline,reason
   if requested:return
   requested=True;deadline=time.monotonic()+3;reason='merged_hotkey_or_signal'
   # SDL installs SIGINT as a normal quit request. Never signal the frontend or Router.
   if needs_exit_keyboard(entry):
    (run/'exit-request').touch();deadline=time.monotonic()+6;reason='normal_escape_request'
   else:
    try:os.killpg(child.pid,signal.SIGINT)
    except ProcessLookupError:pass
  for sig in(signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,request_exit)
  while child.poll()is None:
   if req.get('test_seconds')and time.monotonic()-started>=req['test_seconds']:request_exit()
   if time.monotonic()-started>2 and time.monotonic()-last_device_scan>1:
    latest=opened_input_devices(child.pid)
    if latest:device_opens=latest
    last_device_scan=time.monotonic()
   readable,_,_=select.select(pads,[],[],.03)
   for pad in readable:
    try:
     for event in pad.read():
      if event.type in(E.EV_KEY,E.EV_ABS):counts[str(rows[pads.index(pad)]['player'])]+=1
    except BlockingIOError:pass
   for pad in pads:
    held=set(pad.active_keys())
    if E.BTN_START in held and(E.BTN_MODE in held or E.BTN_SELECT in held):request_exit()
   if requested and time.monotonic()>deadline:
    try:os.killpg(child.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:
     reason='forced_exit_after_unresponsive_native_game';os.killpg(child.pid,signal.SIGKILL);child.wait()
  result=child.returncode
  write(run/'result.json',dict(returncode=result,exit_reason=reason,Router_events_by_player=counts,ended=time.time(),system=req['system'],entry=req['entry'],saved_configuration_rewritten=False,test_seconds=req.get('test_seconds',0),opened_input_devices=device_opens))
  return 0 if requested else result
 finally:
  if console_group is not None:
   os.tcsetpgrp(0,console_group);signal.signal(signal.SIGTTOU,old_ttou)
  for pad in pads:pad.close()
  if child and child.poll()is None:
   os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=5)

def main():
 configure()
 if sys.argv[1:]==['--child-probe']:return child_probe()
 if len(sys.argv)==3 and sys.argv[1]=='--joystick-name':
  import fcntl
  with open(sys.argv[2],'rb',buffering=0)as joystick:
   print(fcntl.ioctl(joystick.fileno(),0x80806a13,bytes(128)).split(b'\0')[0].decode());return 0
 if len(sys.argv)==3 and sys.argv[1]=='--namespace':return namespace(sys.argv[2])
 if len(sys.argv)==3 and sys.argv[1]=='--worker':return worker(sys.argv[2])
 p=argparse.ArgumentParser();p.add_argument('--entry',required=True);p.add_argument('--rom',default='');p.add_argument('--basename',default='');p.add_argument('--xres',default='');p.add_argument('--yres',default='');p.add_argument('--inspect',action='store_true');p.add_argument('--test-seconds',type=int,default=0);return prepare(p.parse_args())
if __name__=='__main__':sys.exit(main())
