# WALKTHROUGH — perception/, brick by brick

> Read this before touching anything. It is the full build log + operating
> manual for the on-rover intelligence layer: **why** every file exists, **how**
> the math works, **what contract** each piece obeys, exactly **what was
> verified on which machine**, and what **still needs a human**.
>
> Written for: hackathon teammates, their agents, and future-you at 2 AM.

---

## 0. 60-second orientation (for agents reading this cold)

**Product:** a rover patrols the UW campus (Webots sim now, real rover later).
Students lose things. A student scans a QR, uploads a photo or types
"green water bottle", and the answer is
*"last seen near the NE quadrant of the route at 13:02, confidence ~80% — photo"*.

**This folder** is the rover's brain: it converts raw camera frames into
described, identified, geotagged objects in Supabase. The web/mobile branch
(git branch `rishi_dev`, teammate-owned) is the student UI and calls
`match_agent.py`'s helpers — it does NOT run any model itself.
`simulation/` (main branch, pre-existing) is the Webots world + driving
controller; we made ONE small guarded addition to it, documented in §5.

**Pipeline (the architecture flowchart, instantiated):**

```
Webots cameras (4×320×240, near-FoV 1.64 rad)
      │ perception_hook.py (optional, guarded by PERCEPTION_INBOX env var)
      ▼  every FRAME_INTERVAL_S = 5 s (sim time)
perception/inbox/          frame_<seq>_c{0..3}.png  +  frame_<seq>.json
      │ run_service.py (watch loop, 1 poll/s, newest tick first)
      ▼
isaac_detector.py          Isaac-0.2-1B runs LOCALLY (transformers, MPS on Apple Silicon)
      │ returns JSON detections: label, description, color, bbox_norm(0..1), confidence
      ▼
geotag.py                  bbox center + rover GPS/heading + camera geometry
      │                    → world (x, y) meters + WGS84 lat/lon + bearing + range
      ▼
tracker.py                 IoU/text/color/spatial association → stable IDs (OBJ-HHMMSS-N)
      │                    emits state changes: new | moved | gone
      ▼
events.py                  shapes rows, throttles 'seen' heartbeats (10 s)
      ▼
supabase_store.py          crop PNG → storage bucket 'sightings-crops'
                           row → table 'sightings'   (INSERT after upload, never before)
      │                    on ANY failure: state/outbox.jsonl, auto-flushed later
      ▼
[Supabase]  sightings / lost_items / storage / recent_sightings view
      │
      ▼
match_agent.py             (web branch imports this) find_matches(text) → answer string
```

**Golden rule of this codebase:** the rover controller stays stdlib-only and
driving-focused. Perception failure must NEVER stop the rover. Hence the
file-pass-through-filesystem bridge (§5) instead of in-process model calls.

---

## 1. Why this architecture (the decisions, and the reasons)

