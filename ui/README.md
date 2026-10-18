# HuskyFind

Native iOS/Android lost-and-found app for UW Seattle, built with Expo SDK 57, React Native, TypeScript, Expo Router, NativeWind, Supabase, TanStack Query, React Native Maps, Reanimated, and Lucide.

## Run

1. Run `npm ci`. The project installs Node 24.19 locally; all npm app/check scripts use that supported runtime automatically.
2. Copy `.env.example` to `.env` with your Supabase URL and publishable key. This workspace already has the supplied values in its ignored `.env`.
3. Complete the Supabase setup below.
   For SDK 57 Expo Go on physical iPhone, run `npm run login:expo`, manually open its newly printed URL in your computer's browser, and leave the terminal running until login completes. Sign into the same Expo account in Expo Go. This is separate from the in-app Supabase demo login.
4. Run `npm run start:tunnel` and scan its new QR code with SDK 57-compatible Expo Go on iPhone or Android. Keep the terminal open.
5. Tap **Explore Demo**. It creates a real anonymous Supabase account and prepares sample listings, a missing report, matches, a queued search, and a claim before opening Discover. No test-account setup is needed. **Sign in to HuskyFind** remains available for existing email/password accounts.

Run `npm run typecheck`, `npm test`, and `npm run export:native` for validation. A native JavaScript export is not a signed app binary or a device UI test. Android local builds require Android Studio; local iOS builds require macOS/Xcode. EAS build profiles are included for cloud builds.

## Supabase setup

The publishable key cannot deploy SQL. In PowerShell, run:

```powershell
supabase login
supabase link --project-ref salsusdncqbtrkcqxdkg
supabase db push
```

Follow the login browser instructions. If prompted for the database password, enter it locally. Alternatively, run the SQL files under `supabase/migrations` in filename order using the project's Supabase SQL Editor. Never put privileged keys in mobile environment variables.

Anonymous Sign-Ins is enabled on this project. Set `EXPO_PUBLIC_ENABLE_DEMO_AUTH=true` in `.env` (also the template default) to show Explore Demo. Email/password sign-in remains available through the email provider. If configuring institutional SSO in the future, add `huskyfind://auth/callback` to allowed redirect URLs. Migrations create the tables, private/public storage buckets, RLS policies, matching triggers, notifications, and realtime publication entries.

Demo photos are illustrative Unsplash samples, not actual recovered property. Anonymous accounts see only `is_demo=true` records; other authenticated accounts see only real listings. Demo access is enabled by default in the environment template. Set `EXPO_PUBLIC_ENABLE_DEMO_AUTH=false` to hide it in deployments that do not offer demo access. Regular tester accounts may initially see an empty feed because the seeded listings are demo-only. Rover searches stay queued until a trusted service changes their status.

## UW authentication

NetID sign-in is hidden until UW approves and registers an institutional integration. Configure an approved Supabase SSO provider and set `EXPO_PUBLIC_UW_SSO_PROVIDER_ID`. The app opens a secure browser and exchanges a PKCE authorization code; it never collects UW passwords. Configure issuer, audience, and signature validation in the identity provider/Supabase integration. `university_verified` is administrator-controlled and is never derived from editable user metadata. Test end-to-end with UW-issued configuration before release.

## Permissions and service integration

- Only trusted backend services may publish found listings, including rover records. Ingestion must provide approximate coordinates, never precise private locations.
- Profiles, missing reports, search requests, saves, and notifications are owner-only. Private claims are visible to claimants and authorized human reviewers.
- Assign reviewers using trusted Auth `app_metadata` containing `{"role":"reviewer"}`. Reviewers can update claim status only. Review occurs through an authorized admin/backend workflow; the student app has no staff console.
- Rover services set assignment, status, start/completion timestamps, and confirmed pickup locations using server-only credentials. Clients create only queued searches for their own reports.
- `found-photos` and `avatars` are public. `missing-photos` and `ownership-evidence` are private with owner-prefixed storage paths and MIME/size limits.
- Account deletion cleans uploaded photos before cascading database deletion. Interrupted cleanup can be retried. Add production cleanup jobs for orphan uploads and abandoned anonymous accounts.

## Matching and realtime

Server triggers recheck active reports when found listings or reports are inserted. Weights: category 35, color 20, nearby location 20, time 10, description keywords 15. Scores of 50+ create possible matches; 75+ are labeled strong. The TypeScript model in `src/lib/matching.ts` mirrors SQL; tune both together. Students see reasons, not artificial confidence percentages. Unique constraints prevent duplicate matches and preserve dismissals.

