# Testing HuskyFind on iPhone and Android

## Start the app

The app targets the SDK 57.0.0 runtime (using maintained Expo 57 patch releases) to match the SDK 57 Expo Go client. All npm scripts launch the included project-local Node 24.19 executable, even if the computer's global `node --version` is older. Do not independently upgrade Expo or individual native dependencies; use the committed package lock. Do not change to SDK 58 unless the client on your phone supports it.

1. From this repository, run `npm ci` on a fresh checkout. Dependencies are already installed in the current workspace.
2. Configure the Supabase URL and publishable key in `.env` using `.env.example`. This workspace already has its connection configured.
3. Close any previous Metro process with Ctrl+C.
   Run `npm run login:expo` on the computer. Open the newly printed login URL in your computer's browser and keep the terminal running until login completes. The command deliberately skips automatic browser launching to avoid a Windows launcher error. Sign into the same Expo account in Expo Go on your phone (avatar icon on Home). This Expo account is separate from HuskyFind's Supabase demo account. Check the computer login with `npm run whoami:expo`.
4. Run `npm run start:tunnel`. Wait for the tunnel-ready message and scan the new QR code. This command explicitly selects Expo Go and uses a tunnel. Sign in to the CLI and physical-iPhone Expo Go with the same Expo account first.
5. Keep the terminal running. The first native bundle can take a minute.

On iPhone, scan with the Camera app and open the link in an SDK 57-compatible Expo Go installation. On Android, scan from Expo Go. Expo Go must support SDK 57; installing a mismatched SDK client cannot be repaired by changing JavaScript code.

Expo's September 3, 2026 announcement confirms SDK 57 support in the iOS App Store client and requires the same Expo account in the CLI and Expo Go: https://expo.dev/changelog/expo-go-57-login. Older SDK compatibility pages may describe the earlier SDK 54 store client.

For a permissive home/local network, `npm run start:lan` is faster. Shared campus networks can block device-to-device connections. A browser preview is available with `npm run start:web`; native maps and device push are not browser features.

## Explore the demo

Anonymous sign-in is enabled, and `EXPO_PUBLIC_ENABLE_DEMO_AUTH=true` makes **Explore Demo** the main welcome action. Tap it to create a real anonymous Supabase account. The app finishes preparing the demo before opening the tabs, and repeats the idempotent preparation when restoring a session. A failed preparation displays a retry action rather than an indefinite loader. No tester account or UW registration is needed for this path.

Demo accounts see the five demo listings and their own private report, matches, queued search, claim, and notifications. Demo search requests never advance without actual backend updates and must not be dispatched to physical rovers. Signing out of an anonymous account makes that account unrecoverable.

## Optional email/password accounts

**Sign in to HuskyFind** remains available for existing Supabase Auth email/password accounts.

A project administrator can open the Supabase dashboard for `salsusdncqbtrkcqxdkg`, navigate to Authentication → Users → Add user → Create user, and create a tester with a dedicated email/password. Confirm the email, or use Auto Confirm User for a team-managed test account. Share its credentials privately with the tester. This app never asks for a UW NetID password.

Tap **Sign in to HuskyFind** and enter that account's credentials. University verification stays false until a trusted administrator verifies the student. NetID sign-in appears only when its approved SSO provider is configured.

Normal email/password accounts see real found listings. The five seeded listings have `is_demo=true`, so an empty real feed is expected until trusted ingestion adds real listings. Do not change demo rows into real recovered-property records just to populate a test screen.

## Device smoke test

- Launch, tap Explore Demo, close/reopen the app, and confirm the session and seeded data restore.
- Open all five tabs; verify empty states where no real data exists.
- Report an item with title, category, color, description, photo, campus location, and last-seen time.
- Confirm the report appears in Activity and My Missing Items after relaunch.
- Request a rover search. Confirm it stays queued until a trusted backend changes the actual status.
- Have the ingestion teammate publish a corresponding authorized found record; verify Discover/Map refresh and matching appears for the report.
- Open the listing, save/unsave it, share it, and submit a correction.
- Submit a claim with private distinguishing details and optional evidence. Verify My Claims shows pending, then reflects a human reviewer's status update.
- Resolve a report and confirm it stops appearing in active matches.
- Deny photo/location permission once; confirm the app shows a useful explanation and remains usable.
- Test sign-out, invalid credentials, lost connectivity, and the startup retry screen.

Device push is intentionally skipped in Expo Go. In-app Activity notifications still work. Registering remote push requires a development/production build, EAS project, and configured push credentials.

## Automated checks

```powershell
npm run doctor
npm run check:dependencies
npm run typecheck
npm test
npm run check:backend
npm run export:native
npm run export:web
```

With demo mode enabled, the backend check creates an isolated anonymous account, initializes its demo, checks authenticated table reads, and deletes the temporary account afterward. It never changes authentication settings. With demo mode disabled, it checks service/schema availability; to exercise authenticated reads using an existing account, set `HUSKYFIND_TEST_EMAIL` and `HUSKYFIND_TEST_PASSWORD` as local shell environment variables before running it. They are server/test-only variables; never prefix passwords with `EXPO_PUBLIC_` or commit them.

## Installable builds

The repository includes Expo Dev Client and EAS profiles:

- `development`: native development client for physical iPhone/Android testing. Connect it with `npm run start:dev`.
- `preview`: internal distribution; Android produces an installable APK.
- `simulator`: iOS simulator development build.
- `production`: release build with automatic version incrementing.

Creating signed binaries requires an Expo/EAS account and project. Physical iPhone distribution also needs Apple signing/provisioning. Standalone Android maps require a restricted Google Maps SDK key (`GOOGLE_MAPS_API_KEY`). Set Supabase public environment variables in the EAS build environment; an ignored local `.env` is not a reliable cloud-build configuration source.

Bundle exports validate JavaScript/Hermes compilation. They do not produce APK/IPA files and do not replace the physical-device smoke test above.

## Browser startup regression check

Start Metro on port 8082, then run `npm run smoke:browser`. This uses installed Edge on Windows; set `CHROME_PATH` on other systems and `HUSKYFIND_TEST_URL` to override the server URL. The check uses an isolated browser context, creates a temporary demo account through the actual welcome button, exercises loading/search/saves/activity/profile/session restoration, and deletes that account afterward. It validates shared application startup in the browser and does not replace native-device testing.
