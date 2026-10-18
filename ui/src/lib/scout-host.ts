import Constants from "expo-constants";
import { Platform } from "react-native";
import { expoOrigin } from "./scout";

export function scoutHost(): string {
  if (Platform.OS === "web" && typeof window !== "undefined")
    return window.location.origin;
  const host = Constants.expoConfig?.hostUri;
  if (!host)
    throw new Error(
      "Open this development project from the new Expo QR code to connect Scout.",
    );
  return expoOrigin(host);
}
