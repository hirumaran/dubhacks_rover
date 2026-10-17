"""Geotag: pixel + rover pose -> world/map coordinates.

Webots camera-frame conventions (verified against the Webots reference manual,
  https://cyberbotics.com/doc/reference/camera):
  * Camera local frame: X = depth (view axis), Y = horizontal, Z = up.
  * Pixel column u: s=0 <-> theta=+hFov/2, s=(width-1)/2 <-> theta=0, s=width-1 <-> -hFov/2.
    => +Y = image LEFT, and the bearing angle from the view axis is
       theta(u) = hFov/2 * (1 - 2u/(w-1))     (positive = image left)
  * Pixel row v: v=0 <-> phi=+vFov/2 (top of image, +Z up)
    => phi(v) = vFov/2 * (1 - 2v/(h-1))     (negative = below horizon)

Rover heading: the controller computes heading = atan2(north_x, north_y) from
the compass, which resolves to the world yaw measured CCW from +x (east).
(This is the same heading the steering math relies on, so it is self-consistent.)

Camera mounts (CampusScout.proto): camera_i is rotated `0 0 1 i*pi/2` inside the
rover body, and the camera view axis is its local +X, so the world view yaw of
camera_i = heading + i*pi/2.

World bearing of an object at pixel column u (camera i):
    bearing = heading + i*pi/2 + theta(u)

Range:
  * Precise mode: the controller-side Recognition node reports `position` in the
    camera frame [X,Y,Z]; X is the depth axis -> horizontal range ~= X.
  * VLM-only mode: assume the object stands on the ground; the bbox bottom row v1
    gives phi(v1) < 0, and ground range = (z_cam) / tan(-phi(v1)), clamped.

World position:
    x = rover_x + range * cos(bearing)
    y = rover_y + range * sin(bearing)
WSG84 output is an affine offset from the mission origin at 47.66 N (~mm/10m
level accuracy at this scale; good enough for "last seen near ...").
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass

from config import CameraSpec, MAX_RANGE_M, REPO_ROOT

MISSION_PATH = REPO_ROOT / "simulation" / "maps" / "mission.json"

_LAT0 = 47.65865
_DEG_PER_M_LAT = 1.0 / 110574.0
_DEG_PER_M_LON = 1.0 / (111320.0 * math.cos(math.radians(_LAT0)))


@dataclass
class RoverPose:
    x: float
    y: float
    z: float
    heading_rad: float
    sim_time_s: float


def _load_origin():
    try:
        m = json.loads(MISSION_PATH.read_text())
        return m["reference_lat_lon"]
    except (OSError, KeyError, ValueError):
        return [_LAT0, -122.3074]


def theta_from_u(u_norm: float, cam: CameraSpec) -> float:
    """Horizontal bearing offset from the camera view axis (positive = image left)."""
    w = cam.width
    return cam.hfov * 0.5 * (1.0 - 2.0 * (u_norm * (w - 1)) / (w - 1))


def phi_from_v(v_norm: float, cam: CameraSpec) -> float:
    vfov = 2.0 * math.atan(math.tan(cam.hfov / 2.0) * cam.height / cam.width)
    h = cam.height
    return vfov * 0.5 * (1.0 - 2.0 * (v_norm * (h - 1)) / (h - 1))


def ground_range_from_bbox_bottom(cy2_norm: float, z_cam: float, cam: CameraSpec, clamp_m: float = MAX_RANGE_M) -> float:
    """VLM-only range: object is assumed to sit on the ground (z_ground ~ 0.07 m)."""
    phi = phi_from_v(cy2_norm, cam)
    if phi > -0.05:  # bbox bottom at/above horizon -> unusable, fall back to max
        return clamp_m
    z_ground = 0.07
    r = (z_cam - z_ground) / math.tan(-phi)
    return min(max(r, 1.2), clamp_m)


def locate(
    bbox_norm: list[float],
    cam: CameraSpec,
    pose: RoverPose,
    recog_x: float | None = None,
) -> dict:
    """Turn a bbox (+optional recognition depth) into world + WGS84 geotag."""
    cx = (bbox_norm[0] + bbox_norm[2]) / 2.0
    cy1, cy2 = bbox_norm[1], bbox_norm[3]
    z_cam = pose.z + cam.local_offset[2]

    if recog_x is not None and 0.05 < recog_x < MAX_RANGE_M:
        rng = float(recog_x)
        scheme = "recognition_depth"
    else:
        rng = ground_range_from_bbox_bottom(cy2, z_cam, cam)
        scheme = "ground_plane"

    theta = theta_from_u(cx, cam)
    bearing = pose.heading_rad + cam.mount_yaw + theta
    # sin/cos flip: +theta means image-left, which is CCW in world yaw -> bearing already CCW.
    x = pose.x + rng * math.cos(bearing)
    y = pose.y + rng * math.sin(bearing)

    lat0, lon0 = _load_origin()
    lat = lat0 + y * _DEG_PER_M_LAT
    lon = lon0 + x * _DEG_PER_M_LON

    return {
        "x": round(x, 3),
        "y": round(y, 3),
        "lat": round(lat, 7),
        "lon": round(lon, 7),
        "bearing_deg": round(math.degrees(bearing) % 360.0, 2),
        "range_m": round(rng, 2),
        "z_cam_m": round(z_cam, 3),
        "scheme": scheme,
    }


def area_hint(x: float, y: float) -> str:
    """Cheap human hint for the student answer: quadrant relative to the route centroid."""
    if x > 0 and y > 0:
        return "NE quadrant of the route"
    if x <= 0 and y > 0:
        return "NW quadrant of the route"
    if x > 0 and y <= 0:
        return "SE quadrant of the route"
    return "SW quadrant of the route"
