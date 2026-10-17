#!/usr/bin/env python3
"""Run the self-contained native simulation and its loopback showcase together."""
from pathlib import Path
import argparse,sys,subprocess,shutil,socket,time,json,os
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
if not preferences.exists():shutil.copy(ROOT/'tools/showcase.wbproj',preferences)
server=None;sim=None
try:
 if not port_open(8768):server=subprocess.Popen([sys.executable,str(ROOT/'tools/serve_showcase.py')],cwd=ROOT)
 print('\nOpen http://127.0.0.1:8768 in your browser.\nCamera controls and Restart mission work while Webots runs.\nCtrl+C stops processes launched by this command.\n',flush=True)
 if not a.presentation_only:
  sim=subprocess.Popen([str(webots),'--batch','--mode=realtime','--stdout','--stderr','--port=1242',str(ROOT/'worlds/gates_atrium.wbt')],cwd=ROOT);sim.wait()
 elif server:server.wait()
except KeyboardInterrupt:pass
finally:
 for process in [sim,server]:
  if process and process.poll() is None:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:process.kill()
