#!/usr/bin/env python3
"""Build an OSM-derived Webots campus, graph route and physical rover. Re-run with the map-build venv."""
from pathlib import Path
import json, math, heapq, re, xml.etree.ElementTree as ET
from pyproj import Proj
import native_osm
ROOT=Path(__file__).resolve().parents[1]
OSM=ROOT/'maps/uw_campus.osm';xml=ET.parse(OSM).getroot()
b=xml.find('bounds').attrib
lat0=(float(b['minlat'])+float(b['maxlat']))/2;lon0=(float(b['minlon'])+float(b['maxlon']))/2
proj=Proj(proj='utm',zone=10,ellps='WGS84');lo=proj(float(b['minlon']),float(b['minlat']));hi=proj(float(b['maxlon']),float(b['maxlat']));off=((lo[0]+hi[0])/2,(lo[1]+hi[1])/2)
nodes={}
for n in xml.findall('node'):
 e,no=proj(float(n.get('lon')),float(n.get('lat')));nodes[n.get('id')]=(e-off[0],no-off[1])
g={}
for w in xml.findall('way'):
 tags={t.get('k'):t.get('v')for t in w.findall('tag')}
 if tags.get('highway')not in ('footway','pedestrian','path') or tags.get('area')=='yes' or tags.get('access')in('private','no') or tags.get('foot')=='no' or tags.get('indoor')=='yes':continue
 refs=[n.get('ref') for n in w.findall('nd')]
 for a,b in zip(refs,refs[1:]):
  if a not in nodes or b not in nodes:continue
  if not all(-80<nodes[v][0]<150 and -220<nodes[v][1]<-30 for v in (a,b)):continue
  d=math.dist(nodes[a],nodes[b]);g.setdefault(a,{})[b]=d;g.setdefault(b,{})[a]=d
# Checkpoints are real OSM pedestrian-junction node IDs around UW's Quad.
checkpoints=['29939252','343780053','7797158565','7797158566','343729577','29939252']
def astar(start,goal):
 q=[(0,0,start)];best={start:0};prev={}
 while q:
  _,cost,u=heapq.heappop(q)
  if cost>best[u]:continue
  if u==goal:
   path=[u]
   while u in prev:u=prev[u];path.append(u)
   return path[::-1]
  for v,d in g[u].items():
   nc=cost+d
   if nc<best.get(v,math.inf):best[v]=nc;prev[v]=u;heapq.heappush(q,(nc+math.dist(nodes[v],nodes[goal]),nc,v))
 raise ValueError('OSM pedestrian checkpoints are not connected')
path=[]
for a,b in zip(checkpoints,checkpoints[1:]):path.extend(astar(a,b)[:-1])
path.append(checkpoints[-1]);pts=[nodes[v] for v in path]
# Interpolate dense targets along the graph polyline for stable following.
dense=[pts[0]]
for a,b in zip(pts,pts[1:]):
 count=max(1,math.ceil(math.dist(a,b)/.75))
 for k in range(1,count+1):dense.append(tuple(a[j]+(b[j]-a[j])*k/count for j in (0,1)))
