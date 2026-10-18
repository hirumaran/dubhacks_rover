import * as ImagePicker from "expo-image-picker";
import { File } from "expo-file-system";
import { Platform } from "react-native";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { supabase, check } from "./supabase";
import { FoundItem, MissingReport, Match, Profile } from "./types";
export const FOUND_PUBLIC_COLUMNS = "id,title,description,category,color,image_path,image_paths,approximate_location,source,rover_id,status,pickup_location,discovered_at,created_at,is_demo";
export async function foundItems(
  search = "",
  category = "All",
  page = 0,
  sort = "newest",
  source = "all",
  days = 0,
) {
  let q = supabase.from("found_items").select(FOUND_PUBLIC_COLUMNS).eq("status", "available");
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
  ) as unknown as FoundItem[];
}
export async function item(id: string) {
  return check(
    await supabase.from("found_items").select(FOUND_PUBLIC_COLUMNS).eq("id", id).single(),
  ) as unknown as FoundItem;
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
      .select(`*,found_items!inner(${FOUND_PUBLIC_COLUMNS}),missing_reports!inner(*)`)
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
  const scale = Math.min(1, 1280 / asset.width, 1280 / asset.height);
  const normalized = await manipulateAsync(
    asset.uri,
    [
      {
        resize: {
          width: Math.max(1, Math.round(asset.width * scale)),
          height: Math.max(1, Math.round(asset.height * scale)),
        },
      },
    ],
    { format: SaveFormat.JPEG, compress: 0.85 },
  );
  const bytes =
    Platform.OS === "web"
      ? new Uint8Array(await (await fetch(normalized.uri)).arrayBuffer())
      : await new File(normalized.uri).bytes();
  if (bytes.byteLength > 10 * 1024 * 1024)
    throw new Error("Please choose a photograph smaller than 10 MB.");
  const mime = "image/jpeg";
  const ext = "jpg";
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
export interface SearchPlan {
  request_id: string;
  rover_id: string | null;
  rover_name: string | null;
  status: string;
  demo: boolean;
  reason: string;
  distance_m: number | null;
  brief: {
    target: string;
    category: string;
    color: string;
    visual_cues: string;
    search_area: string;
    instruction: string;
    matching_weights: Record<string, number>;
  };
}
export async function invokeCloud<T>(
  name: string,
  body: Record<string, unknown>,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);
  try {
    const { data, error } = await supabase.functions.invoke(name, {
      body,
      signal: controller.signal,
    });
    if (error) {
      let message = error.message;
      if (error.context instanceof Response) {
        try {
          const detail = await error.context.json();
          message = detail.error || detail.message || message;
        } catch {}
      }
      throw new Error(message);
    }
    return data as T;
  } finally {
    clearTimeout(timeout);
  }
}
export async function requestSearch(report: MissingReport) {
  return invokeCloud<SearchPlan>("plan-search", { report_id: report.id });
}
