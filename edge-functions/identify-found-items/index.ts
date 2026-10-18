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
//   items?         [{ box, title, description, category, color }]   list these already-identified
//                  items (e.g. confirmed in two rover views) instead of detecting; same checks after that
//   min_box_px?    number   drop detections whose longer side is shorter: with a known camera,
//                  small means far away (another bench across the quad), where false finds cluster
//   detect_tiles?  { cols, rows, band?: [top, bottom] }   run detection on overlapping tiles of the
//                  band (fractions of the image height, default [0, 1]) instead of the whole image;
//                  finds small, distant items in wide-angle frames at the cost of one call per tile

import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";
import { HttpError, json, safeEqual, serve } from "../_shared/http.ts";
import {
  cropToJpeg,
  fromBase64,
  fromFoundImagePath,
  fromStorage,
  fromUrl,
  type LoadedImage,
  tiles,
} from "../_shared/images.ts";
import { CATEGORIES, CATEGORY_GUIDE, COLORS } from "../_shared/items.ts";
import { compareSightings, type Sighting } from "../_shared/rating.ts";
import { askJson, type Box, detect, type Detection, image, locate, text, toDataUrl } from "../_shared/perceptron.ts";

const MAX_ITEMS = 12;
// Detections smaller than this (pixels per side) are too small to describe or compare reliably.
const MIN_SIDE_PX = 12;
// Crops sent for description (and listed as the photo) keep at least this much context, upscaled.
const CROP_MIN_SIDE_PX = 160;
const CROP_UPSCALE_PX = 448;

// Duplicate check. Stored coordinates are rounded to ~100 m, so the radius has to cover that.
const DUP_RADIUS_M = 150;
const DUP_WINDOW_H = 24;
const DUP_MAX_CANDIDATES = 5;
const DUP_MIN_SIMILARITY = 70;

// Open-ended: no fixed list of item names, so anything a person might leave behind can be found.
// The describe step then drops whatever isn't a personal belonging.
const LOCATE_PROMPT = `Find every small, portable personal belonging that someone could have left behind or lost
here (anything a person carries, wears or plays with). Ignore furniture, benches, plants, trees, buildings, vehicles,
signs and other fixtures. Return one box per object, with a short mention naming it. If there are none, say so
without boxes.`;
// Fallback detections (open-ended Detect) larger than this share of the image are scenery, not items.
const MAX_ITEM_AREA = 0.15;

type Description = {
  what_it_is: string;
  part_of_scene: boolean;
  clearly_visible: boolean;
  is_lost_item: boolean;
  title: string;
  description: string;
  category: string;
  color: string;
};

