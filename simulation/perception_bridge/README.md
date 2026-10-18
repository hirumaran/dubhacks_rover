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
| `uploader.py` | Requests to the edge function, offline retry |
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
That file is ground truth for scoring a run, never an input to the pipeline. Results from one lap with
seed 2026: campus 7/7 items found (6 named correctly, 1 false find); indoor 4/4 (2 false finds).

## Notes

- **Cost.** Each image that passes the gate costs one Perceptron call per detection tile, one
  describe call per item found, and one comparison per similar listing nearby. Raise `MOVE_MIN_M`
  to send less.
- **Speed.** A sim running faster than real time outpaces the detector; with `SKIP_STALE=true` the
  bridge then skips views and can miss benches. Run in real time, or set `SKIP_STALE=false`.
- **Location.** Listings use the rover's position, not each item's. Items are within a few
  metres of the rover, and matching treats anything under 600 m as nearby.
- **Duplicates.** The server compares each new item with available listings of the same
  category within ~150 m from the last 24 h and skips it if Perceptron rates it the same object.
  Requests are sent one at a time so two cameras can't list the same item at once.
- The rover's own photo gallery (`campus_rover.py`) still uses Webots Recognition; it is a
  separate showcase feature and does not feed Supabase.
