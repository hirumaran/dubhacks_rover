import assert from "node:assert/strict";
import { test } from "node:test";
import { scoreMatch } from "../src/lib/matching";
import { FoundItem, MissingReport } from "../src/lib/types";
const report = {
  category: "Water Bottles",
  color: " Black ",
  description: "insulated bottle silver lid",
  latitude: 47.65,
  longitude: -122.3,
  last_seen_at: "2026-10-16T12:00:00Z",
} as MissingReport;
const item = {
  category: "Water Bottles",
  color: "black",
  description: "Insulated bottle",
  latitude: 47.6501,
  longitude: -122.3001,
  discovered_at: "2026-10-16T13:00:00Z",
} as FoundItem;
test("ranks matching category, color, nearby location, time and keywords", () => {
  const m = scoreMatch(report, item);
  assert.equal(m.score, 100);
  assert.equal(m.label, "Strong match");
  assert.equal(m.reasons.length, 5);
});
test("an item found before the loss receives no temporal credit", () => {
  const m = scoreMatch(report, {
    ...item,
    discovered_at: "2026-10-15T12:00:00Z",
  });
  assert.equal(m.score, 90);
  assert.ok(!m.reasons.includes("Found after you last saw it"));
});
test("unrelated distant item is weak", () => {
  assert.equal(
    scoreMatch(report, {
      ...item,
      category: "Keys",
      color: "Silver",
      description: "keys",
      latitude: 40,
      discovered_at: "2025-01-01",
    }).score,
    0,
  );
});
test("blank colors never count as matching", () => {
  assert.ok(
    !scoreMatch(
      { ...report, color: "" },
      { ...item, color: "" },
    ).reasons.includes("Similar color"),
  );
});
