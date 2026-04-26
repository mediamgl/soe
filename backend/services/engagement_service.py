"""Engagement analytics — pure derivations from a session document.

Phase 11B — admin-only visualisations powered entirely from data already
captured in earlier phases (response_time_ms on each psychometric answer,
timestamps + latency_ms on conversation turns, and time_on_phase_ms on the
scenario). Never calls the LLM. Never writes to Mongo.

Three top-level functions:
  - psychometric_engagement(session_doc) -> dict
  - ai_discussion_engagement(session_doc) -> dict
  - scenario_engagement(session_doc) -> dict

All three are tolerant of partial or missing data — they return the same
top-level keys even when sub-stages have not yet been completed, with
explicit None / [] fields rather than raising.
"""
from __future__ import annotations
from datetime import datetime
import statistics
from typing import Any, Dict, List, Optional, Tuple

import psychometric_service as ps
from services import scenario_service as scn


# --------------------------------------------------------------------------- #
# 1. Psychometric engagement
# --------------------------------------------------------------------------- #
def _band_for_response_time(rt_ms: int, median_ms: float) -> str:
    """Bucket a per-item response time relative to the participant's own median.

    fast        rt < 0.5 × median
    normal      0.5 × median ≤ rt < 1.5 × median
    slow        1.5 × median ≤ rt < 2.5 × median
    deliberated rt ≥ 2.5 × median
    """
    if median_ms <= 0:
        return "normal"
    ratio = rt_ms / median_ms
    if ratio < 0.5:
        return "fast"
    if ratio < 1.5:
        return "normal"
    if ratio < 2.5:
        return "slow"
    return "deliberated"


def _percentile(values: List[int], pct: float) -> float:
    """Linear-interpolated percentile. `pct` in [0, 100]. Returns 0 for empty."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return float(s[lo]) + (s[hi] - s[lo]) * frac


def psychometric_engagement(session_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Per-item response time analytics + summary stats.

    Empty-data shape (when no answers or psychometric block missing):
      {"items": [], "summary": None}
    """
    psych = (session_doc or {}).get("psychometric") or {}
    answers = psych.get("answers") or []
    if not answers:
        return {"items": [], "summary": None}

    # Display order: prefer the participant-specific `psychometric.order`
    # (randomised at session init); fall back to the order they were answered
    # in if order was somehow not stored.
    order: List[str] = psych.get("order") or [a.get("item_id") for a in answers]
    answered_by_id: Dict[str, Dict[str, Any]] = {a.get("item_id"): a for a in answers}

    rts = [int(a.get("response_time_ms", 0) or 0) for a in answers]
    median_ms = statistics.median(rts) if rts else 0.0
    p25 = _percentile(rts, 25.0)
    p75 = _percentile(rts, 75.0)
    iqr = p75 - p25
    deliberation_threshold = p75 + 1.5 * iqr

    item_id_to_meta: Dict[str, Dict[str, Any]] = {}
    for it in ps.get_items():
        item_id_to_meta[it["item_id"]] = it

    items: List[Dict[str, Any]] = []
    for iid in order:
        a = answered_by_id.get(iid)
        if not a:
            continue
        rt = int(a.get("response_time_ms", 0) or 0)
        meta = item_id_to_meta.get(iid) or {}
        items.append({
            "item_id": iid,
            "scale": meta.get("scale"),
            "subscale": meta.get("subscale"),
            "is_reverse_keyed": bool(meta.get("is_reverse_keyed")),
            "text": meta.get("text"),
            "value": a.get("value"),
            "response_time_ms": rt,
            "response_time_band": _band_for_response_time(rt, median_ms),
        })

    # Fastest / slowest / deliberated lists.
    by_rt_asc = sorted(items, key=lambda x: x["response_time_ms"])
    fastest_3 = [x["item_id"] for x in by_rt_asc[:3]]
    slowest_3 = [x["item_id"] for x in reversed(by_rt_asc[-3:])]
    deliberated_count = sum(
        1 for x in items if x["response_time_ms"] > deliberation_threshold
    )

    return {
        "items": items,
        "summary": {
            "median_ms": int(median_ms),
            "p25_ms": int(p25),
            "p75_ms": int(p75),
            "iqr_ms": int(iqr),
            "deliberation_threshold_ms": int(deliberation_threshold),
            "fastest_3": fastest_3,
            "slowest_3": slowest_3,
            "deliberated_count": deliberated_count,
        },
    }


