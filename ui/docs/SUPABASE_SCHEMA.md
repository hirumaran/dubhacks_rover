# HuskyFind Supabase schema

This describes the three migrations deployed to project `salsusdncqbtrkcqxdkg` on October 17, 2026. Application tables live in the `public` schema. Supabase manages authentication in `auth` and uploaded files in `storage`.

The SQL in `supabase/migrations/` is the schema source of truth. Add a new migration for future changes; editing an already-deployed migration does not update the hosted database.

## How the data fits together

A student authenticates through Supabase Auth, which automatically creates their `profiles` row. They create a `missing_reports` row for an item they lost. The matching system compares that report with `found_items` uploaded by trusted ingestion services. Potential matches go into `item_matches` and generate `notifications`.

Students may request a rover search through `search_requests`. A separate trusted dispatcher assigns a `rovers` record and updates mission progress. To recover a found item, the student submits a `claims` row with private ownership evidence. An authorized human reviewer updates the claim decision.

Relationships:

- `auth.users.id` → `profiles.id` — one profile per authentication account.
- `profiles.id` → `missing_reports.user_id` — a student's missing items.
- `missing_reports.id` → `search_requests.missing_report_id` — at most one search request per report.
- `rovers.id` → `search_requests.rover_id` and `found_items.rover_id` — assignments and discovery source.
- `missing_reports.id` + `found_items.id` → `item_matches` — ranked report/listing pairs.
- `profiles.id` + `found_items.id` → `claims` — private ownership claims.
- `profiles.id` + `found_items.id` → `saved_items` — bookmarks.
- `notifications` can point to a found item, a missing report, or both.

## Field conventions

Unless marked **optional**, columns below are `NOT NULL`.

- `id` is a UUID primary key generated with `gen_random_uuid()`, except for profiles and the two tables with composite primary keys.
- Dates and times use PostgreSQL `timestamptz`; send ISO 8601 timestamps with a timezone, preferably UTC.
- `created_at` defaults to `now()` wherever present.
- `user_id` defaults to `auth.uid()` on student-created tables, except `notifications`, whose recipient is explicitly supplied by trusted code.
- Coordinates are `double precision`. Found items and missing reports validate latitude within −90…90 and longitude within −180…180.
- Statuses are case-sensitive lowercase text. Most status fields have database CHECK constraints, listed below. Transitions between statuses are not enforced as a state machine.
- Category and color fields are text, not database enums. Use the app's category spellings for matching: `Electronics`, `Water Bottles`, `Bags`, `Keys`, `Clothing`, `Accessories`, `Other`. `All` is a UI filter only.

## Tables

### `profiles` — private student profile

- `id uuid` — primary key and FK to `auth.users.id`; no generated UUID default.
- `display_name text` — defaults to `Husky`.
- `university_email text` — optional.
- `campus text` — defaults to `UW Seattle`.
- `avatar_url text` — optional; the app currently stores an object path in the `avatars` bucket despite the column name.
- `notifications_enabled boolean` — defaults to `true`; controls the push sender's preference check.
- `university_verified boolean` — defaults to `false`; managed by trusted administrators.
- `created_at timestamptz`.

An Auth insert trigger creates the profile using the account email and its optional `display_name` metadata. Signing in does not automatically set university verification.

### `found_items` — discovered-item listings

- `id uuid`.
- `title text`, `description text`, `category text`, `color text`.
- `image_path text` — primary image; the app accepts a `found-photos` storage path or an HTTPS URL.
- `image_paths text[]` — additional images; defaults to an empty array.
- `approximate_location text` — human-readable campus location.
- `latitude double precision`, `longitude double precision` — approximate public coordinates.
- `source text` — `community` or `rover`; required, with no default.
- `rover_id uuid` — optional FK to `rovers.id`.
- `status text` — `available` (default), `claimed`, or `returned`.
- `pickup_location text` — optional confirmed pickup desk/location.
- `discovered_at timestamptz` — defaults to `now()`.
- `created_at timestamptz`.
- `is_demo boolean` — defaults to `false`; ingestion must set this correctly.

