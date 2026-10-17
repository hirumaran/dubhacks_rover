"""Sends camera images to the identify-found-items edge function.

Network failures and server errors never stop the bridge: the request is written to
state/outbox/ and retried every RETRY_EVERY_S. Requests the server rejects as invalid (4xx) are
logged and dropped, since resending them can't succeed. Requests go out one at a time so the
server's duplicate check sees each new listing before the next image arrives.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import INGEST_SECRET, REQUEST_TIMEOUT_S, RETRY_EVERY_S, STATE_DIR, IDENTIFY_URL

OUTBOX = STATE_DIR / "outbox"


class Uploader:
    def __init__(self):
        OUTBOX.mkdir(parents=True, exist_ok=True)
        self._last_retry = 0.0

    def _post(self, payload: dict) -> tuple[int, dict]:
        req = urllib.request.Request(
            IDENTIFY_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "x-ingest-secret": INGEST_SECRET},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read() or b"{}")
            except ValueError:
                body = {}
            return e.code, body

    def send(self, payload: dict, key: str) -> dict:
        """Returns {"status": "ok"|"queued"|"rejected", ...}."""
        try:
            code, body = self._post(payload)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            self._queue(payload, key)
            return {"status": "queued", "error": str(e)}
        if code >= 500 or code == 429:
            self._queue(payload, key)
            return {"status": "queued", "error": f"HTTP {code}: {body.get('error', '')}"}
        if code >= 400:
            return {"status": "rejected", "error": f"HTTP {code}: {body.get('error', '')}"}
        return {"status": "ok", **body}

    def _queue(self, payload: dict, key: str) -> None:
        tmp = OUTBOX / f".{key}.tmp"
        tmp.write_text(json.dumps(payload))
        tmp.replace(OUTBOX / f"{key}.json")

    def retry_due(self, force: bool = False) -> list[tuple[str, dict]]:
        """Resends queued requests, oldest first. Stops at the first one that fails again."""
        if not force and time.monotonic() - self._last_retry < RETRY_EVERY_S:
            return []
        self._last_retry = time.monotonic()
        results = []
        for path in sorted(OUTBOX.glob("*.json")):
            payload = json.loads(path.read_text())
            path.unlink()
            result = self.send(payload, path.stem)
            results.append((path.stem, result))
            if result["status"] == "queued":
                break
        return results

    def pending(self) -> int:
        return len(list(OUTBOX.glob("*.json")))
