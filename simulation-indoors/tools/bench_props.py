"""Benches beside the patrol route, with random lost items left on them.

Benches are placed off the walkway: each one sits beside the rover's route, faces it, and its
footprint (plus a margin) must clear every paved walkway, building and tree in the world. Items
are real Webots object models (not coloured primitives), so a camera-only detector can recognise
them. Each item is wrapped in a Solid carrying `model "<kind>|<id>"` and recognition colours so
the rover's Recognition-based photo gallery keeps working; the perception bridge never sees that.

Used by build_project.py when the whole campus is regenerated, by apply_bench_props.py to refresh
benches and items in the existing campus world, and by the indoor showcase's build_atrium.py.
"""
from __future__ import annotations

import math
import random
import re

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

PROTO_BASE = "https://raw.githubusercontent.com/cyberbotics/webots/R2025a/projects/objects"
EXTERNPROTOS = [
    f"{PROTO_BASE}/street_furniture/protos/Bench.proto",
    f"{PROTO_BASE}/drinks/protos/WaterBottle.proto",
    f"{PROTO_BASE}/school_furniture/protos/Book.proto",
    f"{PROTO_BASE}/balls/protos/SoccerBall.proto",
    f"{PROTO_BASE}/toys/protos/RubberDuck.proto",
]

# Bench.proto: 2.23 m long (local y), seat top 0.54 m, front edge toward local +x, backrest at x≈-0.2.
BENCH_HALF_LEN = 1.15
BENCH_BACK, BENCH_FRONT = -0.32, 0.50
SEAT_Z = 0.54
SEAT_X = 0.18           # middle of the usable seat, in front of the backrest
SEAT_SLOTS = [-0.75, -0.25, 0.25, 0.75]

# kind -> (node template, height of the item's origin above the surface it rests on, recognition colour)
ITEMS = {
    "backpack": ('Solid {{ translation {x} {y} {z} rotation 0 0 1 {yaw} name "{name}" children [ CadShape {{ url [ "assets/lost-items/backpack/model.obj" ] }} ] boundingObject Pose {{ translation 0 0 .21 children [ Box {{ size .472 .356 .42 }} ] }} }}',0.0,"0.3 0.4 0.6"),
    "laptop": ('Solid {{ translation {x} {y} {z} rotation 0 0 1 {yaw} name "{name}" children [ CadShape {{ url [ "assets/lost-items/laptop/model.obj" ] }} ] boundingObject Pose {{ translation 0 0 .104 children [ Box {{ size .34 .31 .209 }} ] }} }}',0.0,"0.5 0.5 0.55"),
    "bottle": ('WaterBottle {{ translation {x} {y} {z} rotation 0 0 1 {yaw} name "{name}" mass 0 }}', 0.0, "0.75 0.85 0.95"),
    "book": ('Book {{ translation {x} {y} {z} rotation {book_rot} name "{name}" color {color} }}', 0.012, "0.45 0.2 0.2"),
    "ball": ('SoccerBall {{ translation {x} {y} {z} name "{name}" radius 0.11 }}', 0.112, "0.95 0.95 0.95"),
    "toy": ('RubberDuck {{ translation {x} {y} {z} rotation 0 0 1 {yaw} name "{name}" scale 2 density 0 }}', 0.04, "1 0.8 0"),
}
DESCRIPTIONS = {
    "backpack": "Backpack with shoulder straps and front pocket",
    "laptop": "Open laptop with keyboard and screen",
    "bottle": "Clear plastic water bottle",
    "book": "Hardcover book",
    "ball": "Black and white soccer ball",
    "toy": "Yellow rubber duck",
}
BOOK_COLORS = ["0.8 0.25 0.2", "0.2 0.35 0.7", "0.25 0.55 0.3", "0.9 0.8 0.3"]


# ---------------------------------------------------------------- world obstacles

def _floats(s: str) -> list[float]:
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", s)]


def obstacles(world_text: str) -> dict:
    """Paved walkways, building footprints and tree trunks parsed from a generated .wbt."""
    paved, buildings, trees = [], [], []
    for m in re.finditer(
        r"Pose \{ translation (\S+) (\S+) 0 children \[ Shape \{ appearance PBRAppearance \{ baseColor \.59 \.55 \.46"
        r".*?point \[ ([^\]]*) \] \} coordIndex", world_text):
        tx, ty = float(m.group(1)), float(m.group(2))
        v = _floats(m.group(3))
        pts = [(v[i] + tx, v[i + 1] + ty) for i in range(0, len(v), 3)]
        for i in range(0, len(pts) - 2, 3):
            tri = Polygon(pts[i:i + 3])
            if tri.area > 1e-6:
                paved.append(tri)
    for m in re.finditer(
        r'Solid \{ translation (\S+) (\S+) \S+ name "([^"]*)".*?DEF OSM_BUILDING_\d+ IndexedFaceSet \{ coord Coordinate \{ point \[ ([^\]]*) \]',
        world_text):
        tx, ty = float(m.group(1)), float(m.group(2))
        v = _floats(m.group(4))
        ring = [(v[i] + tx, v[i + 1] + ty) for i in range(0, len(v), 3) if abs(v[i + 2]) < 1e-6]
        if len(ring) >= 3:
            buildings.append(Polygon(ring).buffer(0))
    for m in re.finditer(r'Solid \{ translation (\S+) (\S+) \S+ name "tree', world_text):
        trees.append(Point(float(m.group(1)), float(m.group(2))))
    return {
        "paved": unary_union(paved) if paved else Polygon(),
        "buildings": unary_union(buildings) if buildings else Polygon(),
        "trees": trees,
    }


