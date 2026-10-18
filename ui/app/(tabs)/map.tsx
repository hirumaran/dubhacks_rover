import React, { useState } from "react";
import { Alert, Text } from "react-native";
import { useInfiniteQuery } from "@tanstack/react-query";
import * as Location from "expo-location";
import {
  Page,
  Categories,
  Chips,
  Button,
  ItemCard,
  State,
  s,
} from "../../src/components/ui";
import CampusMap from "../../src/components/CampusMap";
import { foundItems } from "../../src/lib/api";
import { FoundItem } from "../../src/lib/types";
export default function MapScreen() {
  const [category, setCategory] = useState("All");
  const [source, setSource] = useState("all");
  const [date, setDate] = useState("Any time");
  const [selected, setSelected] = useState<FoundItem>();
  const [center, setCenter] = useState<{
    latitude: number;
    longitude: number;
  }>();
  const q = useInfiniteQuery({
    queryKey: ["map", category, source, date],
    queryFn: ({ pageParam }) =>
      foundItems(
        "",
        category,
        pageParam,
        "newest",
        source,
        date === "Today" ? 1 : date === "This week" ? 7 : 0,
      ),
    initialPageParam: 0,
    getNextPageParam: (last, pages) =>
      last.length === 20 ? pages.length : undefined,
  });
  async function locate() {
    try {
      const p = await Location.requestForegroundPermissionsAsync();
      if (!p.granted)
        throw new Error(
          "Location permission was declined. You can still explore campus.",
        );
      setCenter(
        (
          await Location.getCurrentPositionAsync({
            accuracy: Location.Accuracy.Balanced,
          })
        ).coords,
      );
    } catch (e) {
      Alert.alert("Location", String(e));
    }
  }
  return (
    <Page>
      <Text style={s.label}>UW SEATTLE</Text>
      <Text style={s.title}>A campus of{`\n`}possibilities.</Text>
      <Categories
        value={category}
        onChange={(v) => {
          setCategory(v);
          setSelected(undefined);
        }}
      />
      <Chips
        values={["all", "rover", "community"]}
        value={source}
        onChange={(v) => {
          setSource(v);
          setSelected(undefined);
        }}
      />
      <Chips
        values={["Any time", "Today", "This week"]}
        value={date}
        onChange={(v) => {
          setDate(v);
          setSelected(undefined);
        }}
      />
      <CampusMap
        items={q.data?.pages.flat() || []}
        onSelect={setSelected}
        center={center}
      />
      <Text style={s.small}>
        Pins show approximate discovery locations. Items may have moved.
      </Text>
      <Button title="Center on my location" secondary onPress={locate} />
      <State loading={q.isLoading} error={q.error} retry={() => q.refetch()} />
      {!q.isLoading && !q.error && !q.data?.pages.flat().length && (
        <State empty="No discoveries for these filters." />
      )}
      {q.hasNextPage && (
        <Button
          title="Load more map items"
          secondary
          onPress={() => q.fetchNextPage()}
        />
      )}
      {selected && <ItemCard item={selected} wide />}
    </Page>
  );
}
