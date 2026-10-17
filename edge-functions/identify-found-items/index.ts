// identify-found-items
//
// Trusted ingestion: takes one photo (from a rover or a lost-and-found desk), finds every
// lost-and-found item in it with Perceptron Detect, describes each crop with Perceptron Mk1.5,
// uploads the crops to `found-photos`, and inserts one `found_items` row per item.
// The database's INSERT trigger then runs matching and notifications.
//
// Before listing, each item is compared with recent available listings of the same category
// nearby; if Perceptron rates it the same object, it is reported under `duplicates` instead of
// being listed again. Send one image at a time per rover so two requests can't both list the
// same item.
//
// Auth: `x-ingest-secret: <ROVER_INGEST_SECRET>`. Deploy with verify_jwt = false.
//
// Body:
//   image_path?    string   object path in the public `found-photos` bucket
//   image_url?     string   HTTPS URL
//   image_base64?  string   raw base64 or a data: URL          (exactly one of the three)
//   approximate_location  string   human-readable campus location
//   latitude, longitude   number   rounded to 3 decimals (~100 m) before storing
//   is_demo        boolean  required, so demo scans never become real listings by accident
//   source?        "rover" | "community"   default "rover"; "rover" requires rover_id
//   rover_id?      uuid
//   discovered_at? ISO 8601 timestamp, default now
//   dry_run?       boolean  identify only; no uploads or inserts

import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";
import { HttpError, json, safeEqual, serve } from "../_shared/http.ts";
import {
  cropToJpeg,
  fromBase64,
  fromFoundImagePath,
  fromStorage,
  fromUrl,
  type LoadedImage,
} from "../_shared/images.ts";
import { CATEGORIES, CATEGORY_GUIDE, COLORS } from "../_shared/items.ts";
import { compareSightings, type Sighting } from "../_shared/rating.ts";
import { askJson, type Box, detect, type Detection, image, text, toDataUrl } from "../_shared/perceptron.ts";

const MAX_ITEMS = 12;
// Detections smaller than this (pixels per side) are too small to describe or compare reliably.
const MIN_SIDE_PX = 24;

// Duplicate check. Stored coordinates are rounded to ~100 m, so the radius has to cover that.
const DUP_RADIUS_M = 150;
const DUP_WINDOW_H = 24;
const DUP_MAX_CANDIDATES = 5;
const DUP_MIN_SIMILARITY = 70;

// What Detect looks for. Kept to concrete nouns: Detect's mention is one of these.
const DETECT_CATEGORIES = [
  "phone",
  "laptop",
  "tablet",
  "headphones",
  "earbuds case",
  "charger",
  "calculator",
  "wallet",
  "keys",
  "id card",
  "water bottle",
  "travel mug",
  "backpack",
  "bag",
  "tote bag",
  "lunch box",
  "jacket",
  "sweatshirt",
  "hat",
  "scarf",
  "gloves",
  "glasses",
  "sunglasses",
  "watch",
  "umbrella",
  "book",
  "notebook",
];

type Description = {
  is_lost_item: boolean;
  title: string;
  description: string;
  category: string;
  color: string;
};

const DESCRIPTION_SCHEMA = {
  type: "object",
  properties: {
    is_lost_item: {
      type: "boolean",
      description: "False if this is furniture, a fixture, trash, or not clearly a personal belonging.",
    },
    title: {
      type: "string",
      description: "Short listing title, e.g. 'Blue Hydro Flask water bottle'. At most 60 characters.",
    },
    description: {
      type: "string",
      description: "One or two sentences on visible type, brand, material and condition.",
    },
    category: { type: "string", enum: CATEGORIES },
    color: { type: "string", enum: COLORS, description: "The single dominant color." },
  },
  required: ["is_lost_item", "title", "description", "category", "color"],
  additionalProperties: false,
};

const DESCRIBE_PROMPT = `This photo was taken by a campus lost-and-found service. Describe the
detected item (a "{label}") for a public listing that its owner will search.

Use only what you can clearly see; leave out anything you are unsure of. Do NOT transcribe
names, student or ID numbers, phone numbers, email addresses, or any other text that identifies
the owner: owners describe those privately to prove the item is theirs, so publishing them would
let anyone claim it.

${CATEGORY_GUIDE}`;

function iou(a: Box, b: Box): number {
  const ix = Math.max(0, Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1));
  const iy = Math.max(0, Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1));
  const inter = ix * iy;
  const area = (r: Box) => (r.x2 - r.x1) * (r.y2 - r.y1);
  return inter / (area(a) + area(b) - inter || 1);
}