| # | Decision | Reason |
|---|----------|--------|
| 1 | **Hybrid local+cloud**, not pure-local, not pure-cloud | Pure local: a 1B VLM can't beat embeddings+DB retrieval for matching user queries. Pure cloud (e.g. Perceptron Mk1.5): rover perception then stalls on Wi-Fi dropouts and adds round-trip latency around a 5 s perception cadence. |
| 2 | **Isaac-0.2-1B on the rover** | 1B params, self-host weights, native grounding + structured output; explicit edge focus. Isaac-0.5 (36B sparse) needs a discrete GPU + big VRAM/power — out of rover budget. Mk1.5 is API-only, so it can't run on the rover at all. |
| 3 | **Same-machine bridge via filesystem** | Webots + the model run on ONE teammate's computer (confirmed). A shared folder is the simplest reliable handoff — no sockets, no ports, no firewalls, survives model restarts. |
| 4 | **Recognition sidecar kept** | Webots' camera Recognition gives simulator *ground truth* bbox+depth for free. We don't trust it for SEMANTICS (that's Isaac's job) but we use its depth for precise geotag when available (`scheme: recognition_depth`) and as mock-test scaffolding. The original controller's comment ("deliberately replaceable") is why this layering was even possible. |
| 5 | **MPS-first device stack** | The teammate's GPU machine is Apple Silicon. float16 + SDPA attention on `torch.backends.mps`; bfloat16 + flash-attn-2 only on CUDA per the Isaac HF card; float32 on CPU. |
| 6 | **Two loader backends + mock** | `transformers` is the documented, verifiable path (`trust_remote_code=True` per HF card). `perceptron` SDK adapter exists but its local API varies by release — it is STUBBED and raises a loud error telling whoever picks it up to verify against docs (§14: caveats). Mock detector guarantees pipeline verifiability with zero GPU. |
| 7 | **Supabase as the single source of truth** | Persistent, queryable, free tier, pgvector optional, and the web branch already assumes it. Rover writes use the service-role key (trusted local writer); the web branch uses the anon key under RLS. |
| 8 | **Offline-first writes** | Wi-Fi WILL drop at a hackathon demo. Every failed push lands in a JSONL outbox and is silently re-flushed (30 s interval). Nothing is ever lost, nothing ever crashes. |

---

## 2. File map (who owns what)

```
perception/
├── config.py                 knobs + camera specs + .env loader (no hardcoding of secrets)
├── frames.py                 PNG load / VLM downscale / normalized bbox crop
├── geotag.py                 THE MATH: pixel→bearing→range→world→lat/lon
├── isaac_detector.py         backends: TransformersIsaac | SDKIsaac(stub) | MockDetector
├── tracker.py                stable IDs + association + gone detection + state file
├── events.py                 event shaping + 'seen' throttle
├── supabase_store.py         storage upload → insert → outbox → flush
├── run_service.py            the loop that ties bricks 1–8 together
├── match_agent.py            query side for the web branch
├── supabase/
│   └── schema.sql            PASTE-ONCE into SQL editor (builds everything)
├── tools/
│   ├── smoke_test.py         full pipeline on archived captures / live inbox, no Webots
│   └── bridge_selftest.py    fabricates 2 inbox ticks, verifies contract without Webots
├── inbox/                    (runtime) Webots → service. Gitignored, recreated on demand
├── state/                    (runtime) tracks.json, outbox.jsonl, crops/*.png. Gitignored
├── reports/                  (runtime) dry-run JSONL mirrors of what WOULD hit Supabase
├── .env.example              copy → .env and fill
├── requirements.txt          torch/transformers/supabase/Pillow/dotenv
├── README.md                 quickstart (short)
└── WALKTHROUGH.md            ← this file (deep)

simulation/controllers/campus_rover/
├── perception_hook.py        NEW: optional frame-writer hook (stdlib only)
└── campus_rover.py           MODIFIED: 8 guarded lines; identical behavior when env unset
```

**Ownership boundaries** (agents: respect these):
- `perception/inbox/` — written by Webots hook, consumed+deleted by service. Never hand-edit.
- `perception/state/` — owned by the service. Delete it to reset IDs (it regenerates).
- `simulation/` — existing driving logic is sacrosanct; only the guarded hook blocks were added (§5).

---

## 3. Brick 1 — `config.py` (all knobs in one place)

Everything is env-driven so nothing needs code changes between machines:

