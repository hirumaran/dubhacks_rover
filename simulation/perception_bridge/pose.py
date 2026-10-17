"""Rover pose -> latitude/longitude and per-camera view direction.

The simulator's GPS reports metres in the world frame (x east, y north) around the mission's
reference point. This uses the same affine conversion as the original geotag module, which is
accurate to well under a metre at campus scale.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from config import CAMERA_MOUNT_YAW, MISSION_PATH

_FALLBACK_ORIGIN = (47.65865, -122.3074)


def _origin() -> tuple[float, float]:
    try:
        lat, lon = json.loads(MISSION_PATH.read_text())["reference_lat_lon"]
        return float(lat), float(lon)
    except (OSError, KeyError, ValueError, TypeError):
        return _FALLBACK_ORIGIN


LAT0, LON0 = _origin()
DEG_PER_M_LAT = 1.0 / 110574.0
DEG_PER_M_LON = 1.0 / (111320.0 * math.cos(math.radians(LAT0)))


@dataclass
class Pose:
    x: float
    y: float
    heading_rad: float  # world yaw, CCW from +x (east)
    sim_time_s: float

    @classmethod
    def from_meta(cls, meta: dict) -> "Pose":
        gps = meta["gps"]
        return cls(x=float(gps[0]), y=float(gps[1]), heading_rad=float(meta["heading_rad"]),
                   sim_time_s=float(meta.get("sim_time_s", 0.0)))

    def lat_lon(self) -> tuple[float, float]:
        return LAT0 + self.y * DEG_PER_M_LAT, LON0 + self.x * DEG_PER_M_LON

    def camera_yaw(self, camera_idx: int) -> float:
        return (self.heading_rad + CAMERA_MOUNT_YAW[camera_idx % len(CAMERA_MOUNT_YAW)]) % (2 * math.pi)


def angle_diff_deg(a_rad: float, b_rad: float) -> float:
    d = (a_rad - b_rad + math.pi) % (2 * math.pi) - math.pi
    return abs(math.degrees(d))
