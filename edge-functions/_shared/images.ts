// Loading images from Storage / URLs / base64, and cropping detections out of them.

import type { SupabaseClient } from "npm:@supabase/supabase-js@2";
import { decodeBase64 } from "jsr:@std/encoding@1/base64";
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
    bytes = decodeBase64(stripped);
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

/**
 * Crops `box` (plus padding) out of the image and re-encodes it as JPEG.
 * Returns null when the format can't be decoded here (imagescript has no WebP decoder),
 * so callers can fall back to the full image.
 */
export async function cropToJpeg(img: LoadedImage, box: Box, padding = 0.15): Promise<Uint8Array | null> {
  let decoded: Image;
  try {
    const d = await decode(img.bytes, true);
    if (!(d instanceof Image)) return null;
    decoded = d;
  } catch {
    return null;
  }

  const padX = (box.x2 - box.x1) * padding, padY = (box.y2 - box.y1) * padding;
  const x1 = Math.max(0, Math.floor(box.x1 - padX));
  const y1 = Math.max(0, Math.floor(box.y1 - padY));
  const x2 = Math.min(decoded.width, Math.ceil(box.x2 + padX));
  const y2 = Math.min(decoded.height, Math.ceil(box.y2 + padY));
  if (x2 - x1 < 8 || y2 - y1 < 8) return null;

  return await decoded.crop(x1, y1, x2 - x1, y2 - y1).encodeJPEG(88);
}
