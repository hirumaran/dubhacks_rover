# QR kiosk + rover geolocation + fleet dispatch (for teammates and their agents)

This is the student-facing half of perception: **a printable QR on a desk opens
a phone form; the report lands in the cloud; the closest live rover is
assigned; local Isaac-0.2-1B hunts for that description on the next camera
ticks; the phone polls until the item is matched.**

Everything here is already implemented and tested end-to-end in dry-run. Read
`WALKTHROUGH.md` first if you are cold on Isaac / inbox / sightings.

---

## 0. What a student actually does

1. Librarian / UWPD tapes a PNG from `kiosk/qr/` on a desk.
2. Student scans it. Phone opens `{PUBLIC_APP_URL}/?station=gates-atrium`
   (mobile form in `kiosk/index.html`, served by `tools/serve_kiosk.py`).
3. They type "green hydroflask, dented lid" and/or take a photo.
4. Report lands in Supabase `lost_items`, photo in bucket `lost-item-queries`
   (dry-run: `reports/lost_reports.jsonl` + local file).
5. `dispatch.py` assigns the **nearest live rover** (heartbeat fresher than
   `HEARTBEAT_STALE_S`). The pick and reason are saved on the row.
6. That rover's `state/missions.json` gains the mission; `run_service.py`
   feeds the student text into Isaac as a **hunt-priority prompt** each tick.
7. The phone polls `/api/status?id=…` every 5 s. Status goes
   `assigned → hunting → matched`; when matched, the page shows
   `match_reason` ("found near x=…, y=…, area …").
8. If the item was already seen before the report, the match fires *at submit
   time* (immediate match) and the page never needs to poll.

**Isaac vs Mk.1.5 (do not confuse these):**

| piece | where it runs | role |
|---|---|---|
| **Isaac-0.2-1B** | on the rover (this folder) | detect / describe / hunt a student query via `HUNT_SUFFIX` |
| **Supabase** | cloud | bus: sightings, lost_items, rover heartbeats, kiosk_stations |
| **Perceptron Mk.1.5** | cloud API only | **not on the rover.** `ISAAC_BACKEND` stays `transformers｜sdk｜mock`; Mk.1.5 is a possible future cloud matcher, never a local load |

Hybrid = edge VLM + cloud tables. The phone never talks to Isaac. Isaac never
talks to the phone.

---

## 1. Files added / touched

