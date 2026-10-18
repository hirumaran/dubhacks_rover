import PrivatePhoto from "../../src/components/PrivatePhoto";
import React from "react";
import { Alert, Text, View } from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Page, Button, ItemCard, State, s } from "../../src/components/ui";
import { reports, matches, requestSearch } from "../../src/lib/api";
import { supabase, check } from "../../src/lib/supabase";
import { matchLabel } from "../../src/lib/matching";
export default function Activity() {
  const cache = useQueryClient();
  const r = useQuery({ queryKey: ["reports"], queryFn: reports });
  const m = useQuery({ queryKey: ["matches"], queryFn: matches });
  const searches = useQuery({
    queryKey: ["searches"],
    queryFn: async () =>
      check(
        await supabase
          .from("search_requests")
          .select("*,rovers(name)")
          .order("created_at", { ascending: false }),
      ),
  });
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: async () =>
      check(
        await supabase
          .from("notifications")
          .select("*")
          .order("created_at", { ascending: false }),
      ),
  });
  async function action(fn: () => Promise<unknown>) {
    try {
      await fn();
      await cache.invalidateQueries();
    } catch (e) {
      Alert.alert("Couldn’t update", String(e));
    }
  }
  return (
    <Page>
      <Text style={s.label}>GOOD THINGS FIND THEIR WAY BACK</Text>
      <Text style={s.title}>Your activity.</Text>
      <Text style={s.heading}>Possible matches</Text>
      <State
        loading={m.isLoading}
        error={m.error}
        empty={
          !m.data?.length
            ? "New matches will appear here as items are discovered."
            : undefined
        }
        retry={() => m.refetch()}
      />
      {m.data?.map((match) => (
        <View key={match.id} style={s.card}>
          <Text style={s.label}>{matchLabel(match.match_score)}</Text>
          <Text style={s.body}>For your {match.missing_reports?.title}</Text>
          <ItemCard item={match.found_items} wide />
          <Text style={s.body}>{match.match_reasons.join(" · ")}</Text>
          <Button
            title="Not my item"
            secondary
            onPress={() =>
              action(async () =>
                check(
                  await supabase
                    .from("item_matches")
                    .update({ status: "dismissed" })
                    .eq("id", match.id),
                ),
              )
            }
          />
        </View>
      ))}
      <Text style={s.heading}>My searches</Text>
      <State
        loading={r.isLoading}
        error={r.error}
        empty={
          !r.data?.length
            ? "Report a missing item to start your search."
            : undefined
        }
        retry={() => r.refetch()}
      />
      {r.data?.map((report) => (
        <View key={report.id} style={s.card}>
          <PrivatePhoto path={report.image_path} />
          <Text style={s.heading}>{report.title}</Text>
          <Text style={s.body}>
            {report.last_seen_location} · {report.status}
          </Text>
          <Text style={s.small}>
            {m.data?.filter((x) => x.missing_report_id === report.id).length ||
              0}{" "}
            potential matches
          </Text>
          {report.status === "active" && (
            <>
              <Button
                title="Request rover search"
                secondary
                disabled={
                  searches.isLoading ||
                  Boolean(
                    searches.data?.some(
                      (x) => x.missing_report_id === report.id,
                    ),
                  )
                }
                onPress={() => action(() => requestSearch(report))}
              />
              <Button
                title="I found it — resolve report"
                secondary
                onPress={() =>
                  action(async () =>
                    check(
                      await supabase
                        .from("missing_reports")
                        .update({ status: "resolved" })
                        .eq("id", report.id),
                    ),
                  )
                }
              />
            </>
          )}
        </View>
      ))}
      <Text style={s.heading}>Rover search requests</Text>
      <State
        loading={searches.isLoading}
        error={searches.error}
        empty={
          !searches.data?.length
            ? "No requests yet. You can request a search after reporting an item."
            : undefined
        }
        retry={() => searches.refetch()}
      />
      {searches.data?.map((request) => (
        <View key={request.id} style={s.card}>
          <Text style={s.label}>{request.status.replaceAll("_", " ")}</Text>
          <Text style={s.heading}>{request.target_location}</Text>
          <Text style={s.body}>
            {request.rovers?.name || "Awaiting rover assignment"}
          </Text>
          <Text style={s.small}>
            Requested {new Date(request.created_at).toLocaleString()}
          </Text>
          {request.started_at && (
            <Text style={s.small}>
              Started {new Date(request.started_at).toLocaleString()}
            </Text>
          )}
          {request.completed_at && (
            <Text style={s.small}>
              Completed {new Date(request.completed_at).toLocaleString()}
            </Text>
          )}
        </View>
      ))}
      <Text style={s.heading}>Notifications</Text>
      <State
        loading={notifications.isLoading}
        error={notifications.error}
        empty={
          !notifications.data?.length ? "You’re all caught up." : undefined
        }
        retry={() => notifications.refetch()}
      />
      {notifications.data?.map((n) => (
        <View
          key={n.id}
          style={[s.card, !n.read_at && { backgroundColor: "#EAF0E8" }]}
        >
          <Text style={s.heading}>{n.title}</Text>
          <Text style={s.body}>{n.message}</Text>
          <Text style={s.small}>{new Date(n.created_at).toLocaleString()}</Text>
          <Button
            title={
              n.related_item_id
                ? "Open item"
                : n.read_at
                  ? "Read"
                  : "Mark as read"
            }
            secondary
            onPress={() =>
              action(async () => {
                check(
                  await supabase
                    .from("notifications")
                    .update({ read_at: new Date().toISOString() })
                    .eq("id", n.id),
                );
                if (n.related_item_id)
                  router.push(`/item/${n.related_item_id}`);
              })
            }
          />
        </View>
      ))}
    </Page>
  );
}