Only trusted services/admins can write listings under the current policies. Both community and rover listings require this trusted ingestion path; the student app reports missing items rather than publishing found listings.

No constraint currently requires a rover source to include `rover_id`, or verifies that coordinates are rounded. Ingestion is responsible for those rules. Never include private ownership answers in listing descriptions.

### `missing_reports` — items students have lost

- `id uuid`, `user_id uuid` → `profiles.id`.
- `title text` — between 1 and 150 characters.
- `description text`, `category text`, `color text`.
- `image_path text` — optional object path in private `missing-photos` storage.
- `last_seen_location text`.
- `latitude double precision`, `longitude double precision`.
- `last_seen_at timestamptz` — required; no default.
- `status text` — `active` (default), `resolved`, or `closed`.
- `created_at timestamptz`.
- `is_demo boolean` — derived from the owning authentication account by a trigger.

These reports and their location details are private to their owner. Inserting a report triggers matching.

### `rovers` — rover registry

- `id uuid`, `name text`, `status text`.
- `operating_zone text` — optional.
- `last_seen_at timestamptz` — optional.

`status` is free text with no default or CHECK constraint. Agree on a vocabulary in the rover service before relying on it. Authenticated students can read every row; put only public operational information here. This is not a telemetry, camera-feed, or navigation table.

### `search_requests` — requested rover missions

- `id uuid`, `user_id uuid` → `profiles.id`.
- `missing_report_id uuid` → `missing_reports.id`; **unique**, so only one request can exist per report, including completed requests.
- `rover_id uuid` — optional FK to `rovers.id`.
- `target_location text` — required human-readable search area.
- `status text` — `queued` (default), `assigned`, `searching`, `completed`, `no_match_found`, or `interrupted`.
- `started_at timestamptz`, `completed_at timestamptz` — optional.
- `created_at timestamptz`.
- `is_demo boolean` — derived from the owner.

Students can create only queued requests for their own report, with no rover assignment or start/completion timestamps. A trusted dispatcher controls mission updates. Coordinates are on the linked missing report, not on this table.

**Dispatch physical rovers only for `is_demo = false`.** Demo requests share this table and must never become physical missions.

### `item_matches` — missing/found item associations

- `id uuid`.
- `missing_report_id uuid` → `missing_reports.id`.
- `found_item_id uuid` → `found_items.id`.
- `match_score integer` — internal weighted score; no column default or range CHECK.
- `match_reasons text[]` — human-readable reasons; required.
- `status text` — `active` (default) or `dismissed`.
- `created_at timestamptz`.

The report/item pair is unique. Matching triggers create rows; students can read their own report's matches and change only `status`, to `dismissed`. They cannot edit the score or reasons.

### `claims` — private ownership verification

- `id uuid`, `user_id uuid` → `profiles.id`.
- `found_item_id uuid` → `found_items.id`.
- `verification_details jsonb` — required private answers.
- `evidence_path text` — optional object path in private `ownership-evidence` storage.
- `status text` — `pending` (default), `under_review`, `approved`, or `rejected`.
- `created_at timestamptz`.
- `is_demo boolean` — derived from the owner.

There can be one claim per user/item pair. The app writes this JSON shape, although PostgreSQL does not enforce the JSON keys:

```json
{
  "features": "Distinguishing details",
  "where_and_when": "Where and when the item was lost",
  "additional": "Other supporting evidence"
}
```

Students can submit pending claims for available, visible listings. Only the claimant and authorized reviewers can read them; only reviewers can update claim status through authenticated client access. Existing answers cannot be edited by students under the current policies.

Approval does **not** automatically change `found_items.status`, resolve a report, assign a pickup desk, or prevent another student's claim from being approved. The trusted review workflow must coordinate those actions.

### `saved_items` — student bookmarks

- `user_id uuid` → `profiles.id`.
- `found_item_id uuid` → `found_items.id`.
- `created_at timestamptz`.

Composite primary key: `(user_id, found_item_id)`. No separate `id`. Students manage their own bookmarks.

### `notifications` — persistent in-app updates

