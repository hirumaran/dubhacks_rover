# Real webcam · Campus Scout

Use a laptop or USB webcam with the same **real Perceptron Mk1.5** detector/description pipeline used by the rover. Webots is not required. This is sampled image analysis, not continuous video tracking. A regular webcam covers its own field of view, not 360°.

## Start

From the repository root, initialize the existing bridge environment if needed:

```sh
python3 -m venv simulation/perception_bridge/.venv
simulation/perception_bridge/.venv/bin/pip install -r simulation/perception_bridge/requirements.txt
simulation/perception_bridge/.venv/bin/python webcam/launch.py
```

Or double-click **Start Webcam.command**. Node/npm or Deno is required. The launcher reads `PERCEPTRON_API_KEY` and `ROVER_INGEST_SECRET` from the existing private `edge-functions/.env`. `ui/.env` is optional in this mode; its configuration only initializes the unused database client. Keys never reach the browser. No extra `perception/.env` is needed.

Open **http://127.0.0.1:8769/** in Chrome. Choose **Enable webcam**, allow camera access, and select the desired camera. The microphone remains off. Place an item with space around it so its full shape is visible, then choose **Scan this view**. **Start 5-second scans** repeats automatically; when inference takes longer, scans wait rather than piling up. **Pause scans** stops new requests; an existing request finishes. **Stop camera** releases the webcam. Background tabs pause automatic scanning. Ctrl+C in the launcher stops the local services.

The right panel shows the exact submitted frame and its boxes. The live preview can move independently. A second overlapping detection of the same type/color in consecutive scans gets a repeat-sighting label. It does not prove exact physical identity, ownership, or abandonment. No simulator labels, synthetic coordinates or fake detections are used to recognize items. Literal zero latitude/longitude values are sent only to satisfy the existing API schema; real location is never collected.

## Data flow

`Browser camera → local Python gateway :8769 → existing Edge Function on loopback :8001 → hosted Perceptron API`

The identifier is forced to dry-run, with no database reads, photo storage or Supabase listings. Photos are not written to disk by these services; up to 12 scan images remain in the browser tab’s memory until cleared/reloaded. Selected frames are transmitted to Perceptron for inference; this is not offline inference. Provider retention is governed by your Perceptron account. The demo requests neither microphone nor geolocation. The gateway serves only `presentation/`, checks same-origin requests and session tokens, and does not log camera contents. Keep `.env` files private.

## Checks

```sh
simulation/perception_bridge/.venv/bin/python -m unittest discover -s webcam/tests
node --test webcam/tests/tracker.test.mjs
npx deno check --node-modules-dir=none edge-functions/identify-found-items/index.ts
```

Camera image quality, lighting, occlusion, request latency and model errors affect results. The app does not infer reliable numerical confidence or claim that every visible object is lost property. Large scene-sized boxes are rejected by the shared model pipeline; move a close-up item farther from the lens if necessary.