| Env var | Default | Meaning |
|---|---------|---------|
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` / `SUPABASE_ANON_KEY` | — | Supabase access. Service key = rover writes; anon = web reads (RLS enforced). If missing → whole stack runs in dry-run (§11). |
| `SUPABASE_STORAGE_BUCKET` | `sightings-crops` | bucket name; matches schema.sql |
| `ISAAC_HF_PATH` | `PerceptronAI/Isaac-0.2-1B` | HF repo or local path already in the HF cache |
| `ISAAC_BACKEND` | `auto` | `auto`(→transformers→sdk→mock) / `transformers` / `sdk` / `mock` |
| `ISAAC_DEVICE` | `auto` | `auto/mps/cuda/cpu` |
| `ISAAC_MAX_SIDE` | `640` | frames are downscaled before the VLM (small frames anyway; knob exists for real-rover cameras) |
| `ISAAC_ENABLE_THINKING` | `0` | reasoning traces toggle (slower, better on tiny objects) |
| `FRAME_INTERVAL_S` | `5.0` | the flowchart's "camera every 5 s" — used BOTH by hook and service |
| `INBOX_POLL_S` | `1.0` | service watch poll |
| `GONE_AFTER_S` | `8.0` | unseen for >8 s ⇒ emit `gone`, retire ID |
| `MOVE_MIN_M` | `0.15` | geotag jump >15 cm ⇒ `moved` instead of silent EMA |
| `MATCH_IOU_MIN` / `MATCH_TEXT_MIN` | `0.20` / `0.35` | association floors |
| `MAX_RANGE_M` | `6.0` | sanity clamp on any estimated range |

**CameraSpec** (mirrors `simulation/protos/CampusScout.proto` — do not diverge):

| camera | mount yaw (rad) | width×height | hFov | mount offset on rover |
|---|---|---|---|---|
| 0 (front) | 0 | 320×240 | 1.64 | (−0.015, 0, 0.21) |
| 1 (left? → see §4 sign note) | π/2 | 320×240 | 1.64 | same |
| 2 (back) | π | 320×240 | 1.64 | same |
| 3 | 3π/2 | 320×240 | 1.64 | same |

The `.env` loader degrades gracefully: full `python-dotenv` if installed,
otherwise a minimal `KEY=VALUE` line parser that never crashes.

---

## 4. Brick 2 — the geometry behind `geotag.py` (the part to actually understand)

This is the highest-risk math in the repo, so here is the complete derivation,
verified against the Webots reference manual and the *existing controller's own
steering math* (self-consistency is the proof).

**Camera frame (from https://cyberbotics.com/doc/reference/camera):**
- `X` = depth (the view axis), `Y` = horizontal, `Z` = up.
- Pixel column `u`: `s=0 ↔ θ=+hFov/2` … `s=(width−1)/2 ↔ θ=0` … `s=width−1 ↔ −hFov/2`
  ⇒ **image-left is +Y**, and the bearing angle off the view axis is

  ```
  θ(u) = (hFov/2)·(1 − 2u/(w−1))        # positive = image left
  ```

- Pixel row `v`: `v=0 ↔ φ=+vFov/2` (top); vertical FoV derives from hFov:
  `vFov = 2·atan(tan(hFov/2)·h/w)`

**Rover heading** (must agree with the driving controller, or geotags are garbage):
- The original controller computes `heading = atan2(compass[0], compass[1])`.
- Compass returns world-north expressed in the BODY frame: `n_body = R(−θ_world)·(0,1) = (sinθ, cosθ)`.
- `atan2(sinθ, cosθ) = θ` ⇒ **heading = world yaw, CCW-positive, measured from +x (east)**.
- Sanity: the controller's steering error `err = wrap(θ_goal − heading)` only converges
  under this convention, and the rover demonstrably navigates — so this is consistent.

**Mount composition:** camera_i is rotated `0 0 1 · i·π/2` *inside the rover body*,
and the camera's view axis is its local `+X` (per the docs above). Therefore:

```
world view yaw(camera i) = heading + i·π/2
world bearing(pixel u, camera i) = heading + i·π/2 + θ(u)
```

**World position from range:**

```
x = rover_x + range·cos(bearing)
y = rover_y + range·sin(bearing)
```

**Range — two schemes, best available wins:**

1. `recognition_depth` (precise): Recognition's `position[0]` IS the camera-frame
   depth `X`. Use directly when `0.05 < X < MAX_RANGE_M`.
   *(Note the sign: Recognition coordinates are camera-frame, X=depth — no
   negation games needed. Verified in the bridge selftest: rover (5,−3) heading
   45°, depth 2.0 ⇒ geotag (6.10, −1.33), bearing 56.75° — arithmetic exact.)*
2. `ground_plane` (VLM-only fallback): assume the object stands on the ground
   (z≈0.07 m); the bbox BOTTOM row `cy2` gives `φ(cy2) < 0` (below horizon), so

   ```
   ground_range = (z_cam − z_ground) / tan(−φ(cy2)),  z_cam = rover_z + 0.21
   ```
   clamped to `[1.2, MAX_RANGE_M]`. Noisy but honest — good enough for
   "last seen near …". If the bbox bottom sits at/above the horizon (`φ > −0.05`),
   fall back to `MAX_RANGE_M` (far object).

**Lat/lon:** affine offset from `simulation/maps/mission.json`'s `reference_lat_lon`
(47.65865, −122.3074): `lat = lat0 + y/110574`, `lon = lon0 + x/(111320·cos(lat0))`.
At a ≤150 m scale this is demo-grade truth (≈ mm–cm level error).

**`area_hint`** is a quadrant string ("NE quadrant of the route") for the
student-facing answer.

---

## 5. Brick 3 — the Webots bridge (guarded, zero-cost when off)

**`simulation/controllers/campus_rover/perception_hook.py`** — NEW file, stdlib only
(json/math/os/struct/zlib — same discipline as the rest of the controller).

**`campus_rover.py`** — exactly two insertions, both guarded:

```python
# in __init__ (after emitter setup):
inbox=os.environ.get('PERCEPTION_INBOX')
self.hook=None
if inbox:
 from perception_hook import PerceptionHook
 self.hook=PerceptionHook(self.cameras,self.gps,self.compass,inbox)
