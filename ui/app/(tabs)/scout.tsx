import React, { useCallback, useEffect, useRef, useState } from "react";
import { AppState, Linking, Platform, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { CameraView, useCameraPermissions } from "expo-camera";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { File } from "expo-file-system";
import { Button, Chips, Field, Page, s } from "../../src/components/ui";
import ScoutImage from "../../src/components/ScoutImage";
import { scoutHost } from "../../src/lib/scout-host";
import {
  Feed,
  Pairing,
  parsePairing,
  RepeatTracker,
  Scan,
  scoutRequest,
} from "../../src/lib/scout";

export default function Scout() {
  const cloudMode = !__DEV__;
  const [link, setLink] = useState("");
  const [pair, setPair] = useState<Pairing | null>(
    cloudMode ? { url: "", token: "", transport: "supabase" } : null,
  );
  const [connecting, setConnecting] = useState(false);
  const [mode, setMode] = useState("Live feed");
  const [source, setSource] = useState("Laptop webcam");
  const [permission, requestPermission] = useCameraPermissions();
  const [cameraOn, setCameraOn] = useState(false);
  const [ready, setReady] = useState(false);
  const [front, setFront] = useState(false);
  const [active, setActive] = useState(false);
  const [automatic, setAutomatic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(
    "Connect to Scout to scan with your phone or view the rover.",
  );
  const [history, setHistory] = useState<Scan[]>([]);
  const [selected, setSelected] = useState<Scan | null>(null);
  const [feed, setFeed] = useState<Feed | null>(null);
  const camera = useRef<CameraView>(null);
  const tracker = useRef(new RepeatTracker());
  const generation = useRef(0);
  const focused = useRef(false);
  const scanning = useRef(false);
  const request = useRef<AbortController | null>(null);
  const pairingRequest = useRef<AbortController | null>(null);
  const scanAction = useRef<() => Promise<void>>(async () => {});

  const stop = useCallback(() => {
    generation.current++;
    request.current?.abort();
    pairingRequest.current?.abort();
    setConnecting(false);
    setAutomatic(false);
    setCameraOn(false);
    setReady(false);
    tracker.current = new RepeatTracker();
  }, []);
  useFocusEffect(
    useCallback(() => {
      focused.current = true;
      setActive(true);
      return () => {
        focused.current = false;
        setActive(false);
        stop();
      };
    }, [stop]),
  );
  useEffect(() => {
    const listener = AppState.addEventListener("change", (state) => {
      setActive(state === "active" && focused.current);
      if (state !== "active") stop();
    });
    return () => listener.remove();
  }, [stop]);

  useEffect(() => {
    if (!pair || mode !== "Live feed" || !active) return;
    setFeed(null);
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    let analysisSince = 0;
    const poll = async () => {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 30000);
      try {
        const result = await scoutRequest<Feed>(
          pair,
          `feed?source=${source === "Rover" ? "rover" : "webcam"}&analysis_since=${analysisSince}&request=${Date.now()}`,
          controller.signal,
        );
        if (!cancelled) {
          if (result.analysis) analysisSince = result.analysis.updated_at;
          if (!result.image) analysisSince = 0;
          setFeed((previous) => ({
            ...result,
            analysis:
              result.analysis === undefined
                ? previous?.analysis
                : result.analysis,
          }));
          setMessage(
            result.online
              ? "Connected to the camera. Preview updates independently of analyzed snapshots."
              : "Feed offline or stale. Start the camera publisher on the computer.",
          );
        }
      } catch (error) {
        if (!cancelled) {
          analysisSince = 0;
          setFeed(null);
          setMessage(String(error instanceof Error ? error.message : error));
        }
      } finally {
        clearTimeout(timeout);
        if (!cancelled)
          timer = setTimeout(
            poll,
            cloudMode ? 1500 : source === "Rover" ? 1000 : 250,
          );
      }
    };
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [pair, mode, source, active]);

  async function connect() {
    setConnecting(true);
    const controller = new AbortController();
    pairingRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const value = parsePairing(link, scoutHost());
      await scoutRequest(value, "status", controller.signal);
      if (!controller.signal.aborted) {
        setPair(value);
        setLink("");
        setMessage("Scout connected. Choose a camera source to begin.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      clearTimeout(timeout);
      setConnecting(false);
    }
  }
  async function enable() {
    try {
      const result = permission?.granted
        ? permission
        : await requestPermission();
      if (!result.granted) {
        setMessage(
          "Camera access was denied. Enable it in phone settings to scan.",
        );
        return;
      }
      setReady(false);
      setCameraOn(true);
      setMessage("Camera warming up…");
    } catch {
      setMessage(
        "Could not open the camera. Check camera permission in settings.",
      );
    }
  }
  async function scan() {
    if (!pair || scanning.current || !active) return;
    if (mode === "Phone camera" && (!ready || !cameraOn)) return;
    if (mode === "Live feed" && !feed?.image) return;
    scanning.current = true;
    setBusy(true);
    const epoch = generation.current;
    const controller = new AbortController();
    request.current = controller;
    const timeout = setTimeout(() => controller.abort(), 190000);
    const cacheFiles: string[] = [];
    try {
      let image = feed?.image || "";
      let frameWidth = feed?.width || 640,
        frameHeight = feed?.height || 480;
      if (mode === "Phone camera") {
        // The web camera announces its stream before the first playable frame.
        if (Platform.OS === "web") {
          const deadline = Date.now() + 10000;
          while (true) {
            const video = document.querySelector("video");
            if (video && video.readyState >= 2 && video.videoWidth > 0) break;
            if (epoch !== generation.current) return;
            if (Date.now() > deadline)
              throw new Error("The camera is still warming up. Try again.");
            await new Promise((resolve) => setTimeout(resolve, 100));
          }
        }
        const photo = await camera.current?.takePictureAsync({
          quality: 0.8,
          shutterSound: false,
        });
        if (!photo)
          throw new Error("The camera is still warming up. Try again.");
        cacheFiles.push(photo.uri);
        const scale = Math.min(1, 1280 / photo.width, 960 / photo.height);
        const resized = await manipulateAsync(
          photo.uri,
          [
            {
              resize: {
                width: Math.round(photo.width * scale),
                height: Math.round(photo.height * scale),
              },
            },
          ],
          { compress: 0.8, format: SaveFormat.JPEG, base64: true },
        );
        cacheFiles.push(resized.uri);
        frameWidth = resized.width;
        frameHeight = resized.height;
        if (!resized.base64)
          throw new Error("Could not prepare this camera frame.");
        image = `data:image/jpeg;base64,${resized.base64}`;
      }
      if (epoch !== generation.current) return;
      setMessage("Analyzing this frame with Perceptron…");
      const result = await scoutRequest<Omit<Scan, "image">>(
        pair,
        "analyze",
        controller.signal,
        image,
        { width: frameWidth, height: frameHeight },
      );
      if (epoch !== generation.current) return;
      const entry: Scan = {
        ...result,
        image,
        time: new Date().toLocaleTimeString(),
        detections: tracker.current.update(result.detections),
      };
      setSelected(entry);
      setHistory((old) => [entry, ...old].slice(0, 12));
      setMessage(
        `${entry.detections.length} visible belongings identified. No listing was created.`,
      );
    } catch (error) {
      if (epoch === generation.current) {
        setMessage(error instanceof Error ? error.message : String(error));
        setAutomatic(false);
      }
    } finally {
      clearTimeout(timeout);
      if (Platform.OS !== "web")
        for (const uri of new Set(cacheFiles)) {
          try {
            if (uri.startsWith("file:")) new File(uri).delete();
          } catch {}
        }
      scanning.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    scanAction.current = scan;
  });
  useEffect(() => {
    const available =
      mode === "Phone camera" ? ready && cameraOn : feed?.online;
    if (!automatic || busy || !available || !active) return;
    const timer = setTimeout(() => void scanAction.current(), 5000);
    return () => clearTimeout(timer);
  }, [automatic, busy, ready, cameraOn, active, mode, feed?.online]);

  return (
    <Page>
      <Text style={s.label}>CAMPUS SCOUT · PERCEPTRON Mk1.5</Text>
      <Text style={s.title}>A scout in your pocket.</Text>
      <Text style={s.body}>
        Identify belongings with your phone, or see the rover’s latest camera
        frames.
      </Text>
      {cloudMode && (
        <Text style={s.label}>CLOUD JUDGING FEED · NO PAIRING CODE NEEDED</Text>
      )}
      {!pair ? (
        <View style={s.card}>
          <Text style={s.heading}>Connect to Scout</Text>
          <Text style={s.body}>
            Keep both Expo and the Scout gateway running on your laptop. Paste
            the one pairing code printed by the gateway. Scout connects through
            the same Expo tunnel as this app.
          </Text>
          <Field
            label="Scout pairing code"
            value={link}
            onChangeText={setLink}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
            placeholder="Paste the code from scout:gateway"
          />
          <Button
            title={connecting ? "Connecting…" : "Connect to Scout"}
            onPress={() => void connect()}
            disabled={connecting || !link.trim()}
          />
        </View>
      ) : (
        <>
          <Chips
            values={["Phone camera", "Live feed"]}
            value={mode}
            onChange={(value) => {
              stop();
              setFeed(null);
              setMode(value);
            }}
          />
          {mode === "Phone camera" ? (
            <View style={s.card}>
              <Text style={s.heading}>Your phone camera</Text>
              {cameraOn && active && permission?.granted ? (
                <CameraView
                  key={front ? "front" : "back"}
                  ref={camera}
                  style={{
                    width: "100%",
                    aspectRatio: 3 / 4,
                    borderRadius: 16,
                  }}
                  facing={front ? "front" : "back"}
                  mute
                  onCameraReady={() => {
                    setReady(true);
                    setMessage(
                      "Camera ready. Place a belonging in view, then scan.",
                    );
                  }}
                  onMountError={({ message }) => {
                    stop();
                    setMessage(message);
                  }}
                />
              ) : (
                <Button title="Enable camera" onPress={() => void enable()} />
              )}
              {!permission?.granted &&
                permission?.canAskAgain === false &&
                Platform.OS !== "web" && (
                  <Button
                    title="Open phone settings"
                    secondary
                    onPress={() => void Linking.openSettings()}
                  />
                )}
              {cameraOn && (
                <>
                  <Button
                    title={busy ? "Analyzing…" : "Scan this view"}
                    disabled={!ready || busy}
                    onPress={() => void scan()}
                  />
                  <Button
                    title={automatic ? "Pause scans" : "Start 5-second scans"}
                    secondary
                    disabled={!ready || (busy && !automatic)}
                    onPress={() => {
                      setAutomatic(!automatic);
                      if (automatic)
                        setMessage(
                          "Scans paused. The current request will finish.",
                        );
                    }}
                  />
                  <Button
                    title="Flip camera"
                    secondary
                    disabled={busy}
                    onPress={() => {
                      setAutomatic(false);
                      setReady(false);
                      setFront(!front);
                      tracker.current = new RepeatTracker();
                    }}
                  />
                  <Button title="Stop camera" secondary onPress={stop} />
                </>
              )}
              <Text style={s.small}>
                Microphone off. Scans send selected images to Perceptron through
                your computer. Automatic scans wait for inference to finish. No
                GPS or Supabase listings.
              </Text>
            </View>
          ) : (
            <View style={s.card}>
              <Chips
                values={["Laptop webcam", "Rover"]}
                value={source}
                onChange={(value) => {
                  stop();
                  setFeed(null);
                  setSource(value);
                }}
              />
              <Text style={s.heading}>
                {source === "Rover"
                  ? "Rover camera feed"
                  : "Shared computer webcam"}
              </Text>
              <Text style={s.label}>
                {feed?.online ? "LIVE · SAMPLED FRAMES" : "OFFLINE / WAITING"}
              </Text>
              {!!feed?.image && (
                <>
                  <ScoutImage scan={feed} preview />
                  {source !== "Rover" && (
                    <Text testID="live-frame-counter" style={s.label}>
                      Laptop preview · frame {feed.frame_id ?? 0}
                    </Text>
                  )}
                  <Text style={s.small}>
                    {feed.updated_at
                      ? `Last frame ${new Date(feed.updated_at * 1000).toLocaleTimeString()} · ${Math.max(0, Math.round(Date.now() / 1000 - feed.updated_at))}s ago`
                      : ""}
                    {feed.camera !== undefined
                      ? ` · Camera ${feed.camera}`
                      : ""}
                  </Text>
                  <Button
                    title={busy ? "Analyzing…" : "Analyze this feed frame"}
                    disabled={busy || !feed.online}
                    onPress={() => void scan()}
                  />
                  <Button
                    title={automatic ? "Pause scans" : "Start 5-second scans"}
                    secondary
                    disabled={!feed.online || (busy && !automatic)}
                    onPress={() => setAutomatic(!automatic)}
                  />
                  {feed.analysis && (
                    <View style={{ gap: 12 }}>
                      <Text style={s.heading}>Latest laptop analysis</Text>
                      <ScoutImage scan={feed.analysis} />
                      <Text style={s.small}>
                        {new Date(
                          feed.analysis.updated_at * 1000,
                        ).toLocaleTimeString()}{" "}
                        · {feed.analysis.elapsed_s}s response
                      </Text>
                    </View>
                  )}
                </>
              )}
              <Text style={s.small}>
                {source === "Rover"
                  ? "Start the rover vision demo on the computer. This view shows its actual published model frames, usually every five seconds; it is not continuous video."
                  : cloudMode
                    ? "The operator must enable the laptop webcam and click Share with judging link. Consented frames are relayed through Supabase and expire when sharing stops. Phone-camera analysis works independently."
                    : "On your laptop, open http://127.0.0.1:8769/ and choose Enable webcam. Its preview is shared here automatically. Select Rover only when a rover vision demo is running."}
              </Text>
            </View>
          )}
          <Button
            title={cloudMode ? "Refresh cloud feed" : "Disconnect Scout"}
            secondary
            onPress={() => {
              if (cloudMode) {
                setPair({ url: "", token: "", transport: "supabase" });
                return;
              }
              stop();
              setPair(null);
              setFeed(null);
              setSelected(null);
              setHistory([]);
              setMessage(
                "Disconnected. Reconnect with the current pairing code.",
              );
            }}
          />
        </>
      )}
      <Text accessibilityRole="text" style={s.body}>
        {message}
      </Text>
      {selected && (
        <View style={s.card}>
          <Text style={s.heading}>Analyzed snapshot</Text>
          <ScoutImage scan={selected} />
          <Text style={s.small}>
            {selected.time} · {selected.elapsed_s}s response ·{" "}
            {selected.skipped_count} candidates rejected
          </Text>
        </View>
      )}
      {history.length > 0 && (
        <View style={s.card}>
          <Text style={s.heading}>Your last {history.length} scans</Text>
          {history.map((entry, i) => (
            <Button
              key={i}
              secondary
              title={`${entry.time} · ${entry.detections.map((d) => d.title).join(", ") || "No items identified"}`}
              onPress={() => setSelected(entry)}
            />
          ))}
          <Button
            title="Clear scan history"
            secondary
            onPress={() => {
              setAutomatic(false);
              generation.current++;
              request.current?.abort();
              setHistory([]);
              setSelected(null);
              tracker.current = new RepeatTracker();
            }}
          />
          <Text style={s.small}>
            History stays in memory for this session. Repeat sightings show
            similar overlapping detections in consecutive scans; they do not
            establish ownership or abandonment.
          </Text>
        </View>
      )}
    </Page>
  );
}
