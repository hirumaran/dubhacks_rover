"""Cloud -> rover mission bus.

Student reports land in Supabase `lost_items` (or reports/lost_reports.jsonl in
dry-run). This module:

  1. assigns each open report to the closest live rover (rover_geo.closest_rover)
  2. writes THIS rover's missions to state/missions.json so Isaac can hunt
  3. optionally tries an immediate sightings match (match_agent) so students
     get an answer even before a rover physically re-scans

The rover never talks to the phone. Cloud is the bus. Isaac stays on the rover.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import config
from config import OUTBOX_DIR, HEARTBEAT_STALE_S, ROVER_ID, ROVER_DISPLAY_NAME, REPORTS_DIR
from geotag import RoverPose
from rover_geo import closest_rover, live_rovers, pose_to_geo

MISSIONS_PATH = OUTBOX_DIR / "missions.json"
POSE_PATH = OUTBOX_DIR / "rover_pose.json"
LOCAL_REPORTS = REPORTS_DIR / "lost_reports.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts) -> datetime | None:
    if not ts:
        return None
    try:
        t = ts.replace("Z", "+00:00") if isinstance(ts, str) else ts
        dt = datetime.fromisoformat(str(t))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _newer_than(ts, ref) -> bool:
    a, b = _parse_ts(ts), _parse_ts(ref)
    return bool(a and b and a > b)


def _sb():
    if not config.supabase_ready():
        return None
    from supabase import create_client
    key = config.SUPABASE_SERVICE_KEY or config.SUPABASE_ANON_KEY
    return create_client(config.SUPABASE_URL, key)


def load_stations() -> dict[str, dict]:
    raw = json.loads((config.KIOSK_DIR / "stations.json").read_text())
    return {s["id"]: s for s in raw["stations"]}


def station_url(base: str, station_id: str) -> str:
    return f"{base.rstrip('/')}/?station={station_id}"


class Dispatch:
    def __init__(self, rover_id: str | None = None):
        self.rover_id = rover_id or ROVER_ID
        self.display_name = ROVER_DISPLAY_NAME
        self._client = None
        self._cloud = False
        self._init()

    def _init(self):
        try:
            self._client = _sb()
            self._cloud = self._client is not None
        except Exception as e:  # noqa: BLE001
            print(f"[dispatch] supabase unavailable ({e}) -> local missions only", flush=True)
            self._client = None
            self._cloud = False

    # ---------- heartbeat ----------
    def heartbeat(self, pose: RoverPose, status: str = "patrol") -> dict:
        geo = pose_to_geo(pose)
        row = {
            "id": self.rover_id,
            "display_name": self.display_name,
            "lat": geo["lat"],
            "lon": geo["lon"],
            "x": geo["x"],
            "y": geo["y"],
            "heading_rad": geo["heading_rad"],
            "status": status,
            "sim_time_s": geo["sim_time_s"],
            "last_seen_at": _now(),
            "meta": {"origin": geo["origin"]},
        }
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        tmp = POSE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(row, indent=2))
        tmp.replace(POSE_PATH)
        if self._cloud:
            try:
                self._client.table("rovers").upsert(row).execute()
            except Exception as e:  # noqa: BLE001
                print(f"[dispatch] heartbeat upsert failed ({e})", flush=True)
        return row

    def list_rovers(self) -> list[dict]:
        if self._cloud:
            try:
                data = self._client.table("rovers").select("*").execute().data or []
                if data:
                    return data
            except Exception as e:  # noqa: BLE001
                print(f"[dispatch] list rovers failed ({e})", flush=True)
        if POSE_PATH.exists():
            try:
                return [json.loads(POSE_PATH.read_text())]
            except json.JSONDecodeError:
                return []
        return []

    # ---------- reports ----------
    def ingest_report(self, payload: dict) -> dict:
        """Insert a student report, then assign the closest rover.

        payload keys: query_text, created_by?, station_id?, station_lat?,
        station_lon?, station_name?, query_image_url?
        """
        stations = load_stations()
        station = stations.get(payload.get("station_id") or "", {})
        lat = payload.get("station_lat", station.get("lat"))
        lon = payload.get("station_lon", station.get("lon"))
        name = payload.get("station_name", station.get("name"))
        row = {
            "created_by": payload.get("created_by"),
            "query_text": (payload.get("query_text") or "").strip(),
            "query_image_url": payload.get("query_image_url"),
            "status": "open",
            "station_id": payload.get("station_id") or station.get("id"),
            "station_name": name,
            "station_lat": lat,
            "station_lon": lon,
        }
        if not row["query_text"] and not row["query_image_url"]:
            raise ValueError("Need a description or a photo.")

        stored = self._insert_lost_item(row)
        assigned = self.assign_open(stored)
        self._try_immediate_match(assigned)
        self.refresh_local_missions()
        return assigned

    def _insert_lost_item(self, row: dict) -> dict:
        if self._cloud:
            res = self._client.table("lost_items").insert(row).execute()
            data = res.data or []
            if data:
                return data[0]
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        local = {
            **row,
            "id": row.get("id") or f"local-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            "created_at": _now(),
        }
        with LOCAL_REPORTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(local) + "\n")
        return local

    def _update_lost_item(self, item_id: str, fields: dict) -> dict:
        if self._cloud:
            try:
                res = (
                    self._client.table("lost_items")
                    .update(fields)
                    .eq("id", item_id)
                    .execute()
                )
                data = res.data or []
                if data:
                    return data[0]
            except Exception as e:  # noqa: BLE001
                print(f"[dispatch] update lost_items failed ({e})", flush=True)
        local = self._update_local_item(item_id, fields)
        return local if local is not None else {"id": item_id, **fields}

    def _update_local_item(self, item_id: str, fields: dict) -> dict | None:
        """Rewrite reports/lost_reports.jsonl in place (dry-run keeps assignment
        state too, so missions_for_me / status polling behave like cloud mode)."""
        if not LOCAL_REPORTS.exists():
            return None
        rows: dict[str, dict] = {}
        found: dict | None = None
        for line in LOCAL_REPORTS.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            oid = row.get("id")
            if oid == item_id:
                row = {**row, **fields, "updated_at": _now()}
                found = row
            rows[oid] = row
        if found is None:
            return None
        tmp = LOCAL_REPORTS.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows.values()))
        tmp.replace(LOCAL_REPORTS)
        return found

    def get_report(self, item_id: str) -> dict | None:
        """One report by id (kiosk /api/status). Cloud first, local fallback."""
        if self._cloud:
            try:
                data = (
                    self._client.table("lost_items")
                    .select("*").eq("id", item_id).limit(1)
                    .execute().data or []
                )
                if data:
                    return data[0]
            except Exception as e:  # noqa: BLE001
                print(f"[dispatch] get lost_item failed ({e})", flush=True)
        if LOCAL_REPORTS.exists():
            for line in reversed(LOCAL_REPORTS.read_text().splitlines()):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("id") == item_id:
                    return row
        return None

    def assign_open(self, item: dict) -> dict:
        lat, lon = item.get("station_lat"), item.get("station_lon")
        rovers = self.list_rovers()
        pick = None
        if lat is not None and lon is not None and rovers:
            pick = closest_rover(float(lat), float(lon), rovers, stale_s=HEARTBEAT_STALE_S)
        if pick is None and rovers:
            pick = {**rovers[0], "distance_m": None}
        if pick is None:
            # No fleet yet: park the job on this process so a solo demo still hunts.
            pick = {"id": self.rover_id, "distance_m": None}

        reason = (
            f"closest live rover {pick.get('id')} "
            + (f"({pick['distance_m']:.0f} m from kiosk)" if pick.get("distance_m") is not None else "(solo/fallback)")
        )
        fields = {
            "assigned_rover_id": pick.get("id"),
            "assigned_at": _now(),
            "dispatch_reason": reason,
            "status": "assigned" if item.get("status") in (None, "open") else item.get("status"),
        }
        updated = self._update_lost_item(item["id"], fields)
        merged = {**item, **updated, **fields, "distance_m": pick.get("distance_m")}
        print(f"[dispatch] {merged['id']} -> {fields['assigned_rover_id']} | {reason}", flush=True)
        return merged

    def reclaim_unassigned(self) -> int:
        """Re-assign reports that never got a rover, or whose rover heartbeat
        went stale (crashed / powered off). Keeps the fleet self-healing."""
        live_ids = {r.get("id") for r in live_rovers(self.list_rovers(), HEARTBEAT_STALE_S)}
        n = 0
        for item in self._open_items():
            assigned = item.get("assigned_rover_id")
            if assigned and assigned in live_ids:
                continue
            result = self.assign_open(item)
            if assigned and result.get("assigned_rover_id") != assigned:
                print(f"[dispatch] {item.get('id')} reclaimed from stale rover {assigned}", flush=True)
            n += 1
        if n:
            self.refresh_local_missions()
        return n

    def _open_items(self) -> list[dict]:
        if self._cloud:
            try:
                return (
                    self._client.table("lost_items")
                    .select("*")
                    .in_("status", ["open", "assigned", "hunting"])
                    .order("created_at", desc=True)
                    .limit(50)
                    .execute()
                    .data
                    or []
                )
            except Exception as e:  # noqa: BLE001
                print(f"[dispatch] list lost_items failed ({e})", flush=True)
        items = []
        if LOCAL_REPORTS.exists():
            for line in LOCAL_REPORTS.read_text().splitlines():
                if line.strip():
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return items

    def missions_for_me(self) -> list[dict]:
        mine = [
            it for it in self._open_items()
            if (it.get("assigned_rover_id") or self.rover_id) == self.rover_id
            and it.get("status") != "resolved"
        ]
        return mine

    def refresh_local_missions(self) -> list[dict]:
        missions = self.missions_for_me()
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        blob = {
            "rover_id": self.rover_id,
            "updated_utc": _now(),
            "missions": missions,
        }
        tmp = MISSIONS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2, default=str))
        tmp.replace(MISSIONS_PATH)
        return missions

    def hunt_query(self) -> str | None:
        texts = []
        for m in self.missions_for_me():
            q = (m.get("query_text") or "").strip()
            if q:
                texts.append(q)
        return "; ".join(texts) if texts else None

    # ---------- hunt lifecycle ----------
    def reconcile_matches(self) -> int:
        """Advance MY open missions and close them when the hunt succeeds.

        * open/assigned -> hunting once this rover owns the mission
        * hunting -> matched as soon as a sighting of a matching object is
          NEWER than the assignment (i.e. found during this hunt, not an old
          sighting already handled by the immediate match at ingest).

        Cloud-only; safe no-op in dry-run. Called on the run_service dispatch
        poll. The web branch sees status flip to 'matched' + match_reason.
        """
        if not self._cloud:
            return 0
        try:
            from match_agent import find_matches, first_sighting, answer_for_object
        except Exception as e:  # noqa: BLE001
            print(f"[dispatch] reconcile skip ({e})", flush=True)
            return 0
        updated = 0
        for item in self.missions_for_me():
            status = item.get("status")
            if status in (None, "open", "assigned"):
                self._update_lost_item(item["id"], {"status": "hunting"})
                item = {**item, "status": "hunting"}
                updated += 1
            if item.get("status") != "hunting":
                continue
            q = (item.get("query_text") or "").strip()
            if not q:
                continue
            try:
                matches = find_matches(q)
            except Exception as e:  # noqa: BLE001
                print(f"[dispatch] reconcile match failed ({e})", flush=True)
                continue
            if not matches:
                continue
            best = matches[0]
            if float(best.get("match_score") or 0) < config.MATCH_MIN_SCORE:
                continue
            ref = item.get("assigned_at") or item.get("created_at")
            if not _newer_than(best.get("created_at"), ref):
                continue
            first = first_sighting(best["object_id"])
            answer = answer_for_object(q, best, first)
            self._update_lost_item(item["id"], {
                "status": "matched",
                "matched_object_id": best["object_id"],
                "match_confidence": best.get("match_score"),
                "match_reason": answer,
            })
            print(f"[dispatch] hunt match for {item['id']}: {best['object_id']} ({best.get('label')})", flush=True)
            updated += 1
        return updated

    def _try_immediate_match(self, item: dict) -> None:
        q = (item.get("query_text") or "").strip()
        if not q or not self._cloud:
            return
        try:
            from match_agent import find_matches, first_sighting, answer_for_object
            matches = find_matches(q)
            if not matches:
                return
            best = matches[0]
            if float(best.get("match_score") or 0) < config.MATCH_MIN_SCORE:
                print(f"[dispatch] best match {best['object_id']} below threshold "
                      f"({best.get('match_score')} < {config.MATCH_MIN_SCORE})", flush=True)
                return
            first = first_sighting(best["object_id"])
            answer = answer_for_object(q, best, first)
            self._update_lost_item(item["id"], {
                "status": "matched",
                "matched_object_id": best["object_id"],
                "match_confidence": best.get("match_score"),
                "match_reason": answer,
            })
            print(f"[dispatch] immediate match for {item['id']}: {best['object_id']}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[dispatch] match skip ({e})", flush=True)
