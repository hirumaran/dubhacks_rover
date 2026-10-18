import { FOUND_PUBLIC_COLUMNS } from "../src/lib/api";
import PrivatePhoto from "../src/components/PrivatePhoto";
import React from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Page, Back, ItemCard, State, s } from "../src/components/ui";
import { supabase, check } from "../src/lib/supabase";
import { FoundItem } from "../src/lib/types";
export default function Collection() {
  const { kind = "reports" } = useLocalSearchParams<{ kind: string }>();
  const table =
    (
      {
        reports: "missing_reports",
        claims: "claims",
        saved: "saved_items",
        searches: "search_requests",
      } as Record<string, string>
    )[kind] || "missing_reports";
  const q = useQuery({
    queryKey: [kind, "collection"],
    queryFn: async () =>
      check(
        await supabase
          .from(table)
          .select(
            kind === "saved" || kind === "claims" ? `*,found_items(${FOUND_PUBLIC_COLUMNS})` : "*",
          )
          .order("created_at", { ascending: false }),
      ),
  });
  return (
    <Page>
      <Back />
      <Text style={s.title}>
        {
          (
            {
              reports: "My missing items",
              claims: "My claims",
              saved: "Saved items",
              searches: "Search history",
            } as Record<string, string>
          )[kind]
        }
      </Text>
      <State
        loading={q.isLoading}
        error={q.error}
        empty={!q.data?.length ? "Your items will appear here." : undefined}
        retry={() => q.refetch()}
      />
      {q.data?.map((row: any) => (
        <View key={row.id || row.found_item_id} style={s.card}>
          {row.found_items && (
            <ItemCard item={row.found_items as FoundItem} wide />
          )}
          {row.image_path && <PrivatePhoto path={row.image_path} />}
          {row.evidence_path && (
            <PrivatePhoto
              path={row.evidence_path}
              bucket="ownership-evidence"
            />
          )}
          {row.title && <Text style={s.heading}>{row.title}</Text>}
          <Text style={s.body}>
            {row.last_seen_location || row.target_location}
          </Text>
          {row.status && (
            <Text style={s.label}>{row.status.replaceAll("_", " ")}</Text>
          )}
          {row.verification_details && (
            <>
              <Text style={s.body}>
                Private evidence: {row.verification_details.features}
              </Text>
              <Text style={s.body}>
                {row.verification_details.where_and_when}
              </Text>
            </>
          )}
          <Text style={s.small}>
            {new Date(row.created_at).toLocaleString()}
          </Text>
        </View>
      ))}
    </Page>
  );
}
