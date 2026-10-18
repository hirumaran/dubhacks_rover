import * as ImagePicker from "expo-image-picker";
import { File } from "expo-file-system";
import { supabase, check } from "./supabase";
import { FoundItem, MissingReport, Match, Profile } from "./types";
export async function foundItems(
  search = "",
  category = "All",
  page = 0,
  sort = "newest",
  source = "all",
  days = 0,
) {
  let q = supabase.from("found_items").select("*").eq("status", "available");
  if (search.trim())
    q = q.ilike("title", `%${search.trim().replace(/[%_]/g, "")}%`);
  if (category !== "All") q = q.eq("category", category);
  if (source !== "all") q = q.eq("source", source);
  if (days)
    q = q.gte(
      "discovered_at",
      new Date(Date.now() - days * 86400000).toISOString(),
    );
  return check(
    await q
      .order("discovered_at", { ascending: sort === "oldest" })
      .range(page * 20, page * 20 + 19),
  ) as FoundItem[];
}
export async function item(id: string) {
  return check(
    await supabase.from("found_items").select("*").eq("id", id).single(),
  ) as FoundItem;
}
export async function reports() {
  return check(
    await supabase
      .from("missing_reports")
      .select("*")
      .order("created_at", { ascending: false }),
  ) as MissingReport[];
}
export async function matches() {
  return check(
    await supabase
      .from("item_matches")
      .select("*,found_items!inner(*),missing_reports!inner(*)")
      .eq("status", "active")
      .eq("missing_reports.status", "active")
      .eq("found_items.status", "available")
      .order("match_score", { ascending: false }),
  ) as Match[];
}
export async function profile(id: string) {
  return check(
    await supabase.from("profiles").select("*").eq("id", id).single(),
  ) as Profile;
}
export async function pickPhoto(camera = false) {
  const permission = camera
    ? await ImagePicker.requestCameraPermissionsAsync()
    : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted)
    throw new Error(
      "Photo permission is needed. You can enable it in device settings.",
    );
  const result = await (
    camera ? ImagePicker.launchCameraAsync : ImagePicker.launchImageLibraryAsync
  )({ mediaTypes: ["images"], quality: 0.8 });
  return result.canceled ? null : result.assets[0];
}
export async function uploadPhoto(
  asset: ImagePicker.ImagePickerAsset,
  bucket: string,
  userId: string,
) {
  const bytes = await new File(asset.uri).bytes();
  if (bytes.byteLength > 10 * 1024 * 1024)
    throw new Error("Please choose a photograph smaller than 10 MB.");
  const mime = asset.mimeType || "image/jpeg";
  const ext =
    mime === "image/png" ? "png" : mime === "image/webp" ? "webp" : "jpg";
  const path = `${userId}/${Date.now()}-${Math.random().toString(36).slice(2)}.${ext}`;
  check(
    await supabase.storage
      .from(bucket)
      .upload(path, bytes, { contentType: mime }),
  );
  return path;
}
export async function createReport(
  value: Omit<MissingReport, "id" | "created_at" | "status">,
) {
  return check(
    await supabase.from("missing_reports").insert(value).select().single(),
  ) as MissingReport;
}
export async function requestSearch(report: MissingReport) {
  check(
    await supabase.from("search_requests").insert({
      user_id: report.user_id,
      missing_report_id: report.id,
      target_location: report.last_seen_location,
    }),
  );
}
