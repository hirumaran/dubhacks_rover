import React from "react";
import { Image } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { privatePhoto } from "../lib/supabase";
export default function PrivatePhoto({
  path,
  bucket = "missing-photos",
}: {
  path: string | null;
  bucket?: string;
}) {
  const q = useQuery({
    queryKey: ["private-photo", bucket, path],
    queryFn: () => privatePhoto(path!, bucket),
    enabled: !!path,
    staleTime: 45 * 60 * 1000,
  });
  if (!q.data) return null;
  return (
    <Image
      accessibilityLabel="Your private uploaded photograph"
      source={{ uri: q.data }}
      style={{ height: 190, width: "100%", borderRadius: 18 }}
    />
  );
}
