#!/usr/bin/env python3
"""Loopback-only presentation server; exposes presentation/ only, never navigation logs."""
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import json,os,uuid,argparse,time
ROOT=Path(__file__).resolve().parents[1];WEB=ROOT/'presentation';DATA=WEB/'data'
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(WEB),**kwargs)
 def end_headers(self):
  self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');super().end_headers()
 def do_POST(self):
  if self.path!='/api/control':self.send_error(404);return
  # Only same-origin browser requests may change the simulation camera/reset state.
  origin=self.headers.get('Origin');host=self.headers.get('Host')
  if origin and origin!='http://'+host:self.send_error(403);return
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=512:raise ValueError()
   body=json.loads(self.rfile.read(n));cmd={}
   if body.get('view') in ('orbit','follow','atrium'):cmd['view']=body['view']
   elif body.get('action')=='restart':cmd['action']='restart'
   else:raise ValueError()
   status=DATA/'state.json'
   if not status.exists() or time.time()-status.stat().st_mtime>5 or not json.loads(status.read_text()).get('live'):
    self.send_error(409,'Start Webots to control the live simulation');return
   cmd['nonce']=uuid.uuid4().hex;DATA.mkdir(parents=True,exist_ok=True);tmp=DATA/'control.tmp';tmp.write_text(json.dumps(cmd));os.replace(tmp,DATA/'control.json')
  except (ValueError,TypeError):self.send_error(400);return
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}')
 def log_message(self,*args):pass
 def list_directory(self,path):self.send_error(404);return None
 def translate_path(self,path):
  p=Path(super().translate_path(path)).resolve()
  return str(p)if p.is_relative_to(WEB.resolve())else str(WEB/'__denied__')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8768);args=parser.parse_args();DATA.mkdir(parents=True,exist_ok=True)
 if not(DATA/'items.json').exists():(DATA/'items.json').write_text('[]')
 print(f'Campus Scout showcase: http://127.0.0.1:{args.port} (Ctrl+C to stop)',flush=True)
 ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