# in tick(), first line:
if self.hook:self.hook.maybe(now)
```

With `PERCEPTION_INBOX` unset: zero imports, zero calls, robot identical to
before (verified by reading the diff — no other lines touched).

**What the hook writes per tick** (one seq = one Webots sim moment):

```
frame_<seq>:07d>_c<i>.png     full 320×240 RGB PNG (hand-rolled stdlib PNG encoder:
                              BGRA raw scanlines, filter 0, zlib level 5)
frame_<seq>:07d>.json         the tick's for-real payload:
{
  "sim_time_s": 51.2,
  "gps": [x, y, z],              ← world ENU meters (Webots GPS)
  "heading_rad": 1.234,          ← same formula as controller steering
  "seq": 7,
  "cameras": [
    {"idx": 0, "objects": [
      {"model": "bottle|CS-042",          ← simulator ground-truth name|sample_id
       "position": [2.0, -0.1, -0.15],    ← CAMERA frame: X depth, Y left, Z up
       "position_on_image": [120, 150],   ← pixels
       "size_on_image": [40, 90],         ← pixels
       "distance": 2.04}
    ]}, ... 4 entries ...
  ]
}
```

Invariants agents must preserve:
1. **meta.json is written atomically** (tmp + `os.replace`) — the service
   consumes the moment it sees it complete.
2. PNGs are written BEFORE the meta of the same seq.
3. The hook throttles itself to `FRAME_INTERVAL_S` in *sim time* and prints one
   status line per tick (`PERCEPTION_BRIDGE seq N …`).
4. It does its own PNG encode (reuses the crop encoder's chunk technique
   extended to full frames) — do NOT import Pillow into the controller.

**Why filesystem handshake and not in-process?** (a) keeps the controller
stdlib-only (already the project's discipline), (b) model reload/debug cycles
never touch the rover process, (c) the inbox doubles as a recording — replay
the exact same ticks into any detector backend for A/B testing.

---

## 6. Brick 4 — `isaac_detector.py` (Isaac-0.2-1B, three backends)

**Interface (everything downstream speaks this):**

```python
@dataclass
class Detection:
    label: str            # one of TARGET_CLASSES (else 'other')
    description: str      # <=12 words, includes color + where it sits
    color: str            # 'red', 'yellow', …
    bbox_norm: list[4]    # [x1,y1,x2,y2] floats 0..1 (clamped + degenerate->center box)
    confidence: float
    camera_idx: int
    sim_time_s: float
    recog_x: float|None   # camera-frame depth from the sidecar (optional)
    source: str           # isaac_transformers|isaac_sdk|mock|recognition …
