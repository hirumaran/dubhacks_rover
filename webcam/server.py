#!/usr/bin/env python3
"""Loopback webcam gateway. Keys stay server-side; camera frames are never saved to disk."""
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import base64, binascii, io, json, os, secrets, threading, time, urllib.error, urllib.request
from PIL import Image, UnidentifiedImageError
import mobile
import cloud

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'presentation'
MAX_BODY = 4_000_000

def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values

def decode_frame(value):
    if not isinstance(value, str) or not value.startswith(('data:image/jpeg;base64,', 'data:image/png;base64,')):
        raise ValueError('Send a JPEG or PNG camera frame.')
    try:
        raw = base64.b64decode(value.split(',', 1)[1], validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG', 'PNG') or not (32 <= image.width <= 1920 and 32 <= image.height <= 1440):
                raise ValueError('Frame dimensions must be between 32×32 and 1920×1440.')
            image.load()
            size = image.size
    except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ValueError('Invalid camera image.') from e
    return raw, size

class WebcamServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, identify_url, ingest_secret, mobile_enabled=False, rover_dirs=None):
        super().__init__(address, Handler)
        self.identify_url, self.ingest_secret = identify_url, ingest_secret
        self.token = secrets.token_urlsafe(32)
        self.inference_lock = threading.Lock()
        mobile.configure(self, mobile_enabled, rover_dirs)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)
    def end_headers(self):
        if self.path.startswith('/api/mobile/'):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Permissions-Policy', 'camera=(self), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        super().end_headers()
    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def valid_host(self):
        return self.client_address[0] in ('127.0.0.1', '::1') and self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
    def do_GET(self):
        if self.path.startswith('/api/mobile/'):
            mobile.get(self); return
        if not self.valid_host(): self.reply(403, {'error':'Use the loopback URL.'}); return
        if self.path == '/api/config':
            self.reply(200, {'token':self.server.token, 'model':'Perceptron Mk1.5', 'dry_run':True, 'interval_s':5, 'mobile_enabled':self.server.mobile_enabled}); return
        if self.path.startswith('/api/'):
            self.reply(404, {'error':'Not found'}); return
        super().do_GET()
    def do_OPTIONS(self):
        if not self.path.startswith('/api/mobile/') or not self.server.mobile_enabled:
            self.reply(404, {'error':'Not found'}); return
        self.send_response(204); self.end_headers()
    def do_POST(self):
        is_mobile = self.path == '/api/mobile/analyze'
        if self.path not in ('/api/analyze', '/api/preview', '/api/cloud-sharing', '/api/pairing', '/api/mobile/analyze'): self.reply(404, {'error':'Not found'}); return
        local_auth = self.valid_host() and self.headers.get('Sec-Fetch-Site') != 'cross-site' and self.headers.get('Origin', 'http://'+self.headers.get('Host','')) == 'http://'+self.headers.get('Host','') and secrets.compare_digest(self.headers.get('X-Webcam-Token',''), self.server.token)
        if not (mobile.authorized(self) if is_mobile else local_auth):
            self.reply(403, {'error':'Pair again using the current Scout gateway code.' if is_mobile else 'Open this page locally and reload it.'}); return
        try:
            n = int(self.headers.get('Content-Length','0'))
            if not 0 < n <= MAX_BODY: self.reply(413, {'error':'Camera frame is too large.'}); return
            if self.headers.get_content_type() != 'application/json': raise ValueError('Send JSON.')
            body = json.loads(self.rfile.read(n))
            if self.path == '/api/pairing':
                if not self.server.mobile_enabled:
                    self.reply(409, {'error':'Restart the gateway with --mobile to enable Expo Go pairing.'}); return
                self.reply(200, {'code':self.server.mobile_token}); return
            if self.path == '/api/cloud-sharing':
                if not getattr(self.server,'cloud_config',None):
                    self.reply(503,{'error':'Configure the judging relay first: npm run configure:cloud'});return
                self.server.cloud_enabled=body.get('enabled') is True
                self.server.cloud_deadline=time.monotonic()+15
                if not self.server.cloud_enabled:
                    for source in ('webcam','rover'):cloud.publish(self.server,source=source,clear=True)
                self.reply(200,{'enabled':self.server.cloud_enabled});return
            if self.path == '/api/preview' and body.get('image') is None:
                self.server.preview = None
                self.server.webcam_analysis = None
                if getattr(self.server,'cloud_enabled',False):cloud.publish(self.server,clear=True)
                self.reply(200, {'shared':False}); return
            raw, (w,h) = decode_frame(body.get('image'))
        except (ValueError, TypeError, AttributeError) as e:
            self.reply(400, {'error':str(e)}); return
        if self.path == '/api/preview':
            self.server.preview_sequence += 1
            self.server.preview = {'image':body['image'], 'width':w, 'height':h,
                                   'updated_at':time.time(), 'frame_id':self.server.preview_sequence, 'detections':[]}
            cloud.publish(self.server,self.server.preview)
            self.reply(200, {'shared':True}); return
        if not self.server.inference_lock.acquire(blocking=False):
            self.reply(429, {'error':'Another camera frame is still being analyzed. Please wait.'}); return
        try:
            start = time.monotonic()
            # Only pixels reach the existing identifier. No real location is collected or inferred.
            payload = {'image_base64':base64.b64encode(raw).decode(), 'source':'community', 'is_demo':True,
                       'dry_run':True, 'approximate_location':'Webcam demo — location not collected',
                       'latitude':0, 'longitude':0, 'min_box_px':32}
            req = urllib.request.Request(self.server.identify_url, data=json.dumps(payload).encode(),
                  headers={'Content-Type':'application/json','x-ingest-secret':self.server.ingest_secret}, method='POST')
            with urllib.request.urlopen(req, timeout=180) as res: result = json.load(res)
            if result.get('dry_run') is not True: raise ValueError('Identifier did not confirm dry-run mode.')
            detections = []
            for item in result.get('identified', []):
                b = item.get('box', {})
                try:
                    x1,y1,x2,y2 = [float(b[k]) for k in ('x1','y1','x2','y2')]
                    if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h): continue
                except (ValueError, TypeError, KeyError): continue
                detections.append({k:item.get(k) for k in ('title','description','object_type','category','color')} | {'box':{'x1':x1,'y1':y1,'x2':x2,'y2':y2},'bbox':[x1/w,y1/h,(x2-x1)/w,(y2-y1)/h]})
            response = {'model':'Perceptron Mk1.5','dry_run':True,'width':w,'height':h,'detections':detections,
                        'skipped_count':len(result.get('skipped',[])),'elapsed_s':round(time.monotonic()-start,2)}
            if not is_mobile and self.server.preview is not None:
                self.server.webcam_analysis = {**response, 'image':body['image'], 'updated_at':time.time()}
            self.reply(200, response)
        except urllib.error.HTTPError as e:
            self.reply(502, {'error':f'Vision service returned HTTP {e.code}. Try another scan.'})
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            self.reply(502, {'error':'Vision service is unavailable or timed out. Check the launch terminal, then retry.'})
        finally:
            self.server.inference_lock.release()
    def list_directory(self, path): self.send_error(404); return None
    def translate_path(self, path):
        p = Path(super().translate_path(path)).resolve()
        return str(p) if p.is_relative_to(WEB.resolve()) else str(WEB/'__denied__')
    def log_message(self, *_): pass

def main():
    repo = ROOT.parent
    config = {**read_env(repo/'edge-functions/.env'), **os.environ}
    secret = config.get('ROVER_INGEST_SECRET','')
    if not secret: raise SystemExit('Missing ROVER_INGEST_SECRET in private edge-functions/.env')
    port = int(os.environ.get('WEBCAM_PORT','8769'))
    enabled = os.environ.get('WEBCAM_MOBILE') == '1'
    server = WebcamServer(('127.0.0.1',port), 'http://127.0.0.1:'+os.environ.get('WEBCAM_IDENTIFY_PORT','8001'), secret, mobile_enabled=enabled)
    cloud.configure(server,repo,secret)
    print(f'Webcam demo: http://127.0.0.1:{port}/ — real Perceptron, no Supabase writes', flush=True)
    if enabled:
        print(f'\nSCOUT PAIRING CODE: {server.mobile_token}\n', flush=True)
        print('Paste this one code into the Expo Scout tab. Scout uses the same Expo tunnel as your app; no IP address or firewall rule is needed. Restart to revoke it.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__ == '__main__': main()
