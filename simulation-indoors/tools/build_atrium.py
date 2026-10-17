#!/usr/bin/env python3
"""Reference-inspired Gates atrium. Approximate presentation geometry, not surveyed plans."""
from pathlib import Path
import math,json,random
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
TEX=ROOT/'worlds/textures';TEX.mkdir(parents=True,exist_ok=True)
rng=random.Random(21)
# New procedural textures; the user's reference photographs are not copied or published.
for name,base,kind in [('limestone',(137,137,130),'stone'),('oak',(132,76,40),'wood'),('concrete',(183,181,169),'concrete')]:
 im=Image.new('RGB',(512,512));pix=im.load()
 for y in range(512):
  for x in range(512):
   grain=(7*math.sin(x*.16)+3*math.sin(x*.7+y*.015))if kind=='wood'else 0
   n=rng.randrange(-5,6)+grain;pix[x,y]=tuple(max(0,min(255,int(c+n)))for c in base)
 d=ImageDraw.Draw(im)
 if kind=='stone':
  for x in [0,256,511]:d.line((x,0,x,512),fill=(92,95,92),width=2)
  for y in [0,170,340,511]:d.line((0,y,512,y),fill=(92,95,92),width=2)
 im.save(TEX/(name+'.jpg'),quality=90)
parts=[];idx=0
colors={'white':'.79 .78 .72','dark':'.07 .085 .09','steel':'.22 .24 .25','wood':'.43 .21 .10','glass':'.42 .60 .65','purple':'.24 .12 .29','warm':'.95 .72 .38'}
def app(c,texture=None,transparent=0,emissive=None,rough=.7):
 c=colors.get(c,c);s=f'PBRAppearance {{ baseColor {c} roughness {rough} metalness 0.05'
 if texture:s+=f' baseColorMap ImageTexture {{ url [ "textures/{texture}.jpg" ] }}'
 if texture=='limestone':s+=' textureTransform TextureTransform { scale 12 19 }'
 if transparent:s+=f' transparency {transparent}'
 if emissive:s+=f' emissiveColor {emissive}'
 return s+' }'
def add_box(name,pos,size,c='white',texture=None,collision=False,trans=0,rot=None,emit=None,rough=.7):
 global idx
 idx+=1;geo=f'Box {{ size {size[0]} {size[1]} {size[2]} }}';a=app(c,texture,trans,emit,rough);rotation=f'rotation {rot}'if rot else''
 if collision:
  parts.append(f'Solid {{ translation {pos[0]} {pos[1]} {pos[2]} {rotation} name "{name}_{idx}" children [ Shape {{ appearance {a} geometry DEF G_{idx} {geo} }} ] boundingObject USE G_{idx} }}')
 else:parts.append(f'Pose {{ translation {pos[0]} {pos[1]} {pos[2]} {rotation} children [ Shape {{ appearance {a} geometry {geo} }} ] }}')
def sphere(pos,r,c,scale=None):
 geo=f'Shape {{ appearance {app(c)} geometry Sphere {{ radius {r} subdivision 2 }} }}'
 if scale:geo=f'Transform {{ scale {scale[0]} {scale[1]} {scale[2]} children [ {geo} ] }}'
 parts.append(f'Pose {{ translation {pos[0]} {pos[1]} {pos[2]} children [ {geo} ] }}')
def cylinder(pos,r,h,c,collision=False):
 global idx
 idx+=1;g=f'Cylinder {{ radius {r} height {h} subdivision 16 }}';shape=f'Shape {{ appearance {app(c)} geometry DEF G_{idx} {g} }}'
 if collision:parts.append(f'Solid {{ translation {pos[0]} {pos[1]} {pos[2]} name "column_{idx}" children [ {shape} ] boundingObject USE G_{idx} }}')
 else:parts.append(f'Pose {{ translation {pos[0]} {pos[1]} {pos[2]} children [ {shape} ] }}')
