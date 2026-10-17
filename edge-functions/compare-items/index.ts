// compare-items
//
// Rates whether a student's missing item and a found listing look like the same physical
// object, using Perceptron Mk1.5 on both photos plus the owner's written description.
//
// Auth: a normal Supabase JWT (student session or service role). All reads go through the
// caller's own RLS, so a student can only compare their own reports against listings they
// can see, and can read their own private `missing-photos`.
//
// Body (one of):
//   { match_id }                             rate one item_matches row
//   { missing_report_id, found_item_id }     rate any report/listing pair
//   { missing_report_id }                    rate every active match of the report (max 10)
//
// Read-only: it does not change item_matches scores, which students may not edit.

import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";
import { HttpError, json, serve } from "../_shared/http.ts";
import { fromFoundImagePath, fromStorage, type LoadedImage } from "../_shared/images.ts";
import { compare, type Found, type Report } from "../_shared/rating.ts";

const MAX_PAIRS = 10;

async function rate(supabase: SupabaseClient, report: Report, reportPhoto: LoadedImage | null, found: Found) {
  const foundPhoto = await fromFoundImagePath(supabase, found.image_path);
  return {
    missing_report_id: report.id,
    found_item_id: found.id,
    compared_photos: reportPhoto !== null,
    ...await compare(report, found, reportPhoto, foundPhoto),
  };
}

const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : undefined);
const REPORT_COLS = "id, title, description, category, color, image_path";
const FOUND_COLS = "id, title, description, category, color, image_path";

serve(async (body, req) => {
  const authorization = req.headers.get("Authorization");
  if (!authorization) throw new HttpError(401, "Missing Authorization header");

  // Acts as the caller, so RLS decides what they can compare.
  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false },
  });

  // ---- resolve which pairs to rate
  let reportId = str(body.missing_report_id);
  let foundIds: string[];
  let batch = false;

  const matchId = str(body.match_id);
  if (matchId) {
    const { data, error } = await supabase
      .from("item_matches").select("missing_report_id, found_item_id").eq("id", matchId).maybeSingle();
    if (error) throw new Error(error.message);
    if (!data) throw new HttpError(404, "Match not found");
    reportId = data.missing_report_id;
    foundIds = [data.found_item_id];
  } else if (reportId && str(body.found_item_id)) {
    foundIds = [str(body.found_item_id)!];
  } else if (reportId) {
    batch = true;
    const { data, error } = await supabase
      .from("item_matches").select("found_item_id").eq("missing_report_id", reportId).eq("status", "active")
      .order("match_score", { ascending: false }).limit(MAX_PAIRS);
    if (error) throw new Error(error.message);
    foundIds = data.map((m) => m.found_item_id);
  } else {
    throw new HttpError(400, "Send match_id, or missing_report_id with optional found_item_id");
  }

  const { data: report, error: reportErr } = await supabase
    .from("missing_reports").select(REPORT_COLS).eq("id", reportId!).maybeSingle<Report>();
  if (reportErr) throw new Error(reportErr.message);
  if (!report) throw new HttpError(404, "Missing report not found");
  if (foundIds.length === 0) return json({ ratings: [], failed: [] });

  const { data: found, error: foundErr } = await supabase
    .from("found_items").select(FOUND_COLS).in("id", foundIds).returns<Found[]>();
  if (foundErr) throw new Error(foundErr.message);
  if (found.length === 0) throw new HttpError(404, "Found item not found");

  const reportPhoto = report.image_path ? await fromStorage(supabase, "missing-photos", report.image_path) : null;

  // ---- rate
  const results = await Promise.allSettled(found.map((f) => rate(supabase, report, reportPhoto, f)));
  const ratings = results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
  const failed = results.flatMap((r, i) =>
    r.status === "rejected" ? [{ found_item_id: found[i].id, error: String(r.reason?.message ?? r.reason) }] : []
  );
  ratings.sort((a, b) => b.similarity - a.similarity);

  // Single-pair requests keep a flat shape; batch requests return a ranked list.
  if (!batch) {
    if (failed.length) throw new Error(failed[0].error);
    return json(ratings[0]);
  }
  return json({ ratings, failed });
});
