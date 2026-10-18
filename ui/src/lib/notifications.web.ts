export async function enablePush(): Promise<void> {
  throw new Error(
    "Device push notifications require the iOS or Android app. You can read in-app updates in Activity.",
  );
}