/** Drops near-duplicate boxes (same object returned under two labels). */
function dedupe(dets: Detection[]): Detection[] {
  const kept: Detection[] = [];
  for (const d of dets) {
    if (d.box.x2 - d.box.x1 < MIN_SIDE_PX || d.box.y2 - d.box.y1 < MIN_SIDE_PX) continue;
    if (!kept.some((k) => iou(k.box, d.box) > 0.6)) kept.push(d);
  }
  return kept.slice(0, MAX_ITEMS);
}

async function describe(scene: LoadedImage, det: Detection, crop: Uint8Array | null): Promise<Description> {
  const prompt = DESCRIBE_PROMPT.replace("{label}", det.mention);
  const content = crop ? [image(toDataUrl(crop, "image/jpeg")), text(prompt)] : [
    image(toDataUrl(scene.bytes, scene.mime)),
    text(
      `${prompt}\n\nThe item is inside the pixel box (${Math.round(det.box.x1)},${Math.round(det.box.y1)})` +
        `-(${Math.round(det.box.x2)},${Math.round(det.box.y2)}). Describe only that item.`,
    ),
  ];
  const d = await askJson<Description>(content, "found_item", DESCRIPTION_SCHEMA, 512);
  return {
    ...d,
    title: d.title.trim().slice(0, 80),
    category: CATEGORIES.includes(d.category) ? d.category : "Other",
  };
}

type Listing = Sighting & { id: string; image_path: string; latitude: number; longitude: number };
type Duplicate = { id: string; similarity: number };

/** Campus-scale planar distance in meters. */
function metersBetween(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const dy = (lat2 - lat1) * 111_320;
  const dx = (lng2 - lng1) * 111_320 * Math.cos((lat1 * Math.PI) / 180);
  return Math.hypot(dx, dy);
}

/** Returns the existing listing this item duplicates, if Perceptron rates any nearby one the same object. */
async function findDuplicate(
  supabase: SupabaseClient,
  info: Description,
  photo: LoadedImage,
  where: { lat: number; lng: number; isDemo: boolean; at: string },
): Promise<Duplicate | null> {
  const dLat = DUP_RADIUS_M / 111_320;
  const dLng = DUP_RADIUS_M / (111_320 * Math.cos((where.lat * Math.PI) / 180));
  const since = new Date(Date.parse(where.at) - DUP_WINDOW_H * 3_600_000).toISOString();

  const { data, error } = await supabase
    .from("found_items")
    .select("id, title, description, category, color, image_path, latitude, longitude")
    .eq("status", "available")
    .eq("is_demo", where.isDemo)
    .eq("category", info.category)
    .gte("discovered_at", since)
    .gte("latitude", where.lat - dLat).lte("latitude", where.lat + dLat)
    .gte("longitude", where.lng - dLng).lte("longitude", where.lng + dLng)
    .order("discovered_at", { ascending: false })
    .limit(DUP_MAX_CANDIDATES)
    .returns<Listing[]>();
  if (error) throw new Error(`Duplicate lookup failed: ${error.message}`);

  // A failed comparison counts as "not a duplicate": listing twice beats losing an item.
  const rated = await Promise.allSettled(data.map(async (c) => ({
    id: c.id,
    r: await compareSightings(
      info,
      photo,
      c,
      await fromFoundImagePath(supabase, c.image_path),
      metersBetween(where.lat, where.lng, c.latitude, c.longitude),
    ),
  })));
  let best: Duplicate | null = null;
  for (const x of rated) {
    if (x.status !== "fulfilled") continue;
    const { id, r } = x.value;
    const same = r.verdict === "same_item" || r.verdict === "likely_same";
    if (same && r.similarity >= DUP_MIN_SIMILARITY && (!best || r.similarity > best.similarity)) {
      best = { id, similarity: r.similarity };
    }
  }
  return best;
}

const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : undefined);
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : undefined);

