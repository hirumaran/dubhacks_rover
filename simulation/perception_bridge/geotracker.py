"""Durable, private item anchors. Location narrows candidates; Perceptron decides identity."""
from pathlib import Path
import base64,hashlib,io,json,math,os,time,uuid
from PIL import Image
import config
from pose import Pose
from quality import type_words

class GeoTracker:
    def __init__(self):
        try:mission=json.loads(config.MISSION_PATH.read_text())
        except (OSError,ValueError):mission={}
        context={'map':mission.get('map'),'origin':mission.get('reference_lat_lon'),'demo':config.IS_DEMO}
        self.scope=os.environ.get('ITEM_TRACKING_SCOPE')or hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()[:24]
        self.root=config.STATE_DIR/'geotracking'/self.scope
        self.root.mkdir(parents=True,exist_ok=True);self.root.chmod(0o700)
        self.path=self.root/'tracks.json'
        self.tracks=json.loads(self.path.read_text())if self.path.exists()else []
    def save(self):
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.tracks,indent=2));tmp.chmod(0o600);os.replace(tmp,self.path)
    def associate(self,point,item,frame,compare):
        """Returns (track, reason); ambiguous/failed comparisons defer instead of posting twice."""
        kinds=type_words(item)
        if len(point)!=2 or not all(math.isfinite(v)for v in point):raise ValueError('invalid item position')
        with Image.open(frame)as image:
            b=item['box'];crop=image.crop(tuple(int(b[k])for k in ('x1','y1','x2','y2'))).convert('RGB')
            out=io.BytesIO();crop.save(out,format='JPEG',quality=92);pixels=out.getvalue()
        nearby=[(math.dist(point,t['point_local_m']),t)for t in self.tracks if kinds&set(t['types'])and math.dist(point,t['point_local_m'])<=3]
        if len(nearby)>12:return None,'too many nearby identities; review required'
        uncertain=False;matched=[]
        fresh={**{k:str(item.get(k,''))for k in ('title','description','category','color')},'image_base64':base64.b64encode(pixels).decode()}
        for distance,track in sorted(nearby,key=lambda x:x[0]):
            old=self.root/track['photo']
            if not old.exists():uncertain=True;continue
            existing={**track['identity'],'image_base64':base64.b64encode(old.read_bytes()).decode()}
            try:result=compare({'operation':'compare_geotracked_item','fresh':fresh,'existing':existing,'distance_m':distance})
            except (OSError,ValueError,TimeoutError):uncertain=True;continue
            if result.get('same_item')is True:matched.append(track)
            elif result.get('needs_review',True) or distance<=1:uncertain=True
        if len(matched)>1:return None,'multiple possible identities; review required'
        now=time.time()
        if matched:
            track=matched[0];track['last_seen_at']=now;track['sighting_count']+=1;self.save()
            return track,'same location and visually confirmed item'
        if uncertain:return None,'nearby item comparison unavailable or uncertain; deferred'
        track_id=str(uuid.uuid4());photo=track_id+'.jpg';(self.root/photo).write_bytes(pixels);(self.root/photo).chmod(0o600)
        track={'track_id':track_id,'types':sorted(kinds),'identity':{k:str(item.get(k,''))for k in ('title','description','category','color')},'point_local_m':list(point),'photo':photo,'first_seen_at':now,'last_seen_at':now,'sighting_count':1}
        self.tracks.append(track);self.save();return track,'new item anchor'
    def metadata(self,track):
        x,y=track['point_local_m'];lat,lng=Pose(x,y,0,0).lat_lon()
        return {'latitude':lat,'longitude':lng,'accuracy_m':max(.1,min(25,float(os.environ.get('ITEM_POSITION_ACCURACY_M','2')))),'scope':self.scope,'tracker_id':track['track_id'],'sighting_id':str(uuid.uuid4())}