```

**TransformersIsaac (primary).** Loaded per the HF card (`trust_remote_code=True`
on BOTH processor and model), device/dtype matrix:

| device | dtype | attention |
|---|---|---|
| cuda | bfloat16 | `flash_attention_2` vision + sdpa text (HF-card recommended) |
| mps | float16 | sdpa |
| cpu | float32 | sdpa |

Generation: greedy (`do_sample=False`), `max_new_tokens=512`. The prompt bakes
in the whole detection discipline (this is the actual system+user text, verbatim):

- system: *"You are the vision system of a small campus rover. … answer with
  ONLY a JSON array, no prose, no markdown fences."*
- user: list every distinct lost-item-looking object; allowed labels =
  `backpack, book, notebook, bottle, umbrella, phone, keys, wallet, headphones,
  jacket, hat, lunchbox, sunglasses, laptop, charger, bag, bicycle, toy, other`
  (whittled to what a student actually loses + what the sim spawns; `other` is
  the escape hatch so the model doesn't hallucinate forced fits);
  per-object keys `label / description / color / bbox_xyxy_norm / confidence`;
  ignore buildings/people/roads/ground; duplicates forbidden; `[]` when clean.

**Parsing discipline** (1B models leak prose; assume it will):
`_extract_json_array` regex-hunts the first `[...]` block and `json.loads` it;
bbox validated by `_is_bbox` then `_clamp_bbox` (sort+clip 0..1, degenerate →
0.45..0.55 center box rather than distribute garbage downstream). Unknown labels
collapse to `other`. A frame returning garbage = zero detections that frame,
NOT a crash — tracker simply doesn't see it that tick.

**SDKIsaac (stub, honest).** Perceptron's local SDK API shifts between releases
(FiftyOne integration says `model.operation="detect"`; the hosted docs show
`perceive(...)`-style calls). Rather than guess, the adapter raises an
InstructiveError telling the next engineer to verify at docs.perceptron.inc.
`ISAAC_BACKEND=auto` therefore effectively means transformers→mock for now.

**MockDetector (the secret testing weapon).** Two modes depending on input data:
- *ref-mode*: sidecar recognition objects present → converts them 1:1 into
  Detections (exact bbox from `position_on_image/size_on_image`,
  `recog_x=position[0]`, label from `kind|sid`). This runs the REAL pipeline
  on REAL bridge geometry without a GPU.
- *fake-mode*: no refs (archive captures) → deterministic per-frame pseudo
  detections (`Random(2026)`, varies with sim time). Labels cycle
  backpack/bottle/book. Confidence 0.62, source 'mock'.

`build_detector()` resolution: explicit `ISAAC_BACKEND` honored strictly;
`auto` = transformers → sdk → mock, printing the reason for each skipped
backend — never a silent surprise.

---

## 7. Brick 5 — `tracker.py` (stable object IDs)

**ID format:** `OBJ-<UTC HHMMSS>-<seq>`, seq monotonic persisted in
`state/tracks.json` (survives restarts; retired IDs never reused).

**Track fields carried:** label, description, color, bbox_norm, confidence (EMA
0.7/0.3 with each new confidence), camera_idx, world_x/y, geotag, first/last
seen (sim + UTC), `age_updates`.

**Association scoring** (candidate det, existing track):

```
same camera      : iou = IoU(bbox_track, bbox_det)   (else 0)
label equal      : +1 ……… weight 0.25
color equal      : +1 ……… weight 0.10
text similarity  : token-Jaccard(min set) weight 0.20
IoU weight       : 0.45
SPATIAL HARD GATE: world distance < 1.2 m AND Δt < 10 s, else score = −1
                   (an object cannot teleport; this kills 90% of ID-mixups)