def rod(a,b,r,c):
 dx,dy,dz=(b[i]-a[i]for i in range(3));h=math.sqrt(dx*dx+dy*dy+dz*dz);axis=(-dy,dx,0);norm=math.hypot(*axis[:2]);angle=math.acos(max(-1,min(1,dz/h)))
 rotation=f'{axis[0]/norm} {axis[1]/norm} 0 {angle}'if norm>1e-8 else'0 0 1 0'
 p=tuple((a[i]+b[i])/2 for i in range(3));parts.append(f'Pose {{ translation {p[0]} {p[1]} {p[2]} rotation {rotation} children [ Shape {{ appearance {app(c)} geometry Cylinder {{ radius {r} height {h} subdivision 10 }} }} ] }}')
def glass_rail(x,y,z,length,along='y'):
 size=(.025,length,.83)if along=='y'else(length,.025,.83)
 add_box('glass_balustrade',(x,y,z+.49),size,'glass',trans=.74,rough=.12)
 if along=='y':rod((x,y-length/2,z+.95),(x,y+length/2,z+.95),.025,'dark')
 else:rod((x-length/2,y,z+.95),(x+length/2,y,z+.95),.025,'dark')
 for t in [-.5,-.25,0,.25,.5]:
  px=x if along=='y'else x+t*length;py=y+t*length if along=='y'else y;rod((px,py,z+.05),(px,py,z+.96),.018,'dark')
# Long stone atrium and ground-floor wings. Main camera stays inside open south frontage.
add_box('atrium_floor',(0,0,-.10),(24,38,.2),'1 1 1','limestone',True,rough=.36)
for y in [-10,10]:add_box('wing_floor',(17,y,-.1),(14,4.6,.2),'1 1 1','limestone',True,rough=.36)
add_box('north_end_wall',(0,19,6.4),(24,.25,12.8),'white','concrete',True)
# North glazing, columns and warm timber on each floor.
for level in [0,4.2,8.4]:
 for x in [-9,-6,-3,0,3,6,9]:
  add_box('north_glass',(x,18.82,level+1.55),(2.7,.04,2.9),'glass',trans=.64,rough=.15)
  add_box('north_mullion',(x+1.42,18.76,level+1.7),(.055,.065,3.4),'dark')
for side in [-1,1]:
 x=side*11.7
 for y in [-17,-13,-9,-5,-1,3,7,11,15,18]:
  # Ground-level openings connect the east corridor wings.
  if side==1 and any(abs(y-q)<2.5 for q in [-10,10]):continue
  add_box('structural_column',(x,y,6.4),(.32,.38,12.8),'white','concrete',True)
 # Glazed lab / office frontage with black steel frames and oak panels.
 for level in [0,4.2,8.4]:
  for y in range(-17,19,4):
   if side==1 and level==0 and (abs(y+10)<2.8 or abs(y-10)<2.8):continue
   add_box('glazed_frontage',(x,y,level+1.55),(.035,3.65,2.85),'glass',trans=.58,rough=.13)
   for yy in [y-1.9,y+1.9]:add_box('vertical_mullion',(x-side*.035,yy,level+1.75),(.08,.065,3.45),'dark')
   add_box('oak_cladding',(x+side*.08,y,level+3.55),(.18,3.9,.72),'1 1 1','oak')
   add_box('warm_linear_light',(x-side*.15,y,level+3.15),(.04,3.9,.035),'warm',emit='1 .72 .38',rough=.3)
 # Two overlooking balconies with glass rails and dark steel banding.
 for level in [4.2,8.4]:
  add_box('mezzanine',(side*9,0,level),(5.5,38,.28),'white','concrete')
  add_box('balcony_fascia',(side*6.18,0,level+.02),(.12,38,.35),'dark')
  add_box('balcony_light',(side*6.25,0,level-.17),(.06,37,.045),'warm',emit='1 .74 .4')
  for yy in [-14.2,-4.7,4.7,14.2]:glass_rail(side*6.18,yy,level+.18,9.4)
