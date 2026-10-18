import React from "react";
import { Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { Page, Button, State, s } from "../../src/components/ui";
import { reports } from "../../src/lib/api";
export default function MapScreen() {
  const q = useQuery({ queryKey: ["my-private-search-areas"], queryFn: reports });
  return <Page>
    <Text style={s.label}>PRIVATE TO YOUR ACCOUNT</Text>
    <Text style={s.title}>Your search areas.</Text>
    <Text style={s.body}>Location helps match your missing items and plan rover searches in the background. Public listings do not show object GPS pins. Only your own reported search areas appear here.</Text>
    <State loading={q.isLoading} error={q.error} retry={() => q.refetch()} />
    {q.data?.length === 0 && <State empty="Report a missing item to start your private search." />}
    {q.data?.map(r => <View key={r.id} style={s.card}>
      <Text style={s.heading}>{r.title}</Text>
      <Text style={s.body}>{r.last_seen_location}</Text>
      <Text style={s.small}>{r.status} - Your last-seen area</Text>
    </View>)}
    <Button title="View my search activity" onPress={() => router.push("/(tabs)/activity")} />
  </Page>;
}