| path | role | who may edit |
|---|---|---|
| `kiosk/stations.json` | desk list (id, name, lat, lon) — **source of truth for QRs** | anyone adding a building |
| `kiosk/index.html` + `kiosk.css` | phone form + status polling | web-branch teammates can restyle; keep `/api/report` fields and `/api/status` contract |
| `kiosk/qr/*.png` + `qr/print.html` | **print these** (6 desks, LAN URL baked) | regenerate with `make_qr.py` when the URL changes |
| `kiosk/qr/manifest.json` | which base_url the PNGs encode | generated |
| `tools/make_qr.py` | QR card renderer (`--lan` detects this machine's Wi-Fi IP) | — |
| `tools/serve_kiosk.py` | phone HTTP form, `POST /api/report`, `GET /api/status`, `/health` | — |
| `tools/rover_locate.py` | print rover lat/lon from last pose (or `--fake-xy`) | debug |
| `tools/dispatch_selftest.py` | geo + closest-rover + stale gate + QR URL test | CI/demo |
| `rover_geo.py` | haversine, live-rover filter, `closest_rover`, `pose_to_geo` | math only |
| `dispatch.py` | heartbeat upsert, assign, stale reclaim, mission reconcile, report status | bus |
| `geotag.py` | `world_xy_to_wgs84` / `wgs84_to_world_xy` / `load_origin` + object geotags | keep origin in sync with mission.json |
| `run_service.py` | heartbeat each tick; poll dispatch every 5 s; pass `hunt_query` into Isaac | — |
| `isaac_detector.py` | `user_prompt(hunt_query)` = `USER_PROMPT` + optional `HUNT_SUFFIX` | — |
| `match_agent.py` | query-side scoring; synonym recall; threshold `MATCH_MIN_SCORE` | web branch reads it too |
| `supabase/schema.sql` | full schema incl. section 6 (rovers, kiosk_stations, extra columns) | paste-once |
| `supabase/schema_dispatch.sql` | **same block** for projects that already ran the old schema | paste-once |
| `config.py` / `.env.example` | `ROVER_ID`, `PUBLIC_APP_URL`, `MATCH_MIN_SCORE`, `PERCEPTION_*_DIR` | per machine |

Do **not** put service-role keys in `kiosk/index.html`. The kiosk server
uploads with the service key; the phone only POSTs to our origin.

### Test isolation (new)

`config.py` honors `PERCEPTION_INBOX_DIR`, `PERCEPTION_STATE_DIR`,
`PERCEPTION_REPORTS_DIR`. `tools/bridge_selftest.py` uses throwaway temp dirs,
so it never touches real `inbox/`, `state/`, `reports/` and cannot fail from
stale `state/tracks.json` (it used to — run it twice to confirm it is now
re-runnable). Use the same vars to run a second stack on one machine.

---

## 2. Data contract (agents: do not rename these)

### QR payload (the only thing printed)

```
{PUBLIC_APP_URL}/?station={station_id}
```

`station_id` must exist in `kiosk/stations.json` (and, after SQL, table
`kiosk_stations`). The committed cards encode
`http://172.16.0.2:8787/?station=…` (this machine's LAN IP at generation
time). **If `PUBLIC_APP_URL` or the LAN changes, the paper QRs are wrong until
you regenerate and reprint.**

### `POST /api/report` (multipart)

| field | required | notes |
|---|---|---|
| `query_text` | yes unless photo | student description |
| `photo` | no | image/*; stored in `lost-item-queries` |
| `created_by` | no | email/phone, stored as text |
| `station_id` | yes (from QR) | looks up lat/lon in `stations.json` |

Response JSON: `{id, status, assigned_rover_id, dispatch_reason, match_reason?, station_id, distance_m}`.
`status` starts as `assigned` (or `matched` when an immediate match fired).

### `GET /api/status?id={report_id}` (new)

Response: `{id, status, assigned_rover_id, station_id, match_reason,
matched_object_id, distance_m, updated_at}`. 404 for unknown ids.
The form polls this every 5 s for ~6 minutes after submit.

### `lost_items` status enum

`open → assigned → hunting → matched → resolved`

- `assigned` set at ingest by `Dispatch.assign_open`
- `hunting` set by `Dispatch.reconcile_matches` once the owning rover picks it up
- `matched` set by `_try_immediate_match` (at ingest) or `reconcile_matches`
  (during patrol), together with `matched_object_id`, `match_confidence`,
  `match_reason` (human sentence with location + confidence)
- `resolved` is the web branch's job (student confirms pickup)

### `rovers` row (heartbeat, every perception tick)

```json
{
  "id": "mk1",
  "display_name": "Campus Scout MK1",
  "lat": 47.6533, "lon": -122.3051,
  "x": 14.54, "y": -153.02,
  "heading_rad": 1.23,
  "status": "patrol" | "hunting",
  "sim_time_s": 51.2,
  "last_seen_at": "2026-10-17T23:01:00+00:00",
  "meta": {"origin": [47.65865, -122.3074]}
}
```

Local mirror (always, even dry-run): `state/rover_pose.json` (identical row).
Webots GPS is ENU meters; lat/lon uses `simulation/maps/mission.json`
`reference_lat_lon` via `geotag.world_xy_to_wgs84` (same affine map as object
geotags). `tools/rover_locate.py` prints this row.

### Local mission file (Isaac's inbox for hunts)

`state/missions.json` — gitignored, written by dispatch:

```json
{
  "rover_id": "mk1",
  "updated_utc": "…",
  "missions": [ { "id": "…", "query_text": "green hydroflask", "station_id": "gates-atrium" } ]
}
```

---

## 3. Fleet rules (the scale-up lever)

**Single rover today, fleet tomorrow — same code path.**
With one rover (`mk1`, the default) every rule below collapses to "assign to
mk1": `closest_rover` just returns the only live rover, and if no heartbeat
exists yet the fallback parks the job on this process. Nothing extra to
configure. When you add rover #2, the *same* functions start choosing for
real — no scheduler service, no per-rover queues, no schema change. The loose
threads are deliberately: machine identity (`ROVER_ID`), heartbeat freshness
(`HEARTBEAT_STALE_S`), and the one selection function (`closest_rover`).

```
live     = heartbeat younger than HEARTBEAT_STALE_S (default 45 s)
pick     = argmin haversine(station_lat/lon, rover_lat/lon) among live
fallback = first known rover, else this process's ROVER_ID (solo demo works)
reclaim  = a report assigned to a rover that is NOT live gets re-assigned
           on the next dispatch poll (crashed rover never holds a job)
```

Added behaviors (all in `dispatch.py`):

- **`reclaim_unassigned()`** now also frees reports from stale rovers, not
  just reports with no rover. It only logs when the assignment actually
  changes.
- **`reconcile_matches()`** (cloud-only, runs every 5 s from `run_service`):
  - flips my `open/assigned` missions to `hunting`
  - for each `hunting` mission, runs `match_agent.find_matches`; if the
    best candidate scores ≥ `MATCH_MIN_SCORE` **and its sighting is newer
    than `assigned_at`** (i.e. found during this hunt, not an older sighting),
    the report flips to `matched` with a human `match_reason`.
- Dry-run now persists assignment fields back into
  `reports/lost_reports.jsonl`, so `missions_for_me` and `/api/status` behave
  the same as cloud mode.

**To add rover #2:** clone the stack, set `ROVER_ID=mk2` (and a unique
display name and `PERCEPTION_*_DIR`s if on one machine) in that machine's
`perception/.env`. Same Supabase project. Do not share `state/`. Dispatch
starts choosing. Until then, leave these threads alone — do not add a
scheduler, a queue, or fleet tables; there is intentionally nothing more to
build for one rover.

Changing the rule (indoor floor, building id, battery): edit
`rover_geo.closest_rover` only. Keep the function signature.

### Matching gate (why "hydroflask" finds a "bottle")

`match_agent.find_matches`:
- gate = label in the query **or** token overlap > 25% **or** a synonym hit
- `QUERY_SYNONYMS` expands campus slang (`hydroflask→bottle/flask/water`,
  `airpods→earbuds/buds`, `macbook→laptop`, …). Add entries freely.
- score = `0.5*overlap + 0.2*label + 0.1*color + 0.15*synonym + 0.2*recency`,
  capped at 1.0. Reports auto-match only at `MATCH_MIN_SCORE` (default 0.3).
- Fixed a real bug here: the old gate `label in tokens` was always true, so
  *any* recent sighting could become the top "match". If the web branch has
  old code copying that logic, this is the corrected version.

---

## 4. What to run (human checklist)

### First time / existing Supabase project

1. If `schema.sql` was **never** applied: paste all of `supabase/schema.sql`.
2. If it **was** applied before this QR work: paste `supabase/schema_dispatch.sql`.
3. `cp .env.example .env` and fill keys. Set `ROVER_ID=mk1`.
4. Set `PUBLIC_APP_URL` to the URL phones will actually open, **or** skip this
   and use `--lan` below.
5. Generate print cards (LAN mode detects this machine's Wi-Fi IP):

```bash
cd perception
.venv/bin/pip install -r requirements.txt
.venv/bin/python tools/make_qr.py --lan        # http://<this-LAN-IP>:8787/…
# or for a real deploy:  --url https://your-host
# open kiosk/qr/print.html → Print button. Tape kiosk/qr/<station>.png on desks.
```

6. Terminal A — rover brain (heartbeat + hunts + reconcile):

```bash
.venv/bin/python run_service.py
```

7. Terminal B — phone form (serves QRs from `/qr/` too):

```bash
.venv/bin/python tools/serve_kiosk.py
```

8. Terminal C — Webots with the existing bridge:

```bash
export PERCEPTION_INBOX="/absolute/path/to/perception/inbox"
# then Start Rover.command / the .wbt
```

9. Scan a QR (or open `http://<this-LAN-IP>:8787/?station=gates-atrium`),
   submit a description. Watch `[dispatch] … -> mk1`, then `[service]` hunt
   ticks; the page flips to "Found it!" when a sighting matches. Confirm rows
   in Supabase `lost_items` + `rovers`.

### Zero-cloud / zero-Webots checks (all pass today, no GPU needed)

```bash
python tools/dispatch_selftest.py    # geo, closest rover, stale gate, reconcile gate, synonyms, QR URL
python tools/bridge_selftest.py      # synthetic Webots tick; re-runnable
python tools/rover_locate.py --fake-xy 14.5 -153.0
python tools/make_qr.py --url http://localhost:8787
```

Dry-run kiosk loop (no keys needed):

```bash
python tools/serve_kiosk.py &
curl -F "query_text=green hydroflask" -F "station_id=gates-atrium" localhost:8787/api/report
# -> {"id":"local-…","status":"assigned","assigned_rover_id":"mk1",…}
curl "localhost:8787/api/status?id=local-…"     # same row
cat state/missions.json                          # the mission Isaac will hunt
```

---

## 5. How to change things (agent cookbook)

**Add a desk**
1. Append an object to `kiosk/stations.json` (`id` slug, `name`, `lat`, `lon`).
2. Re-run `schema_dispatch.sql` insert (or add a row in table `kiosk_stations`).
3. `python tools/make_qr.py --station that-id --url $PUBLIC_APP_URL` (or `--lan`)
4. Print `kiosk/qr/that-id.png`.

**Change the public URL**
1. `PUBLIC_APP_URL` in `.env` (or use `--lan`).
2. `python tools/make_qr.py --url …` or `--lan` and **reprint**. Old paper QRs
   will 404 or hit the wrong host. There is no redirect magic.

**Point QRs at the `rishi_dev` web app instead of `serve_kiosk.py`**
Keep the contract: `/?station={id}`, POST the same fields to your `/api/report`,
and expose `GET /api/status?id=` (or call `Dispatch().ingest_report({...})` /
`log_lost_item(..., station_id=...)`). Do not invent a second lost-items table.

**Add a rover to the fleet**
New machine, same repo, unique `ROVER_ID`, same Supabase URL/keys, own
`PERCEPTION_INBOX`/state dirs. Heartbeats upsert on primary key `rovers.id`.
Stale rovers are ignored and their reports reclaimed automatically.

**Retune "live"**
`HEARTBEAT_STALE_S` in `.env`. Too small: all rovers look offline during a
slow Isaac tick. Too large: a wedged rover keeps getting jobs.

**Hunt quality**
`isaac_detector.HUNT_SUFFIX` is the only prompt knob. Do not bake student
text into `SYSTEM_PROMPT` (that persists across missions). `hunt_query` is
per-tick from `state/missions.json`.

**Match strictness**
`MATCH_MIN_SCORE` (0..1). Raise it if false matches annoy; lower it if the
demo item never flips to matched. Synonym lists in `match_agent.QUERY_SYNONYMS`.

**Geotag origin drift**
If `simulation/maps/mission.json` `reference_lat_lon` changes, object geotags
AND rover heartbeats move together (`geotag.load_origin`). Re-check with
`python tools/rover_locate.py --fake-xy 0 0` (must print that origin).

**Run tests without touching real runtime data**
Set `PERCEPTION_INBOX_DIR` / `PERCEPTION_STATE_DIR` / `PERCEPTION_REPORTS_DIR`
(bridge selftest already does).

**Do not**
- Put `SUPABASE_SERVICE_KEY` in the phone page or QR.
- Call Isaac from the kiosk process.
- Import `perception_hook.py` from the kiosk (stdlib rover controller).
- Treat Mk.1.5 as an on-rover backend (`ISAAC_BACKEND` stays
  transformers/sdk/mock).
- Trust a LAN IP baked into old QR PNGs after changing networks.

---

## 6. Pipeline diagram

```
desk QR  →  phone kiosk (/?station=)
              │  POST /api/report  (text + optional photo)
              ▼
         dispatch.ingest_report
              │  insert lost_items (status=open)
              │  closest_rover(station, live heartbeats)
              │  immediate match? (score ≥ MATCH_MIN_SCORE) → status=matched
              ▼
         assigned_rover_id = mkN   (status=assigned)
              │
     ┌────────┴──────────┐
     ▼                   ▼
Supabase lost_items   state/missions.json  (that rover only)
     │                   │
     │                   ▼
     │             run_service tick
     │               heartbeat → rovers + state/rover_pose.json
     │               Isaac detect(..., hunt_query=student text)
     │               geotag + tracker + sightings  (existing)
     │
     │  every 5 s: dispatch poll
     │    reclaim_unassigned   (stale rover → reassign)
     │    reconcile_matches    (assigned → hunting; new sighting → matched)
     ▼
phone polls /api/status  ←──── lost_items.status / match_reason
```

Webots GPS path (unchanged, now also published as WGS84):

```
campus_rover GPS/compass
  → perception_hook frame_<seq>.json  {gps, heading_rad}
  → run_service RoverPose
  → rover_geo.pose_to_geo  {lat, lon, x, y}
  → rovers upsert + state/rover_pose.json
```

---

## 7. Verification evidence (run 2026-10-17, no GPU, no cloud)

```
$ python tools/dispatch_selftest.py
[selftest] PASS origin, haversine, closest-rover, stale gate, reconcile gate, synonyms, QR URL
  gates_assigned=mk1   odegaard_assigned=mk2   ghost(stale) ignored
  sample_qr=https://scout.example.edu/?station=gates-atrium

$ python tools/bridge_selftest.py      # run twice → PASS twice (hermetic)
[event] new OBJ-… bottle @ (6.10, -1.33) range 2.0m conf 0.99
[selftest] PASS

$ python tools/rover_locate.py --fake-xy 14.5 -153.0
{"x": 14.5, "y": -153.0, "lat": 47.6572663, "lon": -122.3072066}   # WGS84 on mission origin

$ python tools/serve_kiosk.py & curl -F "query_text=green hydroflask, dented lid" \
      -F station_id=gates-atrium localhost:8787/api/report
{"id":"local-…","status":"assigned","assigned_rover_id":"mk1",
 "dispatch_reason":"closest live rover mk1 (solo/fallback)"}

$ curl "localhost:8787/api/status?id=local-…"
{"status":"assigned","assigned_rover_id":"mk1","station_id":"gates-atrium", …}

$ cat state/missions.json
{"rover_id":"mk1","missions":[{"query_text":"green hydroflask, dented lid", "station_id":"gates-atrium", …}]}

$ python tools/make_qr.py --lan
wrote kiosk/qr/gates-atrium.png -> http://172.16.0.2:8787/?station=gates-atrium   (×6 desks + print.html)
```

Not yet verified on real hardware: Isaac generation on MPS with the hunt
suffix (needs the teammate's machine with weights), Webots GPS live heartbeat,
and Supabase live upsert/update (needs `.env` + service key).

---

## 8. Troubleshooting

| symptom | cause / fix |
|---|---|
| Phone says "can't reach site" | QR encodes the old URL. `make_qr.py --lan` (or `--url`), reprint, and make sure the phone is on the same Wi-Fi and the kiosk machine's firewall allows port 8787. |
| `dispatch_reason` ends in "(solo/fallback)" | No fresh heartbeat from any rover. Start `run_service.py` (it heartbeats every tick) or check `last_seen_at` in `rovers`. |
| Report stays `assigned`, never `hunting` | `reconcile_matches` needs cloud mode + the report assigned to THIS rover. Check `state/missions.json` exists and `.env` has valid keys. |
| Report stays `hunting`, never `matched` | Rover hasn't sighted a matching object yet; or score < `MATCH_MIN_SCORE`; or the sighting is older than `assigned_at` (by design). Lower the threshold or add a synonym. |
| Report instantly matches something wrong | Raise `MATCH_MIN_SCORE`; check `QUERY_SYNONYMS` isn't too loose. |
| `rover_pose.json` never updates | `run_service.py` isn't processing ticks (no Webots frames in `inbox/`), or `PERCEPTION_STATE_DIR` points elsewhere. |
| Updates silently don't stick in Supabase | You're using the anon key. Dispatch writes (`upsert rovers`, `update lost_items`) need `SUPABASE_SERVICE_KEY` — rover-side only. |
| QR print sheet prints one card per page | Use the "Print" button in `print.html`; ensure background graphics on. Cards are ~506×666 px. |
| `bridge_selftest` says FAIL | Should not happen anymore (hermetic). If it does, capture the `[event]` lines and the last `[selftest]`: it means tracking/geotag broke, not state pollution. |

---

## 9. Known limitations / next steps

- The uploaded `query_image_url` is stored but not yet compared to sightings
  (Isaac hunts the text; the photo helps a human rescuer later). Future:
  pgvector embedding column (schema.sql §2 comment) or a Mk.1.5 cloud compare.
- One location per camera frame; two items in one frame share coordinates.
- `open → resolved` (student confirms pickup) is the web branch's UI flow.
- `state/missions.json` holds all my open missions; `hunt_query` joins them
  with `; `. If reports pile up, oldest-first triage can be added in
  `missions_for_me`.