serve(async (body, req) => {
  const secret = Deno.env.get("ROVER_INGEST_SECRET");
  if (!secret) throw new Error("ROVER_INGEST_SECRET secret is not set");
  if (!safeEqual(req.headers.get("x-ingest-secret") ?? "", secret)) {
    throw new HttpError(401, "Missing or wrong x-ingest-secret");
  }

  // ---- validate input
  const sources = [str(body.image_path), str(body.image_url), str(body.image_base64)].filter(Boolean);
  if (sources.length !== 1) throw new HttpError(400, "Send exactly one of image_path, image_url, image_base64");

  const location = str(body.approximate_location);
  const lat = num(body.latitude), lng = num(body.longitude);
  if (!location) throw new HttpError(400, "approximate_location is required");
  if (lat === undefined || lat < -90 || lat > 90) throw new HttpError(400, "latitude must be within -90..90");
  if (lng === undefined || lng < -180 || lng > 180) throw new HttpError(400, "longitude must be within -180..180");
  if (typeof body.is_demo !== "boolean") throw new HttpError(400, "is_demo (boolean) is required");

  const source = body.source ?? "rover";
  if (source !== "rover" && source !== "community") throw new HttpError(400, "source must be rover or community");
  const roverId = str(body.rover_id);
  if (source === "rover" && !roverId) throw new HttpError(400, "rover_id is required when source is rover");

  const discoveredAt = str(body.discovered_at) ?? new Date().toISOString();
  if (Number.isNaN(Date.parse(discoveredAt))) throw new HttpError(400, "discovered_at must be an ISO 8601 timestamp");
  const dryRun = body.dry_run === true;

  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false },
  });

  const scene = str(body.image_path)
    ? await fromStorage(supabase, "found-photos", str(body.image_path)!)
    : str(body.image_url)
    ? await fromUrl(str(body.image_url)!)
    : fromBase64(str(body.image_base64)!);

  // ---- identify
  const detections = dedupe(await detect(toDataUrl(scene.bytes, scene.mime), DETECT_CATEGORIES));
  const crops = await Promise.all(detections.map((d) => cropToJpeg(scene, d.box)));
  const results = await Promise.allSettled(detections.map((d, i) => describe(scene, d, crops[i])));

  let items: { detection: Detection; crop: Uint8Array | null; info: Description }[] = [];
  const skipped: { label: string; box: Box; reason: string }[] = [];
  results.forEach((r, i) => {
    const detection = detections[i];
    if (r.status === "rejected") {
      skipped.push({ label: detection.mention, box: detection.box, reason: String(r.reason?.message ?? r.reason) });
    } else if (!r.value.is_lost_item) {
      skipped.push({ label: detection.mention, box: detection.box, reason: "not a personal belonging" });
    } else {
      items.push({ detection, crop: crops[i], info: r.value });
    }
  });

  // ---- drop items that are already listed nearby
  const where = { lat, lng, isDemo: body.is_demo, at: discoveredAt };
  const dupChecks = await Promise.all(
    items.map((it) =>
      findDuplicate(supabase, it.info, it.crop ? { bytes: it.crop, mime: "image/jpeg" } : scene, where)
    ),
  );
  const duplicates = items.flatMap((it, i) => {
    const dup = dupChecks[i];
    return dup
      ? [{
        label: it.detection.mention,
        box: it.detection.box,
        existing_found_item_id: dup.id,
        similarity: dup.similarity,
      }]
      : [];
  });
  items = items.filter((_, i) => !dupChecks[i]);

  if (dryRun || items.length === 0) {
    return json({
      dry_run: dryRun,
      listed: [],
      identified: items.map(({ detection, info }) => ({ ...info, label: detection.mention, box: detection.box })),
      duplicates,
      skipped,
    });
  }

  // ---- upload photos
  const folder = `${source}/${discoveredAt.slice(0, 10)}`;
  const upload = async (bytes: Uint8Array, mime: string) => {
    const ext = mime === "image/png" ? "png" : mime === "image/webp" ? "webp" : "jpg";
    const path = `${folder}/${crypto.randomUUID()}.${ext}`;
    const { error } = await supabase.storage.from("found-photos").upload(path, bytes, { contentType: mime });
    if (error) throw new Error(`Upload to found-photos failed: ${error.message}`);
    return path;
  };

  // The full scene is kept as a secondary photo so reviewers can see context.
  const scenePath = str(body.image_path) ??
    (str(body.image_url) ? str(body.image_url)! : await upload(scene.bytes, scene.mime));
  const imagePaths = await Promise.all(items.map((it) => (it.crop ? upload(it.crop, "image/jpeg") : scenePath)));

  // ---- insert listings (INSERT trigger runs matching + notifications)
  const round = (v: number) => Math.round(v * 1000) / 1000;
  const rows = items.map((it, i) => ({
    id: crypto.randomUUID(),
    title: it.info.title,
    description: it.info.description,
    category: it.info.category,
    color: it.info.color,
    image_path: imagePaths[i],
    image_paths: imagePaths[i] === scenePath ? [] : [scenePath],
    approximate_location: location,
    latitude: round(lat),
    longitude: round(lng),
    source,
    rover_id: roverId ?? null,
    status: "available",
    discovered_at: discoveredAt,
    is_demo: body.is_demo,
  }));

  const { data, error } = await supabase
    .from("found_items")
    .insert(rows)
    .select("id, title, description, category, color, image_path");
  if (error) throw new Error(`Insert into found_items failed: ${error.message}`);

  return json({
    dry_run: false,
    listed: data!.map((row) => {
      const { detection } = items[rows.findIndex((r) => r.id === row.id)];
      return { ...row, label: detection.mention, box: detection.box };
    }),
    duplicates,
    skipped,
  }, 201);
});
