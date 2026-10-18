"""Self-contained native Webots meshes from official importer geometry."""
import re,math,json
from pathlib import Path
from shapely.geometry import Polygon,LineString
from shapely.geometry.polygon import orient
from shapely.ops import triangulate
counter=0
NUM=r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?'
def field(s,key,default=0):
 m=re.search(r'\b'+key+r'\s+('+NUM+r')',s);return float(m[1])if m else default
def vector(s,key,dim=3):
 m=re.search(r'\b'+key+r'\s+('+NUM+r'(?:\s+'+NUM+r'){'+str(dim-1)+r'})',s)
 return list(map(float,m[1].split()))if m else [0]*dim
def array(s,key,dim):
 m=re.search(r'\b'+key+r'\s*\[([^\]]*)\]',s,re.S)
 if not m:return []
 vals=list(map(float,re.findall(NUM,m[1])));return [vals[i:i+dim]for i in range(0,len(vals)-dim+1,dim)]
def appearance(c):return f'PBRAppearance {{ baseColor {c} roughness 1 metalness 0 }}'
def polygon_geometry(poly,z=.003):
 if not poly.is_valid:poly=poly.buffer(0)
 if poly.is_empty:return ''
 polys=list(poly.geoms)if hasattr(poly,'geoms')else[poly];verts=[];indices=[]
 for p in polys:
  for tri in triangulate(p):
   if not p.covers(tri.representative_point()):continue
   coords=list(tri.exterior.coords)[:3];k=len(verts);verts.extend((x,y,z)for x,y in coords);indices.extend([k,k+1,k+2,-1])
 return f'IndexedFaceSet {{ coord Coordinate {{ point [ '+','.join(' '.join(f'{v:.5f}'for v in p)for p in verts)+' ] } coordIndex [ '+' '.join(map(str,indices))+' ] }'
def convert(typ,s):
 global counter
 counter+=1;idx=counter;tr=vector(s,'translation');name=re.search(r'\bname\s+"([^"]*)"',s);name=name[1]if name else f'OSM_{typ}_{idx}'
 if typ in ('Road','Crossroad'):
  if typ=='Road':
   pts=array(s,'wayPoints',3)
   if len(pts)<2:return ''
   poly=LineString([(p[0],p[1])for p in pts]).buffer(field(s,'width',2)/2,cap_style=2,join_style=2)
  else:
   pts=array(s,'shape',3)
   if len(pts)<3:return ''
   poly=Polygon([(p[0],p[1])for p in pts])
  geo=polygon_geometry(poly)
  if not geo:return ''
  return f'Pose {{ translation {tr[0]} {tr[1]} 0 children [ Shape {{ appearance {appearance(".59 .55 .46")} geometry {geo} }} ] }}'
 if typ=='SimpleBuilding':
  pts=array(s,'corners',2)
  if len(pts)<3:return ''
  if pts[0]==pts[-1]:pts=pts[:-1]
  pts=list(orient(Polygon(pts),sign=1).exterior.coords)[:-1]
  height=max(3,field(s,'floorNumber',3)*field(s,'floorHeight',3));n=len(pts);coords=[(x,y,z)for z in [0,height]for x,y in pts];walls=[];uv=[]
  for i in range(n):
   j=(i+1)%n;walls.extend([i,j,j+n,i+n,-1]);w=math.dist(pts[i],pts[j])/3.2;uv.extend([(0,0),(w,0),(w,height/3.2),(0,height/3.2)])
  tc=' '.join(f'{x:.4f} {y:.4f},'for x,y in uv);ci=' '.join(str(v)for v in walls);ti=' '.join(f'{k*4} {k*4+1} {k*4+2} {k*4+3} -1'for k in range(n));coord=' '.join(f'{x:.4f} {y:.4f} {z:.4f},'for x,y,z in coords)
  geo=f'DEF OSM_BUILDING_{idx} IndexedFaceSet {{ coord Coordinate {{ point [ {coord} ] }} coordIndex [ {ci} ] texCoord TextureCoordinate {{ point [ {tc} ] }} texCoordIndex [ {ti} ] }}'
  roof=polygon_geometry(Polygon(pts),height)
  return f'''Solid {{ translation {tr[0]} {tr[1]} {tr[2]} name {json.dumps(name)} children [ Shape {{ appearance PBRAppearance {{ baseColorMap ImageTexture {{ url [ "textures/campus_facade.png" ] }} roughness 1 metalness 0 }} geometry {geo} }} Shape {{ appearance {appearance('.46 .43 .38')} geometry {roof} }} ] boundingObject USE OSM_BUILDING_{idx} }}'''
 if typ=='SimpleTree':
  h=field(s,'height',5.5);cherry='cherry' in s;col='.83 .58 .65'if cherry else'.22 .38 .19';r=max(1,h*.24)
  return f'''Solid {{ translation {tr[0]} {tr[1]} 0 name {json.dumps(name)} children [ Pose {{ translation 0 0 {h*.25} children [ Shape {{ appearance {appearance('.29 .22 .15')} geometry Cylinder {{ radius .13 height {h*.5} subdivision 8 }} }} ] }} Pose {{ translation 0 0 {h*.7} children [ Shape {{ appearance {appearance(col)} geometry Sphere {{ radius {r} subdivision 2 }} }} ] }} ] boundingObject Pose {{ translation 0 0 {h*.25} children [ Cylinder {{ radius .13 height {h*.5} subdivision 8 }} ] }} }}'''
 return ''
def textures(root):
 from PIL import Image,ImageDraw
 d=root/'worlds/textures';d.mkdir(exist_ok=True)
 im=Image.new('RGB',(256,256),(137,105,81));q=ImageDraw.Draw(im)
 for y in range(0,256,16):
  q.line((0,y,256,y),fill=(109,91,74),width=1)
  for x in range((-16 if (y//16)%2 else 0),256,32):q.line((x,y,x,y+16),fill=(109,91,74))
 q.rectangle((65,42,191,207),fill=(196,185,158));q.rectangle((72,49,184,200),fill=(48,72,75));q.line((128,49,128,200),fill=(168,167,144),width=5);q.line((72,126,184,126),fill=(168,167,144),width=4);q.rectangle((57,205,199,219),fill=(192,181,151));q.polygon([(80,57),(121,57),(80,114)],fill=(75,96,96));im.save(d/'campus_facade.png')