# ---------------------------------------------------------------- placement

def _route_at(pts, d):
    """Point, unit left-normal and heading at distance d along the (looping) route."""
    total = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    d %= total
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        if seg and d <= seg:
            f = d / seg
            dx, dy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), (-dy, dx), total
        d -= seg
    return pts[-1], (0.0, 1.0), total


def bench_footprint(x, y, yaw, margin=0.0) -> Polygon:
    c, s = math.cos(yaw), math.sin(yaw)
    corners = [(BENCH_BACK - margin, -BENCH_HALF_LEN - margin), (BENCH_FRONT + margin, -BENCH_HALF_LEN - margin),
               (BENCH_FRONT + margin, BENCH_HALF_LEN + margin), (BENCH_BACK - margin, BENCH_HALF_LEN + margin)]
    return Polygon([(x + c * u - s * v, y + s * u + c * v) for u, v in corners])


def campus_blocked(world_text: str):
    """Where a campus bench may not go: walkways, buildings (+0.8 m) and tree crowns (1.3 m)."""
    o = obstacles(world_text)
    return unary_union([o["paved"], o["buildings"].buffer(0.8)] + [t.buffer(1.3) for t in o["trees"]])


def place_benches(route_pts, blocked, count, rng, allowed=None, offsets=(1.7, 2.0, 2.3, 2.7, 3.1, 3.6),
                  margin=0.35, min_gap_m=10.0):
    """Benches spread along the route, each beside it and facing it.

    A bench's footprint plus `margin` must not touch `blocked` (walkways, walls, furniture...) and,
    when given, must lie inside `allowed` (e.g. an indoor floor plate).
    """
    _, _, total = _route_at(route_pts, 0)
    benches = []
    start = rng.uniform(0, total)
    for k in range(count * 4):  # extra attempts in case a stretch has no room
        if len(benches) == count:
            break
        d = start + (k + rng.uniform(-0.3, 0.3)) * total / count
        p, n, _ = _route_at(route_pts, d)
        for side in rng.sample([1, -1], 2):
            placed = None
            for off in offsets:
                x, y = p[0] + n[0] * off * side, p[1] + n[1] * off * side
                yaw = math.atan2(-n[1] * side, -n[0] * side)  # front (+x) faces the walkway
                fp = bench_footprint(x, y, yaw, margin=margin)
                if fp.intersects(blocked) or (allowed is not None and not allowed.contains(fp)):
                    continue
                if min(math.dist((x, y), q) for q in route_pts) < off - 0.05:
                    continue  # closer to another stretch of the route than to this one
                if any(math.dist((x, y), (b[0], b[1])) < min_gap_m for b in benches):
                    continue
                placed = (x, y, yaw)
                break
            if placed:
                benches.append(placed)
                break
    return benches


def render(route_pts, blocked, rng, bench_count=6, max_items_per_bench=2, allowed=None, id_prefix="CS",
           required_kinds=(), **place_kw):
    """World nodes (one per line) for benches and the items left on them, plus a summary."""
    benches = place_benches(route_pts, blocked, bench_count, rng, allowed=allowed, **place_kw)
    nodes, summary = [], []
    item_no = 0
    for i, (bx, by, yaw) in enumerate(benches, start=1):
        nodes.append(f'DEF BENCH_{i} Bench {{ translation {bx:.3f} {by:.3f} 0 rotation 0 0 1 {yaw:.5f} name "bench_{i}" }}')
        c, s = math.cos(yaw), math.sin(yaw)
        slots = rng.sample(SEAT_SLOTS, k=rng.randint(0, max_items_per_bench))
        for slot in slots:
            item_no += 1
            kind = required_kinds[item_no-1] if item_no<=len(required_kinds) else rng.choice(list(ITEMS))
            template, z0, col = ITEMS[kind]
            u = SEAT_X + rng.uniform(-0.06, 0.06)
            v = slot + rng.uniform(-0.12, 0.12)
            ix, iy = bx + c * u - s * v, by + s * u + c * v
            spin = yaw-math.pi/2 if kind=='laptop' else rng.uniform(-math.pi, math.pi)  # the wrapper Solid turns the item on the seat
            sid = f"{id_prefix}-{item_no:03d}"
            inner = template.format(x=0, y=0, z=z0, yaw=0, name=f"{kind}_{item_no}",
                                    book_rot="0 1 0 1.5708",  # lie the upright book flat
                                    color=rng.choice(BOOK_COLORS))
            nodes.append(
                f'DEF ITEM_{item_no} Solid {{ translation {ix:.3f} {iy:.3f} {SEAT_Z} rotation 0 0 1 {spin:.4f} '
                f'name "lost_{kind}_{item_no}" model "{kind}|{sid}" recognitionColors [ {col} ] children [ {inner} ] }}'
            )
            summary.append({"id": sid, "kind": kind, "description": DESCRIPTIONS[kind], "bench": i,
                            "x": round(ix, 2), "y": round(iy, 2)})
    return nodes, benches, summary
