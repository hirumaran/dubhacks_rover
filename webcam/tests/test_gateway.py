import base64, io, json, sys, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import WebcamServer, decode_frame

def frame(w=640,h=480):
    out=io.BytesIO();Image.new('RGB',(w,h),'#557766').save(out,format='JPEG')
    return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()

class Identifier(BaseHTTPRequestHandler):
    payloads=[]
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.payloads.append(body)
        result={'dry_run':True,'identified':[{'title':'Black backpack','object_type':'backpack','category':'Bags','color':'Black','box':{'x1':100,'y1':80,'x2':250,'y2':280}}, {'title':'Bad box','box':{'x1':-1,'y1':0,'x2':99999,'y2':5}}],'skipped':[]}
        data=json.dumps(result).encode();self.send_response(200);self.end_headers();self.wfile.write(data)
    def log_message(self,*_): pass

class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=ThreadingHTTPServer(('127.0.0.1',0),Identifier)
        cls.server=WebcamServer(('127.0.0.1',0),f'http://127.0.0.1:{cls.model.server_port}','test-private-secret')
        for s in (cls.model,cls.server):threading.Thread(target=s.serve_forever,daemon=True).start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        for s in (cls.model,cls.server):s.shutdown();s.server_close()
    def post(self,body,**headers):
        req=urllib.request.Request(self.url+'/api/analyze',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Webcam-Token':self.server.token,**headers})
        return urllib.request.urlopen(req)
    def test_pixels_only_forced_demo_dry_run(self):
        with self.post({'image':frame(),'dry_run':False,'latitude':123,'items':[{'title':'fake'}]})as r:d=json.load(r)
        sent=Identifier.payloads[-1]
        self.assertTrue(sent['dry_run']);self.assertTrue(sent['is_demo']);self.assertEqual(sent['latitude'],0);self.assertNotIn('items',sent)
        self.assertEqual(len(d['detections']),1);self.assertEqual(d['detections'][0]['title'],'Black backpack')
    def test_cross_origin_rejected_before_inference(self):
        n=len(Identifier.payloads)
        with self.assertRaises(urllib.error.HTTPError)as e:self.post({'image':frame()},Origin='https://external.invalid')
        self.assertEqual(e.exception.code,403);self.assertEqual(n,len(Identifier.payloads))
    def test_missing_token_rejected(self):
        with self.assertRaises(urllib.error.HTTPError)as e:self.post({'image':frame()},**{'X-Webcam-Token':''})
        self.assertEqual(e.exception.code,403)
    def test_invalid_and_oversized_dimensions(self):
        for value in ['not an image','data:image/jpeg;base64,ZmFrZQ==',frame(1921,32)]:
            with self.assertRaises(ValueError):decode_frame(value)
    def test_config_has_no_service_credentials(self):
        with urllib.request.urlopen(self.url+'/api/config')as r:
            d=json.load(r);self.assertIn('microphone=()',r.headers['Permissions-Policy'])
        self.assertEqual(set(d),{'token','model','dry_run','interval_s','mobile_enabled'});self.assertNotIn('test-private-secret',json.dumps(d))
    def test_private_sources_are_not_served(self):
        for p in ['/server.py','/../edge-functions/.env','/api/other']:
            with self.assertRaises(urllib.error.HTTPError)as e:urllib.request.urlopen(self.url+p)
            self.assertEqual(e.exception.code,404)
if __name__=='__main__':unittest.main()