reject if        : same-camera and iou<0.20 and label mismatch and text<0.35
```

Greedy: for every live track take its best-scoring unmatched det.

**State changes emitted:**
- `new` — leftover det becomes a track at its geotag.
- `moved` — matched det's geotag jumps > `MOVE_MIN_M` (0.15 m).
- otherwise position EMA `0.8·old + 0.2·new` absorbs per-frame range jitter
  (this is why a stationary object's geotag *converges* instead of dancing).
- `gone` — unseen > `GONE_AFTER_S` (8 s); ID retired to `state/tracks.json`.
  If the object is picked up and later re-spotted, it earns a NEW id — students
  care about "first seen where", and first-sighting rows answer that.

**Same-object-across-cameras folding:** within one tick, two cameras can each see
the same bottle. Their images-bboxes never IoU-overlap (different views) but the
spatial gate passes; leftover dets that match a track TOUCHED this tick in label
and within 1.2 m are folded (EMA) instead of minted — no duplicate IDs, no churn.

---

## 8. Brick 6 — `events.py` (don't flood Supabase)

Tracker emits *state changes*; shaper decides rows:

| tracker event | rows sent |
|---|---|
| new | 1 × `new` |
| moved | 1 × `moved` + 1 × `seen` if >10 s since last heartbeat |
| gone | 1 × `gone` (description suffixed " \| not seen again") |

Row contract (equals the `sightings` table minus timestamps):

```
object_id, label, description, color, confidence, bbox_norm(jsonb),
camera_idx, event ∈ {new,seen,moved,gone}, geotag(jsonb), rover_pose(jsonb),
sim_time_s, model_backend
```

---

## 9. Brick 7 — `supabase_store.py` (upload-then-insert + outbox)

1. Crop PNG (bbox +5% padding) → bucket object
   `YYYYMMDD/<object_id>/<millis>.png` (content-type png, upsert true).
2. INSERT the row with `image_url = <SUPABASE_URL>/storage/v1/object/public/public URL`.
   Insert AFTER upload ⇒ a row never dangles.
3. ANY exception (upload, insert, network) → append full attempt to
   `state/outbox.jsonl` and continue. The loop flushes the outbox every 30 s
   (5 s in --once mode); already-uploaded crops are reused via stored
   `storage_path`.
4. `enabled=False` (no env / failed probe) ⇒ DRY-RUN: rows go to
   `reports/sightings_dry_run.jsonl`, events always to `reports/events.jsonl`.

Connection probe at startup: tiny `select id from sightings limit 1` so a bad
URL/key/table fails LOUD and EARLY, not at first event.

---

## 10. Brick 8 — `supabase/schema.sql` (paste-once)

- `sightings` — the append-only perceived-object log (columns above +
  `created_at timestamptz default now()`, indexes on object_id / created_at / label).
- `lost_items` — student reports: `query_text`, `query_image_url`, `status`
  (open/matched/resolved), `matched_object_id`, `match_confidence`, `match_reason`.
- RLS: sightings read = public; lost_items insert = public; rover writes bypass
  RLS via service key. This is the ONLY key split you need.
- storage bucket `sightings-crops` (public read; writes stay service-role).
- view `recent_sightings` — `DISTINCT ON (object_id)` latest non-gone per ID,
  newest-first: the one endpoint the web branch needs.
- pgvector: commented block (create extension, `embedding vector(512)`,
  ivfflat index) — enable later IF embedding-based matching is wanted; DO NOT
  require it for the demo path.

---

## 11. Brick 9 — `run_service.py` (the loop)

```
watch:  poll inbox/ every 1 s
        glob frame_*_c*.png beside frame_<seq>.json  ⇒ complete ticks only
