import { Alert } from "../src/lib/dialog";
import React, { useState } from "react";
import { Linking, Text } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { Page, Back, Button, s } from "../src/components/ui";
import { check, supabase } from "../src/lib/supabase";
import { useSession } from "../src/lib/session";
export default function Info() {
  const { kind } = useLocalSearchParams<{ kind: string }>();
  const { session } = useSession();
  const [busy, setBusy] = useState(false);
  async function remove() {
    setBusy(true);
    try {
      for (const bucket of [
        "missing-photos",
        "ownership-evidence",
        "avatars",
      ]) {
        let more = true;
        while (more) {
          const files = check(
            await supabase.storage
              .from(bucket)
              .list(session!.user.id, { limit: 100 }),
          );
          more = files.length > 0;
          if (more)
            check(
              await supabase.storage
                .from(bucket)
                .remove(files.map((f) => `${session!.user.id}/${f.name}`)),
            );
        }
      }
      check(await supabase.rpc("delete_my_account"));
      await supabase.auth.signOut({ scope: "local" });
      router.replace("/");
    } catch (e) {
      Alert.alert("Couldn’t delete account", String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page>
      <Back />
      <Text style={s.title}>
        {kind === "privacy" ? "Your privacy matters." : "A little help, Husky."}
      </Text>
      {kind === "privacy" ? (
        <>
          <Text style={s.heading}>Private by design</Text>
          <Text style={s.body}>
            Your profile, missing-item reports, search requests, and ownership
            answers are private. Authorized reviewers can access claim evidence.
            Object GPS coordinates are hidden from public listings. Only your own
            last-seen search areas appear in My areas; coordinates remain available
            privately to server matching and rover planning.
          </Text>
          <Text style={s.heading}>You’re in control</Text>
          <Text style={s.body}>
            Change notification preferences in Profile. You can remove saved
            items, resolve missing reports, or permanently delete your account
            and uploaded photos below.
          </Text>
          <Text style={s.body}>
            Demo accounts are anonymous. If you sign out, you cannot recover
            that account. Demo records are separate from real campus listings.
          </Text>
          <Button
            title={busy ? "Deleting…" : "Delete my account and data"}
            disabled={busy}
            secondary
            onPress={() =>
              Alert.alert(
                "Permanently delete your account?",
                "This removes your reports, claims, saved items, notifications, and uploaded photos. It cannot be undone.",
                [
                  { text: "Cancel", style: "cancel" },
                  {
                    text: "Delete account",
                    style: "destructive",
                    onPress: remove,
                  },
                ],
              )
            }
          />
        </>
      ) : (
        <>
          <Text style={s.heading}>How do I recover an item?</Text>
          <Text style={s.body}>
            Open a found item and choose “This might be mine.” Share
            distinguishing details privately. An authorized reviewer checks your
            claim. A confirmed pickup desk appears on the listing when one has
            been assigned.
          </Text>
          <Text style={s.heading}>What does a rover search mean?</Text>
          <Text style={s.body}>
            Demo searches receive a saved plan from a virtual rover fleet. This is
            simulated dispatch. Real searches queue until an available rover
            reports in. A camera detection does not mean an item has been collected.
          </Text>
          <Text style={s.heading}>Need campus assistance?</Text>
          <Text style={s.body}>
            HuskyFind is an independent campus project, not an official UW
            service. Use the university’s official website to find current
            lost-and-found contact information.
          </Text>
          <Button
            title="Open University of Washington"
            secondary
            onPress={() => {
              void Linking.openURL("https://www.washington.edu/").catch((e) =>
                Alert.alert("Unable to open browser", String(e)),
              );
            }}
          />
        </>
      )}
    </Page>
  );
}