# Steel beams, exposed service runs and a cyan glazed skylight.
for yy in [-17,-13,-9,-5,-1,3,7,11,15,18]:
 add_box('roof_crossbeam',(0,yy,12.65),(24,.22,.32),'steel')
 add_box('roof_light',(0,yy-.2,12.4),(11.4,.035,.035),'warm',emit='.85 .9 .9')
for xx in [-5.8,0,5.8]:add_box('skylight_rib',(xx,0,12.88),(.14,38,.14),'steel')
for yy in range(-16,19,4):add_box('skylight_glass',(0,yy,12.95),(11.6,3.8,.035),'.41 .76 .8',trans=.52,rough=.08)
for x in [-10.6,-10.2,10.1]:rod((x,-18,3.85),(x,18,3.85),.045,'steel')
# Iconic steel-and-oak staircase: foot at south, rising toward north.
run=5.5;height=4.2;steps=25;angle=math.atan2(height,run)
for i in range(steps):
 yy=-3.2+run*(i+.5)/steps;zz=height*(i+1)/steps
 add_box('wood_stair_tread',(-1.5,yy,zz),(2.5,run/steps,.075),'1 1 1','oak',True)
for xx in [-2.82,-.18]:
 add_box('steel_stair_stringer',(xx,-.45,2.04),(.13,math.hypot(run,height),.22),'dark',rot=f'1 0 0 {angle}')
 rod((xx,-3.2,1.08),(xx,2.3,5.28),.035,'steel')
 for i in range(0,steps,4):
  yy=-3.2+run*(i+.5)/steps;zz=height*(i+1)/steps
  rod((xx,yy,zz),(xx,yy,zz+1.0),.02,'steel')
 add_box('stair_glass',(xx,-.45,3.04),(.02,math.hypot(run,height),.62),'glass',trans=.76,rot=f'1 0 0 {angle}')
add_box('landing',(-1.5,3.2,4.2),(3,2,.23),'white','concrete')
add_box('bridge',(0,3.9,4.2),(12.4,1.55,.25),'white','concrete')
for yy in [3.1,4.7]:glass_rail(0,yy,4.35,12.3,'x')
# Upper flight hints at the atrium's stacked circulation.
for i in range(20):add_box('upper_stair',(1.5,6+i*.23,4.2+(i+1)*.21),(2.0,.23,.065),'1 1 1','oak')
for x in [.45,2.55]:rod((x,6,5.2),(x,10.6,9.4),.035,'dark')
# East ground-floor corridor wings and glass-walled meeting rooms.
for yy in [-10,10]:
 for side in [-1,1]:
  add_box('wing_wall',(17,yy+side*2.2,1.75),(14,.15,3.5),'white','concrete',True)
  for xx in [12.7,16.2,19.7]:
   add_box('meeting_room_glass',(xx,yy+side*1.55,1.45),(3.2,.035,2.8),'glass',trans=.56,rough=.15)
   add_box('meeting_room_frame',(xx+1.62,yy+side*1.55,1.5),(.06,.07,3),'dark')
   add_box('meeting_room_desk',(xx,yy+side*1.85,.73),(1.4,.5,.07),'1 1 1','oak')
 add_box('wing_end',(24,yy,1.75),(.15,4.5,3.5),'white','concrete',True)
# Purple lounge furniture and stools, kept clear of the patrol lanes.
def sofa(x,y,rot=0):
 add_box('sofa_base',(x,y,.23),(1.7,.78,.28),'dark',collision=True)
 add_box('sofa_cushion',(x,y,.43),(1.66,.75,.18),'purple',rough=.94)
 add_box('sofa_back',(x,y+.33,.69),(1.7,.16,.52),'purple',collision=True)
 for xx in [x-.82,x+.82]:add_box('sofa_arm',(xx,y,.56),(.15,.79,.31),'purple')
sofa(6.1,6);sofa(-6.4,9)
for x,y in [(7.7,8),(5.9,8.8),(-6.1,6.6),(-7.7,7)]:
 add_box('lounge_seat',(x,y,.42),(.66,.65,.18),'purple',collision=True)
 add_box('lounge_back',(x,y+.26,.69),(.66,.14,.52),'purple',collision=True)
 for sx in [-1,1]:rod((x+sx*.25,y-.2,0),(x+sx*.25,y-.2,.36),.018,'dark')