cadence: process at most one tick per FRAME_INTERVAL_S (5 s)
order:   newest seq first
per tick:
   meta → RoverPose(gps/heading/sim)
   for each camera png of that seq (0..3):
        image = load_png()
        refs  = meta.cameras[idx].objects
        detections = detector.detect(image, idx, sim, refs)
        each det → geotag.locate(bbox, cam_spec, pose, recog_x) + area_hint
   ONE tracker.update(sim, all geo_dets)      ← cross-camera association happens here
   events → shaper → commit: crop→storage→insert   (dry-run mirror otherwise)
   tracker.save_state(); store.flush_due()
hygiene: consumed seq files are deleted (png + json); stale older seqs too
   (a hiccupping home / disk-full inbox never grows unbounded)
```

Also handy flags: `python run_service.py --once` processes whatever is pending
and exits (CI/cron/debug).

---

## 12. Brick 10 — `match_agent.py` (web branch integration)

```python
from perception.match_agent import find_matches, first_sighting, log_lost_item, answer_for_object

matches = find_matches("green water bottle")            # top-5 object candidates
answer  = answer_for_object("green water bottle",
                            matches[0],
                            first_sighting(matches[0]["object_id"]))
log_lost_item("green water bottle", created_by=anon_user, matches=matches)
```

Scoring: `0.5·token-overlap + 0.2·label-hit + 0.1·color-hit + 0.2·exp(−age_h/24)`
through the `recent_sightings` view, deduped by object_id.
`first_sighting()` = earliest `sightings` row for the matched ID — **that** is
the answer students want (where the item STARTED being seen; it may be moved or
gone now, and the timeline rows tell the rest).
Read path uses the ANON key intentionally (RLS proves itself).

---

## 13. What was VERIFIED, on which machine (evidence, not vibes)

**On Thiru's mac (no torch, no Supabase, CPU-only, Python 3.14):**

| test | command | result |
|---|---|---|
| all modules compile | `python3 -m py_compile` × 12 files | OK |
| full pipeline, archive captures | `python tools/smoke_test.py --mode archive` | 5 captures → 9 events (5 `new`, 4 `gone` — synthetic sim times are 15 s apart ⇒ >`GONE_AFTER_S`), correct geotags (47.6587, −122.3073 …), `bbox_norm`, `rover_pose`, payload keys EXACT match to schema; crops (PNG, valid) saved under `state/crops/`; dry-run JSONLs written |
| bridge contract without Webots | `python tools/bridge_selftest.py` | **PASS** — synthetic tick #1: recognized bottle with camera-side depth 2.0 m ⇒ geotag (6.10, −1.33), bearing 56.75°, range 2.0 (`recognition_depth`), lat/lon sane; tick #2 with moved pose produced correct new geotag; tracker state persisted |
| controller hook guards | `git diff simulation/.../campus_rover.py` | only the two guarded blocks; behavior unchanged when env unset |

**Deliberately NOT verified here (on purpose — wrong machine):**
1. Real `TransformersIsaac` generation on the teammate's MPS box (torch absent locally).
2. A real Supabase push (no URL/keys yet) — dry-run path is identical logic.
3. the `perceptron` SDK adapter (stub by design; §6).

**Teammate-A/node-must-do checklist, in order:**
1. `cd perception && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. ensure Isaac weights present: `.venv/bin/huggingface-cli download PerceptronAI/Isaac-0.2-1B`
3. `python tools/bridge_selftest.py` (mock, no Webots — pure plumbing check)
4. Once .env filled: `python tools/smoke_test.py --mode archive --supabase`
5. `python run_service.py`; watch `[service] backend=isaac-0.2-1B[transformers] supabase=live`
6. In another shell: `export PERCEPTION_INBOX=<abs>/perception/inbox` then open Webots world
7. Watch: `PERCEPTION_BRIDGE seq …` (Webots) ⇄ `[event] …` (service); verify rows in Supabase
   Table editor → `sightings`.

