#!/usr/bin/env python3
"""Run the self-contained native simulation and its loopback showcase together."""
from pathlib import Path
import argparse,sys,subprocess,shutil,socket,time,json,os,atexit,signal
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--presentation-only',action='store_true');p.add_argument('--fresh',action='store_true');a=p.parse_args()
def port_open(port):
 with socket.socket() as s:s.settimeout(.3);return s.connect_ex(('127.0.0.1',port))==0
webots=Path('/Applications/Webots.app/Contents/MacOS/webots')
if not webots.exists():
 found=shutil.which('webots')
 if found:webots=Path(found)
 elif not a.presentation_only:sys.exit('Webots was not found. Install Webots R2025a or put webots on your PATH.')
if port_open(1242) and not a.presentation_only:sys.exit('An indoor Webots session already uses port 1242. Open http://127.0.0.1:8768 or close that Webots session before launching again.')
data=ROOT/'presentation/data';data.mkdir(parents=True,exist_ok=True)
if a.fresh or not(data/'items.json').exists():
 old=ROOT/'logs'/('capture_archive_'+time.strftime('%Y%m%d_%H%M%S'))
 if(data/'items.json').exists():
  old.mkdir(parents=True,exist_ok=True);shutil.copy(data/'items.json',old/'items.json')
  if(data/'snapshots.json').exists():shutil.copy(data/'snapshots.json',old/'snapshots.json')
  if(data/'snapshots').exists():shutil.copytree(data/'snapshots',old/'snapshots')
  if(data/'captures').exists():shutil.copytree(data/'captures',old/'captures')
 (data/'items.json').write_text('[]');(data/'snapshots.json').write_text('[]')
(data/'control.json').unlink(missing_ok=True)
preferences=ROOT/'worlds/.gates_atrium.wbproj'
if a.fresh or not preferences.exists():shutil.copy(ROOT/'tools/showcase.wbproj',preferences)
server=None;sim=None;bridge=None;identifier=None
def child(*args,**kwargs):
 return subprocess.Popen(*args,start_new_session=(os.name=='posix'),**kwargs)
def cleanup():
 for process in [sim,server,bridge,identifier]:
  if process and process.poll() is None:
   if os.name=='posix':os.killpg(process.pid,signal.SIGTERM)
   else:process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:
    if os.name=='posix':os.killpg(process.pid,signal.SIGKILL)
    else:process.kill()
atexit.register(cleanup)
model_env=os.environ.copy()
def read_env(path):
 values={}
 for line in path.read_text().splitlines():
  if line.strip() and not line.lstrip().startswith('#') and '='in line:
   key,value=line.split('=',1);values[key.strip()]=value.strip().strip('"').strip("'")
 return values
repo=next((p for p in ROOT.parents if (p/'edge-functions/identify-found-items/index.ts').exists()),None)
if os.environ.get('LOCAL_VISION')=='1' and not a.presentation_only:
 if not repo:sys.exit('The local vision demo requires the repository edge-functions/ folder.')
 if port_open(8000):sys.exit('Port 8000 is in use. Stop the existing local identification server first.')
 secrets_path=repo/'edge-functions/.env';ui_path=repo/'ui/.env'
 if not secrets_path.exists() or not ui_path.exists():sys.exit('Local vision requires the supplied edge-functions/.env and ui/.env files (kept private).')
 ui_config=read_env(ui_path)
 identifier_env={**os.environ,**read_env(secrets_path),'LOCAL_ONLY':'1','SUPABASE_URL':ui_config['EXPO_PUBLIC_SUPABASE_URL'],'SUPABASE_SERVICE_ROLE_KEY':ui_config['EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY']}
 deno=[shutil.which('deno')] if shutil.which('deno') else ['npx','--yes','deno@2.9.6']
 identifier=child(deno+['run','--node-modules-dir=none','--allow-net','--allow-env',str(repo/'edge-functions/identify-found-items/index.ts')],cwd=repo,env=identifier_env)
 for attempt in range(120):
  if port_open(8000):break
  if identifier.poll() is not None:sys.exit('Local identification server could not start.')
  time.sleep(.25)
 else:
  identifier.terminate();sys.exit('Local identification server timed out.')
 model_env.update({'IDENTIFY_URL':'http://127.0.0.1:8000','DRY_RUN':'true'})
 print('Local hardened vision API is ready. Actual hosted Perceptron model; database writes disabled.',flush=True)

bridge_root=next((p for p in [ROOT.parent/'simulation/perception_bridge',ROOT.parent/'perception_bridge']if (p/'config.py').exists()),None)
if bridge_root and (bridge_root/'.env').exists() and not a.presentation_only:
 interpreter=bridge_root/'.venv/bin/python'
 if not interpreter.exists():sys.exit('Install the vision bridge first: python3 -m venv simulation/perception_bridge/.venv && simulation/perception_bridge/.venv/bin/pip install -r simulation/perception_bridge/requirements.txt')
 model_env.update({'PERCEPTION_INBOX':str(bridge_root/'inbox'),'PERCEPTION_MISSION':str(ROOT/'maps/mission.json'),'PERCEPTION_PUBLIC_DIR':str(ROOT/'presentation/data'),'LOCATION_LABEL':'Gates Center atrium (simulated)'})
 inbox=bridge_root/'inbox'
 if inbox.exists() and any(inbox.iterdir()):
  old_inbox=ROOT/'logs'/('inbox_archive_'+time.strftime('%Y%m%d_%H%M%S'));old_inbox.mkdir(parents=True,exist_ok=True)
  for old_file in inbox.iterdir():
   if old_file.is_file():shutil.move(str(old_file),str(old_inbox/old_file.name))
 print('Starting actual Perceptron vision bridge; simulator reference labels disabled.',flush=True)
 bridge=child([str(interpreter),str(bridge_root/'run_bridge.py')],cwd=bridge_root,env=model_env)
 time.sleep(.5)
 if bridge.poll() is not None:sys.exit('Perception bridge could not start. Check its configuration.')
try:
 if not port_open(8768):server=child([sys.executable,str(ROOT/'tools/serve_showcase.py')],cwd=ROOT)
 print('\nOpen http://127.0.0.1:8768 in your browser.\nCamera controls and Restart mission work while Webots runs.\nCtrl+C stops processes launched by this command.\n',flush=True)
 if not a.presentation_only:
  sim=child([str(webots),'--batch','--mode=realtime','--stdout','--stderr','--port=1242',str(ROOT/'worlds/gates_atrium.wbt')],cwd=ROOT,env=model_env);sim.wait()
 elif server:server.wait()
except KeyboardInterrupt:pass
finally:cleanup()
