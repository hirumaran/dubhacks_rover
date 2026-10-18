import { createClient } from "npm:@supabase/supabase-js@2";
import { HttpError, json, serve } from "../_shared/http.ts";

serve(async (body, req) => {
  const authorization = req.headers.get("Authorization");
  if (!authorization) throw new HttpError(401, "Sign in to plan a search");
  if (typeof body.report_id !== "string") throw new HttpError(400, "Choose a saved report");
  const client = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: authorization } }, auth: { persistSession: false },
  });
  const { data: { user } } = await client.auth.getUser(authorization.replace(/^Bearer\s+/i, ""));
  if (!user) throw new HttpError(401, "Your sign-in expired. Please sign in again.");
  const { data, error } = await client.rpc("plan_rover_search", { report_id: body.report_id });
  if (error) throw new HttpError(400, error.message);
  return json(data);
});
