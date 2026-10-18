import { Alert } from "../../src/lib/dialog";
import React, { useState } from "react";
import { Image, Platform, ScrollView, Share, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Page, Back, Button, Field, State, s } from "../../src/components/ui";
import { item } from "../../src/lib/api";
import { supabase, check, photo } from "../../src/lib/supabase";
export default function Detail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const cache = useQueryClient();
  const q = useQuery({ queryKey: ["item", id], queryFn: () => item(id) });
  const saved = useQuery({
    queryKey: ["saved", id],
    queryFn: async () =>
      check(
        await supabase
          .from("saved_items")
          .select("*")
          .eq("found_item_id", id)
          .maybeSingle(),
      ),
  });
  const [reason, setReason] = useState("");
  const [correction, setCorrection] = useState(false);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      check(
        saved.data
          ? await supabase.from("saved_items").delete().eq("found_item_id", id)
          : await supabase.from("saved_items").insert({ found_item_id: id }),
      );
      await cache.invalidateQueries({ queryKey: ["saved"] });
    } catch (e) {
      Alert.alert("Couldn’t save", String(e));
    } finally {
      setBusy(false);
    }
  }
  async function report() {
    if (!reason.trim()) return;
    setBusy(true);
    try {
      check(
        await supabase
          .from("listing_reports")
          .insert({ found_item_id: id, reason: reason.trim() }),
      );
      setCorrection(false);
      setReason("");
      Alert.alert(
        "Thanks for looking out",
        "Your correction was sent for human review.",
      );
    } catch (e) {
      Alert.alert("Couldn’t send", String(e));
    } finally {
      setBusy(false);
    }
  }
  const i = q.data;
  return (
    <Page>
      <Back />
      <State loading={q.isLoading} error={q.error} retry={() => q.refetch()} />
      {i && (
        <>
          <ScrollView
            horizontal
            pagingEnabled
            showsHorizontalScrollIndicator={false}
          >
            {[i.image_path, ...(i.image_paths || [])].map((p, n) => (
              <Image
                key={n}
                source={{ uri: photo(p) }}
                style={{
                  width: 320,
                  height: 330,
                  borderRadius: 28,
                  marginRight: 12,
                  backgroundColor: "#EEE8F5",
                }}
              />
            ))}
          </ScrollView>
          <Text style={s.label}>
            {i.is_demo ? "DEMO · " : ""}
            {i.source === "rover" ? "ROVER FOUND" : "COMMUNITY FOUND"} ·{" "}
            {i.status}
          </Text>
          <Text style={s.title}>{i.title}</Text>
          <Text style={s.body}>{i.description}</Text>
          <View style={s.row}>
            <Text style={s.body}>{i.category}</Text>
            <Text style={s.body}>· {i.color}</Text>
          </View>
          <View style={s.card}>
            <Text style={s.heading}>Discovery location kept private</Text>
            <Text style={s.body}>
              Discovered {new Date(i.discovered_at).toLocaleString()}
            </Text>
            {i.pickup_location ? (
              <>
                <Text style={s.label}>CONFIRMED PICKUP DESK</Text>
                <Text style={s.body}>{i.pickup_location}</Text>
              </>
            ) : (
              <Text style={s.body}>
                {i.source === "rover"
                  ? "This item was spotted by a rover. It may have moved; its physical location is not guaranteed."
                  : "Discovery location is approximate. A pickup location has not been confirmed."}
              </Text>
            )}
          </View>
          <Button
            title="This might be mine"
            disabled={i.status !== "available"}
            onPress={() =>
              router.push({ pathname: "/claim", params: { id: i.id } })
            }
          />
          <Button
            title={saved.data ? "Remove from saved" : "Save item"}
            secondary
            disabled={busy || saved.isLoading}
            onPress={save}
          />
          <Button
            title="Share listing"
            secondary
            onPress={() => {
              const url = `https://huskyfind-uw.expo.app/item/${i.id}`;
              if (Platform.OS === "web") {
                Alert.alert("Share this item", url, [
                  { text: "Copy link", onPress: () => {
                    void Promise.race([
                      navigator.clipboard.writeText(url),
                      new Promise((_, reject) => setTimeout(() => reject(new Error("Copy unavailable")), 1500)),
                    ]).then(() => Alert.alert("Link copied", "Paste the link to share this item."))
                      .catch(() => Alert.alert("Copy this link", url));
                  } },
                  { text: "Done", style: "cancel" },
                ]);
              } else {
                void Share.share({ message: `${i.title}\n${url}` }).catch(e => Alert.alert("Share", String(e)));
              }
            }}
          />
          <Button
            title="Report incorrect information"
            secondary
            onPress={() => setCorrection(!correction)}
          />
          {correction && (
            <View style={s.card}>
              <Field
                label="What needs correcting?"
                value={reason}
                onChangeText={setReason}
                multiline
              />
              <Button
                title="Send for review"
                disabled={busy || !reason.trim()}
                onPress={report}
              />
            </View>
          )}
        </>
      )}
    </Page>
  );
}
