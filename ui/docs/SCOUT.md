# Scout: phone recognition and rover feed

Scout runs in Expo Go with the existing SDK **57.0.0** runtime (`expo ~57.0.30`). It uses the SDK 57 versions of `expo-camera` and `expo-image-manipulator`; no custom native build is required.

## Start on Windows

1. Put your team's `PERCEPTRON_API_KEY` and `ROVER_INGEST_SECRET` in the ignored repository file `edge-functions/.env`. These are server credentials: never add them to `ui/.env` or any `EXPO_PUBLIC_` variable. The ingest secret can be a new random value for this isolated local demo; the launcher passes it to both local services.
2. Install Python 3, then run `python -m pip install Pillow` if needed. Node/npm is already installed with the app; the launcher uses Deno or downloads its pinned Deno runtime through npx on first use.
3. In PowerShell:

   ```powershell
   cd D:\GitHub\dubhacks_rover\ui
   npm run scout:gateway
   ```

4. Leave it running. In another PowerShell terminal:

   ```powershell
   cd D:\GitHub\dubhacks_rover\ui
   npm run start:tunnel
   ```

5. The gateway opens the laptop camera page at `http://127.0.0.1:8769/`. Click **Enable webcam** on the laptop and allow camera access. Its preview is shared with the paired app automatically; use Stop sharing preview to stop sharing.
6. Open the app from the **new Expo QR code**, sign in or choose Explore Demo, then open **Scout**. Paste the single **SCOUT PAIRING CODE** printed by the gateway. The app discovers the Expo host and routes its camera API requests through that same connection. **Live feed → Laptop webcam** is selected initially. Choose **Phone camera** to use your phone instead, or **Rover** when a rover vision demo is running.

The Expo tunnel now carries both the app and the allowlisted Scout API routes through Metro's gateway proxy. No laptop IP selection, separate gateway tunnel, same-Wi-Fi requirement, or Python firewall opening is needed with `start:tunnel`. Python stays bound to loopback. **Restart Expo after updating** so its new Metro middleware loads. Both commands must run on the same computer. A stopped gateway returns a specific 503 message instead of a generic network timeout. The temporary pairing code grants camera/model access; share it only with your test devices. Restart the gateway to revoke it. Privileged Perceptron/ingest keys never reach the phone. The pairing token stays in app memory.

## Phone camera

Choose **Phone camera → Enable camera**, allow camera permission, then **Scan this view** or **Start 5-second scans**. Preview stays live; the exact submitted image and normalized detection boxes appear below. Scans run sequentially with a five-second pause after each completed response, so slow inference never queues more captures. Pause finishes the current scan; Stop cancels the local request and releases the camera. Leaving Scout or backgrounding the app also releases the camera. A server request already being processed may finish even if the phone cancels it.

Front/back switching resets repeat tracking. History retains at most 12 analyzed frames in memory and can be cleared. Native capture/cache files are removed after each request. The microphone and GPS are not requested. Selected frames reach the real hosted Perceptron API through the computer; the gateway forces dry-run and never creates Supabase listings. A repeat label only means overlapping detections of the same kind/color in consecutive scans, not physical identity or abandonment.

## Computer webcam on your phone

Open `http://127.0.0.1:8769/` on the computer and click **Enable webcam**. In mobile gateway mode that explicit camera action also starts preview sharing. In Scout choose **Live feed → Laptop webcam**. Sharing publishes compact 640×480 JPEG previews up to four times per second; the phone requests the next preview 250 ms after the previous response finishes. Network latency and browser throttling determine the actual rate. The visible **Laptop preview · frame** counter advances with new published frames. Upload interruptions retry automatically, and switching away from the laptop tab does not intentionally stop sharing. Keep the laptop awake with its camera page open. No model calls happen until you select Analyze this feed frame or automatic scans. Stop sharing/camera to remove the shared frame. Frames older than ten seconds are labeled offline. Camera permission is always requested on the computer; pairing a phone cannot bypass it.

Select **Start 5-second scans** on the phone to analyze the current laptop/rover frames automatically. Each completed response is followed by a five-second pause; incoming preview frames do not reset the scan timer. If you run scans on the laptop's browser page instead, the phone also displays that page's exact analyzed snapshot and boxes under **Latest laptop analysis**, while its separate live preview continues moving. Stopping laptop sharing clears both the shared preview and cached laptop analysis.

## Rover feed

Start the existing **rover vision demo** on the computer using `simulation-indoors/Start Vision Demo.command` (macOS) or your team's Webots/bridge setup. The bridge must publish its actual model frames with `PERCEPTION_PUBLIC_DIR` set. The gateway automatically reads the newest `perception.json` from either `simulation-indoors/presentation/data` or `simulation/indoor_showcase/presentation/data`. For another bridge output directory, set the same `PERCEPTION_PUBLIC_DIR` in the gateway terminal before starting it.

In Scout choose **Live feed → Rover**. This is a sampled image feed of real published rover camera frames, commonly every five seconds, with the model's boxes and camera ID. It is not an RTSP/video stream. The gateway re-encodes only the image and whitelisted recognition fields, not simulator poses or ground-truth labels. Unchanged frames older than thirty seconds are marked stale/offline, with the last capture time visible. No running rover means no live feed. The existing bridge's Supabase found-item inserts still flow to Discover/Activity through their existing realtime integration; Scout phone scans remain dry-run.

## Validation

```powershell
python -m unittest discover -s webcam/tests
node --test webcam/tests/tracker.test.mjs
cd ui
npm run typecheck
npm test
npm run doctor
npm run export:native
```

For the isolated browser regression, start Metro on localhost port 8082, then set `$env:HUSKYFIND_SCOUT_SMOKE='1'` and run `npm run smoke:browser`. It uses Chromium's synthetic camera and a clearly separated offline model fixture, exercising the production gateway and UI without provider credentials/cost. It does not validate actual model accuracy or physical iPhone/Android permissions/networking. The anonymous Supabase test account is deleted after testing.
