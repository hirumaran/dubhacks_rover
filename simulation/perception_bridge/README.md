# Perception bridge

Connects the Webots rover to the item-recognition backend. Every few seconds the rover saves
what its four cameras see; this service decides which of those images are worth looking at and
sends them to the `identify-found-items` edge function, which uses Perceptron Mk1.5 to find,
describe and list lost items in Supabase (`found_items`).

Only what a real rover could sense goes in: camera pixels and the rover's own GPS and compass
pose. Simulator ground truth (Webots Recognition objects) is not exported.

```
controllers/campus_rover/perception_hook.py      every 5 s: frame_<seq>_c1.jpg / _c3.jpg + frame_<seq>.json (GPS, heading)
        │  inbox/                                from the rover's left/right perception cameras (1920×1440,
        ▼                                        50° lens on a 0.9 m mast, tilted ~10° down at bench seats)
run_bridge.py
  change_gate.py   send a camera's image only if the rover moved ≥1.5 m, that camera turned ≥20°,
                   or the picture changed (64-bit image hash); otherwise skip it
  pose.py          rover GPS (sim metres) → latitude/longitude, per-camera facing
  confirm.py       two-view confirmation: a find is listed only once a second rover position sees the
                   same kind of item and both sight lines cross at one spot (triangulation)
  uploader.py      POST to identify-found-items, both cameras at once; offline queue in state/outbox/
                   (when the bridge falls behind it skips to the newest tick, unless SKIP_STALE=false)
        │
        ▼
edge-functions/identify-found-items   open-ended Mk1.5 search on 2 tiles ("any small personal belonging",
                                      no fixed item list) → drop boxes under 48 px (too far away) →
                                      describe each crop, rejecting scenery/furniture/unclear objects →
                                      skip items already listed nearby → found_items
```

## Files

| File | Role |
| - | - |
| `run_bridge.py` | Watches the inbox and drives everything |
| `change_gate.py` | Decides which images are new views; state in `state/gate.json` |
| `pose.py` | GPS → lat/lon (mission reference point), camera facing |
| `confirm.py` | Two-view confirmation before anything is listed (`CONFIRM_VIEWS=1` turns it off) |
| `uploader.py` | Requests to the edge function, offline retry |
| `tools/reset_demo_listings.py` | List or delete this rover's demo listings and their photos |
| `config.py` | Settings from `.env` |
| `tools/selftest.py` | Offline test with a mock server: gate, request contents, retry |

## Setup

```bash
cd simulation/perception_bridge
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # fill ROVER_INGEST_SECRET and ROVER_ID
```

- `ROVER_INGEST_SECRET` is the same value the edge function has (`edge-functions/.env`).
- `ROVER_ID` must be a row in the `rovers` table (it is a foreign key on `found_items`).
- Keep `IS_DEMO=true` for the simulator so sim items only show to demo accounts.
- `DRY_RUN=true` identifies items without listing anything.

## Run

```bash
.venv/bin/python run_bridge.py
# in another terminal:
export PERCEPTION_INBOX="$(pwd)/inbox"
open "../Start Rover.command"    # or open ../worlds/uw_autonomous.wbt in Webots
```

Without `PERCEPTION_INBOX` the rover controller does not load the hook at all.
Every request and result is appended to `reports/events.jsonl`.

## Test

```bash
.venv/bin/python tools/selftest.py    # no network, no Webots: expects "[selftest] PASS"
```

## Indoor showcase

The Gates atrium rover (`indoor_showcase/`, and the standalone copy in `simulation-indoors/`) has the
same mast cameras (94° lens, since its benches are only 1.2 m from the route) and the same hook:

```bash
export PERCEPTION_INBOX="$(pwd)/inbox"
PERCEPTION_MISSION=../indoor_showcase/maps/mission.json LOCATION_LABEL="Gates Center atrium" \
  MOVE_MIN_M=1.0 .venv/bin/python run_bridge.py
```

## Checking detections

The simulators write the layout they generated to `maps/lost_items.json` (benches, items, positions).
That file is ground truth for scoring a run, never an input to the pipeline. Historical baseline before the October 17 fixes, from one lap with
seed 2026 (not a score for the current scene): campus 7/7 items found (6 named correctly, 1 false find); indoor 4/4 (2 false finds).

## Notes

- **Cost.** Each image that passes the gate costs one Perceptron call per detection tile, one
  describe call per item found, and one comparison per similar listing nearby. Raise `MOVE_MIN_M`
  to send less.
- **Speed.** A sim running faster than real time outpaces the detector; with `SKIP_STALE=true` the
  bridge then skips views and can miss benches. Run in real time, or set `SKIP_STALE=false`.
- **Location.** Tracked listings use a two-view estimate of the item position. Untracked legacy inputs carry only the observer position. Public coordinates stay approximate.
- **Duplicates.** Precise tracked items use private nearby anchors and visual identity, without a 24-hour expiry. Older untracked rows use the approximate-location fallback until visually matched and attached to a private track.
  First-view detection can run across cameras in parallel; confirmed listing requests run sequentially.