for x,y in [(6.5,7.3),(-6.9,8)]:cylinder((x,y,.42),.48,.05,'white',True);cylinder((x,y,.2),.045,.4,'steel')
for y in [-14,-10,-6]:
 cylinder((-9.0,y,.36),.24,.72,'.48 .5 .46',True);add_box('recycling_lid',(-9,y,.74),(.50,.5,.05),'.1 .28 .44')
for x,y in [(8,-15),(-8,14),(8,15),(-8,-15)]:
 cylinder((x,y,.25),.26,.5,'.69 .65 .55',True);rod((x,y,.45),(x,y,1.6),.04,'wood')
 for a in range(7):sphere((x+math.cos(a)*.22,y+math.sin(a)*.22,1.2+(a%3)*.16),.25,'.18 .3 .16',(1,1,1.5))
# A glass/wood reception corner echoes the supplied atrium photograph.
add_box('wood_reception_wall',(9.8,-15.5,1.85),(2.1,4.5,3.7),'1 1 1','oak',True)
add_box('reception_counter',(7.8,-15,.55),(1.8,3,1.1),'.43 .42 .39',collision=True)
# Lights are presentation approximations. Geometry works without downloaded assets.
lights=['DirectionalLight { direction .15 .1 -1 intensity 1.0 ambientIntensity .40 color .92 .96 1 castShadows TRUE }']
for yy in [-13,-3,7,16]:lights.append(f'PointLight {{ location 0 {yy} 5.5 color 1 .88 .72 intensity 1.3 radius 16 attenuation 0 0 .025 }}')
# Route avoids the stairs and furniture and visits a corridor wing.
checkpoints=[(0,-12),(4,-12),(4,-10),(14,-10),(4,-10),(4,8),(0,12),(-4,8),(-4,-10),(0,-12)]
dense=[checkpoints[0]]
for a,b in zip(checkpoints,checkpoints[1:]):
 n=max(1,math.ceil(math.dist(a,b)/.5))
 dense.extend(tuple(a[j]+(b[j]-a[j])*k/n for j in [0,1])for k in range(1,n+1))
mission={'map':'Reference-inspired Gates atrium and corridor','length_m':round(sum(math.dist(a,b)for a,b in zip(checkpoints,checkpoints[1:])),3),'waypoints':dense,'wheel_radius_m':.0271,'track_width_m':.1772,'cruise_speed_m_s':.40,'loop':True,'planner':'Ground-floor corridor patrol; reference-inspired approximate layout','detector':'Webots camera Recognition ground truth','localization':'Simulated indoor pose via GPS device; no real indoor GPS or SLAM claim','total_items':6}
(ROOT/'maps/mission.json').write_text(json.dumps(mission,indent=2))
# Reuse the validated six-wheel geometry, retaining the actual 8-inch footprint.
proto=(ROOT/'tools/CampusScout.base.proto').read_text().replace('PROTO CampusScout','PROTO IndoorScout').replace('controller "campus_rover"','controller "indoor_rover"').replace('width 320 height 240','width 640 height 480')
proto=proto.replace('Emitter { name "telemetry" channel 37 }','''LED { translation -.01 0 .22 name "photo_flash" color [ 1 1 1 ] children [ PointLight { location 0 0 .03 intensity 1 radius 2 attenuation 0 0 1 } Shape { appearance PBRAppearance { baseColor 1 1 1 emissiveColor 0 0 0 } geometry Sphere { radius .008 subdivision 1 } } ] }
Emitter { name "telemetry" channel 39 }''')
(ROOT/'protos/IndoorScout.proto').write_text(proto)
# Model lost objects with recognizable backpack seams, straps, pages and bottle cap.
def item(kind,sid,x,y,color,heading=0):
 children=[]
 def ob(pos,size,c):return f'Pose {{ translation {pos[0]} {pos[1]} {pos[2]} children [ Shape {{ appearance {app(c)} geometry Box {{ size {size[0]} {size[1]} {size[2]} }} }} ] }}'
 if kind=='backpack':
  children=[ob((0,0,.18),(.16,.28,.36),color),ob((.088,0,.105),(.035,.23,.14),'.56 .36 .21'),ob((.111,0,.18),(.012,.21,.01),'.13 .13 .12')]
  for yy in [-.075,.075]:children.append(ob((-.092,yy,.18),(.022,.035,.30),'.09 .10 .10'))
  children.append(ob((0,0,.38),(.05,.09,.025),'.13 .13 .12'));bo='Pose { translation 0 0 .18 children [ Box { size .16 .28 .36 } ] }'
 elif kind=='book':
  children=[ob((0,0,.018),(.26,.19,.036),color),ob((.006,0,.022),(.245,.18,.022),'.88 .85 .76'),ob((-.125,0,.021),(.015,.19,.038),color)];bo='Pose { translation 0 0 .02 children [ Box { size .26 .19 .04 } ] }'
 else:
  children=[f'Pose {{ translation 0 0 .125 children [ Shape {{ appearance {app(color)} geometry Cylinder {{ radius .04 height .25 }} }} ] }}',f'Pose {{ translation 0 0 .26 children [ Shape {{ appearance {app("dark")} geometry Cylinder {{ radius .028 height .025 }} }} ] }}'];bo='Pose { translation 0 0 .13 children [ Cylinder { radius .04 height .26 } ] }'
 parts.append(f'DEF ITEM_{sid} Solid {{ translation {x} {y} .003 rotation 0 0 1 {heading} name "{kind}_{sid}" model "{kind}|GATES-{sid:03}" recognitionColors [ {color} ] children [ {" ".join(children)} ] boundingObject {bo} }}')
