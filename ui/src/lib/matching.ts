import { FoundItem, MissingReport } from "./types";
export const weights = {
  category: 35,
  color: 20,
  location: 20,
  time: 10,
  keywords: 15,
};
export function scoreMatch(report: MissingReport, item: FoundItem) {
  let score = 0;
  const reasons: string[] = [];
  if (report.category === item.category) {
    score += weights.category;
    reasons.push("Same category");
  }
  if (
    report.color.trim() &&
    report.color.toLowerCase().trim() === item.color.toLowerCase().trim()
  ) {
    score += weights.color;
    reasons.push("Similar color");
  }
  const distance = Math.hypot(
    (report.latitude - item.latitude) * 111320,
    (report.longitude - item.longitude) * 75000,
  );
  if (distance < 600) {
    score += weights.location;
    reasons.push("Nearby location");
  }
  const elapsed =
    Date.parse(item.discovered_at) - Date.parse(report.last_seen_at);
  if (elapsed >= 0 && elapsed < 7 * 86400000) {
    score += weights.time;
    reasons.push("Found after you last saw it");
  }
  const words = report.description.toLowerCase().match(/\b[a-z]{4,}\b/g) || [];
  if (words.some((w) => item.description.toLowerCase().includes(w))) {
    score += weights.keywords;
    reasons.push("Similar description");
  }
  return { score, reasons, label: matchLabel(score) };
}
export function matchLabel(score: number) {
  return score >= 75
    ? "Strong match"
    : score >= 50
      ? "Possible match"
      : "Weak match";
}
