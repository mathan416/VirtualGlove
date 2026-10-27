"""Read canonical Router output for legacy native adapters; never read a physical controller."""
from pathlib import Path
import os
from router_shared.controller_router import SourceState
from router_shared.merged_gamepad import BUTTON_CODES,AXIS_CODES
class CanonicalMapper:
 def __init__(self,source):self.source=source
 def event(self,kind,code,value):
  if kind==1:
   for name,number in BUTTON_CODES.items():
    if code==number:
     if value:self.source.buttons.add(name)
     else:self.source.buttons.discard(name)
  elif kind==3:
   for name,number in AXIS_CODES.items():
    if code==number:self.source.set_axis(name,value)
def discover_merged(state,opened,players=(1,)):
 for player in players:
  identity='merged-player-'+str(player)
  if any(row[0]==identity for row in opened.values()):continue
  matches=[]
  for p in Path('/sys/class/input').glob('event*'):
   d=p/'device'
   try:actual=((d/'name').read_text().strip(),int((d/'id/vendor').read_text(),16),int((d/'id/product').read_text(),16))
   except(OSError,ValueError):continue
   if actual==('VirtualGlove Merged Player '+str(player),0x1209,0x5650+player):matches.append(p)
  if len(matches)>1:raise RuntimeError('Ambiguous merged player identity')
  if matches:
   fd=os.open('/dev/input/'+matches[0].name,os.O_RDONLY|os.O_NONBLOCK)
   source=state.physical.setdefault(identity,SourceState());opened[fd]=(identity,source,CanonicalMapper(source))