length=sum(math.dist(a,b) for a,b in zip(pts,pts[1:]));start=pts[0];theta=math.atan2(pts[1][1]-start[1],pts[1][0]-start[0])
mission={'map':'OpenStreetMap / UW Seattle Quad','map_date':'2026-10-17','projection':proj.srs,'origin_utm':off,'reference_lat_lon':[lat0,lon0],'planner':'A* on OSM pedestrian graph; no steps or indoor corridors','route_osm_nodes':path,'checkpoints':checkpoints,'length_m':round(length,3),'waypoints':dense,'loop':True,'cruise_speed_m_s':.32,'wheel_radius_m':.0271,'track_width_m':.1772,'detector':'webots_camera_recognition_ground_truth','note':'The controller receives route waypoints, never item locations.'}
(ROOT/'maps/mission.json').write_text(json.dumps(mission,indent=2))
(ROOT/'maps/pedestrian_graph.json').write_text(json.dumps({'nodes':{k:nodes[k]for k in g},'adjacency':g},indent=2))
def app(c):return f'PBRAppearance {{ baseColor {c} roughness 0.85 metalness 0 }}'
def shape(size,c):return f'Shape {{ appearance {app(c)} geometry Box {{ size {size} }} }}'
def pose(x,y,z,s):return f'Pose {{ translation {x} {y} {z} children [ {s} ] }}'
def camera_rot(yaw):return f'0 0 1 {yaw:.8f}'
# All geometry uses x forward, y left, z up in ENU.
parts=[pose(0,0,.087,shape('.178 .136 .078','.26 .17 .40')),pose(0,0,.130,shape('.180 .138 .006','.88 .89 .85')),pose(0,0,.134,shape('.15 .108 .002','.31 .23 .44')),pose(0,0,.043,shape('.174 .124 .004','.45 .5 .5'))]
for y in [-.069,.069]:
 parts.extend([pose(0,y,.079,shape('.145 .001 .005','.77 .65 .35')),pose(0,y,.103,shape('.08 .001 .018','.88 .87 .81'))])
for x in [-.096,.096]:parts.append(pose(x,0,.055,shape('.011 .114 .012','.08 .1 .1')))
parts.extend([pose(-.015,0,.160,f'Shape {{ appearance {app(".12 .15 .15")} geometry Cylinder {{ radius .006 height .05 }} }}'),pose(-.015,0,.200,shape('.022 .024 .029','.83 .84 .8')),pose(.091,0,.098,shape('.003 .095 .024','.05 .08 .09')),pose(.053,.032,.140,f'Shape {{ appearance {app(".8 .1 .1")} geometry Cylinder {{ radius .007 height .006 }} }}')])
for side,sign in [('left',1),('right',-1)]:
 for j,x in enumerate([-.0745,0,.0745]):
  y=sign*.0886;wheel=f'{side}_{j}';parts.append(f'''HingeJoint {{ jointParameters HingeJointParameters {{ anchor {x} {y} .0271 axis 0 1 0 dampingConstant .0001 }}
 device [ RotationalMotor {{ name "{wheel}" maxVelocity 20 maxTorque .12 acceleration 25 sound "" }} PositionSensor {{ name "{wheel}_encoder" }} ]
 endPoint Solid {{ translation {x} {y} .0271 rotation 1 0 0 1.57079632679 name "{wheel}_wheel" contactMaterial "tire"
 children [ DEF TIRE_{wheel} Shape {{ appearance {app('.08 .10 .11')} geometry Cylinder {{ radius .0271 height .026 subdivision 24 }} }}
 Pose {{ translation 0 0 {sign*-.0135} children [ Shape {{ appearance {app('.72 .73 .7')} geometry Cylinder {{ radius .018 height .001 subdivision 18 }} }} ] }} ]
 boundingObject USE TIRE_{wheel} physics Physics {{ density -1 mass .045 }} }} }}''')
parts.extend(['GPS { name "gps" accuracy .003 }','Compass { name "compass" }','InertialUnit { name "imu" }',
'''Lidar { translation .04 0 .170 name "lidar" fieldOfView 6.283185307 horizontalResolution 180 numberOfLayers 1 verticalFieldOfView .01 near .04 minRange .04 maxRange 5 noise .005 type "fixed" }'''])
for i in range(4):
 parts.append(f'''Camera {{ translation -.015 0 .21 rotation {camera_rot(i*math.pi/2)} name "camera_{i}" width 320 height 240 fieldOfView 1.64 near .02 far 60 recognition Recognition {{ maxRange 3 maxObjects 12 occlusion 2 frameThickness 1 segmentation TRUE }} }}''')
