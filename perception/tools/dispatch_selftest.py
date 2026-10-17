#!/usr/bin/env python3
"""Fleet geo + closest-rover + QR URL contract, no Webots / no GPU / no cloud."""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geotag import world_xy_to_wgs84, wgs84_to_world_xy, load_origin
from rover_geo import haversine_m, closest_rover, live_rovers
from dispatch import load_stations, station_url, _newer_than
from match_agent import _tokens, _synonyms
import config


def _assert(cond, msg):
    if not cond:
        raise SystemExit(f"[selftest] FAIL: {msg}")


def main():
    origin = load_origin()
    lat, lon = world_xy_to_wgs84(0.0, 0.0)
    _assert(abs(lat - origin[0]) < 1e-9 and abs(lon - origin[1]) < 1e-9, "origin maps to (0,0)")
    x, y = wgs84_to_world_xy(lat, lon)
    _assert(abs(x) < 1e-6 and abs(y) < 1e-6, "inverse origin")

    # 100 m east should be ~100 m haversine
    lat_e, lon_e = world_xy_to_wgs84(100.0, 0.0)
    d = haversine_m(lat, lon, lat_e, lon_e)
    _assert(90 < d < 110, f"100m east haversine got {d:.1f}")

    now = datetime.now(timezone.utc)
    fleet = [
        {"id": "mk1", "lat": 47.65328, "lon": -122.30505, "last_seen_at": now.isoformat()},
        {"id": "mk2", "lat": 47.65662, "lon": -122.31025, "last_seen_at": now.isoformat()},
        {"id": "ghost", "lat": 47.65585, "lon": -122.30895,
         "last_seen_at": (now - timedelta(seconds=120)).isoformat()},
    ]
    stations = load_stations()
    gates = stations["gates-atrium"]
    pick = closest_rover(gates["lat"], gates["lon"], fleet, stale_s=45, now=now)
    _assert(pick and pick["id"] == "mk1", f"gates should pick mk1, got {pick}")
    ode = stations["odegaard-helpdesk"]
    pick2 = closest_rover(ode["lat"], ode["lon"], fleet, stale_s=45, now=now)
    _assert(pick2 and pick2["id"] == "mk2", f"odegaard should pick mk2, got {pick2}")
    _assert({r["id"] for r in live_rovers(fleet, stale_s=45, now=now)} == {"mk1", "mk2"},
            "stale heartbeat must be treated offline (reclaim logic depends on it)")

    # hunt reconcile gate: only sightings newer than the assignment count
    t0 = (now - timedelta(minutes=10)).isoformat()
    _assert(_newer_than(now.isoformat(), t0), "fresh sighting newer than assignment")
    _assert(not _newer_than(t0, now.isoformat()), "old sighting must not close a hunt")
    _assert(not _newer_than(None, t0), "missing sighting time never matches")

    # synonym recall: the canonical demo phrase must reach a 'bottle' sighting
    q = _tokens("green hydroflask, dented lid")
    _assert("bottle" in _synonyms(q), "hydroflask synonym expansion -> bottle")

    # reconcile: assigned -> hunting -> matched when a NEW sighting matches
    import dispatch as dispatch_mod
    import match_agent

    d = dispatch_mod.Dispatch.__new__(dispatch_mod.Dispatch)
    d.rover_id = "mk1"
    d._cloud = True
    assigned_at = (now - timedelta(minutes=1)).isoformat()
    items = [{
        "id": "r1", "query_text": "green hydroflask", "status": "assigned",
        "assigned_rover_id": "mk1", "assigned_at": assigned_at,
        "created_at": (now - timedelta(minutes=2)).isoformat(),
    }]
    updates: list[tuple] = []
    d._open_items = lambda: items
    d._update_lost_item = lambda i, f: (updates.append((i, f)), {"id": i, **f})[1]
    saved = (match_agent.find_matches, match_agent.first_sighting, match_agent.answer_for_object)
    try:
        match_agent.find_matches = lambda q, top_k=5: [{
            "object_id": "OBJ-1", "label": "bottle", "match_score": 0.6,
            "created_at": now.isoformat(), "geotag": {"x": 6.1, "y": -1.3},
        }]
        match_agent.first_sighting = lambda oid: {
            "created_at": now.isoformat(), "geotag": {"x": 6.1, "y": -1.3, "area_hint": "SE quadrant"},
        }
        match_agent.answer_for_object = lambda q, c, f: "matched near x=6.1, y=-1.3"
        n = d.reconcile_matches()
    finally:
        match_agent.find_matches, match_agent.first_sighting, match_agent.answer_for_object = saved
    _assert(n == 2, f"reconcile should flip hunting + matched, got {n} ({updates})")
    _assert(updates[0][1]["status"] == "hunting", "assigned must become hunting")
    _assert(updates[1][1]["status"] == "matched" and updates[1][1]["matched_object_id"] == "OBJ-1",
            "fresh sighting must close the hunt with the object id")

    # and an OLD sighting must NOT close it
    updates.clear()
    saved = (match_agent.find_matches, match_agent.first_sighting, match_agent.answer_for_object)
    try:
        match_agent.find_matches = lambda q, top_k=5: [{
            "object_id": "OBJ-1", "label": "bottle", "match_score": 0.6,
            "created_at": (now - timedelta(hours=1)).isoformat(), "geotag": {},
        }]
        match_agent.first_sighting = lambda oid: None
        match_agent.answer_for_object = lambda q, c, f: "stale"
        d.reconcile_matches()
    finally:
        match_agent.find_matches, match_agent.first_sighting, match_agent.answer_for_object = saved
    _assert(not any(f.get("status") == "matched" for _, f in updates),
            f"old sighting must not auto-match ({updates})")

    url = station_url("https://scout.example.edu", "gates-atrium")
    _assert(url == "https://scout.example.edu/?station=gates-atrium", url)

    for sid in stations:
        _assert(sid.replace("-", "").replace("_", "").isalnum() or "-" in sid, sid)

    print("[selftest] PASS origin, haversine, closest-rover, stale gate, reconcile gate, synonyms, QR URL")
    print(json.dumps({
        "origin": origin,
        "gates_assigned": pick["id"],
        "odegaard_assigned": pick2["id"],
        "sample_qr": url,
        "default_app_url": config.PUBLIC_APP_URL,
        "match_min_score": config.MATCH_MIN_SCORE,
        "stations": list(stations),
    }, indent=2))


if __name__ == "__main__":
    main()
