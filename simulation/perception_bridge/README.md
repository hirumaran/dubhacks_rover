# Perception bridge

Connects the Webots rover to the item-recognition backend. Every few seconds the rover saves
what its four cameras see; this service decides which of those images are worth looking at and
sends them to the `identify-found-items` edge function, which uses Perceptron Mk1.5 to find,
describe and list lost items in Supabase (`found_items`).

Only what a real rover could sense goes in: camera pixels and the rover's own GPS and compass
pose. Simulator ground truth (Webots Recognition objects) is not exported.

```
controllers/campus_rover/perception_hook.py      every 5 s: frame_<seq>_c<i>.png + frame_<seq>.json (GPS, heading)
        │  inbox/
        ▼
run_bridge.py
  change_gate.py   send a camera's image only if the rover moved ≥2 m, that camera turned ≥20°,
                   or the picture changed (64-bit image hash); otherwise skip it
  pose.py          rover GPS (sim metres) → latitude/longitude, per-camera facing
  uploader.py      POST to identify-found-items, one at a time; offline queue in state/outbox/
        │
        ▼
edge-functions/identify-found-items   Perceptron Detect → describe each crop → skip items already
                                      listed nearby (Perceptron same-object check) → found_items
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

## Notes

- **Cost.** Each image that passes the gate costs one Perceptron Detect call, one describe call
  per item found, and one comparison per similar listing nearby. Raise `MOVE_MIN_M` to send less.
- **Location.** Listings use the rover's position, not each item's. Items are within a few
  metres of the rover, and matching treats anything under 600 m as nearby.
- **Duplicates.** The server compares each new item with available listings of the same
  category within ~150 m from the last 24 h and skips it if Perceptron rates it the same object.
  Requests are sent one at a time so two cameras can't list the same item at once.
- The rover's own photo gallery (`campus_rover.py`) still uses Webots Recognition; it is a
  separate showcase feature and does not feed Supabase.
