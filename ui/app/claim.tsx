import { Alert } from "../src/lib/dialog";
import React, { useState } from "react";
import { Image, Text } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { ImagePickerAsset } from "expo-image-picker";
import { useQueryClient } from "@tanstack/react-query";
import { Page, Back, Button, Field, s } from "../src/components/ui";
import { pickPhoto, uploadPhoto } from "../src/lib/api";
import { supabase, check } from "../src/lib/supabase";
import { useSession } from "../src/lib/session";
export default function Claim() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { session } = useSession();
  const cache = useQueryClient();
  const [features, setFeatures] = useState("");
  const [where, setWhere] = useState("");
  const [additional, setAdditional] = useState("");
  const [image, setImage] = useState<ImagePickerAsset | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    if (!session) return;
    setBusy(true);
    try {
      const evidence_path = image
        ? await uploadPhoto(image, "ownership-evidence", session.user.id)
        : null;
      check(
        await supabase.from("claims").insert({
          found_item_id: id,
          user_id: session.user.id,
          verification_details: {
            features: features.trim(),
            where_and_when: where.trim(),
            additional: additional.trim(),
          },
          evidence_path,
        }),
      );
      await cache.invalidateQueries();
      Alert.alert(
        "Claim submitted",
        "An authorized person will review your evidence. Follow its progress in My Claims.",
        [
          {
            text: "View claims",
            onPress: () =>
              router.replace({
                pathname: "/collection",
                params: { kind: "claims" },
              }),
          },
        ],
      );
    } catch (e) {
      if (String(e).includes("claims_user_id_found_item_id_key")) {
        Alert.alert("You already have a claim", "Your claim is saved. Open My Claims to follow its review.", [{ text: "View claims", onPress: () => router.replace({ pathname: "/collection", params: { kind: "claims" } }) }]);
      } else Alert.alert("Couldn’t submit claim", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page>
      <Back />
      <Text style={s.label}>A LITTLE PROOF. A HAPPY REUNION.</Text>
      <Text style={s.title}>Make it yours, again.</Text>
      <Text style={s.body}>
        Your answers are private. Only you and authorized reviewers can access
        them. A person makes the ownership decision.
      </Text>
      <Field
        label="Distinguishing features"
        placeholder="A hidden sticker, engraving, or unique detail…"
        value={features}
        onChangeText={setFeatures}
        multiline
      />
      <Field
        label="Where and when did you lose it?"
        value={where}
        onChangeText={setWhere}
        multiline
      />
      <Field
        label="Additional evidence"
        value={additional}
        onChangeText={setAdditional}
        multiline
      />
      {image && (
        <Image
          source={{ uri: image.uri }}
          style={{ height: 200, borderRadius: 20 }}
        />
      )}
      <Button
        title={
          image ? "Replace earlier photograph" : "Add an earlier photograph"
        }
        secondary
        onPress={async () => {
          try {
            const p = await pickPhoto();
            if (p) setImage(p);
          } catch (e) {
            Alert.alert("Photo", String(e));
          }
        }}
      />
      <Button
        title={busy ? "Submitting…" : "Submit ownership claim"}
        disabled={busy || !features.trim() || !where.trim()}
        onPress={submit}
      />
    </Page>
  );
}
