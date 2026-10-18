import React from "react";
import { Image, Text, View } from "react-native";
import { Scan } from "../lib/scout";
import { colors, s } from "./ui";

export default function ScoutImage({
  scan,
  preview = false,
}: {
  scan: Scan;
  preview?: boolean;
}) {
  return (
    <View style={{ gap: 12 }}>
      <View
        style={{
          width: "100%",
          aspectRatio: scan.width / scan.height,
          backgroundColor: "#18231E",
          overflow: "hidden",
          borderRadius: 16,
        }}
      >
        <Image
          accessibilityLabel={
            preview ? "Live camera preview" : "Exact frame analyzed by Scout"
          }
          source={{ uri: scan.image }}
          style={{ width: "100%", height: "100%" }}
          resizeMode="contain"
        />
        {scan.detections.map((item, index) => (
          <View
            key={index}
            style={{
              position: "absolute",
              left: `${item.bbox[0] * 100}%`,
              top: `${item.bbox[1] * 100}%`,
              width: `${item.bbox[2] * 100}%`,
              height: `${item.bbox[3] * 100}%`,
              borderWidth: 2,
              borderColor: colors.peach,
            }}
          >
            <Text
              numberOfLines={2}
              style={{
                backgroundColor: colors.peach,
                color: colors.ink,
                fontSize: 11,
              }}
            >
              {item.title}
            </Text>
          </View>
        ))}
      </View>
      {!preview && scan.detections.length === 0 && (
        <Text style={s.body}>
          No clearly identifiable belongings in this frame.
        </Text>
      )}
      {scan.detections.map((item, i) => (
        <View key={i}>
          <Text style={[s.body, { color: colors.ink, fontWeight: "600" }]}>
            {item.title}
          </Text>
          <Text style={s.small}>
            {item.category}
            {item.repeated
              ? ` · Seen in ${item.consecutive_scans} consecutive scans`
              : item.consecutive_scans
                ? " · First sighting"
                : ""}
          </Text>
          {!!item.description && (
            <Text style={s.small}>{item.description}</Text>
          )}
        </View>
      ))}
    </View>
  );
}