Realtime invalidates query caches on changes and reconnect; foregrounding also refreshes queries. Subscriptions are cleaned up. Search/claim status notifications come from database triggers.

## Push scaffolding

In-app notifications require no push credentials. For remote device push:

1. Create an EAS project and set `EXPO_PUBLIC_EAS_PROJECT_ID`.
2. Configure APNs/FCM and create a development or production build; remote push is unavailable in Expo Go.
3. Deploy `supabase/functions/push` using `supabase functions deploy push --no-verify-jwt`.
4. Set `PUSH_WEBHOOK_SECRET` as a function secret and configure a database webhook on `notifications` INSERT with the matching `x-webhook-secret` header.
5. Enable push in Profile. Notification taps open the corresponding item or Activity.

The webhook checks its secret and reads the canonical record and user preference. Production delivery still needs an idempotent queue, receipt processing, expired-token cleanup, retries, and monitoring. An Expo acceptance ticket is not proof of device delivery.

## Maps

Apple Maps is used on iOS. Android standalone builds need a restricted Google Maps SDK key in `GOOGLE_MAPS_API_KEY`; the React Native Maps config plugin in `app.config.ts` adds it to the native build. Restrict it to the package and signing certificate. Device location is requested only when centering the map and is not stored.

## Structure

- `app/`: welcome, auth, five tabs, item details, claims, collections, privacy/help.
- `src/components/`: native UI, maps, notification navigation.
- `src/lib/`: typed data models/services, Supabase session lifecycle, uploads, matching, notifications.
- `supabase/migrations/`: schema, RLS, triggers, demo setup.
- `supabase/functions/push/`: authenticated notification webhook scaffold.
- `tests/`: matching edge cases.

Before public release, validate both platforms on real devices, test RLS across student/reviewer accounts, complete UW SSO registration, configure maps/push, check accessibility, and arrange human claim review and campus pickup operations. This is an independent project, not an official UW service. No rover camera processing or navigation software is included.

## Validation status

TypeScript checking, five automated tests (including migrations and RLS in local PGlite with mocked Supabase auth/storage schemas), and iOS/Android Hermes bundle exports pass. The hosted schema is deployed and backend health checks pass. Live anonymous authentication, seeded data, matching, and account cleanup are verified against Supabase. Physical-device UI testing still requires phones. `npm audit` reports inherited dependency advisories; resolving remaining advisories requires reviewing upstream Expo/NativeWind dependency upgrades before a public release. Do not use `npm audit fix --force` blindly because its proposed versions break the pinned Expo stack.

Search dispatchers must filter `search_requests.is_demo = false` before assigning physical hardware. The database derives demo flags from the owning auth account, preventing clients from presenting demo searches as real missions.

## Teammate database reference

See [Supabase schema and integration guide](docs/SUPABASE_SCHEMA.md) for every table and field, relationships, access policies, storage buckets, triggers, and rover/backend integration rules.

For iPhone/Android setup, tester accounts, and installable build prerequisites, see [Testing HuskyFind](docs/TESTING.md).

## If Expo Go stays on “Opening project”

Stop Metro with Ctrl+C, then run `npm run start:tunnel` and scan the newly generated QR code. Campus/shared Wi-Fi can prevent phones from reaching the computer's LAN address even when both devices are on the same network. The ngrok tunnel helper is included locally. SDK 57 scripts explicitly select Expo Go (`--go`) and use a tunnel. The CLI and physical-iPhone Expo Go must be signed into the same Expo account. Keep the terminal running while testing; the first native bundle after clearing the cache can take a minute.

Use `npm run start:lan` on networks that permit device-to-device traffic, or `npm run start:web` for a browser preview. The browser preview has a campus location list in place of the native interactive map; device push remains native-only. A React Native DevTools download warning uses Expo's fallback tools and does not itself stop the app from loading.

The browser startup regression check (`npm run smoke:browser`) has also passed against the live backend: welcome → demo authentication → populated Discover feed → search → save/unsave → Activity → Profile → restored session, with no uncaught runtime errors. This uses an isolated test account that is deleted afterward; physical iOS/Android UI testing remains a separate check.

## Phone camera recognition and rover feed

Open the new **Scout** tab for Perceptron phone-camera scans, automatic scanning, detection boxes/history, and paired rover/webcam feeds. Run `npm run scout:gateway` in a separate terminal before connecting. See [Scout setup and networking](docs/SCOUT.md) for private server credentials, pairing, and starting a rover feed. Expo SDK 57 is retained.
