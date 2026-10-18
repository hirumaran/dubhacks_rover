// Loading images from Storage / URLs / base64, and cropping detections out of them.

import type { SupabaseClient } from "npm:@supabase/supabase-js@2";
import { decode, Image } from "https://deno.land/x/imagescript@1.3.0/mod.ts";
import { HttpError } from "./http.ts";
import type { Box } from "./perceptron.ts";

export const MAX_IMAGE_BYTES = 10 * 1024 * 1024; // matches the Storage bucket limit

export type LoadedImage = { bytes: Uint8Array; mime: string };

/** Identifies JPEG/PNG/WebP from magic bytes; these are the only types the buckets accept. */
export function sniffMime(b: Uint8Array): string | null {
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  if (
    b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 &&
    b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50
  ) return "image/webp";
  return null;
}

function checked(bytes: Uint8Array, what: string): LoadedImage {
  if (bytes.length > MAX_IMAGE_BYTES) throw new HttpError(413, `${what} is larger than 10 MiB`);
  const mime = sniffMime(bytes);
  if (!mime) throw new HttpError(415, `${what} must be a JPEG, PNG or WebP image`);
  return { bytes, mime };
}

export async function fromStorage(
  supabase: SupabaseClient,
  bucket: string,
  path: string,
): Promise<LoadedImage> {
  const { data, error } = await supabase.storage.from(bucket).download(path);
  if (error || !data) throw new HttpError(404, `Could not read ${bucket}/${path}`);
  return checked(new Uint8Array(await data.arrayBuffer()), `${bucket}/${path}`);
}

export async function fromUrl(url: string): Promise<LoadedImage> {
  if (!url.startsWith("https://")) throw new HttpError(400, "Image URLs must use https");
  const res = await fetch(url, { signal: AbortSignal.timeout(30_000) });
  if (!res.ok) throw new HttpError(422, `Could not fetch image (${res.status})`);
  return checked(new Uint8Array(await res.arrayBuffer()), "Image URL");
}

export function fromBase64(b64: string): LoadedImage {
  const stripped = b64.replace(/^data:[^;]+;base64,/, "");
  let bytes: Uint8Array;
  try {
    bytes = Uint8Array.from(atob(stripped), char => char.charCodeAt(0));
  } catch {
    throw new HttpError(400, "image_base64 is not valid base64");
  }
  return checked(bytes, "image_base64");
}

/**
 * found_items.image_path holds either a found-photos object path or an HTTPS URL.
 */
export function fromFoundImagePath(supabase: SupabaseClient, path: string): Promise<LoadedImage> {
  return path.startsWith("https://") ? fromUrl(path) : fromStorage(supabase, "found-photos", path);
}

async function decoded(img: LoadedImage): Promise<Image | null> {
  try {
    const d = await decode(img.bytes, true);
    return d instanceof Image ? d : null;
  } catch {
    return null;
  }
}

/**
 * Crops `box` (plus padding) out of the image and re-encodes it as JPEG.
 * The crop is widened to at least `minSide` pixels so small items keep some context, and
 * upscaled so its longer side is at least `upscaleTo`. Returns null when the format can't be
 * decoded here (imagescript has no WebP decoder), so callers can fall back to the full image.
 */
export async function cropToJpeg(
  img: LoadedImage,
  box: Box,
  { padding = 0.15, minSide = 0, upscaleTo = 0 } = {},
): Promise<Uint8Array | null> {
  const full = await decoded(img);
  if (!full) return null;

  const cx = (box.x1 + box.x2) / 2, cy = (box.y1 + box.y2) / 2;
  const halfW = Math.max((box.x2 - box.x1) * (0.5 + padding), minSide / 2);
  const halfH = Math.max((box.y2 - box.y1) * (0.5 + padding), minSide / 2);
  const x1 = Math.max(0, Math.floor(cx - halfW)), y1 = Math.max(0, Math.floor(cy - halfH));
  const x2 = Math.min(full.width, Math.ceil(cx + halfW)), y2 = Math.min(full.height, Math.ceil(cy + halfH));
  if (x2 - x1 < 8 || y2 - y1 < 8) return null;

  const crop = full.crop(x1, y1, x2 - x1, y2 - y1);
  const longest = Math.max(crop.width, crop.height);
  if (upscaleTo && longest < upscaleTo) crop.resize(Math.round(crop.width * upscaleTo / longest), Image.RESIZE_AUTO);
  return await crop.encodeJPEG(88);
}

export type Tile = { bytes: Uint8Array; x: number; y: number; w: number; h: number };

/**
 * Splits the image into `cols` x `rows` overlapping JPEG tiles covering the horizontal band
 * between `band[0]` and `band[1]` (fractions of the height). Small, distant objects take up a
 * larger share of a tile than of the whole frame, which is what lets the detector find them.
 */
export async function tiles(
  img: LoadedImage,
  cols: number,
  rows: number,
  band: [number, number],
  overlap = 0.2,
): Promise<Tile[] | null> {
  const full = await decoded(img);
  if (!full) return null;
  const top = Math.round(full.height * band[0]), bandH = Math.round(full.height * (band[1] - band[0]));
  const tw = Math.ceil(full.width / (cols - (cols - 1) * overlap));
  const th = Math.ceil(bandH / (rows - (rows - 1) * overlap));
  const out: Tile[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const x = Math.min(full.width - tw, Math.round(c * tw * (1 - overlap)));
      const y = top + Math.min(bandH - th, Math.round(r * th * (1 - overlap)));
      const w = Math.min(tw, full.width), h = Math.min(th, bandH);
      out.push({ bytes: await full.clone().crop(x, y, w, h).encodeJPEG(90), x, y, w, h });
    }
  }
  return out;
}

/** Decode once for dimensions/blank-frame validation before any paid model request. */
export async function sceneInfo(img:LoadedImage):Promise<{width:number;height:number;bitmap:Uint8Array|Uint8ClampedArray}|null>{
 const full=await decoded(img);return full?{width:full.width,height:full.height,bitmap:full.bitmap}:null;
}
