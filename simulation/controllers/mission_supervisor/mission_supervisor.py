"""Display and test monitor only. Does not drive or teleport the rover."""
from controller import Supervisor
from pathlib import Path
import json,os,math,time
ROOT=Path(__file__).resolve().parents[2];LOGS=ROOT/'logs';LOGS.mkdir(exist_ok=True)
s=Supervisor();dt=64;recv=s.getDevice('telemetry');recv.enable(dt)
limit=float(os.environ.get('CAMPUS_SCOUT_TEST_SECONDS','0'));last=-1;state={};image_done=False;map_image=False;map_started=False;view_restored=False
rover=s.getFromDef('ROVER');view=s.getFromDef('MISSION_VIEW');mission=json.loads((ROOT/'maps/mission.json').read_text());sx,sy=mission['waypoints'][0]
def look_at(eye,target):
 dx,dy,dz=(target[i]-eye[i]for i in range(3));yaw=math.atan2(dy,dx);pitch=math.atan2(-dz,math.hypot(dx,dy));sy=math.sin(yaw/2);cy=math.cos(yaw/2);sp=math.sin(pitch/2);cp=math.cos(pitch/2);q=(-sy*sp,cy*sp,sy*cp,cy*cp);angle=2*math.acos(max(-1,min(1,q[3])));scale=math.sqrt(sum(v*v for v in q[:3]));return [q[0]/scale,q[1]/scale,q[2]/scale,angle]if scale>1e-9 else[0,0,1,0]
while s.step(dt)!=-1:
 now=s.getTime()
 while recv.getQueueLength():
  try:state=json.loads(recv.getString())
  except ValueError:pass
  recv.nextPacket()
 if now-last>=.5:
  last=now
  s.setLabel(0,'CAMPUS SCOUT  |  UW QUAD',.36,.025,.06,0x263A2F,0,'Arial')
  text=f'{state.get("state","STARTING")}   {state.get("distance_m",0):.1f} m   FOUND {state.get("captures",0)}/5   OSM WAYPOINT {state.get("waypoint",0)}/{state.get("waypoints",0)}'
  s.setLabel(1,text,.36,.08,.05,0x394D33,0,'Arial')
  s.setLabel(2,'GPS + COMPASS  /  LIDAR AVOIDANCE  /  CAMERA RECOGNITION (SIMULATOR GROUND TRUTH)',.025,.93,.04,0x263A2F,0,'Arial')
 if limit and not map_started and now>=1:
  view.getField('follow').setSFString('')
  view.getField('near').setSFFloat(5.0);eye=[-35,-235,115];view.getField('position').setSFVec3f(eye);view.getField('orientation').setSFRotation(look_at(eye,[25,-135,0]));map_started=True
 if limit and map_started and not map_image and now>=1.8:
  s.exportImage(str(LOGS/'campus_overview.png'),95);map_image=True
 if limit and map_image and not view_restored and now>=2.2:
  view.getField('near').setSFFloat(.08);rp=rover.getPosition();eye=[rp[0]-1.4,rp[1]-1.8,rp[2]+1.25]
  view.getField('position').setSFVec3f(eye);view.getField('orientation').setSFRotation(look_at(eye,[rp[0],rp[1],rp[2]+.10]));view.getField('follow').setSFString('CampusScout');view_restored=True
 if now>3 and not image_done:
  s.exportImage(str(LOGS/'rover_preview.png'),90);image_done=True
 if limit and now>=limit:
  summary={'simulated_seconds':round(now,2),'robot':state,'world':'uw_autonomous.wbt','success_motion':state.get('distance_m',0)>2,'success_capture':state.get('new_captures',0)>0}
  (LOGS/('test_result.json'if limit>=100 else'preview_result.json')).write_text(json.dumps(summary,indent=2));s.exportImage(str(LOGS/'test_end.png'),90)
  print('CAMPUS_SCOUT_TEST_COMPLETE '+json.dumps(summary),flush=True);s.simulationQuit(0);break
