#!/usr/bin/env python3
"""Read-only local gallery server. Exposes only the gallery directory, never logs/maps."""
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'gallery'
print('Campus Scout gallery: http://127.0.0.1:8767 — Ctrl+C to stop',flush=True)
ThreadingHTTPServer(('127.0.0.1',8767),partial(SimpleHTTPRequestHandler,directory=str(root))).serve_forever()
