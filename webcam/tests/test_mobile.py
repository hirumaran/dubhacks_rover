import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
from test_gateway import Identifier, frame
from server import WebcamServer
from http.server import ThreadingHTTPServer


class MobileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.model = ThreadingHTTPServer(('127.0.0.1', 0), Identifier)
        self.server = WebcamServer(('127.0.0.1', 0), f'http://127.0.0.1:{self.model.server_port}', 'private-secret', True, [self.root])
        for server in (self.model, self.server):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        for server in (self.model, self.server):
            server.shutdown(); server.server_close()
        self.temp.cleanup()

    def call(self, path, body=None, token=True):
        headers = {'Content-Type': 'application/json'}
        if token: headers['Authorization'] = 'Bearer ' + self.server.mobile_token
        request = urllib.request.Request(self.url + path, headers=headers, data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(request) as response: return json.load(response)

    def test_mobile_auth_and_dry_run(self):
        for path in ['/api/mobile/status', '/api/mobile/feed', '/api/mobile/analyze']:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call(path, {'image':frame()} if path.endswith('analyze') else None, False)
            self.assertEqual(error.exception.code, 403)
        result = self.call('/api/mobile/analyze', {'image':frame(), 'dry_run':False})
        self.assertEqual(result['detections'][0]['title'], 'Black backpack')
        self.assertTrue(Identifier.payloads[-1]['dry_run'])
        self.assertNotIn('private-secret', json.dumps(result))
        config = json.load(urllib.request.urlopen(self.url + '/api/config'))
        self.assertNotIn(self.server.mobile_token, json.dumps(config))

    def test_feeds_use_only_published_pixels_and_expire(self):
        self.assertFalse(self.call('/api/mobile/feed')['online'])
        self.server.preview = {'image':frame(), 'width':640, 'height':480, 'updated_at':0, 'detections':[]}
        self.assertFalse(self.call('/api/mobile/feed?source=webcam')['online'])
        from PIL import Image
        Image.new('RGB', (640,480)).save(self.root/'frame.jpg')
        state = {'image':'frame.jpg','camera':1,'detections':[{'description':'Bottle','bbox':[.1,.1,.2,.2]}], 'secret':'never exported'}
        (self.root/'perception.json').write_text(json.dumps(state))
        feed = self.call('/api/mobile/feed')
        self.assertTrue(feed['online'])
        self.assertEqual(feed['detections'][0]['title'], 'Bottle')
        self.assertTrue(feed['image'].startswith('data:image/jpeg;base64,'))
        self.assertNotIn('never exported', json.dumps(feed))
        state['image'] = '../outside.jpg'
        (self.root/'perception.json').write_text(json.dumps(state))
        self.assertIsNone(self.call('/api/mobile/feed')['image'])

    def test_mobile_mode_is_opt_in(self):
        self.server.mobile_enabled = False
        with self.assertRaises(urllib.error.HTTPError) as error: self.call('/api/mobile/status')
        self.assertEqual(error.exception.code, 403)

    def test_completed_laptop_analysis_is_shared_with_paired_app(self):
        def desktop(path, body):
            request = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), headers={
                'Content-Type':'application/json', 'X-Webcam-Token':self.server.token})
            with urllib.request.urlopen(request) as response: return json.load(response)
        image = frame()
        desktop('/api/preview', {'image':image})
        desktop('/api/analyze', {'image':image})
        result = self.call('/api/mobile/feed?source=webcam')
        self.assertEqual(result['analysis']['image'], image)
        self.assertEqual(result['analysis']['detections'][0]['title'], 'Black backpack')
        cached = self.call('/api/mobile/feed?source=webcam&analysis_since=' + str(result['analysis']['updated_at']))
        self.assertNotIn('analysis', cached)
        self.assertEqual(cached['image'], image)
        first_id = result['frame_id']
        desktop('/api/preview', {'image':frame(320,240)})
        refreshed = self.call('/api/mobile/feed?source=webcam')
        self.assertGreater(refreshed['frame_id'], first_id)
        self.assertNotEqual(refreshed['image'], result['image'])
        desktop('/api/preview', {'image':None})
        self.assertFalse(self.call('/api/mobile/feed?source=webcam')['online'])
        self.assertIsNone(self.server.webcam_analysis)

if __name__ == '__main__': unittest.main()
