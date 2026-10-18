"""Offline UI test fixture. Never used by the production launcher or mobile app."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import WebcamServer
from test_gateway import Identifier

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    Image.new('RGB', (640,480), '#557766').save(root/'frame.jpg')
    (root/'perception.json').write_text(json.dumps({'image':'frame.jpg','camera':1,'detections':[{'description':'Fixture bottle','category':'Water Bottles','bbox':[.1,.1,.3,.4]}]}))
    model = ThreadingHTTPServer(('127.0.0.1',0), Identifier)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    server = WebcamServer(('127.0.0.1',8769), f'http://127.0.0.1:{model.server_port}', 'test-only', True, [root])
    print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/#{server.mobile_token}'}), flush=True)
    try: server.serve_forever()
    finally: server.server_close(); model.shutdown(); model.server_close()
