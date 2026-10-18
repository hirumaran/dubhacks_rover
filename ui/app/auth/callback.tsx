import { exchangeCode } from "../../src/lib/auth";
import React, { useEffect, useState } from "react";
import { useLocalSearchParams, router } from "expo-router";
import { Page, State } from "../../src/components/ui";
import { supabase, check } from "../../src/lib/supabase";
import { useSession } from "../../src/lib/session";
export default function Callback() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const { session } = useSession();
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    if (session) {
      router.replace("/(tabs)");
      return;
    }
    if (code)
      exchangeCode(code)
        .then(() => {
          router.replace("/(tabs)");
        })
        .catch(setError);
    else
      setError(
        new Error("Missing sign-in code. Return to sign in and try again."),
      );
  }, [code, session]);
  return (
    <Page>
      <State loading={!error} error={error} retry={() => router.replace("/")} />
    </Page>
  );
}
