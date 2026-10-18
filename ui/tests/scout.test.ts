import assert from "node:assert/strict";
import { test } from "node:test";
import {
  parsePairing,
  RepeatTracker,
  Detection,
  expoOrigin,
} from "../src/lib/scout";

const token = "a".repeat(43);
test("one pairing code uses the Expo tunnel instead of a laptop adapter address", () => {
  const origin = expoOrigin("test-8082.exp.direct");
  assert.equal(origin, "https://test-8082.exp.direct");
  assert.equal(expoOrigin("192.168.1.5:8081"), "http://192.168.1.5:8081");
  assert.deepEqual(parsePairing(token, origin), { url: origin, token });
  assert.equal(
    parsePairing(`http://192.168.56.1:8769/#${token}`, origin).url,
    origin,
  );
  assert.throws(() => parsePairing(token));
});
test("pairing accepts a private LAN or HTTPS gateway and separates its code from the URL", () => {
  assert.deepEqual(parsePairing(`http://192.168.1.10:8769/#${token}`), {
    url: "http://192.168.1.10:8769",
    token,
  });
  assert.equal(
    parsePairing(`https://gateway.example/#${token}`).url,
    "https://gateway.example",
  );
  for (const value of [
    `http://public.example/#${token}`,
    "http://192.168.1.10:8769/",
    `https://user:pass@gateway.example/#${token}`,
    `https://gateway.example/private#${token}`,
  ])
    assert.throws(() => parsePairing(value));
});
test("repeat sightings require consecutive overlapping detections of the same kind and color", () => {
  const tracker = new RepeatTracker();
  const bottle: Detection = {
    title: "Black bottle",
    color: "Black",
    bbox: [0.1, 0.1, 0.3, 0.3],
  };
  assert.equal(tracker.update([bottle])[0].repeated, false);
  const repeated = tracker.update([bottle, bottle]);
  assert.equal(repeated[0].consecutive_scans, 2);
  assert.equal(repeated[1].repeated, false); // One old object cannot match two new ones.
  tracker.update([]);
  assert.equal(tracker.update([bottle])[0].repeated, false);
  assert.equal(
    tracker.update([{ ...bottle, color: "Blue" }])[0].repeated,
    false,
  );
  assert.equal(
    tracker.update([{ ...bottle, bbox: [0.7, 0.7, 0.2, 0.2] }])[0].repeated,
    false,
  );
});
