"""Match agent (query side of the flowchart) - the web branch imports this.

Compose match candidates for a student's lost-item report:
  * text similarity (label exact + description token overlap + color)
  * recency decay
  * returns the FIRST sighting of the matched object (that's where it stopped)
"""
from __future__ import annotations
import math
import re
from datetime import datetime, timezone

import config
from config import SUPABASE_URL

WORDS_RE = re.compile(r"[a-z]{3,}")


def _tokens(text: str) -> set[str]:
    return set(WORDS_RE.findall((text or "").lower()))


def _client():
    if not config.supabase_ready():
        raise RuntimeError("Fill perception/.env with SUPABASE_URL + keys first.")
    from supabase import create_client
    # Read side needs no RLS bypass; anon key is the safe key here.
    key = config.SUPABASE_ANON_KEY or config.SUPABASE_SERVICE_KEY
    return create_client(SUPABASE_URL, key)


def find_matches(query_text: str, top_k: int = 5) -> list[dict]:
    """Top-k candidate objects for a typed description."""
    sb = _client()
    q_tokens = _tokens(query_text)
    if not q_tokens:
        return []
    rows = (
        sb.table("recent_sightings")
        .select("*")
        .order("created_at", desc=True)
        .limit(300)
        .execute()
        .data or []
    )
    scored = []
    now = datetime.now(timezone.utc)
    for r in rows:
        blob = f"{r.get('label', '')} {r.get('description', '')} {r.get('color', '')}"
        tokens = _tokens(blob)
        if not tokens:
            continue
        label_hit = r["label"] in query_text.lower() or r["label"] in tokens
        overlap = len(q_tokens & tokens) / max(1, len(q_tokens))
        color_hit = 1.0 if (r.get("color") and r["color"] in q_tokens) else 0.0
        if not (label_hit or overlap > 0.25):
            continue
        age_h = _age_hours(r.get("created_at"), now)
        recency = math.exp(-age_h / 24.0)
        score = round(0.5 * overlap + 0.2 * float(label_hit) + 0.1 * color_hit + 0.2 * recency, 3)
        scored.append({**r, "match_score": score})
    scored.sort(key=lambda d: d["match_score"], reverse=True)
    dedup, seen = [], set()
    for s in scored:
        if s["object_id"] in seen:
            continue
        seen.add(s["object_id"])
        dedup.append(s)
        if len(dedup) >= top_k:
            break
    return dedup


def first_sighting(object_id: str) -> dict | None:
    """Earliest sighting of an object = where it stopped / was left."""
    sb = _client()
    rows = (
        sb.table("sightings")
        .select("*")
        .eq("object_id", object_id)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
        .data or []
    )
    return rows[0] if rows else None


def log_lost_item(query_text: str, created_by: str | None = None, matches: list[dict] | None = None) -> str | None:
    sb = _client()
    best = (matches or [None])[0]
    payload = {
        "created_by": created_by,
        "query_text": query_text,
        "status": "open",
    }
    if best:
        payload.update({
            "status": "matched",
            "matched_object_id": best["object_id"],
            "match_confidence": best["match_score"],
            "match_reason": f"matched on {best['label']} similarity {best['match_score']:.2f}",
        })
    res = sb.table("lost_items").insert(payload).execute()
    data = res.data or []
    return data[0]["id"] if data else None


def _age_hours(ts, now) -> float:
    if not ts:
        return 999.0
    try:
        t = ts.replace("Z", "+00:00") if isinstance(ts, str) else ts
        dt = datetime.fromisoformat(str(t))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt).total_seconds() / 3600.0)
    except ValueError:
        return 999.0


def answer_for_object(query_text: str, candidate: dict, first: dict | None) -> str:
    g = first["geotag"] if first else (candidate.get("geotag") or {})
    loc = f"x={g.get('x', '?')}, y={g.get('y', '?')}" if g else "unknown"
    area = g.get("area_hint", "")
    age = _age_hours(candidate.get("created_at"), datetime.now(timezone.utc))
    conf = float(candidate.get("match_score", 0)) * 100
    return (
        f"Best match for \"{query_text}\": {candidate.get('label')} "
        f"({candidate.get('description')}). First seen near {loc}"
        + (f" ({area}), " if area else ", ")
        + f"at {first['created_at'] if first else 'unknown time'}, "
        f"~{age:.1f}h ago, match confidence {conf:.0f}%."
        + (f" Photo: {first['image_url']}" if first and first.get("image_url") else "")
    )
