// Thin client for the Perceptron HTTP API (https://docs.perceptron.inc).
// The key comes from the PERCEPTRON_API_KEY function secret and never leaves the server.

import { encodeBase64 } from "jsr:@std/encoding@1/base64";

const API_BASE = "https://api.perceptron.inc/v1";
export const MODEL = "perceptron-mk1.5";
const TIMEOUT_MS = 90_000;

export class PerceptronError extends Error {
  constructor(readonly status: number, readonly body: string) {
    super(`Perceptron API returned ${status}: ${body.slice(0, 500)}`);
  }
}

export type ContentPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

export const text = (t: string): ContentPart => ({ type: "text", text: t });
export const image = (url: string): ContentPart => ({ type: "image_url", image_url: { url } });

export function toDataUrl(bytes: Uint8Array, mime: string): string {
  return `data:${mime};base64,${encodeBase64(bytes)}`;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const key = Deno.env.get("PERCEPTRON_API_KEY");
  if (!key) throw new Error("PERCEPTRON_API_KEY secret is not set");

  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) throw new PerceptronError(res.status, await res.text());
  return await res.json() as T;
}

/** Pixel-space box: top-left (x1, y1), bottom-right (x2, y2). */
export type Box = { x1: number; y1: number; x2: number; y2: number };
export type Detection = { mention: string; box: Box };

type DetectResponse = {
  detections: {
    mention: string;
    point_box?: { top_left: { x: number; y: number }; bottom_right: { x: number; y: number } };
  }[];
  finish_reason: "complete" | "max_tokens";
};

/** POST /v1/detect: boxes (in image pixels) for the given categories. */
export async function detect(imageUrl: string, categories: string[]): Promise<Detection[]> {
  const res = await post<DetectResponse>("/detect", {
    media: { type: "image", image_url: imageUrl },
    categories,
    // Non-"none" lets category detection inspect extra image regions, which helps with small items.
    config: { output: "box", reasoning_effort: "low" },
  });
  return res.detections
    .filter((d) => d.point_box)
    .map((d) => ({
      mention: d.mention,
      box: {
        x1: d.point_box!.top_left.x,
        y1: d.point_box!.top_left.y,
        x2: d.point_box!.bottom_right.x,
        y2: d.point_box!.bottom_right.y,
      },
    }));
}

type ChatResponse = {
  choices: { message: { content: string | null }; finish_reason: string }[];
};

/** POST /v1/chat/completions constrained to a JSON Schema; returns the parsed answer. */
export async function askJson<T>(
  content: ContentPart[],
  schemaName: string,
  schema: Record<string, unknown>,
  maxTokens = 1024,
): Promise<T> {
  const res = await post<ChatResponse>("/chat/completions", {
    model: MODEL,
    messages: [{ role: "user", content }],
    max_completion_tokens: maxTokens,
    response_format: {
      type: "json_schema",
      json_schema: { name: schemaName, strict: true, schema },
    },
  });
  const choice = res.choices[0];
  if (!choice || choice.finish_reason !== "stop") {
    throw new Error(`Perceptron answer incomplete (finish_reason=${choice?.finish_reason})`);
  }
  return JSON.parse(choice.message.content ?? "") as T;
}
