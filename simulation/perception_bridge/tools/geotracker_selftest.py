"""Location/identity and restart regression tests; no model credits or database calls."""
from pathlib import Path
import json,os,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=Path(tempfile.mkdtemp(prefix='item_geo_test_'))
os.environ.update(PERCEPTION_STATE=str(root/'state'),PERCEPTION_MISSION=str(root/'mission.json'))
(root/'mission.json').write_text(json.dumps({'map':'Test room','reference_lat_lon':[47,-122]}))
from PIL import Image
from geotracker import GeoTracker
frame=root/'frame.jpg';Image.new('RGB',(640,480),'navy').save(frame)
item={'title':'Black backpack','description':'Black backpack with a pocket','category':'Bags','color':'Black','box':{'x1':80,'y1':80,'x2':220,'y2':280}}
def never(_):raise AssertionError('New/far/type-distinct item should not need a comparison')
g=GeoTracker();first,why=g.associate((1,2),item,frame,never);assert first['sighting_count']==1
restarted=GeoTracker();second,why=restarted.associate((1.4,2.2),item,frame,lambda _:{'same_item':True,'needs_review':False})
assert first['track_id']==second['track_id'] and second['sighting_count']==2
print('PASS same nearby visual item retains its ID across service restart')
other,_=restarted.associate((2.6,2.1),item,frame,lambda _:{'same_item':False,'needs_review':False})
assert other['track_id']!=first['track_id']
print('PASS visually different same-type item 1.6 meters away gets a separate track')
conflict,_=restarted.associate((1.1,2.1),item,frame,lambda _:{'same_item':False,'needs_review':False});assert conflict is None
print('PASS contradictory descriptions at the same anchor are deferred, not duplicated')
bottle={**item,'title':'Black bottle','category':'Water Bottles'}
third,_=restarted.associate((1,2),bottle,frame,never);assert third['track_id']not in (first['track_id'],other['track_id'])
print('PASS different type at the same location is not suppressed')
far,_=restarted.associate((50,2),item,frame,never);assert far['track_id']!=first['track_id']
print('PASS far-away lookalike is a separate item')
unclear,_=restarted.associate((1,2),item,frame,lambda _:{'same_item':False,'needs_review':True});assert unclear is None
failed,_=restarted.associate((1,2),item,frame,lambda _:(_ for _ in ()).throw(OSError('offline')));assert failed is None
print('PASS ambiguity/network failure cannot create a second listing')
meta=restarted.metadata(first);assert meta['latitude']!=0 and meta['longitude']!=0 and meta['tracker_id']==first['track_id']
assert meta['sighting_id']!=restarted.metadata(first)['sighting_id']
assert (restarted.path.stat().st_mode&0o777)==0o600
print('PASS private item geotag and retry-safe unique sighting IDs')
print('[geotracker] ALL PASS')