- When the actual bridge hook is active, the showcase disables reference labels. Without the hook, Webots Recognition remains a clearly labeled reference mode.


## Accuracy fixes and connection checks (October 17, 2026)

- All HTTPS calls verify certificates using `certifi`; credentials are read from private `.env` files and remain gitignored.
- The controller emits session ID, actual image size/FOV and sampling interval. The bridge uses each frame's FOV, rather than assuming the outdoor 50° lens for the indoor 94° cameras.
- Camera buffers are rendered at the GPS/compass sampling cadence shortly before the capture timer fires. Pairing an older 256 ms image with a newer heading during turns is avoided.
- New capture sessions clear pending associations and view-change state; launchers archive stale inbox files before starting the bridge.
- Blank/near-uniform images, invalid/out-of-frame/scene-sized boxes, generic “rectangular object” descriptions and furniture identities are rejected locally. Matching broad category/color alone cannot confirm an item. Sight lines need a meaningful intersection angle and a separate viewpoint.
- Distinct item types at nearby positions are no longer suppressed by one global “already found” radius.
- Optional `PERCEPTION_PUBLIC_DIR` writes only model frame images, normalized pixel boxes, status and confirmed item summaries for the local showcase. It exports no secrets or navigation coordinates.
- The Edge Function fix independently validates blank images/boxes, asks the model to judge crop **and full-scene context**, rechecks caller-supplied candidates, and makes dry-run identification independent of database reads. Deploy it from a Supabase account with access to the project; browser sign-in alone is not project membership.

Regression commands:

```sh
simulation/perception_bridge/.venv/bin/python simulation/perception_bridge/tools/selftest.py
simulation/perception_bridge/.venv/bin/python simulation/perception_bridge/tools/quality_selftest.py
simulation/perception_bridge/.venv/bin/python simulation/perception_bridge/tools/hook_selftest.py
npx deno test edge-functions/_shared/detection_quality_test.ts
npx deno check --node-modules-dir=none edge-functions/identify-found-items/index.ts
```

Blank-frame and architectural negative controls, imported-backpack and laptop positive controls, a physical two-view backpack confirmation and one authenticated Supabase demo photo/listing insertion were tested. These are targeted regression controls, not a claim of perfect detection across all views. See the indoor project's `validation/perception_verification.json` for measured results.

For a local end-to-end demo without cloud deployment, use `simulation-indoors/Start Vision Demo.command`. It runs the patched Edge Function on loopback with `LOCAL_ONLY=1` (forced dry run), calls the real hosted Perceptron API, and starts the bridge, Webots and presentation. It requires the private bridge, Edge Function and UI `.env` files; do not commit them. The legacy `perception/run_service.py` and `tools/bridge_selftest.py` instructions do not apply to this repository version.

## Private item geotracking

Confirmed items now carry an **estimated item position**, triangulated from camera boxes and the rover's calibrated camera poses, rather than the rover's location alone. This is software geotagging; it does not attach a physical GPS tracker to an item.

The bridge persists item UUIDs, position anchors, reference crops, last-seen times and sighting counts under `state/geotracking/` (gitignored, private permissions). Restarting Webots or the bridge does not discard those anchors. Nearby items of the same type are compared by the real Perceptron model. A verified same-item match retains its UUID; a different item receives a new UUID. Uncertain/failed comparisons are deferred instead of creating a possible duplicate. Location or a matching color alone cannot identify a physical item.

The default site scope derives from mission name and geographic origin. Set `ITEM_TRACKING_SCOPE` to a stable site/floor ID when using separate indoor floors or coordinate maps. Estimated position accuracy defaults to 2 m and can be configured with `ITEM_POSITION_ACCURACY_M`; this is an assumed uncertainty, not a measured GPS specification. Do not share a scope between unrelated maps.

For live posting, deploy `ui/supabase/migrations/202610170004_item_geotracking.sql` and the updated `identify-found-items` function together. Exact positions live in service-role-only tables; public listing coordinates remain approximate. A repeated observation updates the existing listing's `last_seen_at` and `sighting_count`. A unique sighting ID makes retries idempotent. The database rejects a stale duplicate-check snapshot when another ingestion inserts a nearby item concurrently, requiring a fresh visual comparison before a new row is allowed. Available tracked items are checked beyond the old 24-hour window.

The bridge checks the endpoint's geotracking capability before live tracked posting. An old cloud function or missing migration cannot silently accept a tracked request as an ordinary new listing. Local Vision Demo remains forced dry-run and uses the durable local tracker without database writes. Webcam-only scans do not supply an item location: the existing zero-valued schema placeholders are never treated as an item geotag.

Additional checks:

```sh
simulation/perception_bridge/.venv/bin/python simulation/perception_bridge/tools/geotracker_selftest.py
npx deno test --node-modules-dir=none edge-functions/_shared/geotracking_test.ts
cd ui && npm test
```

A same-type sighting within one meter of an existing anchor that conflicts with its visual description is held for review. This prevents a black/brown lighting change or a front/back view from automatically producing another listing. Different object types can still coexist at the same location. A visually different same-type item farther away can receive its own track.
