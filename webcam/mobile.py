"""Paired, read-only rover feed and phone camera access to the dry-run identifier."""
import base64
import io
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from PIL import Image


def configure(server, enabled=False, rover_dirs=None):
    server.mobile_enabled = enabled
    server.mobile_token = secrets.token_urlsafe(32)
    server.preview = None
    server.preview_sequence = 0
    server.webcam_analysis = None
    repo = Path(__file__).resolve().parent.parent
    configured = os.environ.get('PERCEPTION_PUBLIC_DIR')
    server.rover_dirs = [Path(configured)] if configured else [
        repo / 'simulation-indoors/presentation/data',
        repo / 'simulation/indoor_showcase/presentation/data',
    ]
    if rover_dirs is not None:
        server.rover_dirs = list(rover_dirs)


def authorized(handler):
    return handler.server.mobile_enabled and secrets.compare_digest(
        handler.headers.get('Authorization', ''), 'Bearer ' + handler.server.mobile_token)


def feed(server, source):
    if source == 'webcam':
        frame = server.preview
        if not frame:
            return {'source': source, 'online': False, 'image': None, 'detections': [], 'analysis':None}
        return {**frame, 'source': source, 'online': time.time() - frame['updated_at'] < 10,
                'analysis': server.webcam_analysis}
    candidates = [root / 'perception.json' for root in server.rover_dirs
                  if (root / 'perception.json').is_file()]
    if not candidates:
        return {'source': 'rover', 'online': False, 'image': None, 'detections': []}
    state_file = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        state = json.loads(state_file.read_text())
        root = state_file.parent.resolve()
        image_path = (root / (state.get('image') or '__none__')).resolve()
        if not image_path.is_relative_to(root) or not image_path.is_file():
            raise ValueError('No published image')
        # Only a bounded, re-encoded model frame leaves the gateway, never a file path/pose.
        with Image.open(image_path) as photo:
            photo.thumbnail((1280, 960))
            out = io.BytesIO()
            photo.convert('RGB').save(out, format='JPEG', quality=75)
            width, height = photo.size
        updated = state_file.stat().st_mtime
        detections = []
        for item in state.get('detections', []):
            box = item.get('bbox')
            if not isinstance(box, list) or len(box) != 4:
                continue
            detections.append({'title': item.get('description') or 'Visible item',
                               'category': item.get('category'), 'bbox': box})
        return {'source': 'rover', 'online': time.time() - updated < 30,
                'updated_at': updated, 'image': 'data:image/jpeg;base64,' + base64.b64encode(out.getvalue()).decode(),
                'width': width, 'height': height, 'detections': detections,
                'model': 'Perceptron Mk1.5', 'camera': state.get('camera'),
                'simulation_time_s': state.get('simulation_time_s'),
                'confirmed_count': len(state.get('confirmed_items', []))}
    except (OSError, ValueError, TypeError, Image.DecompressionBombError):
        return {'source': 'rover', 'online': False, 'image': None, 'detections': []}


def get(handler):
    if not authorized(handler):
        handler.reply(403, {'error': 'Pair with the current gateway code first.'})
        return
    path = urlsplit(handler.path)
    if path.path == '/api/mobile/status':
        handler.reply(200, {'model': 'Perceptron Mk1.5', 'dry_run': True, 'interval_s': 5})
    elif path.path == '/api/mobile/feed':
        source = parse_qs(path.query).get('source', ['rover'])[0]
        if source not in ('rover', 'webcam'):
            handler.reply(400, {'error': 'Choose rover or webcam.'})
            return
        result = feed(handler.server, source)
        try:
            since = float(parse_qs(path.query).get('analysis_since', ['0'])[0])
        except ValueError:
            handler.reply(400, {'error':'Invalid analysis timestamp.'}); return
        analysis = result.get('analysis')
        if analysis and analysis.get('updated_at', 0) <= since:
            result.pop('analysis', None)
        handler.reply(200, result)
    else:
        handler.reply(404, {'error': 'Not found'})
