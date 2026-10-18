import React from "react";
import MapView, { Marker, MapPressEvent } from "react-native-maps";
import { campus } from "../lib/types";
import { CampusMapProps } from "./CampusMap.types";
export default function CampusMap({
  items = [],
  pin,
  onPin,
  onSelect,
  center,
}: CampusMapProps) {
  return (
    <MapView
      key={center ? `${center.latitude},${center.longitude}` : "campus"}
      style={{ height: 300, borderRadius: 24, width: "100%" }}
      initialRegion={{ ...campus, ...center }}
      onPress={(e: MapPressEvent) => onPin?.(e.nativeEvent.coordinate)}
    >
      {items.map((i) => (
        <Marker
          key={i.id}
          coordinate={{ latitude: i.latitude, longitude: i.longitude }}
          title={i.title}
          description={i.approximate_location}
          pinColor={i.source === "rover" ? "#4B2E83" : "#B7A57A"}
          onPress={() => onSelect?.(i)}
        />
      ))}
      {pin && <Marker coordinate={pin} pinColor="#4B2E83" />}
    </MapView>
  );
}
