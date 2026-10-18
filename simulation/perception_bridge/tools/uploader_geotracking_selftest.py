"""An older cloud endpoint must not silently post a tracked item as a new listing."""
from pathlib import Path
import os,sys,tempfile,json,threading
from http.server import BaseHTTPRequestHandler,HTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
state={'capable':False,'posts':0}
class Mock(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(405)
  if state['capable']:self.send_header('X-Item-Geotracking','v1')
  self.end_headers()
 def do_POST(self):
  state['posts']+=1;self.rfile.read(int(self.headers['Content-Length']))
  self.send_response(200);self.end_headers();self.wfile.write(b'{"dry_run":false,"listed":[]}')
 def log_message(self,*_):pass
server=HTTPServer(('127.0.0.1',0),Mock);threading.Thread(target=server.serve_forever,daemon=True).start()
os.environ.update(IDENTIFY_URL=f'http://127.0.0.1:{server.server_port}',DRY_RUN='false',ROVER_INGEST_SECRET='test',PERCEPTION_STATE=tempfile.mkdtemp(prefix='geo_upload_test_'))
from uploader import Uploader
u=Uploader();payload={'dry_run':False,'item_location':{'tracker_id':'test'}}
try:
 result=u.send(payload,'one');assert result['status']=='queued'and state['posts']==0
 print('PASS legacy endpoint blocked before any tracked listing POST')
 state['capable']=True
 retries=u.retry_due(force=True);assert retries[0][1]['status']=='ok'and state['posts']==1 and u.pending()==0
 print('PASS same queued request proceeds after compatible endpoint is deployed')
finally:server.shutdown();server.server_close()
