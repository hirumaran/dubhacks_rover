"""Supabase persistence: storage crop upload + sightings insert + offline outbox.

Failures never crash the service - every event gets appended to
state/outbox.jsonl and is retried periodically. Crop refers to a local file that
the outbox keeps until the upload succeeds (iterran uploads first, insert second
retry periodically. The crop upload happens before the insert, so a row never
points at a missing crop.
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import config
from config import SUPABASE_URL, STORAGE_BUCKET, OUTBOX_DIR

OUTBOX_PATH = OUTBOX_DIR / "outbox.jsonl"


class SupabaseStore:
    def __init__(self):
        self._client = None
        self.enabled = False
        self._last_flush = 0.0
        self._init_client()

    def _init_client(self):
        if not config.supabase_ready():
            print("[supabase] URL/keys missing in perception/.env -> DRY-RUN mode (local JSONL only)", flush=True)
            return
        try:
            from supabase import create_client
            key = config.SUPABASE_SERVICE_KEY or config.SUPABASE_ANON_KEY
            self._client = create_client(SUPABASE_URL, key)
            # Fail fast with a tiny select so misconfigured env surfaces immediately
            self._client.table("sightings").select("id").limit(1).execute()
            self.enabled = True
            print("[supabase] connected", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[supabase] connect failed ({e}) -> DRY-RUN mode", flush=True)
            self._client = None
            self.enabled = False

    # ---------------- push path ----------------
    def push_event(self, row: dict, crop_png_path: Path | None) -> bool:
        """True when the row reached (or was already) in Supabase."""
        if not self.enabled:
            return False
        crop_path_rel = None
        try:
            if crop_png_path is not None and crop_png_path.exists():
                crop_path_rel = self._upload_crop(row["object_id"], crop_png_path)
                if crop_path_rel:
                    row["image_url"] = self.public_url(crop_path_rel)
            self._client.table("sightings").insert(row).execute()
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[supabase] push failed -> queued ({e})", flush=True)
            self._queue(row, crop_path_rel, crop_png_path)
            return False

    def _upload_crop(self, object_id: str, path: Path) -> str | None:
        storage_path = f"{datetime.now(timezone.utc).strftime('%Y%m%d')}/{object_id}/{path.name}"
        try:
            self._client.storage.from_(STORAGE_BUCKET).upload(
                storage_path, path.read_bytes(),
                file_options={"content-type": "image/png", "upsert": "true"},
            )
            return storage_path
        except Exception as e:  # noqa: BLE001
            print(f"[supabase] crop upload failed -> queued ({e})", flush=True)
            return None

    def public_url(self, storage_path: str | None) -> str | None:
        if not storage_path:
            return None
        return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{storage_path}"

    # ---------------- outbox ----------------
    def _queue(self, row: dict, storage_path: str | None, crop_path: Path | None):
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "row": row,
            "storage_path": storage_path,
            "crop": str(crop_path) if crop_path else None,
            "queued_utc": datetime.now(timezone.utc).isoformat(),
        }
        with OUTBOX_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def flush_due(self, min_interval_s: float = 30.0) -> int:
        now = time.time()
        if not self.enabled or now - self._last_flush < min_interval_s or not OUTBOX_PATH.exists():
            return 0
        self._last_flush = now
        remaining, sent = [], 0
        for line in OUTBOX_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                storage_path = e.get("storage_path")
                crop = Path(e["crop"]) if e.get("crop") else None
                if storage_path is None and crop and crop.exists():
                    storage_path = self._upload_crop(e["row"]["object_id"], crop)
                    if storage_path:
                        e["row"]["image_url"] = self.public_url(storage_path)
                self._client.table("sightings").insert(e["row"]).execute()
                sent += 1
            except Exception:  # noqa: BLE001 - keep line for next retry
                remaining.append(line)
        OUTBOX_PATH.write_text("\n".join(remaining) + ("\n" if remaining else ""))
        if sent:
            print(f"[supabase] flushed {sent} queued sighting(s)", flush=True)
        return sent
