export type Detection = {
  title: string;
  description?: string;
  object_type?: string;
  category?: string;
  color?: string;
  bbox: [number, number, number, number];
  consecutive_scans?: number;
  repeated?: boolean;
};
export type Scan = {
  image: string;
  width: number;
  height: number;
  detections: Detection[];
  elapsed_s?: number;
  skipped_count?: number;
  time?: string;
};
export type Feed = Scan & {
  source: "rover" | "webcam";
  online: boolean;
  updated_at?: number;
  camera?: number;
  confirmed_count?: number;
  frame_id?: number;
  analysis?: (Scan & { updated_at: number }) | null;
};
export type Pairing = { url: string; token: string };

export function expoOrigin(host: string): string {
  const value = host.replace(/^(exp|exps|http|https):\/\//, "");
  const name = value.split(/[/:]/)[0];
  const local =
    /^(localhost|127\.0\.0\.1|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(
      name,
    );
  return new URL(`${local ? "http" : "https"}://${value}`).origin;
}

export function parsePairing(value: string, origin?: string): Pairing {
  const code = value.trim();
  if (/^[\w-]{32,128}$/.test(code)) {
    if (!origin)
      throw new Error(
        "Reopen the project from its Expo QR code so Scout can find your computer.",
      );
    return { url: new URL(origin).origin, token: code };
  }
  let parsed: URL;
  try {
    parsed = new URL(value.trim());
  } catch {
    throw new Error("Paste the pairing code printed by npm run scout:gateway.");
  }
  const local =
    /^(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(
      parsed.hostname,
    );
  if (
    !(parsed.protocol === "https:" || (parsed.protocol === "http:" && local)) ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.pathname !== "/"
  )
    throw new Error(
      "Use the launcher's local-network pairing link or an HTTPS gateway link.",
    );
  const token = parsed.hash.slice(1);
  if (!/^[\w-]{32,128}$/.test(token))
    throw new Error("The pairing link must include the complete code after #.");
  // Old IP links are still accepted, but use Expo's tunnel when available.
  return { url: origin ? new URL(origin).origin : parsed.origin, token };
}

export async function scoutRequest<T>(
  pair: Pairing,
  path: string,
  signal: AbortSignal,
  image?: string,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${pair.url}/api/mobile/${path}`, {
      cache: "no-store",
      method: image ? "POST" : "GET",
      signal,
      headers: {
        Authorization: `Bearer ${pair.token}`,
        "ngrok-skip-browser-warning": "1",
        ...(image ? { "Content-Type": "application/json" } : {}),
      },
      ...(image ? { body: JSON.stringify({ image }) } : {}),
    });
  } catch (error) {
    if (signal.aborted)
      throw new Error(
        "Scout timed out through the Expo connection. Restart both terminals and scan the new Expo QR code, then enter the new pairing code.",
      );
    throw new Error(
      "Cannot reach Scout through Expo. Keep npm run start:tunnel and npm run scout:gateway running on the same computer, then reopen the latest Expo QR code.",
    );
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      "Expo returned a page instead of the Scout API. Restart npm run start:tunnel to load the new gateway connection.",
    );
  }
  if (!response.ok)
    throw new Error(data.error || `Scout returned HTTP ${response.status}.`);
  return data as T;
}

const kinds = [
  "backpack",
  "laptop",
  "bottle",
  "book",
  "phone",
  "wallet",
  "keys",
  "umbrella",
  "headphones",
  "glasses",
  "bag",
  "jacket",
  "hat",
  "calculator",
  "watch",
  "purse",
];
function kind(item: Detection) {
  const text = (item.title || item.object_type || "")
    .toLowerCase()
    .split(/\b(?:on|near|beside|under|with)\b/)[0];
  return (
    kinds.find((k) => new RegExp(`\\b${k}s?\\b`).test(text)) ||
    text
      .replace(/\b(black|white|blue|red|green|yellow|small|large|the|a)\b/g, "")
      .trim()
  );
}
function overlap(a: number[], b: number[]) {
  const [x, y, w, h] = a,
    [u, v, r, s] = b;
  const area =
    Math.max(0, Math.min(x + w, u + r) - Math.max(x, u)) *
    Math.max(0, Math.min(y + h, v + s) - Math.max(y, v));
  return area / (w * h + r * s - area || 1);
}
export class RepeatTracker {
  private previous: (Detection & {
    kind: string;
    consecutive_scans: number;
  })[] = [];
  update(items: Detection[]): Detection[] {
    const used = new Set<number>();
    const next = items.map((item) => {
      const type = kind(item);
      const index = this.previous.findIndex(
        (old, i) =>
          !used.has(i) &&
          old.kind === type &&
          overlap(old.bbox, item.bbox) > 0.25 &&
          (!old.color || !item.color || old.color === item.color),
      );
      if (index >= 0) used.add(index);
      const count = index >= 0 ? this.previous[index].consecutive_scans + 1 : 1;
      return {
        ...item,
        kind: type,
        consecutive_scans: count,
        repeated: count >= 2,
      };
    });
    this.previous = next;
    return next;
  }
}
