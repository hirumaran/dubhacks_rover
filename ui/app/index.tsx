import { Alert } from "../src/lib/dialog";
import { exchangeCode } from "../src/lib/auth";
import React, { useState } from "react";
import { Text, View } from "react-native";
import { Redirect, router } from "expo-router";
import { LocateFixed, MapPin, Sparkles } from "lucide-react-native";
import * as WebBrowser from "expo-web-browser";
import { makeRedirectUri } from "expo-auth-session";
import { Page, Button, s, colors } from "../src/components/ui";
import { supabase, check, configured } from "../src/lib/supabase";
import { useSession } from "../src/lib/session";
WebBrowser.maybeCompleteAuthSession();
export default function Welcome() {
  const { session } = useSession();
  const [busy, setBusy] = useState(false);
  const demoEnabled = process.env.EXPO_PUBLIC_ENABLE_DEMO_AUTH === "true";
  const uwEnabled = !!process.env.EXPO_PUBLIC_UW_SSO_PROVIDER_ID;
  if (session) return <Redirect href="/(tabs)" />;
  async function login(demo: boolean) {
    setBusy(true);
    try {
      if (!configured)
        throw new Error(
          "Add the Expo Supabase environment variables, then restart Expo.",
        );
      if (demo) {
        check(await supabase.auth.signInAnonymously());
      } else {
        const providerId = process.env.EXPO_PUBLIC_UW_SSO_PROVIDER_ID;
        if (!providerId)
          throw new Error(
            "UW institutional sign-in is not configured yet. Explore Demo uses a real Supabase anonymous account. No UW password is collected.",
          );
        const redirectTo = makeRedirectUri({
          scheme: "huskyfind",
          path: "auth/callback",
        });
        const data = check(
          await supabase.auth.signInWithSSO({
            providerId,
            options: { redirectTo, skipBrowserRedirect: true },
          }),
        );
        const result = await WebBrowser.openAuthSessionAsync(
          data.url,
          redirectTo,
        );
        if (result.type === "success") {
          const url = new URL(result.url);
          const code = url.searchParams.get("code");
          if (!code)
            throw new Error(
              url.searchParams.get("error_description") ||
                "No authorization code returned.",
            );
          await exchangeCode(code);
        }
      }
    } catch (e) {
      Alert.alert(
        "Sign-in unavailable",
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page>
      <View style={{ paddingTop: 26, gap: 30 }}>
        <Text style={s.label}>UNIVERSITY OF WASHINGTON · SEATTLE</Text>
        <View
          style={{
            height: 300,
            backgroundColor: "#EEE8F5",
            borderRadius: 45,
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
          }}
        >
          <View
            style={{
              position: "absolute",
              width: 240,
              height: 240,
              borderRadius: 120,
              borderWidth: 1,
              borderColor: "#D6C8E7",
            }}
          />
          <View
            style={{
              position: "absolute",
              width: 170,
              height: 170,
              borderRadius: 85,
              borderWidth: 1,
              borderColor: "#D6C8E7",
            }}
          />
          <View
            style={{
              backgroundColor: colors.sage,
              width: 105,
              height: 105,
              borderRadius: 34,
              alignItems: "center",
              justifyContent: "center",
              transform: [{ rotate: "-12deg" }],
            }}
          >
            <LocateFixed color="white" size={62} />
          </View>
          <View
            style={{
              position: "absolute",
              bottom: 24,
              right: 20,
              backgroundColor: colors.peach,
              padding: 15,
              borderRadius: 20,
            }}
          >
            <Text style={{ fontWeight: "700" }}>A little closer to found.</Text>
          </View>
          <MapPin
            color={colors.sage}
            size={25}
            style={{ position: "absolute", top: 35, right: 40 }}
          />
          <Sparkles
            color={colors.sage}
            size={25}
            style={{ position: "absolute", bottom: 55, left: 30 }}
          />
        </View>
        <View style={{ gap: 14 }}>
          <Text style={[s.title, { fontSize: 48 }]}>
            HuskyFind<Text style={{ color: colors.sage }}>.</Text>
          </Text>
          <Text style={[s.heading, { fontSize: 28 }]}>
            Lost on campus.{"\n"}Found by HuskyFind.
          </Text>
          <Text style={s.body}>
            Find your missing belongings, discover items around campus, and get
            notified when something matching yours turns up.
          </Text>
        </View>
        <View style={{ gap: 12 }}>
          {demoEnabled && (
            <Button
              title={busy ? "Opening your campus…" : "Explore Demo"}
              onPress={() => login(true)}
              disabled={busy}
            />
          )}
          <Button
            title="Sign in to HuskyFind"
            onPress={() => router.push("/sign-in")}
            secondary={demoEnabled}
            disabled={busy}
          />
          {uwEnabled && (
            <Button
              title={busy ? "Connecting…" : "Continue with UW NetID"}
              onPress={() => login(false)}
              secondary
              disabled={busy}
            />
          )}
          <Text style={[s.small, { textAlign: "center" }]}>
            Made for Huskies. Built around community.
            {demoEnabled
              ? "\nDemo uses a separate anonymous account."
              : "\nSign in with your team's HuskyFind account."}
          </Text>
        </View>
      </View>
    </Page>
  );
}
