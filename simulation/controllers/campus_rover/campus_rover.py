"""Sensor-driven autonomous campus search. This controller has no Supervisor access.
Navigation: GPS + compass, OSM graph route, differential drive and lidar avoidance.
Detection: simulator camera Recognition (ground truth), deliberately replaceable.
No item world coordinates or Supervisor object lookups are used by this controller.
"""
from controller import Robot
from pathlib import Path
import json, math, os, struct, zlib
ROOT=Path(__file__).resolve().parents[2]
MISSION=json.loads((ROOT/'maps/mission.json').read_text())
GALLERY=ROOT/'gallery';CAPTURES=GALLERY/'captures';CAPTURES.mkdir(parents=True,exist_ok=True)
LOGS=ROOT/'logs';LOGS.mkdir(exist_ok=True)
def atomic_json(path,value):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));os.replace(tmp,path)
def wrap(a):return math.atan2(math.sin(a),math.cos(a))
def clamp(v,a,b):return max(a,min(b,v))
def crop_png(camera,obj,path):
 """Encode a tight RGB crop from the sensor image, using only standard-library PNG code."""
 w,h=camera.getWidth(),camera.getHeight();cx,cy=obj.getPositionOnImage();bw,bh=obj.getSizeOnImage()
 pad=4;x0=max(0,int(cx-bw/2)-pad);x1=min(w,int(cx+bw/2)+pad);y0=max(0,int(cy-bh/2)-pad);y1=min(h,int(cy+bh/2)+pad)
 raw=camera.getImage()
 if not raw or x1<=x0 or y1<=y0:return False
 rows=bytearray()
 for y in range(y0,y1):
  rows.append(0)
  for x in range(x0,x1):
   k=(y*w+x)*4;rows.extend((raw[k+2],raw[k+1],raw[k]))
 def chunk(t,d):return struct.pack('!I',len(d))+t+d+struct.pack('!I',zlib.crc32(t+d)&0xffffffff)
 data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',x1-x0,y1-y0,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows,6))+chunk(b'IEND',b'')
 path.write_bytes(data);return True

