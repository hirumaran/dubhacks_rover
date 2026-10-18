import "react-native-url-polyfill/auto";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";
import { Platform } from "react-native";
const serverRender = Platform.OS === "web" && typeof window === "undefined";
const url = process.env.EXPO_PUBLIC_SUPABASE_URL;
const key = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
export const configured = Boolean(url && key);
export const supabase = createClient(
  url || "https://unconfigured.supabase.co",
  key || "unconfigured",
  {
    auth: {
      storage: serverRender ? undefined : AsyncStorage,
      autoRefreshToken: !serverRender,
      persistSession: !serverRender,
      detectSessionInUrl: false,
      flowType: "pkce",
    },
  },
);
export function check<
  T extends { data?: unknown; error: { message: string } | null },
>(result: T): NonNullable<T["data"]> {
  if (result.error) throw new Error(result.error.message);
  return result.data as NonNullable<T["data"]>;
}
export function photo(
  path: string | null | undefined,
  bucket = "found-photos",
) {
  if (!path) return undefined;
  return path.startsWith("https://")
    ? path
    : supabase.storage.from(bucket).getPublicUrl(path).data.publicUrl;
}
export async function privatePhoto(path: string, bucket = "missing-photos") {
  return check(await supabase.storage.from(bucket).createSignedUrl(path, 3600))
    .signedUrl;
}
