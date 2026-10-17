import React, { createContext, useContext, useEffect, useState } from "react";
import { AppState } from "react-native";
import { Session } from "@supabase/supabase-js";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "./supabase";
const Context = createContext<{ session: Session | null; ready: boolean }>({
  session: null,
  ready: false,
});
export const useSession = () => useContext(Context);
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const cache = useQueryClient();
  useEffect(() => {
    let alive = true;
    supabase.auth.getSession().then(({ data }) => {
      if (alive) {
        setSession(data.session);
        setReady(true);
      }
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setReady(true);
      if (_event === "SIGNED_OUT") cache.clear();
    });
    const state = AppState.addEventListener("change", (s) => {
      if (s === "active") {
        supabase.auth.startAutoRefresh();
        void cache.invalidateQueries();
      } else supabase.auth.stopAutoRefresh();
    });
    return () => {
      alive = false;
      data.subscription.unsubscribe();
      state.remove();
    };
  }, [cache]);
  useEffect(() => {
    if (!session) return;
    const channel = supabase.channel(`huskyfind-${session.user.id}`);
    for (const table of [
      "found_items",
      "missing_reports",
      "item_matches",
      "search_requests",
      "claims",
      "notifications",
    ])
      channel.on(
        "postgres_changes",
        { event: "*", schema: "public", table },
        () => {
          void cache.invalidateQueries();
        },
      );
    channel.subscribe((status) => {
      if (status === "SUBSCRIBED") void cache.invalidateQueries();
    });
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [session?.user.id, cache]);
  return (
    <Context.Provider value={{ session, ready }}>{children}</Context.Provider>
  );
}
