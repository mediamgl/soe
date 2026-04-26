"""Cohort aggregation — pure derivations across N session documents.

Phase 11C — admin-only N≥2 cohort view. No LLM calls. No Mongo writes.
Six top-level derivations, each independently unit-testable:
  - aggregate_dimensions(sessions) → 6 dimension_stats rows
  - compute_heatmap(sessions)      → rows × 6-dim matrix
  - find_outliers(sessions, z=1.5) → per-dim low / high lists
  - derive_cohort_type(dim_stats)  → top_strengths / top_dev_areas + sentences
  - summarise_categories_and_flags(sessions) → distribution counts
  - build_cohort(sessions)         → bundle of all of the above

Score field paths are taken from `deliverable.dimension_profiles` when
available (already normalised) and fall back to the raw `scores.*` paths.
"""
from __future__ import annotations
import math
import statistics
from typing import Any, Dict, List, Optional


# Same axis order as the participant radar / admin compare radar.
COHORT_AXIS_ORDER: List[str] = [
    "learning_agility",
    "tolerance_for_ambiguity",
    "cognitive_flexibility",
    "self_awareness_accuracy",
    "ai_fluency",
    "systems_thinking",
]
COHORT_DIM_LABELS: Dict[str, str] = {
    "learning_agility":         "Learning Agility",
    "tolerance_for_ambiguity":  "Tolerance for Ambiguity",
    "cognitive_flexibility":    "Cognitive Flexibility",
    "self_awareness_accuracy":  "Self-Awareness Accuracy",
    "ai_fluency":               "AI Fluency",
    "systems_thinking":         "Systems Thinking",
}

# Five-bucket band scheme used in the cohort heatmap and band_distribution.
# Names per the Phase 11C brief.
COHORT_BAND_THRESHOLDS = [
    ("Exceptional", 4.5),
    ("Strong",      4.0),
    ("Moderate",    3.0),
    ("Limited",     2.0),
    ("Low",         0.0),
]
COHORT_BAND_NAMES = [b[0] for b in COHORT_BAND_THRESHOLDS]

