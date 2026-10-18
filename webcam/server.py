#!/usr/bin/env python3
"""Loopback webcam gateway. Keys stay server-side; camera frames are never saved to disk."""
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import base64, binascii, io, json, os, secrets, threading, time, urllib.error, urllib.request
from PIL import Image, UnidentifiedImageError

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
    def __init__(self, address, identify_url, ingest_secret):
        super().__init__(address, Handler)
        self.identify_url, self.ingest_secret = identify_url, ingest_secret
        self.token = secrets.token_urlsafe(32)
        self.inference_lock = threading.Lock()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)
    def end_headers(self):
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
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
    def do_GET(self):
        if not self.valid_host(): self.reply(403, {'error':'Use the loopback URL.'}); return
        if self.path == '/api/config':
            self.reply(200, {'token':self.server.token, 'model':'Perceptron Mk1.5', 'dry_run':True, 'interval_s':5}); return
        if self.path.startswith('/api/'):
            self.reply(404, {'error':'Not found'}); return
        super().do_GET()
    def do_POST(self):
        if self.path != '/api/analyze': self.reply(404, {'error':'Not found'}); return
        if not self.valid_host() or self.headers.get('Sec-Fetch-Site') == 'cross-site' or self.headers.get('Origin', 'http://'+self.headers.get('Host','')) != 'http://'+self.headers.get('Host','') or not secrets.compare_digest(self.headers.get('X-Webcam-Token',''), self.server.token):
            self.reply(403, {'error':'Open this page locally and reload it.'}); return
        try:
            n = int(self.headers.get('Content-Length','0'))
            if not 0 < n <= MAX_BODY: self.reply(413, {'error':'Camera frame is too large.'}); return
            if self.headers.get_content_type() != 'application/json': raise ValueError('Send JSON.')
            body = json.loads(self.rfile.read(n))
            raw, (w,h) = decode_frame(body.get('image'))
        except (ValueError, TypeError, AttributeError) as e:
            self.reply(400, {'error':str(e)}); return
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
            self.reply(200, {'model':'Perceptron Mk1.5','dry_run':True,'width':w,'height':h,'detections':detections,
                            'skipped_count':len(result.get('skipped',[])),'elapsed_s':round(time.monotonic()-start,2)})
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
    server = WebcamServer(('127.0.0.1',port), 'http://127.0.0.1:'+os.environ.get('WEBCAM_IDENTIFY_PORT','8001'), secret)
    print(f'Webcam demo: http://127.0.0.1:{port}/ — real Perceptron, no Supabase writes', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__ == '__main__': main()