- `id uuid`, `user_id uuid` → recipient `profiles.id`.
- `title text`, `message text`.
- `related_item_id uuid` — optional FK to `found_items.id`.
- `related_report_id uuid` — optional FK to `missing_reports.id`.
- `read_at timestamptz` — optional; NULL means unread.
- `created_at timestamptz`.

Trusted code and triggers insert notifications. Students read their own notifications and can update only `read_at`. In-app records are independent of successful push delivery.

### `push_tokens` — Expo device destinations

- `user_id uuid` → `profiles.id`.
- `token text` — Expo push token.

Composite primary key: `(user_id, token)`. No separate `id` or timestamp. Students manage their own device tokens; the trusted push sender reads them server-side.

### `listing_reports` — listing corrections for human review

- `id uuid`, `user_id uuid` → `profiles.id`.
- `found_item_id uuid` → `found_items.id`.
- `reason text`.
- `created_at timestamptz`.

Students can submit corrections and read their own submissions. Reviewers can read all submissions. There is currently no moderation status column or client update policy.

## Access rules

All 11 application tables have row-level security enabled.

- Supabase's unauthenticated `anon` role has no application-table access policies. An **anonymous signed-in user** has an authenticated session and is different from an unauthenticated request.
- Anonymous signed-in users can read demo found listings only. Other authenticated users can read real found listings only. This visibility policy does not itself require university verification.
- Profiles are owner-only. Students can update only display name, campus, avatar, and notification preference; email and university verification are protected.
- Missing reports, searches, matches, saves, notifications, and tokens are scoped to the owning student, with the write restrictions described above.
- Reviewer access uses `auth.jwt()->'app_metadata'->>'role' = 'reviewer'`. Set this through trusted administration, never editable user metadata. Reviewer access does not grant blanket access to all private tables.
- Trusted server code uses privileged credentials to ingest listings and manage operations. Keep those credentials out of the mobile app and public repositories.

Foreign-key behavior: deleting an Auth user cascades through their profile and owned application records. Deleting a found item cascades to its matches, claims, saves, corrections, and linked notifications. Deleting a missing report cascades to its matches, search request, and linked notifications. Rover foreign keys do not have cascading deletion; reassign or clear references before deleting a referenced rover.

Database cascades do not delete Storage objects. The app removes the account's uploaded photos before calling the account deletion RPC.

## Storage buckets

- `found-photos`: public; 10 MiB per file. Trusted ingestion uploads found-item photographs.
- `missing-photos`: private; 10 MiB per file. The owner can upload, read, and delete their photographs.
- `ownership-evidence`: private; 10 MiB per file. Owners upload/read/delete; authorized reviewers can also read.
- `avatars`: public; 5 MiB per file. Owners upload, list/read, and delete their own objects; public image URLs are readable by anyone.

All buckets allow JPEG, PNG, and WebP. Student-uploaded paths must start with `<auth-user-uuid>/`, for example `<user-id>/photo.jpg`. Store object paths in database columns and create signed URLs when reading private images. Student Storage policies do not allow overwriting objects; use a new filename.

## Automatic behavior and matching

The database runs matching after an INSERT into `missing_reports` or `found_items`. Each candidate must be an available item in the same demo/real group as the report owner.

Scoring:

- Same category: 35 points; exact, case-sensitive equality.
- Same color after lowercasing/trimming: 20 points; blank report colors do not count.
- Approximate distance under 600 meters: 20 points, using a campus-scale planar calculation.
- Found at or after last seen, and less than seven days later: 10 points.
- A report-description token of at least four letters appears in the found description: 15 points.

A score of at least 50 inserts a match and one notification. The UI labels scores of 75+ as Strong match, 50–74 as Possible match, and lower scores as Weak match; the current trigger does not store scores below 50. These scores are heuristics, not probabilities.

Matching uses `ON CONFLICT DO NOTHING`: it preserves dismissals and does not update existing scores/reasons. Edits to existing reports or found items do not automatically rerun matching. The trusted backend would need to explicitly invoke the server-only `recheck_report(report_id)` function or add a migration to change this behavior. At present it scans candidate items rather than using a dedicated search/geospatial index.

Other triggers:

