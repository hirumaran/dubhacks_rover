# Edge functions

Supabase Edge Functions (Deno) for everything that calls the Perceptron vision API (`perceptron-mk1.5` and
`/v1/detect`), written against the HuskyFind Supabase schema (`found_items`, `missing_reports`, `item_matches`, Storage
buckets `found-photos` / `missing-photos`).

| Function                | Who calls it                     | What it does                                                                                                                                                                                |
| ----------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `identify-found-items`  | Rover / desk ingestion (trusted) | Detects every lost item in a photo, crops and describes each one, uploads the crops to `found-photos`, inserts `found_items` rows. The INSERT trigger then runs matching and notifications. |
| `analyze-missing-photo` | Student app                      | Suggests title, description, category and color from a photo of the student's lost item, so the report form is pre-filled with the app's exact category spellings before insert. Read-only. |
| `compare-items`         | Student app or backend           | Rates 0–100 whether a missing report and a found listing are the same physical object, using both photos plus the owner's description. Read-only.                                           |

`_shared/` holds the Perceptron client, the category/color vocabulary (`items.ts`), image loading/cropping, and HTTP
helpers.

## Secrets

`edge-functions/.env` (gitignored) holds:

- `PERCEPTRON_API_KEY`: Perceptron key.
- `ROVER_INGEST_SECRET`: shared secret the rover sends as `x-ingest-secret`.

Supabase injects `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` itself.

```bash
supabase secrets set --env-file edge-functions/.env --project-ref salsusdncqbtrkcqxdkg
```

## Deploy

- `identify-found-items`: `verify_jwt = false`. It authenticates with `x-ingest-secret` and writes with the service
  role.
- `analyze-missing-photo`: `verify_jwt = true`. Storage reads run as the caller.
- `compare-items`: `verify_jwt = true`. It runs as the caller, so RLS limits it to the student's own reports and visible
  listings.

The Supabase CLI looks for functions in `supabase/functions/`, so deploy from a copy laid out that way:

```bash
W=$(mktemp -d) && mkdir -p $W/supabase/functions && cp -R edge-functions/{_shared,identify-found-items,analyze-missing-photo,compare-items} $W/supabase/functions/
(cd $W && supabase functions deploy identify-found-items --project-ref salsusdncqbtrkcqxdkg --no-verify-jwt --use-api \
       && supabase functions deploy analyze-missing-photo --project-ref salsusdncqbtrkcqxdkg --use-api \
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

Send exactly one of `image_path` (in `found-photos`), `image_url` (HTTPS), or `image_base64`. The response lists the
inserted rows under `listed`, and detections that were dropped (furniture, or a failed description) under `skipped`.

```ts
// Pre-fill the report form (before or after uploading to missing-photos):
const { data } = await supabase.functions.invoke("analyze-missing-photo", { body: { image_path } });
// -> { item_visible, title, description, category, color }
```

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

- `identify-found-items` doesn't use a fixed list of item names: it asks Mk1.5 for "any small, portable personal
  belonging" (optionally per tile, `detect_tiles`), drops boxes smaller than `min_box_px`, then has Mk1.5 name each crop
  and reject furniture, scenery and anything it can't make out before listing.

- Listing descriptions are told to leave out names, ID numbers and other owner text, because owners use those details
  privately to prove a claim.
- Crops are made with imagescript, which can't decode WebP. WebP scans fall back to the full photo with a box hint.
- Comparison is most reliable when the owner's photo is a close-up. If the item is tiny in a wide scene, the score is
  noisy.
- `compare-items` doesn't store its rating, because `item_matches` has no column for it. Persisting it would need a
  migration (for example `visual_similarity integer`).


## Hardened identification

The identification function now rejects uniform/loading images before a model call, checks all boxes against decoded image dimensions/area, requires a specific identity and judges a crop alongside the complete scene. Pre-identified items do not bypass visual checks. Dry runs return validated detections before querying stored listings. Local regression controls are in `_shared/detection_quality_test.ts`.
