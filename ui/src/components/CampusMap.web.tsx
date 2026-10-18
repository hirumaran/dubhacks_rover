import React from "react";
import { Linking, Pressable, Text, View } from "react-native";
import { MapPin } from "lucide-react-native";
import { CampusMapProps } from "./CampusMap.types";
import { campus, places } from "../lib/types";
import { Button, colors, s } from "./ui";

// Browser preview keeps native map imports out of the web bundle.
export default function CampusMap({
  items = [],
  pin,
  onPin,
  onSelect,
  center,
}: CampusMapProps) {
  const point = pin || center || campus;
  return (
    <View style={s.card}>
      <MapPin color={colors.sage} size={28} />
      <Text style={s.heading}>UW Seattle campus</Text>
      <Text style={s.body}>
        Open HuskyFind on iOS or Android for the interactive campus map. This
        browser preview shows the same listing locations below.
      </Text>
      <Button
        title="Open campus map"
        secondary
        onPress={() => {
          void Linking.openURL(
            `https://www.openstreetmap.org/?mlat=${point.latitude}&mlon=${point.longitude}#map=16/${point.latitude}/${point.longitude}`,
          );
        }}
      />
      {onPin &&
        places.map((place) => (
          <Pressable
            key={place.name}
            accessibilityRole="button"
            onPress={() => onPin(place)}
            style={s.chip}
          >
            <Text style={s.body}>{place.name}</Text>
          </Pressable>
        ))}
      {items.map((item) => (
        <Pressable
          key={item.id}
          accessibilityRole="button"
          onPress={() => onSelect?.(item)}
          style={s.chip}
        >
          <Text style={[s.body, { color: colors.ink }]}>{item.title}</Text>
          <Text style={s.small}>{item.approximate_location}</Text>
        </Pressable>
      ))}
    </View>
  );
}
