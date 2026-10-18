import React from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  TextInputProps,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { ArrowUpRight, MapPin, Radio, Search } from "lucide-react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { FoundItem, categories } from "../lib/types";
import { photo } from "../lib/supabase";
export const colors = {
  sage: "#5B8174",
  peach: "#FCCFA5",
  ink: "#231F20",
  paper: "#FAFAF7",
  muted: "#747A76",
  line: "#E6E9E3",
};
export const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.paper },
  content: { padding: 24, paddingBottom: 120, gap: 20 },
  title: {
    fontSize: 34,
    fontWeight: "700",
    letterSpacing: -1.2,
    color: colors.ink,
  },
  heading: {
    fontSize: 22,
    fontWeight: "700",
    letterSpacing: -0.5,
    color: colors.ink,
  },
  body: { fontSize: 15, lineHeight: 23, color: colors.muted },
  label: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.5,
    color: colors.sage,
    textTransform: "uppercase",
  },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  card: {
    backgroundColor: "white",
    padding: 20,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: colors.line,
    gap: 12,
  },
  input: {
    backgroundColor: "white",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 16,
    padding: 16,
    fontSize: 16,
    color: colors.ink,
    minHeight: 54,
  },
  button: {
    backgroundColor: colors.sage,
    minHeight: 54,
    borderRadius: 18,
    paddingHorizontal: 20,
    paddingVertical: 15,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonText: { color: "white", fontSize: 15, fontWeight: "700" },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 30,
    backgroundColor: "white",
    borderWidth: 1,
    borderColor: colors.line,
  },
  small: { fontSize: 12, color: colors.muted, lineHeight: 18 },
});
export function Page({
  children,
  scroll = true,
}: {
  children: React.ReactNode;
  scroll?: boolean;
}) {
  return (
    <SafeAreaView edges={["top"]} style={s.page}>
      {scroll ? (
        <ScrollView
          contentContainerStyle={s.content}
          keyboardShouldPersistTaps="handled"
        >
          {children}
        </ScrollView>
      ) : (
        children
      )}
    </SafeAreaView>
  );
}
export function Button({
  title,
  onPress,
  secondary = false,
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled}
      onPress={onPress}
      style={[
        s.button,
        secondary && { backgroundColor: "#EBF0EC" },
        disabled && { opacity: 0.45 },
      ]}
    >
      <Text style={[s.buttonText, secondary && { color: colors.sage }]}>
        {title}
      </Text>
    </Pressable>
  );
}
export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={{ gap: 8 }}>
      <Text style={[s.body, { color: colors.ink, fontWeight: "600" }]}>
        {label}
      </Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor="#999F99"
        style={[
          s.input,
          props.multiline && { minHeight: 100, textAlignVertical: "top" },
        ]}
        {...props}
      />
    </View>
  );
}
export function Chips({
  values,
  value,
  onChange,
}: {
  values: readonly string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={{ gap: 8, paddingVertical: 2 }}
    >
      {values.map((v) => (
        <Pressable
          key={v}
          accessibilityRole="button"
          accessibilityState={{ selected: v === value }}
          onPress={() => onChange(v)}
          style={[
            s.chip,
            v === value && {
              backgroundColor: colors.sage,
              borderColor: colors.sage,
            },
          ]}
        >
          <Text
            style={{
              color: v === value ? "white" : colors.muted,
              fontWeight: "600",
            }}
          >
            {v}
          </Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}
export function Categories({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return <Chips values={categories} value={value} onChange={onChange} />;
}
export function State({
  loading,
  error,
  empty,
  retry,
}: {
  loading?: boolean;
  error?: Error | null;
  empty?: string;
  retry?: () => void;
}) {
  if (loading)
    return (
      <View style={{ gap: 16 }}>
        <ActivityIndicator color={colors.sage} />
        <View style={[s.card, { height: 180, backgroundColor: "#EAF0E9" }]} />
      </View>
    );
  if (error)
    return (
      <View style={s.card}>
        <Text style={s.heading}>Couldn’t load this yet</Text>
        <Text style={s.body}>{error.message}</Text>
        {retry && <Button title="Try again" onPress={retry} />}
      </View>
    );
  if (empty)
    return (
      <View style={[s.card, { alignItems: "center", padding: 32 }]}>
        <Search color={colors.sage} size={32} />
        <Text style={s.heading}>A little quiet here</Text>
        <Text style={[s.body, { textAlign: "center" }]}>{empty}</Text>
      </View>
    );
  return null;
}
export function ItemCard({
  item,
  wide = false,
}: {
  item: FoundItem;
  wide?: boolean;
}) {
  return (
    <Animated.View entering={FadeInDown.duration(300)} style={{ flex: 1 }}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`View ${item.title}`}
        onPress={() => router.push(`/item/${item.id}`)}
        style={{
          backgroundColor: "white",
          borderRadius: 22,
          overflow: "hidden",
          borderWidth: 1,
          borderColor: colors.line,
        }}
      >
        <Image
          source={{ uri: photo(item.image_path) }}
          style={{
            width: "100%",
            height: wide ? 210 : 165,
            backgroundColor: "#E9EEE7",
          }}
        />
        <View style={{ padding: 13, gap: 7 }}>
          <View style={s.row}>
            <Radio size={12} color={colors.sage} />
            <Text style={[s.small, { color: colors.sage, fontWeight: "600" }]}>
              {item.source === "rover" ? "Rover found" : "Community found"}
            </Text>
          </View>
          <Text
            numberOfLines={2}
            style={{ fontSize: 17, fontWeight: "700", color: colors.ink }}
          >
            {item.title}
          </Text>
          <Text numberOfLines={2} style={s.small}>
            {item.description}
          </Text>
          <View style={{ flexDirection: "row", gap: 4 }}>
            <MapPin size={13} color={colors.muted} />
            <Text numberOfLines={1} style={[s.small, { flex: 1 }]}>
              {item.approximate_location}
            </Text>
          </View>
          <Text style={s.small}>
            {new Date(item.discovered_at).toLocaleDateString()} · {item.status}
          </Text>
          {item.is_demo && <Text style={s.label}>Demo listing</Text>}
        </View>
      </Pressable>
    </Animated.View>
  );
}
export function Back() {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() =>
        router.canGoBack() ? router.back() : router.replace("/(tabs)")
      }
      style={{ paddingVertical: 12 }}
    >
      <Text style={{ color: colors.sage, fontSize: 16 }}>← Back</Text>
    </Pressable>
  );
}
