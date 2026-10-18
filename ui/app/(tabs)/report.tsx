import React, { useState } from "react";
import { Image, Text, View, ScrollView } from "react-native";
import { router } from "expo-router";
import { Asset } from "expo-asset";
import { ImagePickerAsset } from "expo-image-picker";
import { useQueryClient } from "@tanstack/react-query";
import { Page, Button, Field, Chips, s, colors } from "../../src/components/ui";
import CampusMap from "../../src/components/CampusMap";
import {
  categories,
  Category,
  places,
  MissingReport,
} from "../../src/lib/types";
import {
  createReport,
  pickPhoto,
  uploadPhoto,
  requestSearch,
  invokeCloud,
  SearchPlan,
} from "../../src/lib/api";
import { useSession } from "../../src/lib/session";
import { demoPhotos } from "../../src/lib/demo-photos";

type Suggestion = {
  item_visible: boolean;
  title: string;
  category: Category;
  color: string;
  description: string;
};
export default function Report() {
  const { session } = useSession();
  const cache = useQueryClient();
  const [step, setStep] = useState(1);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<Category>("Water Bottles");
  const [color, setColor] = useState("");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState(places[0]);
  const [when, setWhen] = useState(new Date().toISOString().slice(0, 16));
  const [image, setImage] = useState<ImagePickerAsset | null>(null);
  const [imagePath, setImagePath] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<MissingReport>();
  const [plan, setPlan] = useState<SearchPlan | null>(null);
  async function analyze(photo: ImagePickerAsset) {
    if (!session) return;
    setImage(photo);
    setImagePath(null);
    setSuggestion(null);
    setError("");
    setTitle("");
    setColor("");
    setDescription("");
    setAnalyzing(true);
    try {
      const path = await uploadPhoto(photo, "missing-photos", session.user.id);
      setImagePath(path);
      const data = await invokeCloud<Suggestion>("analyze-missing-photo", {
        image_path: path,
      });
      if (!data.item_visible) {
        setError(
          "The model couldn’t clearly identify a single belonging. Try a closer photo or describe it below.",
        );
        return;
      }
      setSuggestion(data);
      setTitle(data.title);
      setCategory(categories.includes(data.category) ? data.category : "Other");
      setColor(data.color);
      setDescription(data.description);
    } catch (reason) {
      setError(
        `Photo analysis unavailable: ${reason instanceof Error ? reason.message : String(reason)}. You can retry or fill in the details yourself.`,
      );
    } finally {
      setAnalyzing(false);
    }
  }
  async function choose(camera = false) {
    try {
      const photo = await pickPhoto(camera);
      if (photo) await analyze(photo);
    } catch (reason) {
      setError(String(reason));
    }
  }
  async function sample(index: number) {
    try {
      const asset = Asset.fromModule(demoPhotos[index].image);
      await asset.downloadAsync();
      await analyze({
        uri: asset.localUri || asset.uri,
        width: asset.width || 1000,
        height: asset.height || 1000,
        mimeType: "image/jpeg",
        fileName: demoPhotos[index].key + ".jpg",
      });
    } catch (reason) {
      setError(String(reason));
    }
  }
  async function search(report: MissingReport) {
    try {
      const data = await requestSearch(report);
      setPlan(data);
    } catch (reason) {
      setError(
        `Your report is saved. Search planning needs a retry: ${reason instanceof Error ? reason.message : String(reason)}`,
      );
    }
    await cache.invalidateQueries();
  }
  async function submit() {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const path =
        imagePath ||
        (image
          ? await uploadPhoto(image, "missing-photos", session.user.id)
          : null);
      const saved = await createReport({
        user_id: session.user.id,
        title: title.trim(),
        category,
        color: color.trim(),
        description: description.trim(),
        last_seen_location: location.name,
        latitude: location.latitude,
        longitude: location.longitude,
        last_seen_at: new Date(when + "Z").toISOString(),
        image_path: path,
      });
      setResult(saved);
      setStep(4);
      await search(saved);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  function next() {
    setError("");
    if (step === 1 && (!title.trim() || !color.trim() || !description.trim())) {
      setError(
        "Add an item name, color, and description, or let a photo fill them in.",
      );
      return;
    }
    if (
      step === 2 &&
      (!location.name.trim() ||
        !Number.isFinite(Date.parse(when + "Z")) ||
        Date.parse(when + "Z") > Date.now())
    ) {
      setError(
        "Choose a last-seen location and a valid time in the past (UTC).",
      );
      return;
    }
    setStep(step + 1);
  }
  return (
    <Page>
      <Text style={s.label}>
        LET’S BRING IT BACK · {step < 4 ? `STEP ${step} OF 3` : "SEARCH PLAN"}
      </Text>
      <View style={s.row}>
        {[1, 2, 3].map((n) => (
          <View
            key={n}
            style={{
              flex: 1,
              height: 4,
              borderRadius: 5,
              backgroundColor: n <= step ? colors.purple : colors.line,
            }}
          />
        ))}
      </View>
      <Text style={s.title}>
        {step === 1
          ? "A photo. A few clues."
          : step === 2
            ? "Where did you last see it?"
            : step === 3
              ? "Looking good, Husky."
              : "Your search has a plan."}
      </Text>
      {!!error && (
        <View style={[s.card, { borderColor: "#B45555" }]}>
          <Text accessibilityRole="alert" style={s.body}>
            {error}
          </Text>
        </View>
      )}
      {step === 1 && (
        <>
          <Text style={s.body}>
            Upload a photo. Perceptron identifies the visible item through our
            Supabase Edge Function, then you review the details before
            searching.
          </Text>
          {image && (
            <Image
              accessibilityLabel="Your reference photo"
              source={{ uri: image.uri }}
              style={{
                height: 280,
                borderRadius: 24,
                backgroundColor: colors.lavender,
              }}
              resizeMode="contain"
            />
          )}
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Button
                title="Choose photo"
                secondary
                disabled={analyzing}
                onPress={() => void choose()}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Button
                title="Take photo"
                secondary
                disabled={analyzing}
                onPress={() => void choose(true)}
              />
            </View>
          </View>
          <Text style={s.label}>OR TRY A REAL CAMPUS DEMO PHOTO</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: 12 }}
          >
            {demoPhotos.slice(0, 5).map((photo, index) => (
              <View key={photo.key} style={{ width: 150, gap: 8 }}>
                <Image
                  source={photo.image}
                  style={{ width: 150, height: 130, borderRadius: 18 }}
                />
                <Button
                  title={`Try ${photo.key} photo`}
                  secondary
                  disabled={analyzing}
                  onPress={() => void sample(index)}
                />
              </View>
            ))}
          </ScrollView>
          {analyzing && (
            <Text accessibilityLiveRegion="polite" style={s.heading}>
              Analyzing photo with Perceptron…
            </Text>
          )}
          {suggestion && (
            <View style={[s.card, { backgroundColor: colors.lavender }]}>
              <Text style={s.label}>AI PHOTO ANALYSIS COMPLETE</Text>
              <Text style={s.body}>
                The visible item looks like {suggestion.title.toLowerCase()}.
                Review or edit the clues below. This identifies appearance, not
                ownership.
              </Text>
            </View>
          )}
          {image && !analyzing && (
            <Button
              title="Analyze photo again"
              secondary
              onPress={() => void analyze(image)}
            />
          )}
          <Field
            label="Item name"
            value={title}
            onChangeText={setTitle}
            editable={!analyzing}
            maxLength={150}
            placeholder="My black backpack"
          />
          <Chips
            values={categories.filter((c) => c !== "All")}
            value={category}
            onChange={(v) => setCategory(v as Category)}
          />
          <Field
            label="Color"
            value={color}
            onChangeText={setColor}
            editable={!analyzing}
            placeholder="Black"
          />
          <Field
            label="Description"
            value={description}
            onChangeText={setDescription}
            editable={!analyzing}
            multiline
            placeholder="Shape, material, brand, visible wear or distinctive details…"
          />
          <Text style={s.small}>
            Photos are private to your report. Keep unique ownership evidence
            for the claim process.
          </Text>
        </>
      )}
      {step === 2 && (
        <>
          <CampusMap
            pin={location}
            onPin={(p) =>
              setLocation({ ...p, name: "Dropped pin on UW campus" })
            }
          />
          <Chips
            values={places.map((p) => p.name)}
            value={location.name}
            onChange={(name) =>
              setLocation(places.find((p) => p.name === name)!)
            }
          />
          <Field
            label="Last seen location"
            value={location.name}
            onChangeText={(name) => setLocation({ ...location, name })}
          />
          <Field
            label="Last seen date and time (UTC)"
            value={when}
            onChangeText={setWhen}
            placeholder="2026-10-18T16:30"
          />
          <Text style={s.small}>
            Format: YYYY-MM-DDTHH:mm. The closest eligible rover is selected
            using this location; distances are straight-line estimates.
          </Text>
        </>
      )}
      {step === 3 && (
        <View style={s.card}>
          {image && (
            <Image
              source={{ uri: image.uri }}
              style={{ height: 220, borderRadius: 18 }}
              resizeMode="contain"
            />
          )}
          <Text style={s.heading}>{title}</Text>
          <Text style={s.label}>
            {category} · {color}
          </Text>
          <Text style={s.body}>{description}</Text>
          <Text style={s.body}>{location.name}</Text>
          <Text style={s.small}>
            We’ll save your report, evaluate available rovers, and prepare a
            visual search brief. Demo accounts use the demo fleet.
          </Text>
          <Button title="Edit details" secondary onPress={() => setStep(1)} />
        </View>
      )}
      {step === 4 && (
        <>
          {busy && (
            <Text accessibilityLiveRegion="polite" style={s.heading}>
              Selecting a rover and preparing its brief…
            </Text>
          )}
          {plan && (
            <View style={[s.card, { borderColor: colors.gold }]}>
              <Text style={s.label}>
                {plan.demo
                  ? "DEMO FLEET · SIMULATED DISPATCH"
                  : "ROVER SEARCH REQUEST"}
              </Text>
              <Text style={s.heading}>
                {plan.rover_name || "Waiting for an available rover"}
              </Text>
              <Text style={s.body}>{plan.reason}</Text>
              <Text style={s.label}>WHAT THE ROVER SHOULD LOOK FOR</Text>
              <Text style={s.heading}>{plan.brief.target}</Text>
              <Text style={s.body}>
                {plan.brief.color} · {plan.brief.category}
              </Text>
              <Text style={s.body}>{plan.brief.visual_cues}</Text>
              <Text style={s.body}>Search area: {plan.brief.search_area}</Text>
              <Text style={s.small}>{plan.brief.instruction}</Text>
              <Text style={s.label}>HOW CANDIDATES ARE WEIGHED</Text>
              {Object.entries(plan.brief.matching_weights).map(
                ([key, value]) => (
                  <View
                    key={key}
                    style={[s.row, { justifyContent: "space-between" }]}
                  >
                    <Text style={s.body}>
                      {key.charAt(0).toUpperCase() + key.slice(1)}
                    </Text>
                    <Text style={s.label}>{value} points</Text>
                  </View>
                ),
              )}
              <Text style={s.small}>
                {plan.demo
                  ? "This saves a real cloud search request for the demo fleet. It does not start a physical rover."
                  : "Assignment awaits rover acknowledgement. Activity shows the recorded operating status."}{" "}
                Matching points help rank candidates; they are not proof of
                identity.
              </Text>
            </View>
          )}
          {!plan && !busy && result && (
            <Button
              title="Retry rover planning"
              onPress={async () => {
                setBusy(true);
                await search(result);
                setBusy(false);
              }}
            />
          )}
          <Button
            title="See potential matches"
            onPress={() => router.push("/(tabs)/activity")}
          />
          <Button
            title="Report another item"
            secondary
            disabled={busy}
            onPress={() => {
              setStep(1);
              setTitle("");
              setColor("");
              setDescription("");
              setImage(null);
              setImagePath(null);
              setSuggestion(null);
              setResult(undefined);
              setPlan(null);
              setError("");
            }}
          />
        </>
      )}
      {step < 3 && (
        <Button title="Continue" disabled={analyzing} onPress={next} />
      )}
      {step === 3 && (
        <Button
          title={busy ? "Saving and planning…" : "Start my search"}
          disabled={busy}
          onPress={() => void submit()}
        />
      )}
      {step > 1 && step < 4 && (
        <Button
          title="Previous step"
          secondary
          disabled={busy}
          onPress={() => setStep(step - 1)}
        />
      )}
    </Page>
  );
}
