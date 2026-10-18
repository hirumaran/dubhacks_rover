import PrivatePhoto from "../../src/components/PrivatePhoto";
import React, { useState } from "react";
import { Alert, Text, View } from "react-native";
import { router } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Page, Button, ItemCard, State, s } from "../../src/components/ui";
import {
  reports,
  matches,
  requestSearch,
  invokeCloud,
} from "../../src/lib/api";
import { supabase, check } from "../../src/lib/supabase";
import { matchLabel } from "../../src/lib/matching";
export default function Activity() {
  const [comparison, setComparison] = useState<
    Record<
      string,
      {
        similarity: number;
        verdict: string;
        summary: string;
        matching_features: string[];
        differences: string[];
      }
    >
  >({});
  const [comparing, setComparing] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState("");
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
      {!!comparisonError && (
        <Text accessibilityRole="alert" style={s.body}>
          {comparisonError}
        </Text>
      )}
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
            title={
              comparing === match.id
                ? "Comparing appearance…"
                : "Compare item appearance with AI"
            }
            secondary
            disabled={!!comparing}
            onPress={async () => {
              setComparing(match.id);
              setComparisonError("");
              try {
                const result = await invokeCloud<(typeof comparison)[string]>(
                  "compare-items",
                  { match_id: match.id },
                );
                setComparison((old) => ({ ...old, [match.id]: result }));
              } catch (error) {
                setComparisonError(
                  error instanceof Error ? error.message : String(error),
                );
              } finally {
                setComparing(null);
              }
            }}
          />
          {comparison[match.id] && (
            <View style={s.card}>
              <Text style={s.label}>
                AI APPEARANCE COMPARISON · {comparison[match.id].similarity}/100
              </Text>
              <Text style={s.heading}>
                {comparison[match.id].verdict.replaceAll("_", " ")}
              </Text>
              <Text style={s.body}>{comparison[match.id].summary}</Text>
              <Text style={s.small}>
                Visible agreements:{" "}
                {comparison[match.id].matching_features.join(" · ") ||
                  "None confidently identified"}
              </Text>
              <Text style={s.small}>
                Differences:{" "}
                {comparison[match.id].differences.join(" · ") ||
                  "None confidently identified"}
              </Text>
              <Text style={s.small}>
                Model estimate, not ownership verification. Claims still require
                private evidence.
              </Text>
            </View>
          )}
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
          {!!request.assignment_reason && (
            <Text style={s.body}>{request.assignment_reason}</Text>
          )}
          {!!request.search_brief && (
            <>
              <Text style={s.label}>VISUAL SEARCH BRIEF</Text>
              <Text style={s.body}>
                {request.search_brief.target} · {request.search_brief.color}
              </Text>
              <Text style={s.body}>{request.search_brief.visual_cues}</Text>
            </>
          )}
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
          style={[s.card, !n.read_at && { backgroundColor: "#EEE8F5" }]}
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