class CampusRover(Robot):
 def __init__(self):
  super().__init__();self.dt=64;self.route=MISSION['waypoints'];self.wp=1;self.lap=0;self.travel=0.;self.lastxy=None;self.state='PATROL';self.resume_at=0.;self.pending=None;self.evidence={};self.last_status=-1.;self.detour=[];self.detour_started=0.;self.avoid_until=0.;self.avoid_sign=1;self.blocked_seconds=0.;self.last_progress=0.;self.last_progress_xy=None;self.sequence=0
  self.left=[];self.right=[]
  for side,arr in [('left',self.left),('right',self.right)]:
   for i in range(3):
    m=self.getDevice(f'{side}_{i}');m.setPosition(float('inf'));m.setVelocity(0);arr.append(m)
    self.getDevice(f'{side}_{i}_encoder').enable(self.dt)
  self.gps=self.getDevice('gps');self.gps.enable(self.dt);self.compass=self.getDevice('compass');self.compass.enable(self.dt);self.imu=self.getDevice('imu');self.imu.enable(self.dt);self.lidar=self.getDevice('lidar');self.lidar.enable(self.dt)
  self.cameras=[]
  for i in range(4):
   c=self.getDevice(f'camera_{i}');c.enable(128);c.recognitionEnable(128);self.cameras.append(c)
  self.emitter=self.getDevice('telemetry')
  inbox=os.environ.get('PERCEPTION_INBOX')
  self.hook=None
  if inbox:
   from perception_hook import PerceptionHook
   self.hook=PerceptionHook(self.cameras,self.gps,self.compass,inbox)
  try:self.records=json.loads((GALLERY/'items.json').read_text())
  except (OSError,ValueError):self.records=[]
  self.seen={r['sample_id']for r in self.records};self.new_captures=0;self.avoid_events=0
  print(f'CAMPUS_SCOUT READY | OSM route {MISSION["length_m"]:.1f}m | 6 wheel motors | 4 recognition cameras | lidar',flush=True)
 def drive(self,v,w):
  r=MISSION['wheel_radius_m'];track=MISSION['track_width_m'];vl=clamp((v-w*track/2)/r,-17,17);vr=clamp((v+w*track/2)/r,-17,17)
  for m in self.left:m.setVelocity(vl)
  for m in self.right:m.setVelocity(vr)
 def visible(self):
  out=[]
  for i,c in enumerate(self.cameras):
   for obj in c.getRecognitionObjects():
    model=obj.getModel()
    if '|'not in model:continue
    kind,sid=model.split('|',1)
    if kind not in ('backpack','book','bottle')or sid in self.seen:continue
    p=obj.getPosition();dist=math.sqrt(sum(q*q for q in p));bw,bh=obj.getSizeOnImage()
    if dist<1.65 and bw>=10 and bh>=4 and bw*bh>=100:out.append((dist,i,obj,kind,sid))
  return sorted(out,key=lambda v:v[0])
 def inspect(self,now):
  if self.pending is None:return
  self.drive(0,0)
  if now<self.resume_at:return
  sid=self.pending;matches=[v for v in self.visible()if v[4]==sid]
  if matches:
   _,i,obj,kind,sid=matches[0];image=f'captures/{sid}.png'
   if crop_png(self.cameras[i],obj,GALLERY/image):
    record={'sample_id':sid,'category':kind,'simulation_time_s':round(now,2),'image':image,'detector':'Webots camera recognition (simulation ground truth)'}
    self.records.append(record);self.seen.add(sid);self.new_captures+=1;atomic_json(GALLERY/'items.json',self.records)
    print(f'CAPTURE {sid} {kind} | camera {i} | sim {now:.1f}s | item crop saved, no location metadata',flush=True)
  self.pending=None;self.state='PATROL';self.evidence={}
 def ranges(self):
  rs=list(self.lidar.getRangeImage());n=len(rs)
  def sector(center,span):
   vals=[]
   for k,r in enumerate(rs):
    a=math.pi-k*2*math.pi/max(1,n-1)
    if abs(wrap(a-center))<span and math.isfinite(r)and r>.045:vals.append(r)
   return min(vals)if vals else 5.
  return sector(0,.40),sector(.65,.50),sector(-.65,.50)
 def tick(self):
  now=self.getTime()
  if self.hook:self.hook.maybe(now)
  p=self.gps.getValues();north=self.compass.getValues()
  if any(not math.isfinite(q)for q in p+north):self.drive(0,0);return
  xy=(p[0],p[1]);heading=math.atan2(north[0],north[1]);roll,pitch,_=self.imu.getRollPitchYaw()
  if self.lastxy:self.travel+=math.dist(xy,self.lastxy)
  self.lastxy=xy
  if abs(roll)>.8 or abs(pitch)>.8:self.drive(0,0);self.state='TILT_STOP';self.status(now,xy,heading,5.);return
  if self.state=='OBSTACLE_STOP':self.drive(0,0);self.status(now,xy,heading,5.);return
  if self.state=='INSPECT':self.inspect(now);self.status(now,xy,heading,5.);return
  vis=self.visible()
  for _,i,obj,kind,sid in vis:
   self.evidence[sid]=self.evidence.get(sid,0)+1
   if self.evidence[sid]>=4:
    self.pending=sid;self.resume_at=now+1.0;self.state='INSPECT';self.drive(0,0);self.status(now,xy,heading,5.);return
  front,left,right=self.ranges()
  # A local lidar-derived detour stays separate from the mapped global route.
  if self.detour and math.dist(xy,self.detour[0])<.14:
   self.detour.pop(0)
   if not self.detour:
    end=min(len(self.route),self.wp+7)
    self.wp=min(range(self.wp,end),key=lambda i:math.dist(xy,self.route[i]))
  if not self.detour:
   while math.dist(xy,self.route[self.wp])<.30:
    self.wp+=1
    if self.wp>=len(self.route):self.wp=1;self.lap+=1;print(f'PATROL LAP {self.lap} COMPLETE',flush=True)
  goal=self.detour[0]if self.detour else self.route[self.wp]
  err=wrap(math.atan2(goal[1]-xy[1],goal[0]-xy[0])-heading)
  if front<.55 and abs(err)<.35 and not self.detour:
   side=1 if left>right else -1
   fx,fy=math.cos(heading),math.sin(heading);lx,ly=-fy*side,fx*side
   clearance=.65;advance=front+1.05
   self.detour=[(xy[0]+lx*clearance,xy[1]+ly*clearance),
                (xy[0]+fx*advance+lx*clearance,xy[1]+fy*advance+ly*clearance),
                (xy[0]+fx*advance,xy[1]+fy*advance)]
   self.detour_started=now;self.avoid_events+=1;self.state='AVOID'
   print(f'LIDAR DETOUR | sim {now:.1f}s front={front:.2f}m, side={side}',flush=True)
   goal=self.detour[0];err=wrap(math.atan2(goal[1]-xy[1],goal[0]-xy[0])-heading)
  self.state='AVOID'if self.detour else'PATROL'
  w=clamp(2.5*err,-1.5,1.5)
  v=(.16 if self.detour else .32)*max(0.,math.cos(err))
  if abs(err)>.4:v=0.
  if self.detour and front<.18 and abs(err)<.5:
   v=0.;w=1.2*self.avoid_sign
  if self.detour and now-self.detour_started>45:
   self.state='OBSTACLE_STOP';self.drive(0,0);self.status(now,xy,heading,front);return
  self.drive(v,w);self.status(now,xy,heading,front)
 def status(self,now,xy,heading,front):
  if now-self.last_status<.5:return
  self.last_status=now
  status={'time_s':round(now,2),'state':self.state,'waypoint':self.wp,'waypoints':len(self.route),'lap':self.lap,'distance_m':round(self.travel,2),'captures':len(self.records),'new_captures':self.new_captures,'avoid_events':self.avoid_events,'front_range_m':round(front,2),'position_local_m':[round(v,4)for v in xy],'heading_rad':round(heading,4)}
  atomic_json(LOGS/'robot_state.json',status);self.emitter.send(json.dumps(status).encode())
  if int(now)%10==0:print(f'PATROL {now:.1f}s | {self.state} | waypoint {self.wp}/{len(self.route)} | distance {self.travel:.1f}m | found {len(self.records)}',flush=True)
 def run(self):
  while self.step(self.dt)!=-1:self.tick()

CampusRover().run()