- New Auth account → create profile.
- Changed search status → create notification for the requesting student.
- Changed claim status → create notification for the claimant.
- A non-NULL pickup location changes → notify already-approved claimants. Approving a claim after a pickup location is already set generates the claim-status notification, but not a separate pickup notification.
- Inserts/updates to reports, searches, and claims → derive `is_demo` from the owning `auth.users.is_anonymous` value. Clients cannot override the classification.

## Realtime, RPCs, and indexes

The realtime publication includes `found_items`, `missing_reports`, `item_matches`, `search_requests`, `claims`, and `notifications`. Profiles, rover registry rows, saves, push tokens, and listing corrections are not currently published. Realtime access follows RLS. The app uses changes to invalidate cached queries.

Client-callable RPCs:

- `initialize_demo()` — anonymous signed-in accounts only. Creates a sample report, queued request, and claim if the account has no missing report. Matching creates the corresponding matches/notifications. Repeated calls do nothing once any report exists.
- `delete_my_account()` — deletes the current Auth account and cascades application records. Upload cleanup is the caller's responsibility.
- `is_reviewer()` — returns the current JWT's reviewer authorization flag.

`recheck_report(uuid)` is intentionally unavailable to both unauthenticated and authenticated student clients; trigger functions are internal database plumbing.

Besides primary-key/unique indexes, explicit indexes cover found-item discovery time, `(category, is_demo, status)`, report `(user_id, status)`, search user, claim user, notification `(user_id, created_at DESC)`, and match found-item ID. There is no PostGIS extension, full-text index, location-history table, rover-detection table, or direct search-request-to-discovery relationship in the current schema.

## Rover/backend teammate quick start

1. Register a rover in `rovers` through trusted server code.
2. Read queued `search_requests` with `is_demo = false`; join `missing_reports` for category, color, description, and coordinates. Mission assignment should claim a queued row atomically so two workers cannot assign it independently.
3. Set `rover_id` and the actual mission status/timestamps as progress is received. Status transitions do not fill timestamps automatically.
4. Upload found photos to `found-photos`, then insert `found_items`. Supply approximate coordinates, normalized category/color, `source = 'rover'`, the rover ID, and `is_demo = false`. Database triggers handle matches and notifications.
5. Set confirmed pickup information only after an authorized desk has physical custody. Coordinate claim approval, listing availability, and report resolution in the trusted review workflow.

The current schema has no ingestion idempotency key or rover detection ID. If a rover can retry the same upload, use a stable caller-generated found-item UUID and handle duplicate-key responses, or add an ingestion identifier in a future migration. A privileged upsert bypasses student RLS but will not rerun the INSERT-only matching trigger when it updates an existing row.

Push delivery is separate: `supabase/functions/push` is a webhook scaffold for notification INSERTs. Database triggers alone do not send device push messages; the webhook, its secret, device credentials, and EAS project must be configured.
# Cloud judging additions (October 18, 2026)

Migrations `202610180001_search_plans.sql`, `202610180002_judging_feed.sql`, and `202610180003_demo_photos.sql` add:

- Rover coordinates and `is_demo`, plus three explicit virtual fleet records.
- Private search-request `search_brief`, `assignment_reason`, and `assignment_distance_m`. The authenticated `plan_rover_search(report_id)` RPC locks the owned report, returns an existing assignment idempotently, and selects the closest eligible rover. Demo and physical fleets are separated; physical rovers need a recent heartbeat.
- `judging_feeds`, holding the most recent consented camera frame for each source. Only authenticated anonymous demo users can read fresh frames; rows older than 15 seconds are excluded by RLS. Clients have no write privilege. The `judging-feed` Edge Function requires the operator ingestion secret for publishing/clearing and a validated user session for viewing or inference.
- Updated demo-only reference photo URLs and descriptions using supplied campus images. Real listings are untouched.

The report screen calls `analyze-missing-photo`, `plan-search` calls the ownership-checked planning RPC, and Activity can call `compare-items`. Gateway JWT verification remains enabled for these new/deployed user functions. See [judging setup](JUDGING.md) for the permanent hosted app and operator relay.

