import { Alert } from "../../src/lib/dialog";
import React, { useState } from "react";
import { Image, Platform, Pressable, Text, View } from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, User } from "lucide-react-native";
import { Page, Button, Field, State, s, colors } from "../../src/components/ui";
import { useSession } from "../../src/lib/session";
import { profile, pickPhoto, uploadPhoto } from "../../src/lib/api";
import { check, supabase, photo } from "../../src/lib/supabase";
import { enablePush } from "../../src/lib/notifications";
export default function ProfileScreen() {
  const { session } = useSession();
  const cache = useQueryClient();
  const q = useQuery({
    queryKey: ["profile", session?.user.id],
    queryFn: () => profile(session!.user.id),
    enabled: !!session,
  });
  const [name, setName] = useState<string>();
  const [busy, setBusy] = useState(false);
  async function action(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await cache.invalidateQueries();
    } catch (e) {
      Alert.alert("Profile", String(e));
    } finally {
      setBusy(false);
    }
  }
  const p = q.data;
  return (
    <Page>
      <Text style={s.label}>YOUR LITTLE CORNER OF CAMPUS</Text>
      <Text style={s.title}>Hello, Husky.</Text>
      <State loading={q.isLoading} error={q.error} retry={() => q.refetch()} />
      {p && (
        <>
          <View style={[s.card, { alignItems: "center", padding: 28 }]}>
            {p.avatar_url ? (
              <Image
                source={{ uri: photo(p.avatar_url, "avatars") }}
                style={{ width: 90, height: 90, borderRadius: 45 }}
              />
            ) : (
              <View
                style={{
                  padding: 24,
                  borderRadius: 50,
                  backgroundColor: "#EEE8F5",
                }}
              >
                <User size={42} color={colors.sage} />
              </View>
            )}
            <Text style={s.heading}>{p.display_name}</Text>
            <Text style={s.body}>{p.campus}</Text>
            <Text style={s.label}>
              {session?.user.is_anonymous
                ? "DEMO EXPLORER"
                : p.university_verified
                  ? "UW VERIFIED"
                  : "UNIVERSITY NOT VERIFIED"}
            </Text>
            <Button
              title="Change profile photo"
              secondary
              disabled={busy}
              onPress={() =>
                action(async () => {
                  const asset = await pickPhoto();
                  if (asset) {
                    const path = await uploadPhoto(asset, "avatars", p.id);
                    check(
                      await supabase
                        .from("profiles")
                        .update({ avatar_url: path })
                        .eq("id", p.id),
                    );
                  }
                })
              }
            />
          </View>
          <Field
            label="Display name"
            value={name ?? p.display_name}
            onChangeText={setName}
          />
          <Button
            title="Save profile"
            disabled={busy || !name?.trim()}
            onPress={() =>
              action(async () => {
                check(
                  await supabase
                    .from("profiles")
                    .update({ display_name: name?.trim() })
                    .eq("id", p.id),
                );
                setName(undefined);
              })
            }
          />
          {[
            ["My Missing Items", "reports"],
            ["My Claims", "claims"],
            ["Saved Items", "saved"],
            ["Search History", "searches"],
          ].map(([label, kind]) => (
            <Pressable
              key={kind}
              accessibilityRole="button"
              onPress={() =>
                router.push({ pathname: "/collection", params: { kind } })
              }
              style={[s.card, s.row, { justifyContent: "space-between" }]}
            >
              <Text style={{ fontWeight: "600", fontSize: 16 }}>{label}</Text>
              <ChevronRight size={20} color={colors.muted} />
            </Pressable>
          ))}
          <Button
            title="Notifications"
            secondary
            onPress={() => router.push("/(tabs)/activity")}
          />
          {Platform.OS !== "web" && <Button
            title="Enable device push notifications"
            secondary
            disabled={busy}
            onPress={() => action(enablePush)}
          />}
          <Button
            title={
              p.notifications_enabled
                ? "Pause push updates"
                : "Resume push updates"
            }
            secondary
            disabled={busy}
            onPress={() =>
              action(async () =>
                check(
                  await supabase
                    .from("profiles")
                    .update({ notifications_enabled: !p.notifications_enabled })
                    .eq("id", p.id),
                ),
              )
            }
          />
          <Button
            title="Privacy & Security"
            secondary
            onPress={() =>
              router.push({ pathname: "/info", params: { kind: "privacy" } })
            }
          />
          <Button
            title="Help & Support"
            secondary
            onPress={() =>
              router.push({ pathname: "/info", params: { kind: "help" } })
            }
          />
          <Button
            title="Sign out"
            secondary
            disabled={busy}
            onPress={() =>
              Alert.alert(
                "Sign out?",
                session?.user.is_anonymous
                  ? "This anonymous demo account cannot be recovered after signing out."
                  : "You can sign in again with your institutional account.",
                [
                  { text: "Cancel", style: "cancel" },
                  {
                    text: "Sign out",
                    onPress: () =>
                      action(async () => {
                        check(await supabase.auth.signOut());
                        router.replace("/");
                      }),
                  },
                ],
              )
            }
          />
        </>
      )}
    </Page>
  );
}