parts.append('Emitter { name "telemetry" channel 37 }')
robot='''#VRML_SIM R2025a utf8
# Campus Scout physical six-wheel concept; dimensions in meters.
PROTO CampusScout [ field SFVec3f translation 0 0 .005 field SFRotation rotation 0 0 1 0 field SFString name "CampusScout" ] {
 Robot { translation IS translation rotation IS rotation name IS name controller "campus_rover" children [
'''+ '\n'.join(parts)+'''
 ] boundingObject Pose { translation 0 0 .087 children [ Box { size .178 .136 .078 } ] }
 physics Physics { density -1 mass .95 centerOfMass [ 0 0 .070 ] } selfCollision FALSE }
}
'''
(ROOT/'protos/CampusScout.proto').write_text(robot)
# Keep the official importer output intact; select a smaller active Quad view.
raw=(ROOT/'worlds/uw_imported.wbt').read_text()
def blocks(text):
 # Top-level native/PROTO nodes, honoring comments and quoted strings.
 pat=re.compile(r'(?m)^(\w+)\s*\{')
 pos=0
 while True:
  m=pat.search(text,pos)
  if not m:return
  k=m.end();depth=1;quote=False;escape=False;comment=False
  while k<len(text) and depth:
   ch=text[k]
   if comment:
    if ch=='\n':comment=False
   elif quote:
    if escape:escape=False
    elif ch=='\\':escape=True
    elif ch=='"':quote=False
   elif ch=='#':comment=True
   elif ch=='"':quote=True
   elif ch=='{':depth+=1
   elif ch=='}':depth-=1
   k+=1
  yield m.group(1),text[m.start():k]
  pos=k
extern=''
native_osm.textures(ROOT)
world=['#VRML_SIM R2025a utf8',extern,'EXTERNPROTO "../protos/CampusScout.proto"',f'''WorldInfo {{ title "Campus Scout | UW OSM autonomous search" info [ "OSM data (c) OpenStreetMap contributors, ODbL 1.0" "Real UW Quad footprints and paths; flat terrain; approximate building heights" ] basicTimeStep 16 FPS 30 coordinateSystem "ENU" gpsCoordinateSystem "local" randomSeed 42 contactProperties [ ContactProperties {{ material1 "tire" coulombFriction .7 forceDependentSlip .005 bounce 0 softERP .3 softCFM .0001 bumpSound "" rollSound "" slideSound "" }} ] }}''']
def look_at(eye,target):
 import numpy as np
 e=np.array(eye,dtype=float);t=np.array(target,dtype=float);forward=t-e;forward/=np.linalg.norm(forward);left=np.cross(np.array([0,0,1]),forward);left/=np.linalg.norm(left);up=np.cross(forward,left);r=np.column_stack((forward,left,up));angle=math.acos(max(-1,min(1,(np.trace(r)-1)/2)));axis=np.array([r[2,1]-r[1,2],r[0,2]-r[2,0],r[1,0]-r[0,1]])/(2*math.sin(angle));return ' '.join(map(str,[*axis,angle]))

eye=(start[0]-1.4,start[1]-1.8,1.25);orientation=look_at(eye,(*start,.1))
world.append(f'DEF MISSION_VIEW Viewpoint {{ position {eye[0]} {eye[1]} {eye[2]} orientation {orientation} near .08 far 500 follow "CampusScout" followType "Tracking Shot" }}')
world.extend(['Background { skyColor [ .72 .81 .88 ] }','DirectionalLight { direction -.4 .3 -1 intensity 2 ambientIntensity .6 castShadows TRUE }',f'''Solid {{ translation 0 0 -.05 name "campus_ground" children [ Shape {{ appearance {app('.35 .46 .27')} geometry Box {{ size 620 620 .1 }} }} ] boundingObject Box {{ size 620 620 .1 }} }}'''])
counts={}
for typ,txt in blocks(raw):
 if typ in ['WorldInfo','Viewpoint','Floor','TexturedBackground','TexturedBackgroundLight']:continue
 tr=re.search(r'\btranslation\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)',txt)
 if tr:
  x,y,z=map(float,tr.groups())
  if not(-100<x<160 and -245<y<10):continue
 if typ in ['Road','Crossroad']:
  # Paving material and no raised sidewalks are appropriate for campus footways.
  txt=txt.replace('0.010000','0.001000')
  if typ=='Road':
   txt=txt.replace('Road {','Road {\n  appearance '+app('.62 .58 .49'),1)
   txt=re.sub(r'  splineSubdivision\s+\d+','  splineSubdivision -1',txt)
  else:txt=txt.replace('Crossroad {','Crossroad {\n  appearance '+app('.62 .58 .49'),1)
 converted=native_osm.convert(typ,txt)
 if converted:
  world.append(converted);counts[typ]=counts.get(typ,0)+1
