import React, { createContext, useContext, useEffect, useState } from "react";
import { AppState } from "react-native";
import { Session } from "@supabase/supabase-js";
import { useQueryClient } from "@tanstack/react-query";
import { check, supabase } from "./supabase";
const Context = createContext<{
  session: Session | null;
  ready: boolean;
  error: Error | null;
  retry: () => void;
}>({
  session: null,
  ready: false,
  error: null,
  retry: () => {},
});
export const useSession = () => useContext(Context);
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [demoUserId, setDemoUserId] = useState<string | null>(null);
  const [demoError, setDemoError] = useState<Error | null>(null);
  const cache = useQueryClient();
  useEffect(() => {
    let alive = true;
    setReady(false);
    setError(null);
    const timeout = setTimeout(() => {
      if (alive) {
        setError(
          new Error(
            "Sign-in is taking too long. Check your internet connection and try again.",
          ),
        );
        setReady(true);
      }
    }, 20000);
    supabase.auth
      .getSession()
      .then(({ data, error: authError }) => {
        clearTimeout(timeout);
        if (authError) throw authError;
        if (alive) {
          setError(null);
          setSession(data.session);
          setReady(true);
        }
      })
      .catch((reason) => {
        clearTimeout(timeout);
        if (alive) {
          setError(
            reason instanceof Error ? reason : new Error(String(reason)),
          );
          setReady(true);
        }
      });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      if (!alive) return;
      clearTimeout(timeout);
      setError(null);
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
      clearTimeout(timeout);
      data.subscription.unsubscribe();
      state.remove();
    };
  }, [cache, attempt]);
  // Seed before mounting any account screens, including on session restore.
  // Keep database calls outside onAuthStateChange to avoid auth-lock deadlocks.
  useEffect(() => {
    if (!session?.user.is_anonymous) {
      setDemoUserId(null);
      setDemoError(null);
      return;
    }
    let alive = true;
    const userId = session.user.id;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    setDemoError(null);
    setDemoUserId(null);
    void (async () => {
      try {
        check(
          await supabase.rpc("initialize_demo").abortSignal(controller.signal),
        );
        if (alive) {
          setDemoUserId(userId);
          void cache.invalidateQueries();
        }
      } catch (reason) {
        if (alive)
          setDemoError(
            new Error(
              `Couldn’t prepare your demo. Check your connection and try again. ${reason instanceof Error ? reason.message : String(reason)}`,
            ),
          );
      } finally {
        clearTimeout(timeout);
      }
    })();
    return () => {
      alive = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [session?.user.id, session?.user.is_anonymous, attempt, cache]);
  useEffect(() => {
    if (!session) return;
    const channel = supabase.channel(`huskyfind-${session.user.id}`);
    for (const table of [
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
    <Context.Provider
      value={{
        session,
        ready:
          ready &&
          (!session?.user.is_anonymous || demoUserId === session.user.id),
        error: error || demoError,
        retry: () => setAttempt((value) => value + 1),
      }}
    >
      {children}
    </Context.Provider>
  );
}
