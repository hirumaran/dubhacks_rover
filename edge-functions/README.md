# Edge functions

Supabase Edge Functions (Deno) for everything that calls the Perceptron vision API
(`perceptron-mk1.5` and `/v1/detect`), written against the HuskyFind Supabase schema
(`found_items`, `missing_reports`, `item_matches`, Storage buckets `found-photos` / `missing-photos`).

| Function | Who calls it | What it does |
| - | - | - |
| `identify-found-items` | Rover / desk ingestion (trusted) | Detects every lost item in a photo, crops and describes each one, uploads the crops to `found-photos`, inserts `found_items` rows. The INSERT trigger then runs matching and notifications. |
| `compare-items` | Student app or backend | Rates 0–100 whether a missing report and a found listing are the same physical object, using both photos plus the owner's description. Read-only. |

`_shared/` holds the Perceptron client, image loading/cropping, and HTTP helpers.

## Secrets

`edge-functions/.env` (gitignored) holds:

- `PERCEPTRON_API_KEY`: Perceptron key.
- `ROVER_INGEST_SECRET`: shared secret the rover sends as `x-ingest-secret`.

Supabase injects `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` itself.

```bash
supabase secrets set --env-file edge-functions/.env --project-ref salsusdncqbtrkcqxdkg
```

## Deploy

- `identify-found-items`: `verify_jwt = false`. It authenticates with `x-ingest-secret` and writes with the service role.
- `compare-items`: `verify_jwt = true`. It runs as the caller, so RLS limits it to the student's own reports and visible listings.

The Supabase CLI looks for functions in `supabase/functions/`, so deploy from a copy laid out that way:

```bash
W=$(mktemp -d) && mkdir -p $W/supabase/functions && cp -R edge-functions/{_shared,identify-found-items,compare-items} $W/supabase/functions/
(cd $W && supabase functions deploy identify-found-items --project-ref salsusdncqbtrkcqxdkg --no-verify-jwt --use-api \
       && supabase functions deploy compare-items --project-ref salsusdncqbtrkcqxdkg --use-api)
```

## Calling them

```bash
# Identify and list items (dry_run: true returns what would be listed without writing)
curl -X POST "$SUPABASE_URL/functions/v1/identify-found-items" \
  -H "x-ingest-secret: $ROVER_INGEST_SECRET" -H "Content-Type: application/json" \
  -d '{"image_path":"rover/scan-123.jpg","approximate_location":"Suzzallo Library, 2nd floor",
       "latitude":47.6557,"longitude":-122.3080,"source":"rover","rover_id":"<uuid>","is_demo":false}'
```

Send exactly one of `image_path` (in `found-photos`), `image_url` (HTTPS), or `image_base64`.
The response lists the inserted rows under `listed`, and detections that were dropped (furniture, or a failed description) under `skipped`.

```ts
// From the app, with the student's session:
const { data } = await supabase.functions.invoke("compare-items", { body: { match_id } });
// -> { similarity: 0-100, verdict: "same_item" | "likely_same" | "unsure" | "likely_different" | "different",
//      matching_features, differences, summary, compared_photos }

// Rank every active match of a report (up to 10):
await supabase.functions.invoke("compare-items", { body: { missing_report_id } });
// -> { ratings: [...sorted by similarity], failed: [...] }
```

## Local testing

```bash
cd edge-functions
set -a; source .env; set +a
SUPABASE_URL=https://salsusdncqbtrkcqxdkg.supabase.co SUPABASE_SERVICE_ROLE_KEY=x \
  deno run --node-modules-dir=none --allow-net --allow-env identify-found-items/index.ts
# then POST to http://localhost:8000 with "dry_run": true
```

## Notes

- Listing descriptions are told to leave out names, ID numbers and other owner text, because owners use those details privately to prove a claim.
- Crops are made with imagescript, which can't decode WebP. WebP scans fall back to the full photo with a box hint.
- Comparison is most reliable when the owner's photo is a close-up. If the item is tiny in a wide scene, the score is noisy.
- `compare-items` doesn't store its rating, because `item_matches` has no column for it. Persisting it would need a migration (for example `visual_similarity integer`).
