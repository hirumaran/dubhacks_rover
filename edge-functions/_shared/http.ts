// Request/response helpers shared by the edge functions.

export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-ingest-secret",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

export class HttpError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json", "X-Perception-Pipeline":"vision-guard-20261017" },
  });
}

/** Wraps a POST handler with CORS preflight, JSON body parsing and error responses. */
export function serve(handler: (body: Record<string, unknown>, req: Request) => Promise<Response>) {
  Deno.serve({hostname:Deno.env.get("LOCAL_ONLY")==="1"?"127.0.0.1":"0.0.0.0"},async (req) => {
    if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
    if (req.method !== "POST") return json({ error: "Use POST" }, 405);

    try {
      let body: unknown;
      try {
        body = await req.json();
      } catch {
        throw new HttpError(400, "Body must be JSON");
      }
      if (typeof body !== "object" || body === null || Array.isArray(body)) {
        throw new HttpError(400, "Body must be a JSON object");
      }
      return await handler(body as Record<string, unknown>, req);
    } catch (err) {
      if (err instanceof HttpError) return json({ error: err.message }, err.status);
      console.error(err);
      return json({ error: err instanceof Error ? err.message : String(err) }, 500);
    }
  });
}

/** Constant-time string comparison for shared secrets. */
export function safeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const x = enc.encode(a), y = enc.encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}
