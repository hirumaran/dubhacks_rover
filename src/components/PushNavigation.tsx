import { useEffect } from "react";
import * as Notifications from "expo-notifications";
import { router } from "expo-router";
import { useSession } from "../lib/session";
export default function PushNavigation() {
  const { session } = useSession();
  useEffect(() => {
    if (!session) return;
    let lastId: string | undefined;
    function open(response: Notifications.NotificationResponse | null) {
      if (!response || lastId === response.notification.request.identifier)
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
    void Notifications.getLastNotificationResponseAsync().then(open);
    const subscription =
      Notifications.addNotificationResponseReceivedListener(open);
    return () => subscription.remove();
  }, [session?.user.id]);
  return null;
}
