# Demo: the rover finds a lost item and the app reports it

A student reports a lost item in HuskyFind, the simulated rover patrols the UW Quad, Perceptron
spots items left on benches in its camera images, they're listed as found, and the app shows a
match for the student's report.

```
Webots rover ──camera frames + GPS──▶ perception_bridge ──▶ identify-found-items (Perceptron Mk1.5)
                                                                      │ found_items (is_demo = true)
HuskyFind app ◀── Strong match / Rover found ◀── Supabase matching trigger
```

## One-time setup

- Webots R2025a in `/Applications`, Python 3 with Pillow (`pip install pillow`), and Node via the app's own runtime.
- `cd ui && npm ci`, then copy `ui/.env.example` to `ui/.env` with the project URL and publishable key.
- `simulation/perception_bridge/.env` needs `ROVER_INGEST_SECRET` (same value as `edge-functions/.env`)
  and `ROVER_ID` (the `rovers` row "CampusScout (simulator)"). See `simulation/perception_bridge/README.md`.

## Run it (about 8 minutes)

1. **App.** `cd ui && npm run start:web`, open <http://localhost:8081>, click **Explore Demo**.
2. **Report something the rover will find.** Report tab: name `Yellow rubber duck`, category **Other**,
   color `Yellow`, any description, location **Suzzallo Library**, keep the default time (now).
   Click **Start my search**. (The benches also have books, a water bottle and soccer balls, depending
   on the layout in `simulation/maps/lost_items.json`.)
3. **Bridge** (terminal 1, repo root):
   ```bash
   python3 simulation/perception_bridge/run_bridge.py
   ```
4. **Rover** (terminal 2, repo root). Run the launcher with `zsh`, not `open`, so Webots sees the variable:
   ```bash
   PERCEPTION_INBOX="$PWD/simulation/perception_bridge/inbox" zsh "simulation/Start Rover.command"
   ```
   Keep Webots at real-time speed. Fast-forwarding outruns the detector and it skips benches.
5. **Watch.** Terminal 1 prints `listed Yellow rubber duck` and similar. In the app, Discover shows the
   finds as **Rover found · DEMO LISTING** with the rover's own photo, and **Activity** shows
   **Strong match … For your Yellow rubber duck** with the reasons.
6. One lap of the Quad is about 6 minutes. Then close Webots and press Ctrl-C in terminal 1.

To try it without creating listings, set `DRY_RUN=true` for the bridge (it prints `would list …`).

## Indoor version (Gates atrium)

```bash
PERCEPTION_MISSION=simulation/indoor_showcase/maps/mission.json LOCATION_LABEL="Gates Center atrium" \
  MOVE_MIN_M=1.0 python3 simulation/perception_bridge/run_bridge.py
PERCEPTION_INBOX="$PWD/simulation/perception_bridge/inbox" \
  /Applications/Webots.app/Contents/MacOS/webots --mode=realtime simulation/indoor_showcase/worlds/gates_atrium.wbt
```

## Things to know

- Rover listings are `is_demo = true`: only demo accounts see them, never real students.
- Each run adds listings. The duplicate check skips items already listed nearby, but it is imperfect:
  expect the occasional duplicate, or a vague "rectangular object", especially for the green book.
- New item layout: `python3 simulation/tools/apply_bench_props.py --seed <n>` (campus).
- Scoring a run against the layout file is described in `simulation/perception_bridge/README.md`.
