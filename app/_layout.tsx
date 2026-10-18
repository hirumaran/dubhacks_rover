import "../global.css";
import React from "react";
import { Text } from "react-native";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionProvider, useSession } from "../src/lib/session";
import { SafeAreaProvider } from "react-native-safe-area-context";
import PushNavigation from "../src/components/PushNavigation";
import { Page, State, s } from "../src/components/ui";
const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
});
function Navigator() {
  const { session, ready, error, retry } = useSession();
  if (error)
    return (
      <Page>
        <State error={error} retry={retry} />
      </Page>
    );
  if (!ready)
    return (
      <Page>
        <Text style={s.heading}>
          {session?.user.is_anonymous
            ? "Preparing your campus…"
            : "Opening HuskyFind…"}
        </Text>
        <State loading />
      </Page>
    );
  return (
    <>
      <PushNavigation />
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: "#FAFAF7" },
          animation: "slide_from_right",
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="sign-in" />
        <Stack.Screen name="auth/callback" />
        <Stack.Protected guard={!!session}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="item/[id]" />
          <Stack.Screen name="claim" />
          <Stack.Screen name="collection" />
          <Stack.Screen name="info" />
        </Stack.Protected>
      </Stack>
    </>
  );
}
export default function Layout() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={client}>
        <SessionProvider>
          <Navigator />
        </SessionProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
