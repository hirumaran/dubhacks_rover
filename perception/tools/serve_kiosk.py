#!/usr/bin/env python3
"""Mobile kiosk for the desk QR: describe / photograph a lost item.

  python tools/serve_kiosk.py
  # then generate QRs that point here:
  python tools/make_qr.py --url http://THIS_MACHINE:8787

POST /api/report  multipart: query_text, photo?, created_by?, station_id
  -> uploads photo to lost-item-queries bucket (if Supabase live)
  -> dispatch.ingest_report (closest rover + optional immediate match)

GET  /              kiosk form
GET  /api/status?id=  one report's status (student polls until matched)
GET  /health        json
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from config import KIOSK_DIR, KIOSK_PORT, LOST_ITEMS_BUCKET, REPORTS_DIR
from dispatch import Dispatch, load_stations


def _inject_stations(html: str) -> str:
    mapping = {sid: {"name": s["name"]} for sid, s in load_stations().items()}
    blob = json.dumps(mapping)
    return html.replace(
        "const stations = window.KIOSK_STATIONS || {};",
        f"const stations = {blob};",
    )


def _multipart(headers, body: bytes) -> dict:
    """Minimal multipart parser (stdlib only). Values are str; files are (name, bytes, ctype)."""
    ctype = headers.get("Content-Type", "")
    if "multipart/form-data" not in ctype:
        qs = parse_qs(body.decode("utf-8", "replace"))
        return {k: v[0] if v else "" for k, v in qs.items()}
    bound = None
    for part in ctype.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            bound = part.split("=", 1)[1].strip().strip('"')
    if not bound:
        return {}
    token = b"--" + bound.encode()
    fields: dict = {}
    for chunk in body.split(token):
        if not chunk or chunk in (b"--\r\n", b"--"):
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        head, _, data = chunk.partition(b"\r\n\r\n")
        if data.endswith(b"\r\n"):
            data = data[:-2]
        disp = ""
        file_ctype = "application/octet-stream"
        for line in head.decode("utf-8", "replace").split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                disp = line
            if line.lower().startswith("content-type:"):
                file_ctype = line.split(":", 1)[1].strip()
        name = filename = None
        for bit in disp.split(";"):
            bit = bit.strip()
            if bit.startswith("name="):
                name = bit.split("=", 1)[1].strip().strip('"')
            if bit.startswith("filename="):
                filename = bit.split("=", 1)[1].strip().strip('"')
        if not name:
            continue
        if filename:
            fields[name] = (filename, data, file_ctype)
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields


class Handler(BaseHTTPRequestHandler):
    dispatch = Dispatch()

    def log_message(self, fmt, *args):
        print(f"[kiosk] {self.address_string()} {fmt % args}", flush=True)

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = _inject_stations((KIOSK_DIR / "index.html").read_text())
            self._send(200, html.encode(), "text/html; charset=utf-8")
            return
        if path == "/kiosk.css":
            self._send(200, (KIOSK_DIR / "kiosk.css").read_bytes(), "text/css")
            return
        if path == "/health":
            self._json(200, {
                "ok": True,
                "rover_id": config.ROVER_ID,
                "supabase": config.supabase_ready(),
                "public_app_url": config.PUBLIC_APP_URL,
            })
            return
        if path == "/api/status":
            qs = parse_qs(urlparse(self.path).query)
            item_id = (qs.get("id") or [""])[0].strip()
            if not item_id:
                self._json(400, {"error": "id required"})
                return
            item = self.dispatch.get_report(item_id)
            if not item:
                self._json(404, {"error": "unknown report"})
                return
            self._json(200, {
                "id": item.get("id"),
                "status": item.get("status"),
                "assigned_rover_id": item.get("assigned_rover_id"),
                "station_id": item.get("station_id"),
                "match_reason": item.get("match_reason"),
                "matched_object_id": item.get("matched_object_id"),
                "distance_m": item.get("distance_m"),
                "updated_at": item.get("updated_at") or item.get("assigned_at"),
            })
            return
        if path.startswith("/qr/"):
            dest = KIOSK_DIR / "qr" / Path(path).name
            if dest.exists() and dest.suffix == ".png":
                self._send(200, dest.read_bytes(), "image/png")
                return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/report":
            self._json(404, {"error": "not found"})
            return
        n = int(self.headers.get("Content-Length") or 0)
        fields = _multipart(self.headers, self.rfile.read(n))
        query = (fields.get("query_text") or "").strip() if isinstance(fields.get("query_text"), str) else ""
        created = fields.get("created_by") if isinstance(fields.get("created_by"), str) else None
        station_id = fields.get("station_id") if isinstance(fields.get("station_id"), str) else None
        photo = fields.get("photo")
        image_url = None
        if isinstance(photo, tuple) and photo[1]:
            image_url = self._store_photo(photo)
        try:
            item = self.dispatch.ingest_report({
                "query_text": query,
                "created_by": created or None,
                "station_id": station_id,
                "query_image_url": image_url,
            })
        except ValueError as e:
            self._json(400, {"error": str(e)})
            return
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": str(e)})
            return
        self._json(200, {
            "id": item.get("id"),
            "status": item.get("status"),
            "assigned_rover_id": item.get("assigned_rover_id"),
            "dispatch_reason": item.get("dispatch_reason"),
            "match_reason": item.get("match_reason"),
            "station_id": item.get("station_id"),
            "distance_m": item.get("distance_m"),
        })

    def _store_photo(self, photo: tuple) -> str | None:
        filename, data, ctype = photo
        if not data:
            return None
        ext = Path(filename or "photo.jpg").suffix or ".jpg"
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        local = REPORTS_DIR / f"query_{uuid4().hex}{ext}"
        local.write_bytes(data)
        if not config.supabase_ready():
            return str(local)
        try:
            from supabase import create_client
            key = config.SUPABASE_SERVICE_KEY or config.SUPABASE_ANON_KEY
            sb = create_client(config.SUPABASE_URL, key)
            storage_path = f"{datetime.now(timezone.utc).strftime('%Y%m%d')}/{uuid4().hex}{ext}"
            sb.storage.from_(LOST_ITEMS_BUCKET).upload(
                storage_path, data,
                file_options={"content-type": ctype or "image/jpeg", "upsert": "true"},
            )
            return f"{config.SUPABASE_URL}/storage/v1/object/public/{LOST_ITEMS_BUCKET}/{storage_path}"
        except Exception as e:  # noqa: BLE001
            print(f"[kiosk] photo upload failed, keeping local ({e})", flush=True)
            return str(local)


def main():
    addr = ("0.0.0.0", KIOSK_PORT)
    httpd = ThreadingHTTPServer(addr, Handler)
    print(f"[kiosk] http://127.0.0.1:{KIOSK_PORT}/  (QR target = {config.PUBLIC_APP_URL})", flush=True)
    print("[kiosk] phones on the same Wi-Fi should use this machine's LAN IP, then remake QRs with --url", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
