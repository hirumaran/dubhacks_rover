import Constants from "expo-constants";
import * as Device from "expo-device";
import { Platform } from "react-native";
import { supabase, check } from "./supabase";
export async function enablePush() {
  if (Constants.appOwnership === "expo")
    throw new Error(
      "Device push requires a HuskyFind development build. In-app notifications still work in Expo Go.",
    );
  if (!Device.isDevice)
    throw new Error(
      "Push notifications require a physical device and an Expo development build.",
    );
  const projectId = process.env.EXPO_PUBLIC_EAS_PROJECT_ID;
  if (!projectId)
    throw new Error(
      "Push setup needs an EAS project ID. In-app notifications already work.",
    );
  const Notifications = await import("expo-notifications");
  if (Platform.OS === "android")
    await Notifications.setNotificationChannelAsync("default", {
      name: "HuskyFind updates",
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  let permission = await Notifications.getPermissionsAsync();
  if (permission.status !== "granted")
    permission = await Notifications.requestPermissionsAsync();
  if (permission.status !== "granted")
    throw new Error(
      "Notifications were not enabled. You can change this in device settings.",
    );
  const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  check(await supabase.from("push_tokens").upsert({ token }));
}
