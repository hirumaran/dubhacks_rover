"""Cinematic camera, flash/photo presentation and bounded validation. Never drives the rover."""
from controller import Supervisor,Display
from pathlib import Path
import json,os,math,struct,zlib,time
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'presentation/data';LOG=ROOT/'logs';DATA.mkdir(parents=True,exist_ok=True);LOG.mkdir(exist_ok=True)
s=Supervisor();dt=64;receiver=s.getDevice('telemetry');receiver.enable(dt);board=s.getDevice('photo_board') if os.environ.get('GATES_NATIVE_PHOTO','0')=='1' else None;rover=s.getFromDef('ROVER');view=s.getFromDef('SHOWCASE_VIEW')
limit=float(os.environ.get('GATES_TEST_SECONDS','0'));record=os.environ.get('GATES_RECORD','0')=='1';frame_interval=.18 if not record else .128
state={};mode='orbit';last_frame=-1;last_status=-1;last_capture=None;shot_time=-100;last_board=-1;frame_number=0;end_requested=False;visited_modes=set();max_z=0;min_z=10;last_command='';photo_ref=None

def atomic_json(path,obj):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2));os.replace(tmp,path)
def look_at(eye,target):
 dx,dy,dz=(target[i]-eye[i]for i in range(3));yaw=math.atan2(dy,dx);pitch=math.atan2(-dz,math.hypot(dx,dy));sy=math.sin(yaw/2);cy=math.cos(yaw/2);sp=math.sin(pitch/2);cp=math.cos(pitch/2);q=(-sy*sp,cy*sp,sy*cp,cy*cp);v=math.sqrt(sum(a*a for a in q[:3]));return [q[0]/v,q[1]/v,q[2]/v,2*math.acos(max(-1,min(1,q[3])))]if v>1e-8 else[0,0,1,0]
def rgb_png(path):
 data=path.read_bytes();w,h=struct.unpack('!II',data[16:24]);pos=8;chunks=[]
 while pos<len(data):
  n=struct.unpack('!I',data[pos:pos+4])[0];kind=data[pos+4:pos+8]
  if kind==b'IDAT':chunks.append(data[pos+8:pos+8+n])
  pos+=12+n
 raw=zlib.decompress(b''.join(chunks));return w,h,b''.join(raw[y*(w*3+1)+1:(y+1)*(w*3+1)]for y in range(h))
