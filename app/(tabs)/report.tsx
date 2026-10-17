import React, { useState } from "react";
import { Alert, Image, Text, View } from "react-native";
import { router } from "expo-router";
import { ImagePickerAsset } from "expo-image-picker";
import { useQueryClient } from "@tanstack/react-query";
import { Page, Button, Field, Chips, s } from "../../src/components/ui";
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
} from "../../src/lib/api";
import { useSession } from "../../src/lib/session";
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
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<MissingReport>();
  const [requested, setRequested] = useState(false);
  async function choose(camera = false) {
    try {
      const p = await pickPhoto(camera);
      if (p) setImage(p);
    } catch (e) {
      Alert.alert("Photo", String(e));
    }
  }
  async function submit() {
    if (!session) return;
    setBusy(true);
    try {
      const image_path = image
        ? await uploadPhoto(image, "missing-photos", session.user.id)
        : null;
      const r = await createReport({
        user_id: session.user.id,
        title: title.trim(),
        category,
        color: color.trim(),
        description: description.trim(),
        last_seen_location: location.name,
        latitude: location.latitude,
        longitude: location.longitude,
        last_seen_at: new Date(when + "Z").toISOString(),
        image_path,
      });
      setResult(r);
      setStep(4);
      await cache.invalidateQueries();
    } catch (e) {
      Alert.alert("Couldn’t save your report", String(e));
    } finally {
      setBusy(false);
    }
  }
  async function search() {
    if (!result) return;
    setBusy(true);
    try {
      await requestSearch(result);
      setRequested(true);
      await cache.invalidateQueries();
    } catch (e) {
      Alert.alert("Search request", String(e));
    } finally {
      setBusy(false);
    }
  }
  function next() {
    if (step === 1 && (!title.trim() || !color.trim() || !description.trim())) {
      Alert.alert(
        "A few more details",
        "Please add an item name, color, and description.",
      );
      return;
    }
    if (
      step === 2 &&
      (!location.name.trim() ||
        !Number.isFinite(Date.parse(when + "Z")) ||
        Date.parse(when + "Z") > Date.now())
    ) {
      Alert.alert(
        "Check your last-seen details",
        "Add a location and a valid date/time in the past (UTC).",
      );
      return;
    }
    setStep(step + 1);
  }
  return (
    <Page>
      <Text style={s.label}>
        LET’S BRING IT BACK · {step < 4 ? `STEP ${step} OF 3` : "REPORT SAVED"}
      </Text>
      <View style={s.row}>
        {[1, 2, 3].map((n) => (
          <View
            key={n}
            style={{
              flex: 1,
              height: 4,
              borderRadius: 5,
              backgroundColor: n <= step ? "#5B8174" : "#E4E8E2",
            }}
          />
        ))}
      </View>
      <Text style={s.title}>
        {step === 1
          ? "What did you lose?"
          : step === 2
            ? "Where did you last see it?"
            : step === 3
              ? "Looking good, Husky."
              : "Your search starts here."}
      </Text>
      {step === 1 && (
        <>
          <Text style={s.body}>A few details can make all the difference.</Text>
          {image && (
            <Image
              source={{ uri: image.uri }}
              style={{ height: 200, borderRadius: 22 }}
            />
          )}
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Button title="Choose photo" secondary onPress={() => choose()} />
            </View>
            <View style={{ flex: 1 }}>
              <Button
                title="Take photo"
                secondary
                onPress={() => choose(true)}
              />
            </View>
          </View>
          <Field
            label="Item name"
            placeholder="My black Hydro Flask"
            value={title}
            onChangeText={setTitle}
            maxLength={150}
          />
          <Chips
            values={categories.filter((c) => c !== "All")}
            value={category}
            onChange={(v) => setCategory(v as Category)}
          />
          <Field
            label="Color"
            placeholder="Black"
            value={color}
            onChangeText={setColor}
          />
          <Field
            label="Description"
            placeholder="Brand, material, and general appearance…"
            value={description}
            onChangeText={setDescription}
            multiline
          />
          <Text style={s.small}>
            Keep unique ownership details for the private claim process.
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
            onChange={(n) => setLocation(places.find((p) => p.name === n)!)}
          />
          <Field
            label="Last seen location"
            value={location.name}
            onChangeText={(name) => setLocation({ ...location, name })}
          />
          <Field
            label="Last seen date and time (UTC)"
            placeholder="2026-10-17T18:30"
            value={when}
            onChangeText={setWhen}
          />
          <Text style={s.small}>
            Format: YYYY-MM-DDTHH:mm. Your report and location are private.
          </Text>
        </>
      )}
      {step === 3 && (
        <View style={s.card}>
          {image && (
            <Image
              source={{ uri: image.uri }}
              style={{ height: 180, borderRadius: 16 }}
            />
          )}
          <Text style={s.heading}>{title}</Text>
          <Text style={s.body}>
            {category} · {color}
          </Text>
          <Text style={s.body}>{description}</Text>
          <Text style={s.body}>{location.name}</Text>
          <Text style={s.body}>{new Date(when + "Z").toLocaleString()}</Text>
          <Button title="Edit details" secondary onPress={() => setStep(1)} />
        </View>
      )}
      {step === 4 && (
        <>
          <Text style={s.body}>
            We’ll keep checking for matches and let you know when something
            turns up.
          </Text>
          <Button
            title="See potential matches"
            onPress={() => router.push("/(tabs)/activity")}
          />
          <Button
            title={
              requested
                ? "Search request queued"
                : busy
                  ? "Requesting…"
                  : "Request a rover search"
            }
            disabled={busy || requested}
            secondary
            onPress={search}
          />
          <Text style={s.small}>
            A request does not guarantee a rover is available. Activity shows
            the status received from campus operations.
          </Text>
          <Button
            title="Report another item"
            secondary
            onPress={() => {
              setStep(1);
              setTitle("");
              setDescription("");
              setColor("");
              setImage(null);
              setResult(undefined);
              setRequested(false);
            }}
          />
        </>
      )}
      {step < 3 && <Button title="Continue" onPress={next} />}
      {step === 3 && (
        <Button
          title={busy ? "Saving report…" : "Start my search"}
          disabled={busy}
          onPress={submit}
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
