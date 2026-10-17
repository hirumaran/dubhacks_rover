import React from "react";
import MapView, { Marker, MapPressEvent } from "react-native-maps";
import { campus, FoundItem } from "../lib/types";
export default function CampusMap({
  items = [],
  pin,
  onPin,
  onSelect,
  center,
}: {
  items?: FoundItem[];
  pin?: { latitude: number; longitude: number };
  onPin?: (p: { latitude: number; longitude: number }) => void;
  onSelect?: (i: FoundItem) => void;
  center?: { latitude: number; longitude: number };
}) {
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
          pinColor={i.source === "rover" ? "#5B8174" : "#D39A68"}
          onPress={() => onSelect?.(i)}
        />
      ))}
      {pin && <Marker coordinate={pin} pinColor="#5B8174" />}
    </MapView>
  );
}
