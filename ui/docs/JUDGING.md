# HuskyFind judging demo

**Permanent app:** https://huskyfind-uw.expo.app

**One QR:** https://huskyfind-uw.expo.app/judging-qr.png

This hosted app opens in a phone or laptop browser without Expo Go, a developer account, Metro, or a shared Wi-Fi network. The native project remains Expo SDK **57.0.0**. Use the hosted QR for judges; the Expo Go development QR is separate.

## Three-minute walkthrough

1. Open the app and choose **Explore Demo**. This creates an isolated anonymous account; its reports, photos, claims and plans are private to that account.
2. Open **Report**, choose a photo of the missing item, or choose **Try backpack photo** from the supplied campus examples. A real Supabase Edge Function calls Perceptron and fills the item name, category, dominant color and visible description. Review and edit its suggestions.
3. Continue, choose the last-seen UW location and time, then choose **Start my search**. The cloud saves the report and picks the closest available demo rover. Show the assignment reason, approximate distance, visual search brief, and candidate matching weights.
4. Open **Activity** for potential matches and the saved rover plan. **Compare item appearance with AI** calls the deployed comparison function and explains visible agreements/differences. It does not verify ownership.
5. On a laptop, resize the browser to show the responsive grid and centered report form. On a phone, show photo capture/upload and the same saved records after refreshing.

The supplied ZIP photos have been converted from HEIC to compact JPEGs with image metadata removed. Demo listing descriptions and their server-side reference photos are aligned. No real student listings were replaced.

## Keep the same QR when updating

From `ui/`:

```powershell
npm run publish:judging
```

This generates the same QR, exports the app, and promotes the new deployment to **the same production URL**. Judges refresh the page to load UI changes. Supabase data/realtime changes flow into the app without redeploying. Local edits need this publish command before judges see them. The pinned EAS CLI runs through npx using the project's Node 24 wrapper. Windows EAS settings stay in the ignored `.expo/eas-config` directory; the CLI still uses your existing Expo login.

The Expo project is `@alagud/huskyfind`, ID `d817ed9d-7e58-4242-b262-f643998bf60a`. The deployment dashboard is https://expo.dev/accounts/alagud/projects/huskyfind/hosting.

## Optional live camera demonstration

The photo/report/assignment demo works entirely in the cloud. A live camera still needs an operator publishing actual frames.

On the operator laptop, from `ui/`:

```powershell
npm run configure:cloud
npm run scout:gateway
```

The first command requires the operator's existing Supabase CLI login and stores only the project's public legacy anon JWT in the ignored gateway runtime directory; it never stores a service-role key. Private Perceptron and ingestion credentials stay in `edge-functions/.env`.

On the laptop camera page, choose **Enable webcam**, then explicitly choose **Share with judging link**. Judges open **Scout → Live feed → Laptop webcam** on the permanent app. No pairing code is needed in the hosted build. The native development build retains its paired local/tunnel flow.

The cloud relay holds only the latest consented preview for each source. Read policies hide frames more than 15 seconds old. Stop judging-link sharing to clear them. A short heartbeat lease stops publishing if the laptop page closes. The browser-camera preview is sampled; hosted cloud preview is approximately one frame per second, subject to network latency. Camera inference is manual or runs sequentially after selecting automatic scans.

For a rover feed, run the existing Webots vision demo with its `PERCEPTION_PUBLIC_DIR` configured. The same explicit sharing control relays its actual published frames. A stopped rover produces an offline indicator. No prerecorded feed is presented as live.

## What the assignment means

Anonymous demo accounts use three labeled virtual fleet entries near Red Square, the Quad and the HUB. Assignment is a real, persisted cloud record with deterministic closest-rover selection. It is **simulated dispatch**, not a command that starts a physical rover. Real-account planning considers only non-demo rovers with a recent heartbeat and no active assignment; otherwise it queues the request. Straight-line distance is an estimate, not a navigation route. Physical execution still needs a rover controller to acknowledge and execute the plan.

Candidate matching uses category 35, color 20, nearby location 20, description 15 and time 10 points. The separate model comparison evaluates actual reference photos and visible details. Neither score proves ownership.

## Validation

```powershell
npm run typecheck
npm test
npm run doctor
npm run check:judging
npm run export:native
$env:HUSKYFIND_TEST_URL='https://huskyfind-uw.expo.app'
$env:HUSKYFIND_JUDGING_SMOKE='1'
npm run smoke:browser
```

The judging checks use temporary anonymous accounts, invoke the real hosted model, test report/rover planning and operator feed authentication, and clean up their photos/accounts. Browser checks exercise a real file upload and phone/desktop layouts. Physical-device testing remains a separate final check on the devices at the judging table.

Location privacy: public discovery pins and object GPS are hidden. Database column permissions block client reads of discovery coordinates; server matching and rover planning retain coordinates. My areas shows only the signed-in account reports under RLS.

Final readiness checks: hosted claims and listing corrections use cross-platform confirmation dialogs. Web sharing opens a selectable permanent item URL with a clipboard fallback. Browser push setup is hidden; in-app notifications remain available. Public discovery listings refresh every 15 seconds without broadcasting hidden object coordinates.
