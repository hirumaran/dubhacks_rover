"""Location-free local presentation of actual model results; never publishes credentials/poses."""
from pathlib import Path
import json,os,shutil,hashlib
from PIL import Image

class PublicStatus:
 def __init__(self):
  value=os.environ.get('PERCEPTION_PUBLIC_DIR');self.root=Path(value)if value else None;self.items={};self.count=0
  if self.root:
   (self.root/'perception/frames').mkdir(parents=True,exist_ok=True)
   (self.root/'perception.json').write_text(json.dumps({'model':'Perceptron Mk1.5','status':'waiting','image':None,'detections':[],'confirmed_items':[],'requests_processed':0,'rejected_count':0,'simulation_time_s':0,'camera':None,'demo':True}))
 def publish(self,seq,cam,pose,image,accepted,rejected,result,confirmed=()):
  if self.root is None:return
  self.count+=1;key=f'{self.count:06}_{seq}_{cam}';frame=f'perception/frames/{key}.jpg';shutil.copyfile(image,self.root/frame)
  with Image.open(image)as photo:
   w,h=photo.size;dets=[]
   for i,item in enumerate(accepted):
    box=item['box'];crop=f'perception/frames/{key}_{i}.jpg'
    xy=tuple(int(box[k])for k in ('x1','y1','x2','y2'));photo.crop(xy).save(self.root/crop,quality=90)
    det={'sample_id':f'candidate-{key}-{i}','category':item.get('category'),'description':item.get('title'),'image':crop,'frame_image':frame,'snapshot_id':None,'simulation_time_s':pose.sim_time_s,'direction':{0:'Front',1:'Left',2:'Rear',3:'Right'}.get(cam,str(cam)),'bbox':[box['x1']/w,box['y1']/h,(box['x2']-box['x1'])/w,(box['y2']-box['y1'])/h],'detector':'Perceptron Mk1.5 — camera pixels only'}
    dets.append(det)
    for original,listing in confirmed:
     if original is item:
      rows=listing.get('listed',[])or listing.get('identified',[])or listing.get('duplicates',[])
      if listing.get('status')=='ok'and rows:
       row=rows[0];identity=row.get('id')or row.get('existing_found_item_id')or f'confirmed-{key}-{i}'
       self.items[identity]={**det,'sample_id':identity,'confirmed':True,'dry_run':listing.get('dry_run',False)}
  state={'model':'Perceptron Mk1.5','status':result.get('status'),'error':result.get('error'),'simulation_time_s':pose.sim_time_s,'camera':cam,'image':frame,'detections':dets,'rejected_count':rejected,'confirmed_items':list(self.items.values()),'requests_processed':self.count,'demo':True}
  target=self.root/'perception.json';tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));os.replace(tmp,target)