VALID_OVERALL_CATEGORIES = [
    "Transformation Ready",
    "High Potential",
    "Development Required",
    "Limited Readiness",
]
RESPONSE_FLAG_NAMES = [
    "high_acquiescence",
    "low_variance",
    "extreme_response_bias",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _band_for(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    s = float(score)
    for name, lo in COHORT_BAND_THRESHOLDS:
        if s >= lo:
            return name
    return "Low"


def _short_label(participant: Dict[str, Any]) -> str:
    """Compact participant label for charts: 'Ada L.' / 'Claire A.'.
    Falls back to '(redacted)' or the session_id prefix when name is absent."""
    name = (participant or {}).get("name")
    if not name:
        return "(unknown)"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "(unknown)"
    if len(parts) == 1:
        return parts[0][:18]
    last_initial = parts[-1][0].upper()
    return f"{parts[0]} {last_initial}."


def _dim_score_from_doc(doc: Dict[str, Any], dim_id: str) -> Optional[float]:
    """Read a normalised 1.0–5.0 dimension score from a session doc.
    Prefers deliverable.dimension_profiles[].score; falls back to raw paths."""
    profiles = ((doc or {}).get("deliverable") or {}).get("dimension_profiles") or []
    for p in profiles:
        if p.get("dimension_id") == dim_id:
            try:
                return float(p.get("score"))
            except (TypeError, ValueError):
                pass
    raw_paths = {
        "learning_agility":         ("scores", "psychometric", "learning_agility", "mean_1_5"),
        "tolerance_for_ambiguity":  ("scores", "psychometric", "tolerance_for_ambiguity", "mean_1_5"),
        "self_awareness_accuracy":  ("scores", "psychometric", "self_awareness_claimed", "mean_1_5"),
        "ai_fluency":               ("scores", "ai_fluency", "overall_score"),
        "cognitive_flexibility":    ("scores", "scenario", "cognitive_flexibility", "score"),
        "systems_thinking":         ("scores", "scenario", "systems_thinking", "score"),
    }
    path = raw_paths.get(dim_id)
    if not path:
        return None
    node: Any = doc
    for seg in path:
        if not isinstance(node, dict):
            return None
        node = node.get(seg)
        if node is None:
            return None
    try:
        return float(node)
    except (TypeError, ValueError):
        return None


def _percentile(values: List[float], pct: float) -> float:
    """Linear-interpolated percentile. `pct` in [0, 100]. 0.0 for empty."""
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


# --------------------------------------------------------------------------- #
# 1. aggregate_dimensions
# --------------------------------------------------------------------------- #
def aggregate_dimensions(session_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """6-row dimension stats with mean/median/p25/p75/min/max/std_dev and a
    band_distribution count for each of the 5 cohort bands."""
    out: List[Dict[str, Any]] = []
    for dim_id in COHORT_AXIS_ORDER:
        scores: List[float] = []
        for d in session_docs:
            s = _dim_score_from_doc(d, dim_id)
            if s is not None:
                scores.append(s)
        band_counts = {name: 0 for name in COHORT_BAND_NAMES}
        for s in scores:
            band = _band_for(s)
            if band:
                band_counts[band] += 1
        if scores:
            mean = statistics.fmean(scores)
            median = statistics.median(scores)
            p25 = _percentile(scores, 25.0)
            p75 = _percentile(scores, 75.0)
            mn = min(scores)
            mx = max(scores)
            std_dev = statistics.pstdev(scores) if len(scores) > 1 else 0.0
        else:
            mean = median = p25 = p75 = mn = mx = std_dev = 0.0
        out.append({
            "dimension_id": dim_id,
            "label":        COHORT_DIM_LABELS[dim_id],
            "n":            len(scores),
            "mean":         round(mean, 3),
            "median":       round(median, 3),
            "p25":          round(p25, 3),
            "p75":          round(p75, 3),
            "min":          round(mn, 3),
            "max":          round(mx, 3),
            "std_dev":      round(std_dev, 3),
            "band_distribution": band_counts,
        })
    return out


# --------------------------------------------------------------------------- #
# 2. compute_heatmap
# --------------------------------------------------------------------------- #
def compute_heatmap(session_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """rows = participants (in input order), columns = COHORT_AXIS_ORDER."""
    rows: List[Dict[str, Any]] = []
    for d in session_docs:
        scores = [_dim_score_from_doc(d, dim) for dim in COHORT_AXIS_ORDER]
        rows.append({
            "session_id": d.get("session_id"),
            "label":      _short_label(d.get("participant") or {}),
            "name":       (d.get("participant") or {}).get("name"),
            "scores":     [round(s, 3) if s is not None else None for s in scores],
        })
    return {"axis_order": COHORT_AXIS_ORDER, "rows": rows}


# --------------------------------------------------------------------------- #
# 3. find_outliers
# --------------------------------------------------------------------------- #
def find_outliers(session_docs: List[Dict[str, Any]],
                  threshold_z: float = 1.5) -> List[Dict[str, Any]]:
    """Per-dimension low / high outlier lists by absolute z-score."""
    out: List[Dict[str, Any]] = []
    for dim_id in COHORT_AXIS_ORDER:
        scored: List[Dict[str, Any]] = []
        for d in session_docs:
            s = _dim_score_from_doc(d, dim_id)
            if s is None:
                continue
            scored.append({
                "session_id": d.get("session_id"),
                "label":      _short_label(d.get("participant") or {}),
                "name":       (d.get("participant") or {}).get("name"),
                "score":      float(s),
            })
        low: List[Dict[str, Any]] = []
        high: List[Dict[str, Any]] = []
        if len(scored) >= 2:
            scores_only = [x["score"] for x in scored]
            mu = statistics.fmean(scores_only)
            sd = statistics.pstdev(scores_only) if len(scores_only) > 1 else 0.0
            if sd > 0:
                for x in scored:
                    z = (x["score"] - mu) / sd
                    if z <= -threshold_z:
                        low.append({
                            "session_id":     x["session_id"],
                            "label":          x["label"],
                            "name":           x["name"],
                            "score":          round(x["score"], 3),
                            "std_devs_below": round(abs(z), 3),
                        })
                    elif z >= threshold_z:
                        high.append({
                            "session_id":     x["session_id"],
                            "label":          x["label"],
                            "name":           x["name"],
                            "score":          round(x["score"], 3),
                            "std_devs_above": round(z, 3),
                        })
        # Sort within each list — most extreme first.
        low.sort(key=lambda r: -r["std_devs_below"])
        high.sort(key=lambda r: -r["std_devs_above"])
        out.append({
            "dimension_id": dim_id,
            "label":        COHORT_DIM_LABELS[dim_id],
            "low_outliers": low,
            "high_outliers": high,
        })
    return out


# --------------------------------------------------------------------------- #
# 4. derive_cohort_type
# --------------------------------------------------------------------------- #
def _format_means(means: List[float]) -> str:
    return ", ".join(f"{m:.1f}" for m in means[:-1]) + f" and {means[-1]:.1f}" \
        if len(means) > 1 else f"{means[0]:.1f}"


def derive_cohort_type(dimension_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Top-3 strengths and top-3 development areas + template sentences.

    Tie-break: alphabetical on dimension label (so the output is deterministic).
    """
    # Filter to dims with n>=1 so we don't surface dimensions with no data.
    rows = [r for r in dimension_stats if r.get("n", 0) > 0]
    by_strength = sorted(rows, key=lambda r: (-r["mean"], r["label"]))
    by_devarea  = sorted(rows, key=lambda r: ( r["mean"], r["label"]))
    top3_strength = by_strength[:3]
    top3_devarea  = by_devarea[:3]

    if not top3_strength:
        return {
            "top_strengths": [],
            "top_dev_areas": [],
            "strength_summary": "No dimension data is available for this cohort.",
            "dev_summary":      "No dimension data is available for this cohort.",
        }

    strength_labels = [r["label"] for r in top3_strength]
    devarea_labels  = [r["label"] for r in top3_devarea]
    strength_means  = [float(r["mean"]) for r in top3_strength]
    devarea_means   = [float(r["mean"]) for r in top3_devarea]

    def _join_labels(labels: List[str]) -> str:
        if len(labels) == 1:
            return labels[0]
        return ", ".join(labels[:-1]) + f" and {labels[-1]}"

    strength_summary = (
        f"This cohort's strongest dimensions are {_join_labels(strength_labels)}, "
        f"with cohort means of {_format_means(strength_means)} respectively."
    )
    dev_summary = (
        f"Highest-leverage development areas across this cohort are {_join_labels(devarea_labels)}, "
        f"with cohort means of {_format_means(devarea_means)} respectively."
    )
    return {
        "top_strengths": [
            {"dimension_id": r["dimension_id"], "label": r["label"], "mean": r["mean"]}
            for r in top3_strength
        ],
        "top_dev_areas": [
            {"dimension_id": r["dimension_id"], "label": r["label"], "mean": r["mean"]}
            for r in top3_devarea
        ],
        "strength_summary": strength_summary,
        "dev_summary":      dev_summary,
    }


# --------------------------------------------------------------------------- #
# 5. summarise_categories_and_flags
# --------------------------------------------------------------------------- #
def summarise_categories_and_flags(session_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    cat_counts = {c: 0 for c in VALID_OVERALL_CATEGORIES}
    flag_counts: Dict[str, int] = {"none": 0}
    for n in RESPONSE_FLAG_NAMES:
        flag_counts[n] = 0
    total_flagged = 0
    for d in session_docs:
        es = ((d.get("deliverable") or {}).get("executive_summary") or {})
        cat = es.get("overall_category")
        if cat in cat_counts:
            cat_counts[cat] += 1
        flag = ((d.get("scores") or {}).get("psychometric") or {}).get("response_pattern_flag")
        if flag and flag in flag_counts:
            flag_counts[flag] += 1
            total_flagged += 1
        else:
            flag_counts["none"] += 1
    flag_counts["total_flagged"] = total_flagged
    return {
        "category_distribution": cat_counts,
        "flag_summary":          flag_counts,
    }


# --------------------------------------------------------------------------- #
# 6. build_cohort — top-level convenience
# --------------------------------------------------------------------------- #
def _participant_summary(d: Dict[str, Any]) -> Dict[str, Any]:
    es = ((d.get("deliverable") or {}).get("executive_summary") or {})
    psy = ((d.get("scores") or {}).get("psychometric") or {})
    dim_scores = {dim: _dim_score_from_doc(d, dim) for dim in COHORT_AXIS_ORDER}
    return {
        "session_id":            d.get("session_id"),
        "name":                  (d.get("participant") or {}).get("name"),
        "label":                 _short_label(d.get("participant") or {}),
        "organisation":          (d.get("participant") or {}).get("organisation"),
        "role":                  (d.get("participant") or {}).get("role"),
        "completion_date":       d.get("completed_at"),
        "overall_category":      es.get("overall_category"),
        "overall_colour":        es.get("overall_colour"),
        "response_pattern_flag": psy.get("response_pattern_flag"),
        "dimension_scores":      {k: (round(v, 3) if v is not None else None)
                                  for k, v in dim_scores.items()},
    }


def _cohort_summary(session_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    completion_dates = [d.get("completed_at") for d in session_docs if d.get("completed_at")]
    organisations = sorted({(d.get("participant") or {}).get("organisation")
                            for d in session_docs
                            if (d.get("participant") or {}).get("organisation")})
    roles = sorted({(d.get("participant") or {}).get("role")
                    for d in session_docs
                    if (d.get("participant") or {}).get("role")})
    durations: List[int] = []
    for d in session_docs:
        ca, co = d.get("created_at"), d.get("completed_at")
        if ca and co:
            try:
                from datetime import datetime
                dur = (datetime.fromisoformat(co) - datetime.fromisoformat(ca)).total_seconds()
                if dur > 0:
                    durations.append(int(dur))
            except Exception:
                pass
    return {
        "n":              len(session_docs),
        "completion_date_range": {
            "earliest": min(completion_dates) if completion_dates else None,
            "latest":   max(completion_dates) if completion_dates else None,
        },
        "organisations":  organisations,
        "roles":          roles,
        "avg_session_duration_seconds": (
            int(statistics.fmean(durations)) if durations else None
        ),
    }


def build_cohort(session_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    dim_stats = aggregate_dimensions(session_docs)
    return {
        "axis_order":            COHORT_AXIS_ORDER,
        "participants":          [_participant_summary(d) for d in session_docs],
        "cohort_summary":        _cohort_summary(session_docs),
        "dimension_stats":       dim_stats,
        "heatmap":               compute_heatmap(session_docs),
        "outliers":              find_outliers(session_docs, threshold_z=1.5),
        "cohort_type":           derive_cohort_type(dim_stats),
        **summarise_categories_and_flags(session_docs),
    }
