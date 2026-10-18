"""Sensor-driven autonomous indoor showcase. This controller has no Supervisor access.
Navigation: simulated indoor pose, reference-layout waypoints, physical drive and lidar.
The GPS device is idealized localization for simulation; real indoor operation needs SLAM.
Capture: synchronized four-camera snapshot every five simulation seconds, including empty scenes.
Detection: all visible simulated items within each scheduled snapshot, including repeat sightings.
No item world coordinates or Supervisor object lookups are used by this controller.
"""
from controller import Robot
from pathlib import Path
import json, math, os, struct, zlib
ROOT=Path(__file__).resolve().parents[2]
MISSION=json.loads((ROOT/'maps/mission.json').read_text())
GALLERY=ROOT/'presentation/data';CAPTURES=GALLERY/'captures';CAPTURES.mkdir(parents=True,exist_ok=True)
LOGS=ROOT/'logs';LOGS.mkdir(exist_ok=True)
def atomic_json(path,value):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));os.replace(tmp,path)
def wrap(a):return math.atan2(math.sin(a),math.cos(a))
def clamp(v,a,b):return max(a,min(b,v))
def write_png(path,w,h,rows):
 def chunk(t,d):return struct.pack('!I',len(d))+t+d+struct.pack('!I',zlib.crc32(t+d)&0xffffffff)
 data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows,3))+chunk(b'IEND',b'')
 tmp=path.with_suffix('.tmp');tmp.write_bytes(data);os.replace(tmp,path)
def rgb_row(raw,w,y,x0=0,x1=None):
 x1=w if x1 is None else x1;src=raw[(y*w+x0)*4:(y*w+x1)*4];out=bytearray((x1-x0)*3)
 out[0::3]=src[2::4];out[1::3]=src[1::4];out[2::3]=src[0::4];return out
def crop_png(camera,obj,path,raw=None):
 w,h=camera.getWidth(),camera.getHeight();cx,cy=obj.getPositionOnImage();bw,bh=obj.getSizeOnImage()
 x0=max(0,int(cx-bw/2)-4);x1=min(w,int(cx+bw/2)+4);y0=max(0,int(cy-bh/2)-4);y1=min(h,int(cy+bh/2)+4)
 raw=camera.getImage() if raw is None else raw
 if not raw or x1<=x0 or y1<=y0:return False
 rows=bytearray()
 for y in range(y0,y1):rows.append(0);rows.extend(rgb_row(raw,w,y,x0,x1))
 write_png(path,x1-x0,y1-y0,rows);return True

