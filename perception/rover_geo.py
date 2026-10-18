"""Rover geolocation + closest-rover selection.

Object geotags live in geotag.py (pixel -> world). This module is the *rover*
side of the same map: Webots GPS meters <-> WGS84, haversine distance, and
picking which rover in a fleet should take a student report.

Scale-up contract:
  every live rover heartbeats {rover_id, lat, lon, x, y, heading, status}
  a new lost_items row carries the kiosk station lat/lon (from the QR)
  assign to the nearest rover whose heartbeat is fresher than HEARTBEAT_STALE_S
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Iterable

from geotag import RoverPose, world_xy_to_wgs84, wgs84_to_world_xy, load_origin


EARTH_R_M = 6371000.0


def pose_to_geo(pose: RoverPose) -> dict:
    lat, lon = world_xy_to_wgs84(pose.x, pose.y)
    return {
        "x": round(pose.x, 3),
        "y": round(pose.y, 3),
        "z": round(pose.z, 3),
        "lat": lat,
        "lon": lon,
        "heading_rad": round(pose.heading_rad, 4),
        "sim_time_s": round(pose.sim_time_s, 2),
        "origin": load_origin(),
    }


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_R_M * math.asin(min(1.0, math.sqrt(a)))


def _age_s(ts, now: datetime | None = None) -> float:
    if not ts:
        return 1e9
    now = now or datetime.now(timezone.utc)
    try:
        t = ts.replace("Z", "+00:00") if isinstance(ts, str) else ts
        dt = datetime.fromisoformat(str(t))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt).total_seconds())
    except (TypeError, ValueError):
        return 1e9


def live_rovers(rovers: Iterable[dict], stale_s: float, now: datetime | None = None) -> list[dict]:
    """Rovers that heartbeated recently. Missing timestamps are treated as live
    (local dry-run poses have no cloud clock)."""
    out = []
    for r in rovers:
        ts = r.get("last_seen_at")
        if ts is None or _age_s(ts, now) <= stale_s:
            out.append(r)
    return out


def closest_rover(
    target_lat: float,
    target_lon: float,
    rovers: Iterable[dict],
    stale_s: float = 45.0,
    now: datetime | None = None,
) -> dict | None:
    """Nearest live rover to a kiosk / report location. Returns the rover dict
    plus `distance_m`, or None if the fleet is empty / all stale."""
    best = None
    best_d = None
    for r in live_rovers(rovers, stale_s, now):
        lat, lon = r.get("lat"), r.get("lon")
        if lat is None or lon is None:
            x, y = r.get("x"), r.get("y")
            if x is None or y is None:
                continue
            lat, lon = world_xy_to_wgs84(float(x), float(y))
        d = haversine_m(target_lat, target_lon, float(lat), float(lon))
        if best_d is None or d < best_d:
            best_d = d
            best = {**r, "distance_m": round(d, 1)}
    return best


def station_world(station: dict) -> tuple[float, float]:
    if "x" in station and "y" in station:
        return float(station["x"]), float(station["y"])
    return wgs84_to_world_xy(float(station["lat"]), float(station["lon"]))