def update_board(latest,phase):
 global photo_ref
 if board is None:return
 board.setOpacity(1);board.setColor(0x192525);board.fillRectangle(0,0,300,220);board.setColor(0xD8B77C);board.setFont('Arial',13,True);board.drawText('CAMPUS SCOUT / FOUND',16,12)
 if latest:
  try:
   w,h,rgb=rgb_png(DATA/latest['image']);scale=min(268/w,138/h);ow,oh=max(1,int(w*scale)),max(1,int(h*scale));scaled=bytearray()
   for y in range(oh):
    for x in range(ow):
     k=(min(h-1,int(y/scale))*w+min(w-1,int(x/scale)))*3;scaled.extend(rgb[k:k+3])
   if photo_ref:board.imageDelete(photo_ref)
   photo_ref=board.imageNew(bytes(scaled),Display.RGB,ow,oh);board.imagePaste(photo_ref,(300-ow)//2,36+(138-oh)//2,False)
  except (OSError,ValueError,struct.error):pass
  board.setColor(0xF4ECDD);board.setFont('Arial',15,True);board.drawText(latest['category'].upper()+'  '+latest['sample_id'],16,179)
  board.setColor(0xA5C4AD);board.setFont('Arial',11,True);board.drawText(phase,16,204)
 else:
  board.setColor(0xF4ECDD);board.setFont('Arial',18,True);board.drawText('A little rover.',20,75);board.drawText('A thoughtful mission.',20,102);board.setColor(0x9EAFA9);board.setFont('Arial',12,True);board.drawText('Looking for things left behind...',20,152)
update_board(None,'SEARCHING')
while s.step(dt)!=-1:
 now=s.getTime()
 while receiver.getQueueLength():
  try:state=json.loads(receiver.getString())
  except ValueError:pass
  receiver.nextPacket()
 # Camera controls affect only the presentation camera, never the robot's navigation.
 control=DATA/'control.json'
 if control.exists():
  try:
   cmd=json.loads(control.read_text())
   if cmd.get('nonce')!=last_command:
    last_command=cmd.get('nonce');requested=cmd.get('view')
    if requested in ('orbit','follow','atrium'):mode=requested
    if cmd.get('action')=='restart':
     atomic_json(DATA/'items.json',[]);control.unlink(missing_ok=True);s.worldReload();s.step(dt);break
  except (OSError,ValueError):pass
 rp=rover.getPosition();ori=rover.getOrientation();heading=math.atan2(ori[3],ori[0]);latest=state.get('latest');new_id=latest.get('sample_id')if latest else None
 if new_id and new_id!=last_capture:
  last_capture=new_id;shot_time=now;print(f'SHOWCASE PHOTO {new_id}: flash -> presentation gallery',flush=True)
 age=now-shot_time
 phase='CAPTURING'if age<.30 else'UPLOADING TO DEMO GALLERY'if age<2.0 else'ADDED TO LOCAL GALLERY'
 if mode=='atrium' or now<2.5:
  eye=[0,-17.5,1.7];target=[0,2.5,3.3];shot='ATRIUM'
 elif mode=='follow':
  eye=[rp[0]-math.cos(heading)*1.25+math.sin(heading)*.55,rp[1]-math.sin(heading)*1.25-math.cos(heading)*.55,.52];target=[rp[0],rp[1],.28];shot='FOLLOW'
 else:
  angle=now*.18;radius=1.05 if age<2.0 else 1.15
  eye=[rp[0]+math.cos(angle)*radius,rp[1]+math.sin(angle)*radius,.40 if age<2.0 else .44+.025*math.sin(now*.07)];target=[rp[0],rp[1],.26];shot='360 ORBIT'
 view.getField('position').setSFVec3f(eye);view.getField('orientation').setSFRotation(look_at(eye,target));visited_modes.add(shot)
 if now-last_board>.5:
  last_board=now;update_board(latest,phase)
 if now-last_status>.20:
  last_status=now
  public={'simulation_time':round(now,2),'state':state.get('state','STARTING'),'captured':state.get('captures',0),'total':6,'distance_m':state.get('distance_m',0),'camera':mode,'shot':shot,'phase':phase if latest else'SEARCHING','latest':latest,'scene':'Reference-inspired Gates atrium','recognition':'simulated object recognition','live':True}
  atomic_json(DATA/'state.json',public)
  s.setLabel(0,'CAMPUS SCOUT  /  GATES ATRIUM',.025,.035,.065,0xF1DEC0,.1,'Arial')
  s.setLabel(1,f'{shot}    {state.get("state","STARTING")}    FOUND {state.get("captures",0)}/6',.025,.10,.05,0xE4D3B5,.1,'Arial')
  s.setLabel(2,'REFERENCE-INSPIRED INTERIOR   /   AUTONOMOUS SEARCH   /   PRESENTATION DEMO',.025,.94,.035,0xE4D3B5,.15,'Arial')
 if now-last_frame>=frame_interval-1e-7:
  last_frame=now;tmp=DATA/'frame.next.jpg';s.exportImage(str(tmp),82)
  if tmp.exists():
   os.replace(tmp,DATA/'frame.jpg')
   if record:
    import shutil
    frames=ROOT/'recordings/frames';frames.mkdir(parents=True,exist_ok=True);shutil.copyfile(DATA/'frame.jpg',frames/f'{frame_number:06}.jpg');frame_number+=1
 if now>1.5 and not (LOG/'atrium_reference_view.png').exists():s.exportImage(str(LOG/'atrium_reference_view.png'),95)
 if 14<now<15 and not (LOG/'orbit_view.png').exists():s.exportImage(str(LOG/'orbit_view.png'),95)
 if limit and now>=limit and not end_requested:
  summary={'simulated_seconds':round(now,2),'robot':state,'camera_shots':sorted(visited_modes),'captures':state.get('captures',0),'success_capture':state.get('captures',0)==6,'success_lap':state.get('lap',0)>=1,'geometry':'approximate, inspired by two supplied references','recognition':'Webots Recognition (ground truth)'}
  atomic_json(LOG/'test_result.json',summary);s.exportImage(str(LOG/'test_end.png'),95);print('GATES_TEST_COMPLETE '+json.dumps(summary),flush=True);end_requested=True
 if end_requested:
  public['live']=False;atomic_json(DATA/'state.json',public);s.simulationQuit(0);break