world.append(f'DEF ROVER CampusScout {{ translation {start[0]} {start[1]} .003 rotation 0 0 1 {theta} }}')
# Props lie beside the planned route. Their locations are only in world generation, not the robot controller.
def along(d):
 for a,b in zip(pts,pts[1:]):
  seg=math.dist(a,b)
  if d<=seg:
   f=d/seg;dx=(b[0]-a[0])/seg;dy=(b[1]-a[1])/seg
   return (a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f),(-dy,dx),math.atan2(dy,dx)
  d-=seg
 return pts[-1],(0,1),theta
for i,(kind,d,col) in enumerate([('backpack',2.8,'.65 .22 .12'),('book',10,'.24 .16 .5'),('bottle',22,'.08 .53 .57'),('backpack',43,'.12 .21 .45'),('book',68,'.66 .25 .25')]):
 p,n,ang=along(d);side=1 if i%2==0 else -1;x=p[0]+n[0]*.65*side;y=p[1]+n[1]*.65*side
 if kind=='backpack':
  children=[pose(0,0,.17,shape('.14 .26 .34',col)),pose(.082,0,.11,shape('.03 .20 .12','.76 .47 .25')),pose(0,0,.36,f'Shape {{ appearance {app(".12 .13 .12")} geometry Cylinder {{ radius .04 height .012 }} }}')];bo=pose(0,0,.17,'Box { size .14 .26 .34 }')
 elif kind=='book':
  children=[pose(0,0,.018,shape('.24 .17 .036',col)),pose(0,0,.021,shape('.225 .16 .022','.93 .91 .8'))];bo=pose(0,0,.018,'Box { size .24 .17 .036 }')
 else:
  children=[pose(0,0,.125,f'Shape {{ appearance {app(col)} geometry Cylinder {{ radius .04 height .25 }} }}'),pose(0,0,.26,f'Shape {{ appearance {app(".15 .17 .17")} geometry Cylinder {{ radius .027 height .025 }} }}')];bo=pose(0,0,.125,'Cylinder { radius .04 height .25 }')
 world.append(f'''DEF ITEM_{i+1} Solid {{ translation {x} {y} .005 rotation 0 0 1 {ang} name "sample_{kind}_{i+1}" model "{kind}|CS-{i+1:03}" recognitionColors [ {col} ] children [ {' '.join(children)} ] boundingObject {bo} }}''')
# A real static obstacle in the route exercises lidar avoidance (not a lost item).
p,n,ang=along(15)
world.append(f'''DEF TEST_OBSTACLE Solid {{ translation {p[0]} {p[1]} .15 name "test_obstacle" children [ {shape('.24 .24 .3','.83 .52 .12')} ] boundingObject Box {{ size .24 .24 .3 }} }}''')
world.append('DEF MISSION_MONITOR Robot { name "Mission monitor" supervisor TRUE controller "mission_supervisor" children [ Receiver { name "telemetry" channel 37 } ] }')
(ROOT/'worlds/uw_autonomous.wbt').write_text('\n\n'.join(world)+'\n')
meta={'attribution':'© OpenStreetMap contributors','license':'ODbL 1.0','license_url':'https://www.openstreetmap.org/copyright','download_url':'https://api.openstreetmap.org/api/0.6/map?bbox=-122.3100,47.6569,-122.3048,47.6604','download_date':'2026-10-17','bounds':b,'importer':'Webots R2025a official OSM importer','active_world_counts':counts,'patrol_length_m':length,'limits':['Flat terrain; no surveyed elevations','OSM footprints and pedestrian topology; estimated building heights','Rover suspension rigid; skid steering','Recognition is simulator ground truth, not machine learning']}
(ROOT/'maps/provenance.json').write_text(json.dumps(meta,indent=2));print(json.dumps({'patrol_m':length,'waypoints':len(dense),'active_geometry':counts,'start':start},indent=2))
