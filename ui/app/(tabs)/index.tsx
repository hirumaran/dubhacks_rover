import React, { useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { router } from "expo-router";
import { Bell, MapPin, Search, ArrowUpRight } from "lucide-react-native";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { foundItems, matches } from "../../src/lib/api";
import { useSession } from "../../src/lib/session";
import {
  Page,
  ItemCard,
  Categories,
  Chips,
  State,
  s,
  colors,
} from "../../src/components/ui";
export default function Discover() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [sort, setSort] = useState("newest");
  const { session } = useSession();
  const feed = useInfiniteQuery({
    queryKey: ["found", search, category, sort],
    queryFn: ({ pageParam }) => foundItems(search, category, pageParam, sort),
    initialPageParam: 0,
    getNextPageParam: (last, pages) =>
      last.length === 20 ? pages.length : undefined,
  });
  const recommendations = useQuery({ queryKey: ["matches"], queryFn: matches });
  const items = feed.data?.pages.flat() || [];
  return (
    <Page scroll={false}>
      <FlatList
        data={items}
        keyExtractor={(i) => i.id}
        numColumns={2}
        columnWrapperStyle={{ gap: 12 }}
        contentContainerStyle={{ padding: 22, paddingBottom: 125, gap: 14 }}
        onRefresh={() => {
          void feed.refetch();
          void recommendations.refetch();
        }}
        refreshing={feed.isRefetching}
        onEndReached={() => {
          if (feed.hasNextPage && !feed.isFetchingNextPage)
            void feed.fetchNextPage();
        }}
        onEndReachedThreshold={0.4}
        renderItem={({ item }) => (
          <View style={{ flex: 1, maxWidth: "49%" }}>
            <ItemCard item={item} />
          </View>
        )}
        ListHeaderComponent={
          <View style={{ gap: 22, paddingTop: 8, paddingBottom: 8 }}>
            <View style={[s.row, { justifyContent: "space-between" }]}>
              <Text style={s.body}>Welcome back, Husky.</Text>
              <Pressable
                accessibilityLabel="Open notifications"
                accessibilityRole="button"
                onPress={() => router.push("/(tabs)/activity")}
                style={{
                  padding: 12,
                  backgroundColor: "white",
                  borderRadius: 18,
                }}
              >
                <Bell color={colors.ink} size={21} />
              </Pressable>
            </View>
            <Text style={[s.title, { fontSize: 38 }]}>
              Find what{`\n`}matters
              <Text style={{ color: colors.sage }}>.</Text>
            </Text>
            <View style={s.row}>
              <MapPin size={16} color={colors.sage} />
              <Text style={{ color: colors.sage, fontWeight: "600" }}>
                UW Seattle
              </Text>
              {session?.user.is_anonymous && (
                <Text style={[s.small, { marginLeft: "auto" }]}>
                  DEMO CAMPUS
                </Text>
              )}
            </View>
            <View style={[s.input, s.row]}>
              <Search color={colors.muted} size={19} />
              <TextInput
                accessibilityLabel="Search found items"
                placeholder="Search AirPods, backpacks, keys…"
                value={search}
                onChangeText={setSearch}
                style={{ flex: 1, fontSize: 14 }}
              />
            </View>
            <View
              style={{
                backgroundColor: "#E9EFE7",
                borderRadius: 24,
                padding: 22,
                gap: 10,
              }}
            >
              <Text style={s.label}>A CAMPUS THAT LOOKS OUT FOR YOU</Text>
              <Text style={s.heading}>Your things have a way back.</Text>
              <Pressable
                accessibilityRole="button"
                onPress={() => router.push("/(tabs)/report")}
                style={s.row}
              >
                <Text style={{ fontWeight: "600", color: colors.sage }}>
                  Tell us what’s missing
                </Text>
                <ArrowUpRight size={18} color={colors.sage} />
              </Pressable>
            </View>
            {!!recommendations.data?.length && (
              <View style={{ gap: 12 }}>
                <Text style={s.heading}>Could this be yours?</Text>
                <ItemCard item={recommendations.data[0].found_items} wide />
              </View>
            )}
            <Categories value={category} onChange={setCategory} />
            <View style={[s.row, { justifyContent: "space-between" }]}>
              <Text style={s.heading}>Around campus</Text>
              <Chips
                values={["newest", "oldest"]}
                value={sort}
                onChange={setSort}
              />
            </View>
          </View>
        }
        ListEmptyComponent={
          <State
            loading={feed.isLoading}
            error={feed.error}
            empty="No items here yet. Try another category or report what you’re missing."
            retry={() => feed.refetch()}
          />
        }
        ListFooterComponent={
          feed.isFetchingNextPage ? (
            <State loading />
          ) : feed.isError && items.length ? (
            <State error={feed.error} retry={() => feed.fetchNextPage()} />
          ) : undefined
        }
      />
    </Page>
  );
}
