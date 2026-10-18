import { useEffect } from "react";
import type {
  NotificationResponse,
  EventSubscription,
} from "expo-notifications";
import Constants from "expo-constants";
import { router } from "expo-router";
import { useSession } from "../lib/session";
export default function PushNavigation() {
  const { session } = useSession();
  useEffect(() => {
    if (!session || Constants.appOwnership === "expo") return;
    let active = true;
    let subscription: EventSubscription | undefined;
    let lastId: string | undefined;
    function open(response: NotificationResponse | null) {
      if (
        !active ||
        !response ||
        lastId === response.notification.request.identifier
      )
        return;
      lastId = response.notification.request.identifier;
      const data = response.notification.request.content.data || {};
      if (
        typeof data.itemId === "string" &&
        /^[a-f0-9-]{36}$/i.test(data.itemId)
      )
        router.push(`/item/${data.itemId}`);
      else router.push("/(tabs)/activity");
    }
    void import("expo-notifications")
      .then(async (Notifications) => {
        const response = await Notifications.getLastNotificationResponseAsync();
        if (!active) return;
        open(response);
        subscription =
          Notifications.addNotificationResponseReceivedListener(open);
      })
      .catch((error) =>
        console.warn("Notification navigation unavailable:", error.message),
      );
    return () => {
      active = false;
      subscription?.remove();
    };
  }, [session?.user.id]);
  return null;
}