# --------------------------------------------------------------------------- #
# 2. AI Discussion engagement
# --------------------------------------------------------------------------- #
def _word_count(text: Optional[str]) -> int:
    if not text:
        return 0
    return len([w for w in text.strip().split() if w])


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def ai_discussion_engagement(session_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Per-turn engagement stats for the AI Fluency conversation.

    Empty-data shape (when no conversation):
      {"turns": [], "user_summary": None, "assistant_summary": None}
    """
    conversation = (session_doc or {}).get("conversation") or []
    # Filter out internal "dev" turns (those carry kind=='dev' per Phase 5).
    public = [t for t in conversation if t.get("kind") != "dev"]
    if not public:
        return {"turns": [], "user_summary": None, "assistant_summary": None}

    turns: List[Dict[str, Any]] = []
    last_assistant_ts: Optional[datetime] = None
    for idx, t in enumerate(public):
        role = t.get("role")
        content = t.get("content") or ""
        ts = _parse_iso(t.get("timestamp"))
        words = _word_count(content)
        chars = len(content)
        entry: Dict[str, Any] = {
            "turn_index": idx,
            "role": role,
            "content_length_chars": chars,
            "content_length_words": words,
            "timestamp": t.get("timestamp"),
        }
        if role == "user":
            ttr_ms: Optional[int] = None
            if ts and last_assistant_ts:
                delta = (ts - last_assistant_ts).total_seconds() * 1000.0
                # Negative deltas can happen if the seed stamps both turns at
                # the same moment; clamp to 0 so the UI doesn't show negatives.
                ttr_ms = max(0, int(delta))
            entry["time_to_respond_ms"] = ttr_ms
        else:
            entry["model_latency_ms"] = t.get("latency_ms")
            entry["provider"] = t.get("provider")
            entry["model"] = t.get("model")
            entry["fallbacks_tried"] = int(t.get("fallbacks_tried") or 0)
            if ts:
                last_assistant_ts = ts
        turns.append(entry)

    user_turns = [t for t in turns if t["role"] == "user"]
    assistant_turns = [t for t in turns if t["role"] == "assistant"]

    user_summary = None
    if user_turns:
        word_counts = [t["content_length_words"] for t in user_turns]
        ttrs = [t.get("time_to_respond_ms") for t in user_turns
                if t.get("time_to_respond_ms") is not None]
        # Determine longest / shortest by *word count* — more meaningful for
        # transcripts than raw chars (the UI strip says "longest turn"
        # interpreted as "most-said turn").
        longest_idx = max(range(len(user_turns)), key=lambda i: user_turns[i]["content_length_words"])
        shortest_idx = min(range(len(user_turns)), key=lambda i: user_turns[i]["content_length_words"])
        slowest_ttr_idx: Optional[int] = None
        if ttrs:
            with_ttr = [(i, u.get("time_to_respond_ms")) for i, u in enumerate(user_turns)
                        if u.get("time_to_respond_ms") is not None]
            if with_ttr:
                slowest_ttr_idx = max(with_ttr, key=lambda x: x[1])[0]
        user_summary = {
            "total_turns": len(user_turns),
            "avg_words_per_turn": round(sum(word_counts) / len(word_counts), 1),
            "max_words": max(word_counts),
            "min_words": min(word_counts),
            "longest_turn_index": user_turns[longest_idx]["turn_index"],
            "shortest_turn_index": user_turns[shortest_idx]["turn_index"],
            "avg_time_to_respond_ms": int(sum(ttrs) / len(ttrs)) if ttrs else None,
            "slowest_response_turn_index": (
                user_turns[slowest_ttr_idx]["turn_index"] if slowest_ttr_idx is not None else None
            ),
        }

    assistant_summary = None
    if assistant_turns:
        latencies = [int(t["model_latency_ms"]) for t in assistant_turns
                     if isinstance(t.get("model_latency_ms"), (int, float)) and t["model_latency_ms"] >= 0]
        fallbacks_total = sum(int(t.get("fallbacks_tried") or 0) for t in assistant_turns)
        assistant_summary = {
            "total_turns": len(assistant_turns),
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
            "max_latency_ms": max(latencies) if latencies else None,
            "fallbacks_total": fallbacks_total,
        }

    return {
        "turns": turns,
        "user_summary": user_summary,
        "assistant_summary": assistant_summary,
    }


# --------------------------------------------------------------------------- #
# 3. Scenario engagement
# --------------------------------------------------------------------------- #
SCENARIO_PHASE_TARGETS_MIN: List[Tuple[str, int]] = [
    ("read",      scn.DURATION_READ_MIN),
    ("part1",     scn.DURATION_PART1_MIN),
    ("curveball", scn.DURATION_CURVEBALL_MIN),
    ("part2",     scn.DURATION_PART2_MIN),
]


def scenario_engagement(session_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Phase-by-phase actual vs target time analytics.

    Empty-data shape (no scenario.time_on_phase_ms keys present):
      {"phases": [], "summary": None}
    """
    scenario = (session_doc or {}).get("scenario") or {}
    time_on_phase = scenario.get("time_on_phase_ms") or {}
    if not time_on_phase:
        return {"phases": [], "summary": None}

    phases: List[Dict[str, Any]] = []
    total_actual = 0
    total_target = 0
    for phase_name, target_min in SCENARIO_PHASE_TARGETS_MIN:
        actual_ms = int(time_on_phase.get(phase_name) or 0)
        target_ms = int(target_min * 60 * 1000)
        ratio = (actual_ms / target_ms) if target_ms > 0 else 0.0
        phases.append({
            "phase": phase_name,
            "target_minutes": target_min,
            "target_ms": target_ms,
            "actual_ms": actual_ms,
            "ratio": round(ratio, 3),
            "overran": actual_ms > target_ms,
        })
        total_actual += actual_ms
        total_target += target_ms

    overall_ratio = (total_actual / total_target) if total_target > 0 else 0.0
    # Most / least engaged use ratio (so a short target is fairly compared).
    # Phases with actual_ms == 0 (skipped or not yet entered) are excluded.
    nonzero = [p for p in phases if p["actual_ms"] > 0]
    if nonzero:
        most = max(nonzero, key=lambda p: p["ratio"])
        least = min(nonzero, key=lambda p: p["ratio"])
        most_phase = most["phase"]
        least_phase = least["phase"]
    else:
        most_phase = None
        least_phase = None

    return {
        "phases": phases,
        "summary": {
            "total_actual_ms": total_actual,
            "total_target_ms": total_target,
            "overall_ratio": round(overall_ratio, 3),
            "most_engaged_phase": most_phase,
            "least_engaged_phase": least_phase,
        },
    }


# --------------------------------------------------------------------------- #
# Convenience top-level
# --------------------------------------------------------------------------- #
def build_engagement(session_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Bundle of all three engagement payloads for a single session."""
    return {
        "psychometric": psychometric_engagement(session_doc),
        "ai_discussion": ai_discussion_engagement(session_doc),
        "scenario": scenario_engagement(session_doc),
    }