---

## 14. Honest caveats & sharp edges (read before "improving")

1. **SDK adapter is a stub** — finish it against real SDK docs, or ignore transformers is the path.
2. **ground_plane range is an estimate** (assumes ground-standing object, flat earth).
   Expect decimeters-to-meters noise. The `scheme` field always tells you which path produced the number.
3. **MockDetector fake-mode is intentionally dumb** (one pseudo-object per view, cycling labels).
   In bridge selftests it mints per-camera IDs for identical input images — that is the mock,
   NOT the tracker. Real Isaac per real per-camera views is the intended path; with `ref-mode`
   (recognition sidecars) the pipeline behaves precisely.
4. **Isaac's exact generation control flags** (`enable_thinking` etc.) live behind `ISAAC_ENABLE_THINKING`
   — the HF card mentions the toggle; the boilerplate is threaded but untested on-device (team decides per-frame speed/quality).
5. **Camera 1–3 names left/right** depend on the compass convention (§4). The math is convention-consistent
   because bearing derived from the SAME heading the steering uses; only human-readable words like "left"
   could be off by mirror — never the coordinates. If you ever rename, re-verify with bridge_selftest numbers.
6. **Do not add deps to the controller hook.** stdlib-only is its reason to exist.
7. **IDs reset if `state/` is deleted** — by design (clean re-demo), don't treat as a bug.
8. **Archive captures are tight object crops, not full camera frames** — smoke_test uses them solely to
   exercise plumbing (detector→tracker→geotag→persist), so synthetic poses are used there. Real frames
   flow via the inbox when Webots runs.

---

## 15. Data contracts quick reference

**inbox tick** (written by hook): see §5 JSON. Producer: `perception_hook.py`. Consumer: `run_service.Service`.

**Detection** (detector → everything): see §6 dataclass.

**sightings row**: see §8/§11 list. Producer: Service._commit. Consumer: web branch + match_agent.

**outbox entry** (`state/outbox.jsonl`):
```json
{"row": {...sightings row...}, "storage_path": "20261017/OBJ-x/….png|null",
 "crop": "state/crops/x.png|null", "queued_utc": "…"}
```

**state/tracks.json**:
```json
{"active": [track…], "retired": ["OBJ-…"], "seq": 42, "saved_utc": "…"}
```

---

## 16. FAQ (agents: check here before asking)

**Q: Where do secrets live?** `perception/.env` (gitignored). Template `.env.example`. Never hardcode; never move service key into the web branch.

**Q: Add a new object class?** Extend `TARGET_CLASSES` in `isaac_detector.py` (prompt derives from it). Lowercase, singular. Tracker/matching need no changes.

**Q: Change capture cadence?** `FRAME_INTERVAL_S` (respected by BOTH the hook and the service — single source of truth).

**Q: Whole system with zero GPU/GPU-free laptop?** `ISAAC_BACKEND=mock` + `bridge_selftest.py` / `smoke_test.py --mode inbox`: full loop minus VLM quality.

**Q: Resetting demo state?** `rm -rf perception/state perception/inbox/* perception/reports/*` — table rows in Supabase are the source of truth and are not touched by this.

**Q: Where are dry-run artifacts?** `reports/events.jsonl` (every commit, with `persisted` flag), `reports/sightings_dry_run.jsonl` (rows that WOULD reach Supabase), `state/crops/` (the actual crop images the browser shows).

**Q: Renaming — what breaks?** The seq/camera filename pattern (`frame_<seq:07d>_c<i>.png` + `frame_<seq:07d>.json`) is a cross-repo contract shared with the controller hook — change both sides or don't change it.