class CampusRover(Robot):
 def __init__(self):
  super().__init__();self.dt=64;self.route=MISSION['waypoints'];self.wp=1;self.lap=0;self.travel=0.;self.lastxy=None;self.state='PATROL';self.last_status=-1.;self.detour=[];self.detour_started=0.;self.avoid_until=0.;self.avoid_sign=1;self.blocked_seconds=0.
  self.flash=self.getDevice('photo_flash');self.flash.set(0);self.flash_until=0.;self.left=[];self.right=[]
  for side,arr in [('left',self.left),('right',self.right)]:
   for i in range(3):
    m=self.getDevice(f'{side}_{i}');m.setPosition(float('inf'));m.setVelocity(0);arr.append(m)
    self.getDevice(f'{side}_{i}_encoder').enable(self.dt)
  self.gps=self.getDevice('gps');self.gps.enable(self.dt);self.compass=self.getDevice('compass');self.compass.enable(self.dt);self.imu=self.getDevice('imu');self.imu.enable(self.dt);self.lidar=self.getDevice('lidar');self.lidar.enable(self.dt)
  self.cameras=[]
  for i in range(4):
   c=self.getDevice(f'camera_{i}');c.enable(self.dt);c.recognitionEnable(self.dt);self.cameras.append(c)
  self.emitter=self.getDevice('telemetry')
  # Optional vision feed for the perception bridge (simulation/perception_bridge): camera pixels + pose only.
  inbox=os.environ.get('PERCEPTION_INBOX');self.hook=None
  if inbox:
   from perception_hook import PerceptionHook
   cams={}
   for idx,name in [(1,'perception_left'),(3,'perception_right')]:
    d=self.getDevice(name)
    if d:d.enable(256);cams[idx]=d
   self.hook=PerceptionHook(cams or dict(enumerate(self.cameras)),self.gps,self.compass,inbox)
  try:self.records=json.loads((GALLERY/'items.json').read_text())
  except (OSError,ValueError):self.records=[]
  self.seen={r['sample_id']for r in self.records};self.new_captures=0;self.avoid_events=0
  self.catalog=json.loads((ROOT/'maps/items.json').read_text());self.next_snapshot=5.;self.snapshot_interval=5.
  self.snapdir=GALLERY/'snapshots';self.snapdir.mkdir(exist_ok=True)
  try:self.snapshots=json.loads((GALLERY/'snapshots.json').read_text())
  except (OSError,ValueError):self.snapshots=[]
  self.session_prefix=os.urandom(3).hex()
  if self.snapshots or self.records:
   archive=LOGS/'session_history';archive.mkdir(exist_ok=True)
   atomic_json(archive/f'{self.session_prefix}.json',{'items':self.records,'snapshots':self.snapshots})
   self.records=[];self.seen=set();self.snapshots=[]
  atomic_json(GALLERY/'items.json',self.records)
  atomic_json(GALLERY/'snapshots.json',self.snapshots)
  print(f'GATES_SCOUT READY | indoor route {MISSION["length_m"]:.1f}m | 6 wheel motors | 4 recognition cameras | lidar',flush=True)
 def drive(self,v,w):
  r=MISSION['wheel_radius_m'];track=MISSION['track_width_m'];vl=clamp((v-w*track/2)/r,-17,17);vr=clamp((v+w*track/2)/r,-17,17)
  for m in self.left:m.setVelocity(vl)
  for m in self.right:m.setVelocity(vr)
 def snapshot(self,now,scheduled):
  """Capture all four synchronized camera buffers first, then recognize only that sample.
  This is a full-azimuth four-view mosaic, not a spherical/equirectangular photograph.
  Identity labels use visible simulated Recognition results and an ID catalog, never poses.
  """
  frames=[bytes(c.getImage()) for c in self.cameras]
  if not all(frames):return
  order=[0,3,2,1];directions=['Front','Right','Rear','Left'];w=self.cameras[0].getWidth();h=self.cameras[0].getHeight()
  number=len(self.snapshots)+1;sid=f'SCAN-{self.session_prefix}-{number:05}';image=f'snapshots/{sid}.png';rows=bytearray()
  for y in range(h):
   rows.append(0)
   for i in order:rows.extend(rgb_row(frames[i],w,y))
  write_png(GALLERY/image,w*4,h,rows)
  candidates={}
  for i,c in enumerate(self.cameras):
   for obj in c.getRecognitionObjects():
    model=obj.getModel()
    if '|' not in model:continue
    kind,item_id=model.split('|',1)
    if kind not in ('bottle','book','ball','toy'):continue  # items left on benches (bench_props.py)
    bw,bh=obj.getSizeOnImage()
    if bw<6 or bh<3 or bw*bh<36:continue
    # Adjacent cameras overlap slightly. One best view identifies each exact instance.
    if item_id not in candidates or bw*bh>candidates[item_id][0]:candidates[item_id]=(bw*bh,i,obj,kind)
  detections=[]
  for item_id,(_,i,obj,kind) in sorted(candidates.items()):
   cx,cy=obj.getPositionOnImage();bw,bh=obj.getSizeOnImage();tile=order.index(i)
   x0=max(0,cx-bw/2);y0=max(0,cy-bh/2);x1=min(w,cx+bw/2);y1=min(h,cy+bh/2)
   crop=f'captures/{sid}_{item_id}.png'
   if not crop_png(self.cameras[i],obj,GALLERY/crop,frames[i]):continue
   entry={'sample_id':item_id,'category':kind,'description':self.catalog.get(item_id,{}).get('description',kind.title()),'simulation_time_s':round(now,3),'image':crop,'snapshot_id':sid,'direction':directions[tile],'camera':i,'bbox':[(tile*w+x0)/(w*4),y0/h,(x1-x0)/(w*4),(y1-y0)/h],'detector':'Webots camera Recognition (simulation ground truth)'}
   detections.append(entry)
   existing=next((n for n,r in enumerate(self.records)if r['sample_id']==item_id),None)
   if existing is None:self.records.append(entry);self.seen.add(item_id);self.new_captures+=1
   else:self.records[existing]=entry
  shot={'snapshot_id':sid,'simulation_time_s':round(now,3),'scheduled_time_s':round(scheduled,3),'image':image,'width':w*4,'height':h,'projection':'four synchronized perspective views, 360-degree horizontal coverage','directions':directions,'detections':detections}
  self.snapshots.append(shot);atomic_json(GALLERY/'items.json',self.records);atomic_json(GALLERY/'snapshots.json',self.snapshots)
  self.flash.set(1);self.flash_until=now+.22
  print(f'SNAPSHOT {sid} | scheduled {scheduled:.1f}s actual {now:.3f}s | 360 degrees | {len(detections)} items: '+(', '.join(d['description']+' '+d['sample_id']for d in detections) or 'none'),flush=True)
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
  if now>=self.flash_until:self.flash.set(0)
  p=self.gps.getValues();north=self.compass.getValues()
  if any(not math.isfinite(q)for q in p+north):self.drive(0,0);return
  xy=(p[0],p[1]);heading=math.atan2(north[0],north[1]);roll,pitch,_=self.imu.getRollPitchYaw()
  if self.lastxy:self.travel+=math.dist(xy,self.lastxy)
  self.lastxy=xy
  if now+1e-7>=self.next_snapshot:
   scheduled=self.next_snapshot;self.next_snapshot+=self.snapshot_interval
   self.snapshot(now,scheduled);self.last_status=-1.
  if abs(roll)>.8 or abs(pitch)>.8:self.drive(0,0);self.state='TILT_STOP';self.status(now,xy,heading,5.);return
  if self.state=='OBSTACLE_STOP':self.drive(0,0);self.status(now,xy,heading,5.);return
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
  v=(.16 if self.detour else MISSION['cruise_speed_m_s'])*max(0.,math.cos(err))
  if abs(err)>.4:v=0.
  if self.detour and front<.18 and abs(err)<.5:
   v=0.;w=1.2*self.avoid_sign
  if self.detour and now-self.detour_started>45:
   self.state='OBSTACLE_STOP';self.drive(0,0);self.status(now,xy,heading,front);return
  self.drive(v,w);self.status(now,xy,heading,front)
 def status(self,now,xy,heading,front):
  if now-self.last_status<.5:return
  self.last_status=now
  status={'time_s':round(now,2),'state':self.state,'waypoint':self.wp,'waypoints':len(self.route),'lap':self.lap,'distance_m':round(self.travel,2),'captures':len(self.records),'new_captures':self.new_captures,'avoid_events':self.avoid_events,'front_range_m':round(front,2),'position_local_m':[round(v,4)for v in xy],'heading_rad':round(heading,4),'latest':self.snapshots[-1]['detections'][0]if self.snapshots and self.snapshots[-1]['detections']else None,'snapshots':len(self.snapshots),'snapshot_interval_s':self.snapshot_interval,'next_snapshot_s':self.next_snapshot,'latest_snapshot':self.snapshots[-1]if self.snapshots else None}
  atomic_json(LOGS/'robot_state.json',status);self.emitter.send(json.dumps(status).encode())
  if int(now)%10==0:print(f'PATROL {now:.1f}s | {self.state} | waypoint {self.wp}/{len(self.route)} | distance {self.travel:.1f}m | found {len(self.records)}',flush=True)
 def run(self):
  while self.step(self.dt)!=-1:self.tick()

CampusRover().run()