for data in [('backpack',1,2,-11.35,'.48 .21 .12',0),('book',2,4.65,-8.2,'.31 .17 .48',0),('backpack',3,11,-9.3,'.12 .25 .34',0),('bottle',4,4.65,2,'.12 .52 .52',0),('backpack',5,-3.35,8,'.26 .27 .14',0),('book',6,-3.35,-4,'.6 .16 .12',0)]:item(*data)
world='''#VRML_SIM R2025a utf8
EXTERNPROTO "../protos/IndoorScout.proto"
WorldInfo { title "Gates Atrium | Campus Scout Showcase" basicTimeStep 16 FPS 30 coordinateSystem "ENU" randomSeed 42 info [ "Reference-inspired presentation model; approximate dimensions and layout" "No user reference photographs are embedded" ] contactProperties [ ContactProperties { material1 "tire" coulombFriction .7 forceDependentSlip .005 bounce 0 softERP .3 softCFM .0001 bumpSound "" rollSound "" slideSound "" } ] }
DEF SHOWCASE_VIEW Viewpoint { position -1 -13.5 .95 orientation 0 0 1 0 near .06 far 120 fieldOfView 1.18 }
Background { skyColor [ .58 .72 .79 ] }
'''+ '\n'.join(lights)+ '\n'+ '\n'.join(parts)+'''
DEF ROVER IndoorScout { translation 0 -12 .003 rotation 0 0 1 0 }
DEF DIRECTOR Robot { name "GatesDirector" supervisor TRUE controller "showcase_director" children [ Receiver { name "telemetry" channel 39 } Display { name "photo_board" width 300 height 220 } ] }
'''
(ROOT/'worlds/gates_atrium.wbt').write_text(world)
view='Webots Project File version R2025a\n'+''.join(f'renderingDevicePerspectives: CampusScout:camera_{i};0;1;0;0\n'for i in range(4))+'renderingDevicePerspectives: GatesDirector:photo_board;0;1;0.7;0.05\n'
(ROOT/'tools/showcase.wbproj').write_text(view);(ROOT/'worlds/.gates_atrium.wbproj').write_text(view)
print('Built reference-inspired atrium:',len(parts),'geometry groups;',len(dense),'route targets;',mission['length_m'],'m patrol')