// Field order is generation order: the model names the object and checks it against the scene
// before deciding whether it is a lost item.
const DESCRIPTION_SCHEMA = {
  type: "object",
  properties: {
    what_it_is: { type: "string", description: "Plainly, what the object at the centre of the photo is." },
    part_of_scene: {
      type: "boolean",
      description: "True if it is part of furniture (bench slats, armrests, legs, seat), a building, wall, " +
        "plant, tree, ground, path, sign, bin or other fixed or structural thing.",
    },
    clearly_visible: {
      type: "boolean",
      description: "False if it is too small, blurry, cut off or far away to tell confidently what it is.",
    },
    is_lost_item: {
      type: "boolean",
      description: "True only for a portable personal belonging someone could have left behind.",
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
  required: [
    "what_it_is",
    "part_of_scene",
    "clearly_visible",
    "is_lost_item",
    "title",
    "description",
    "category",
    "color",
  ],
  additionalProperties: false,
};

const DESCRIBE_PROMPT = `This photo was taken by a campus lost-and-found service. A detector flagged the
object at the centre of the photo as a possible lost item; it is often wrong, so decide for yourself
what the object is before anything else. Look only at that object, not the rest of the scene.

If it is part of a bench, other furniture, a building, a plant or any fixed part of the scene, or if
you can't clearly tell what it is, say so: it will not be listed. Otherwise describe it for a public
listing that its owner will search.

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

/** Share of the smaller box covered by the larger: catches an item cut in half by a tile edge. */
function containment(a: Box, b: Box): number {
  const ix = Math.max(0, Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1));
  const iy = Math.max(0, Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1));
  const area = (r: Box) => (r.x2 - r.x1) * (r.y2 - r.y1);
  return (ix * iy) / (Math.min(area(a), area(b)) || 1);
}

/** Drops tiny boxes and near-duplicates (same object under two labels, or seen by two tiles). */
function dedupe(dets: Detection[], minLongSide = 0): Detection[] {
  const kept: Detection[] = [];
  const bySize = [...dets].sort((a, b) =>
    (b.box.x2 - b.box.x1) * (b.box.y2 - b.box.y1) - (a.box.x2 - a.box.x1) * (a.box.y2 - a.box.y1)
  );
  for (const d of bySize) {
    const w = d.box.x2 - d.box.x1, h = d.box.y2 - d.box.y1;
    if (w < MIN_SIDE_PX || h < MIN_SIDE_PX || Math.max(w, h) < minLongSide) continue;
    if (!kept.some((k) => iou(k.box, d.box) > 0.6 || containment(k.box, d.box) > 0.7)) kept.push(d);
  }
  return kept.slice(0, MAX_ITEMS);
}

type TileSpec = { cols: number; rows: number; band: [number, number] };

function tileSpec(v: unknown): TileSpec | null {
  if (v === undefined || v === null) return null;
  const t = v as Record<string, unknown>;
  const cols = Number(t.cols), rows = Number(t.rows);
  const band = (Array.isArray(t.band) ? t.band.map(Number) : [0, 1]) as [number, number];
  const ok = Number.isInteger(cols) && Number.isInteger(rows) && cols >= 1 && cols <= 4 && rows >= 1 && rows <= 3 &&
    band.length === 2 && band[0] >= 0 && band[1] <= 1 && band[1] - band[0] >= 0.1;
  if (!ok) throw new HttpError(400, "detect_tiles needs integer cols 1-4, rows 1-3 and an optional band [top, bottom]");
  return { cols, rows, band };
}

/** Finds item boxes (image pixels) on the whole image or on overlapping tiles of it. */
async function detectItems(scene: LoadedImage, spec: TileSpec | null): Promise<Detection[]> {
  const { cols, rows, band } = spec ?? { cols: 1, rows: 1, band: [0, 1] as [number, number] };
  const parts = await tiles(scene, cols, rows, band);
  if (!parts) {
    // A format imagescript can't decode (WebP): open-ended Detect works on the original bytes.
    const all = await detect(toDataUrl(scene.bytes, scene.mime));
    const area = Math.max(...all.map((d) => d.box.x2), 1) * Math.max(...all.map((d) => d.box.y2), 1);
    return all.filter((d) => (d.box.x2 - d.box.x1) * (d.box.y2 - d.box.y1) < MAX_ITEM_AREA * area);
  }
  const perTile = await Promise.all(parts.map((t) => locate(toDataUrl(t.bytes, "image/jpeg"), LOCATE_PROMPT)));
  return perTile.flatMap((boxes, i) => {
    const t = parts[i];
    return boxes.map((b) => ({
      mention: b.mention,
      box: {
        x1: t.x + b.x1 * t.w / 1000,
        y1: t.y + b.y1 * t.h / 1000,
        x2: t.x + b.x2 * t.w / 1000,
        y2: t.y + b.y2 * t.h / 1000,
      },
    }));
  });
}

async function describe(scene: LoadedImage, det: Detection, crop: Uint8Array | null): Promise<Description> {
  const prompt = DESCRIBE_PROMPT;
  const content = crop ? [image(toDataUrl(crop, "image/jpeg")), text(prompt)] : [
    image(toDataUrl(scene.bytes, scene.mime)),
    text(
      `${prompt}\n\nThe item is inside the pixel box (${Math.round(det.box.x1)},${Math.round(det.box.y1)})` +
        `-(${Math.round(det.box.x2)},${Math.round(det.box.y2)}). Judge only the object in that box.`,
    ),
  ];
  const d = await askJson<Description>(content, "found_item", DESCRIPTION_SCHEMA, 1024);
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

/** Validates `items`: listings the caller already identified (from an earlier dry run). */
function preIdentifiedItems(v: unknown): { detection: Detection; info: Description }[] | null {
  if (v === undefined || v === null) return null;
  if (!Array.isArray(v) || v.length === 0 || v.length > MAX_ITEMS) {
    throw new HttpError(400, `items must be a non-empty array of at most ${MAX_ITEMS}`);
  }
  return v.map((raw, i) => {
    const it = raw as Record<string, unknown>;
    const b = it.box as Record<string, unknown> | undefined;
    const box = b && { x1: Number(b.x1), y1: Number(b.y1), x2: Number(b.x2), y2: Number(b.y2) };
    const texts = ["title", "description", "category", "color"].map((k) => it[k]);
    if (!box || ![box.x1, box.y1, box.x2, box.y2].every(Number.isFinite) || box.x2 <= box.x1 || box.y2 <= box.y1) {
      throw new HttpError(400, `items[${i}].box needs numeric x1 < x2 and y1 < y2`);
    }
    if (texts.some((t) => typeof t !== "string" || !t.trim())) {
      throw new HttpError(400, `items[${i}] needs title, description, category and color`);
    }
    const [title, description, category, color] = texts as string[];
    return {
      detection: { mention: title, box },
      info: {
        what_it_is: title,
        part_of_scene: false,
        clearly_visible: true,
        is_lost_item: true,
        title: title.trim().slice(0, 80),
        description: description.trim(),
        category: CATEGORIES.includes(category) ? category : "Other",
        color: COLORS.includes(color) ? color : "Multicolor",
      },
    };
  });
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
  const minBoxPx = num(body.min_box_px) ?? 0;
  if (minBoxPx < 0 || minBoxPx > 2000) throw new HttpError(400, "min_box_px must be within 0..2000");

  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false },
  });

  const scene = str(body.image_path)
    ? await fromStorage(supabase, "found-photos", str(body.image_path)!)
    : str(body.image_url)
    ? await fromUrl(str(body.image_url)!)
    : fromBase64(str(body.image_base64)!);

  let items: { detection: Detection; crop: Uint8Array | null; info: Description }[] = [];
  const skipped: { label: string; box: Box; reason: string }[] = [];
  const preIdentified = preIdentifiedItems(body.items);

  if (preIdentified) {
    // ---- caller already identified these (e.g. a rover confirming an item seen in two views)
    const crops = await Promise.all(
      preIdentified.map((d) =>
        cropToJpeg(scene, d.detection.box, { minSide: CROP_MIN_SIDE_PX, upscaleTo: CROP_UPSCALE_PX })
      ),
    );
    items = preIdentified.map((d, i) => ({ ...d, crop: crops[i] }));
  } else {
    // ---- identify
    const detections = dedupe(await detectItems(scene, tileSpec(body.detect_tiles)), minBoxPx);
    const crops = await Promise.all(
      detections.map((d) => cropToJpeg(scene, d.box, { minSide: CROP_MIN_SIDE_PX, upscaleTo: CROP_UPSCALE_PX })),
    );
    const results = await Promise.allSettled(detections.map((d, i) => describe(scene, d, crops[i])));
    results.forEach((r, i) => {
      const detection = detections[i];
      if (r.status === "rejected") {
        skipped.push({ label: detection.mention, box: detection.box, reason: String(r.reason?.message ?? r.reason) });
      } else if (r.value.part_of_scene || !r.value.clearly_visible || !r.value.is_lost_item) {
        const why = r.value.part_of_scene
          ? "part of the scene"
          : !r.value.clearly_visible
          ? "not clearly visible"
          : "not a personal belonging";
        skipped.push({ label: `${detection.mention} (${r.value.what_it_is})`, box: detection.box, reason: why });
      } else {
        items.push({ detection, crop: crops[i], info: r.value });
      }
    });
  }

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
