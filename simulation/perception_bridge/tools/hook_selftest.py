"""Camera duty-cycle and image/pose timestamp regression test, without Webots."""
import sys,tempfile,json,math,importlib.util
from pathlib import Path
root=Path(__file__).resolve().parents[3];path=root/'simulation-indoors/controllers/indoor_rover/perception_hook.py'
spec=importlib.util.spec_from_file_location('hook_under_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Sensors:
 t=0.
 def getSamplingPeriod(self):return 64
 def getValues(self):return [self.t,0.,0.]
sensor=Sensors()
class Compass:
 def getValues(self):return [0.,1.,0.]
class Camera:
 def __init__(self):self.active=False;self.armed_ticks=0
 def disable(self):self.active=False
 def enable(self,ms):assert ms==64;self.active=True
 def getFov(self):return 1.64
 def getWidth(self):return 1920
 def getHeight(self):return 1440
 def saveImage(self,path,quality):
  assert self.active
  Path(path).write_bytes(b'synchronized-frame');return 0
cams={1:Camera(),3:Camera()};folder=Path(tempfile.mkdtemp(prefix='hook_sync_test_'));hook=module.PerceptionHook(cams,sensor,Compass(),folder)
for tick in range(161):
 sensor.t=tick*.064
 for c in cams.values():c.armed_ticks+=int(c.active)
 hook.maybe(sensor.t)
metas=[json.loads(p.read_text())for p in sorted(folder.glob('frame_*.json'))]
assert len(metas)==2
for index,meta in enumerate(metas,1):
 assert 0<=meta['sim_time_s']-index*5<.065
 assert abs(meta['gps'][0]-meta['sim_time_s'])<.006
 assert meta['sampling_period_ms']==64
 assert all(c['hfov']==1.64 for c in meta['cameras'])
 assert not any(k in meta for k in ['objects','recognition','ground_truth'])
assert all(c.armed_ticks<25 for c in cams.values())
print('[hook] PASS 5-second schedule, current-pose capture, 64ms calibration, bounded rendering duty cycle and no simulator labels in payload')
