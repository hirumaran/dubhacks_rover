# Perception Pipeline (Isaac-0.2-1B, local)

The on-rover intelligence layer of the lost-item rover. Follows the architecture
flowchart: **camera every 5s -> local Isaac detect/describe/track -> stable
object IDs -> geotag -> structured payload -> Supabase**. Students scan a
**desk QR** (`kiosk/qr/`) to report a lost item; cloud dispatch assigns the
**closest live rover**. The web branch (elsewhere in git) can also call
`match_agent.py`. Full QR/fleet manual: [QR_AND_FLEET.md](QR_AND_FLEET.md).

```
[Webots / rover @ teammate A]
  campus_rover.py --(guarded hook, PERCEPTION_INBOX)--> perception/inbox/*
                                                   frame_<seq>_c<i>.png
                                                   frame_<seq>.json   (pose + recognition sidecar)
[This folder @ teammate A, venv]
  run_service.py
    isaac_detector.py   Isaac-0.2-1B (transformers, trust_remote_code) | SDK | mock
    tracker.py          stable object IDs (OBJ-...) across frames/cameras
    geotag.py           pixel bbox + rover GPS/heading -> world x/y + lat/lon
    events.py           new | moved | gone | seen (throttled)
    supabase_store.py   crop -> storage bucket, row -> sightings (offline outbox on failure)
[Supabase]
  sightings / lost_items tables, sightings-crops bucket, recent_sightings view
[Student flow (web branch)]
  match_agent.py -> find_matches(text) -> first_sighting(obj) -> answer
```

## Files

| file | role |
| --- | --- |
| `config.py` | all env-driven knobs, camera specs (mount yaw, FOV) |
| `isaac_detector.py` | Isaac-0.2-1B loaders + structured-output prompt + MockDetector |
| `frames.py` | PNG load / downscale / normalized crops |
| `geotag.py` | projection + range + lat/lon math (documented Webots conventions) |
| `rover_geo.py` | rover WGS84 heartbeat math + closest-rover pick |
| `dispatch.py` | lost-item ingest, fleet assign, `state/missions.json` |
| `tracker.py` | stable IDs, IoU/text/spatial association, gone detection |
| `events.py` | event shaping + heartbeat throttle |
| `supabase_store.py` | storage uploads, inserts, offline outbox + flush |
| `run_service.py` | watches `inbox/`, drives everything, publishes rover GPS |
| `match_agent.py` | query-side helper for the web branch |
| `kiosk/` | phone form + `stations.json` + printable QR PNGs |
| `supabase/schema.sql` | paste into Supabase SQL editor once |
| `supabase/schema_dispatch.sql` | additive SQL if schema.sql already ran |
| `tools/smoke_test.py` | full-pipeline test without Webots |
| `tools/bridge_selftest.py` | fabricates 2 inbox ticks; verifies the Webots->service contract (hermetic, re-runnable) |
| `tools/make_qr.py` | generate desk QR cards (`--lan` auto-detects this machine's IP) |
| `tools/serve_kiosk.py` | mobile report server + `/api/status` for those QRs |
| `tools/rover_locate.py` | print this rover's last lat/lon |
| `tools/dispatch_selftest.py` | closest-rover + stale/reconcile gates + QR URL contract, no GPU |
| `WALKTHROUGH.md` | **detailed build log: every brick, the math, contracts, evidence** |
| `QR_AND_FLEET.md` | **QR product + fleet dispatch for teammates/agents** |
| `../simulation/controllers/campus_rover/perception_hook.py` | controller-side frame writer |

## Setup (teammate's machine Webots-1 / Mac-with-weights)

```bash
cd perception
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
# fill .env: SUPABASE_URL + SUPABASE_SERVICE_KEY (+ ANON key for web branch)
# Isaac weights: ensure PerceptronAI/Isaac-0.2-1B is in the HF cache, or
#   .venv/bin/huggingface-cli download PerceptronAI/Isaac-0.2-1B
```

### 1. Supabase (once, dashboard)

Run `supabase/schema.sql` in the SQL editor. It creates `sightings`,
`lost_items` (tables + RLS + indexes), the public `sightings-crops` bucket, the
`recent_sightings` view. Optional pgvector block is commented inside the file.

### 2. Run the service first

```bash
.venv/bin/python run_service.py
# "backend=isaac-0.2-1B[transformers] supabase=live" (or dry-run if .env empty)
```

### 3. Launch Webots with the bridge on

```bash
export PERCEPTION_INBOX="/absolute/path/to/repo/perception/inbox"
export FRAME_INTERVAL_S=5.0            # optional, default 5
open "simulation/Start Rover.command"  # or open the .wbt in Webots
```

Without `PERCEPTION_INBOX` the rover controller is byte-for-byte unchanged.

## Verification without Webots (works on any machine)

```bash
.venv/bin/python tools/smoke_test.py --mode archive          # mock detector, dry run
.venv/bin/python tools/smoke_test.py --mode archive --supabase  # real push
```

## Verification without the model (bridge test)

Set `ISAAC_BACKEND=mock` in `.env`, run the service + Webots as above. The mock
detector converts the Recognition sidecars into the same Detection format, so
tracking/geotag/upload are exercised end-to-end.

Bridge-only check (two synthetic ticks, no Webots, no GPU):

```bash
.venv/bin/python tools/bridge_selftest.py   # expects "[selftest] PASS"
```

## Student QR (librarians / campus security)

```bash
# 1. SQL: new project → schema.sql; existing → schema_dispatch.sql
# 2. PUBLIC_APP_URL in .env = the URL a phone will open (or just use --lan)
.venv/bin/python tools/make_qr.py --lan  # this machine's Wi-Fi IP + KIOSK_PORT
.venv/bin/python tools/serve_kiosk.py    # phone form + /api/status polling
.venv/bin/python run_service.py          # rover brain + heartbeat + hunt/reconcile
```

Print `kiosk/qr/print.html` or the per-desk PNGs. The phone polls
`/api/status?id=` and flips to "Found it!" when a sighting matches. Details,
fleet scale-up, and what agents must not rename: [QR_AND_FLEET.md](QR_AND_FLEET.md).

```bash
.venv/bin/python tools/dispatch_selftest.py   # expect PASS
```

## Web branch integration

```python
from perception.match_agent import find_matches, first_sighting, log_lost_item, answer_for_object
matches = find_matches("green water bottle")
answer = answer_for_object("green water bottle", matches[0], first_sighting(matches[0]["object_id"]))
```

## Notes

- **MPS**: Apple-GPU path uses float16 + sdpa attention; if a custom op lacks a
  MPS kernel the model auto-falls back to CPU slices (slow but works).
- **Fake/geotag precision**: `recognition_depth` scheme is exact via sim; the
  `ground_plane` scheme assumes the object sits on the ground - good enough for
  "last seen near x,y".
- **Offline resilience**: any Supabase failure appends to `state/outbox.jsonl`;
  rows flush automatically every 30s once connectivity returns.
- **ID stability**: `state/tracks.json` persists IDs between service restarts.
