"""Regression controls for the actual false-positive and wrong-lens failure modes."""
from pathlib import Path
import os,sys,tempfile,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['PERCEPTION_STATE']=tempfile.mkdtemp(prefix='quality_control_')
from PIL import Image
from quality import candidate_reason,image_quality_reason,type_words
from confirm import Confirmer,Sighting,bearing_of,intersect
from pose import Pose

def check(name,condition):
 assert condition,name
 print('[quality] PASS',name)
for color in ['black','white','#222222']:
 check('reject blank '+color,image_quality_reason(Image.new('RGB',(640,480),color))is not None)
item={'title':'Black rectangular object','category':'Other','color':'Black','box':{'x1':0,'y1':0,'x2':640,'y2':480}}
check('reject reproduced whole-scene false positive',candidate_reason(item,640,480)is not None)
item['box']={'x1':100,'y1':100,'x2':200,'y2':220}
check('reject generic identity even with valid box',candidate_reason(item,640,480)is not None)
item.update(title='Navy backpack',category='Bags')
check('accept specific visible backpack',candidate_reason(item,640,480)is None)
check('type association does not use shared color',not (type_words({'title':'Blue bottle'})&type_words({'title':'Blue backpack'})))
W=1920;hfov=1.64;point=(0.,3.);frame=Path(os.environ['PERCEPTION_STATE'])/'frame.png';Image.new('RGB',(W,1440)).save(frame)
def box(x):
 theta=math.atan2(3.,-x)-math.pi/2;cx=W*(.5-math.tan(theta)/(2*math.tan(hfov/2)))
 return {'x1':cx-45,'x2':cx+45,'y1':500,'y2':650}
c=Confirmer();duck={'title':'Yellow rubber duck','category':'Other','color':'Yellow'}
first=c.observe(Pose(0,0,0,0),1,frame,W,[{**duck,'box':box(0)}],hfov=hfov)
second=c.observe(Pose(1.2,0,0,5),1,frame,W,[{**duck,'box':box(1.2)}],hfov=hfov)
check('94-degree camera metadata confirms a real second viewpoint',not first and len(second)==1)
check('wrong lens produces a different bearing',abs(bearing_of(Pose(1.2,0,0,5),1,box(1.2),W,hfov)-bearing_of(Pose(1.2,0,0,5),1,box(1.2),W,.87))>.1)
a=Sighting(0,0,0,duck,frame);b=Sighting(1,0,.001,duck,frame)
check('near-parallel rays cannot confirm',intersect(a,b)is None)
a=Sighting(0,0,0,{'title':'Blue bottle','category':'Other','color':'Blue'},frame);b=Sighting(1,0,1,{'title':'Blue backpack','category':'Other','color':'Blue'},frame)
check('matching broad category and color do not conflate objects',not c._same_item(a,b))
camera=Pose(2,3,math.pi/2,5).at_offset([.343,.257,.90])
check('calibrated camera offset rotates with robot heading',abs(camera.x-(2-.257))<1e-8 and abs(camera.y-(3+.343))<1e-8)
print('[quality] ALL PASS')
