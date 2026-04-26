"""Phase 11C — cohort_service unit tests."""
from __future__ import annotations
import math
from services import cohort_service as cs


def _mk_session(sid: str, name: str, dim_scores: dict, *,
                category: str | None = "High Potential",
                flag: str | None = None,
                org: str = "Acme",
                role: str = "Director",
                completed_at: str = "2026-04-26T10:00:00+00:00",
                created_at: str = "2026-04-26T09:30:00+00:00") -> dict:
    """Build a minimal completed session doc with the given dim scores
    threaded through deliverable.dimension_profiles so the cohort service
    finds them via the preferred path."""
    profiles = [{"dimension_id": k, "score": v} for k, v in dim_scores.items()]
    return {
        "session_id": sid,
        "participant": {"name": name, "organisation": org, "role": role},
        "status": "completed",
        "stage": "results",
        "created_at": created_at,
        "completed_at": completed_at,
        "scores": {
            "psychometric": {"response_pattern_flag": flag},
            "ai_fluency":    {"overall_score": dim_scores.get("ai_fluency", 0)},
            "scenario":      {
                "cognitive_flexibility": {"score": dim_scores.get("cognitive_flexibility", 0)},
                "systems_thinking":      {"score": dim_scores.get("systems_thinking", 0)},
            },
        },
        "deliverable": {
            "dimension_profiles": profiles,
            "executive_summary":  {"overall_category": category, "overall_colour": "gold"},
        },
    }


def _five_session_cohort():
    return [
        _mk_session("s1", "Ada Lovelace",      {"learning_agility": 4.5, "tolerance_for_ambiguity": 4.0, "cognitive_flexibility": 4.0, "self_awareness_accuracy": 3.5, "ai_fluency": 4.5, "systems_thinking": 4.0}, category="Transformation Ready"),
        _mk_session("s2", "Bertrand Russell",  {"learning_agility": 4.0, "tolerance_for_ambiguity": 3.5, "cognitive_flexibility": 3.0, "self_awareness_accuracy": 3.0, "ai_fluency": 4.0, "systems_thinking": 3.5}, category="High Potential"),
        _mk_session("s3", "Carl Sagan",        {"learning_agility": 3.5, "tolerance_for_ambiguity": 3.0, "cognitive_flexibility": 2.5, "self_awareness_accuracy": 2.5, "ai_fluency": 3.5, "systems_thinking": 3.0}, category="Development Required"),
        _mk_session("s4", "Diana Prince",      {"learning_agility": 3.0, "tolerance_for_ambiguity": 2.5, "cognitive_flexibility": 2.0, "self_awareness_accuracy": 2.0, "ai_fluency": 3.0, "systems_thinking": 2.5}, category="Development Required", flag="high_acquiescence"),
        _mk_session("s5", "Eve Polastri",      {"learning_agility": 1.5, "tolerance_for_ambiguity": 5.0, "cognitive_flexibility": 4.5, "self_awareness_accuracy": 4.5, "ai_fluency": 1.5, "systems_thinking": 4.5}, category="High Potential", flag="low_variance"),
    ]


# --------------------------------------------------------------------------- #
# aggregate_dimensions
# --------------------------------------------------------------------------- #
def test_aggregate_dimensions_basic_stats():
    sessions = _five_session_cohort()
    rows = cs.aggregate_dimensions(sessions)
    assert len(rows) == 6
    by_id = {r["dimension_id"]: r for r in rows}
    # Learning Agility: scores [4.5, 4.0, 3.5, 3.0, 1.5]; mean = 3.3, median = 3.5
    la = by_id["learning_agility"]
    assert la["n"] == 5
    assert math.isclose(la["mean"], 3.3, abs_tol=0.001)
    assert la["median"] == 3.5
    assert la["min"] == 1.5
    assert la["max"] == 4.5
    # AI Fluency same mean as LA
    assert math.isclose(by_id["ai_fluency"]["mean"], 3.3, abs_tol=0.001)
    # Tolerance for Ambiguity scores [4.0, 3.5, 3.0, 2.5, 5.0]; mean = 3.6
    ta = by_id["tolerance_for_ambiguity"]
    assert math.isclose(ta["mean"], 3.6, abs_tol=0.001)
    assert ta["max"] == 5.0


def test_aggregate_dimensions_band_distribution():
    sessions = _five_session_cohort()
    rows = cs.aggregate_dimensions(sessions)
    by_id = {r["dimension_id"]: r for r in rows}
    # LA scores [4.5, 4.0, 3.5, 3.0, 1.5]:
    #   4.5 → Exceptional, 4.0 → Strong, 3.5 → Moderate,
    #   3.0 → Moderate, 1.5 → Low
    bd = by_id["learning_agility"]["band_distribution"]
    assert bd == {"Exceptional": 1, "Strong": 1, "Moderate": 2, "Limited": 0, "Low": 1}


def test_aggregate_dimensions_all_keys_present_with_no_data():
    rows = cs.aggregate_dimensions([])
    assert len(rows) == 6
    for r in rows:
        assert r["n"] == 0
        assert r["mean"] == 0.0
        assert sum(r["band_distribution"].values()) == 0


# --------------------------------------------------------------------------- #
# compute_heatmap
# --------------------------------------------------------------------------- #
def test_compute_heatmap_shape():
    sessions = _five_session_cohort()
    out = cs.compute_heatmap(sessions)
    assert out["axis_order"] == cs.COHORT_AXIS_ORDER
    assert len(out["rows"]) == 5
    for r in out["rows"]:
        assert len(r["scores"]) == 6
    # Label format: 'Ada L.' / 'Bertrand R.' etc.
    assert out["rows"][0]["label"] == "Ada L."
    assert out["rows"][1]["label"] == "Bertrand R."


# --------------------------------------------------------------------------- #
# find_outliers
# --------------------------------------------------------------------------- #
def test_find_outliers_z_threshold():
    # Build a dataset where Eve is an extreme outlier on LA (1.5 vs others 4.5/4/3.5/3)
    sessions = _five_session_cohort()
    out = cs.find_outliers(sessions, threshold_z=1.5)
    by_id = {r["dimension_id"]: r for r in out}
    la = by_id["learning_agility"]
    # LA scores [4.5, 4.0, 3.5, 3.0, 1.5]; mean=3.3, pstdev≈1.020
    # z(1.5) = (1.5 - 3.3) / 1.020 ≈ -1.765 → low outlier
    # z(4.5) = (4.5 - 3.3) / 1.020 ≈ +1.176 → NOT a high outlier (under 1.5)
    assert len(la["low_outliers"]) == 1
    assert la["low_outliers"][0]["session_id"] == "s5"  # Eve
    assert la["low_outliers"][0]["std_devs_below"] >= 1.5
    assert len(la["high_outliers"]) == 0
    # Tolerance for Ambiguity [4.0, 3.5, 3.0, 2.5, 5.0] mean=3.6 pstdev≈0.860
    # z(5.0)=(5.0-3.6)/0.860≈+1.628 → high outlier
    ta = by_id["tolerance_for_ambiguity"]
    assert any(o["session_id"] == "s5" for o in ta["high_outliers"])


def test_find_outliers_stable_when_no_variance():
    # All identical → std_dev=0 → no outliers
    sessions = [_mk_session(f"s{i}", f"Person {i}",
                            {k: 4.0 for k in cs.COHORT_AXIS_ORDER}) for i in range(4)]
    out = cs.find_outliers(sessions)
    for row in out:
        assert row["low_outliers"] == []
        assert row["high_outliers"] == []


# --------------------------------------------------------------------------- #
# derive_cohort_type
# --------------------------------------------------------------------------- #
def test_derive_cohort_type_top3_correct():
    sessions = _five_session_cohort()
    rows = cs.aggregate_dimensions(sessions)
    out = cs.derive_cohort_type(rows)
    # Means: LA 3.3, TA 3.6, CF 3.2, SA 3.1, AI 3.3, ST 3.5
    # Top-3 strengths sorted by mean desc, alphabetical tiebreak:
    #   TA 3.6, ST 3.5, AI 3.3 (LA also 3.3 — alphabetical tiebreak puts AI before LA)
    s_labels = [s["label"] for s in out["top_strengths"]]
    assert s_labels[0] == "Tolerance for Ambiguity"
    assert s_labels[1] == "Systems Thinking"
    assert s_labels[2] == "AI Fluency"  # alphabetical tiebreak with LA at 3.3
    # Top-3 dev areas sorted by mean asc:
    #   SA 3.1, CF 3.2, AI 3.3 (LA also 3.3 — alpha picks AI)
    d_labels = [d["label"] for d in out["top_dev_areas"]]
    assert d_labels[0] == "Self-Awareness Accuracy"
    assert d_labels[1] == "Cognitive Flexibility"
    assert d_labels[2] == "AI Fluency"
    # Sentence templates contain the labels and means
    assert "Tolerance for Ambiguity" in out["strength_summary"]
    assert "3.6" in out["strength_summary"]
    assert "Self-Awareness Accuracy" in out["dev_summary"]


def test_derive_cohort_type_all_equal_alphabetical():
    rows = [
        {"dimension_id": d, "label": cs.COHORT_DIM_LABELS[d], "n": 1, "mean": 3.5}
        for d in cs.COHORT_AXIS_ORDER
    ]
    out = cs.derive_cohort_type(rows)
    # All means tied → alphabetical ordering ascending and descending
    s_labels = [s["label"] for s in out["top_strengths"]]
    d_labels = [d["label"] for d in out["top_dev_areas"]]
    # Descending alphabetical wouldn't apply — strengths is mean desc + alpha.
    # When means tie, alpha ascending kicks in (the secondary sort), so the
    # SAME 3 labels appear in BOTH lists:
    assert s_labels == d_labels
    # And those 3 are alphabetically first.
    assert s_labels == ["AI Fluency", "Cognitive Flexibility", "Learning Agility"]


def test_derive_cohort_type_no_data():
    rows = [
        {"dimension_id": d, "label": cs.COHORT_DIM_LABELS[d], "n": 0, "mean": 0.0}
        for d in cs.COHORT_AXIS_ORDER
    ]
    out = cs.derive_cohort_type(rows)
    assert out["top_strengths"] == []
    assert out["top_dev_areas"] == []
    assert "No dimension data" in out["strength_summary"]


# --------------------------------------------------------------------------- #
# summarise_categories_and_flags
# --------------------------------------------------------------------------- #
def test_summarise_categories_and_flags():
    sessions = _five_session_cohort()
    out = cs.summarise_categories_and_flags(sessions)
    cat = out["category_distribution"]
    assert cat["Transformation Ready"] == 1
    assert cat["High Potential"] == 2
    assert cat["Development Required"] == 2
    assert cat["Limited Readiness"] == 0
    flags = out["flag_summary"]
    assert flags["none"] == 3            # 5 sessions − 2 flagged
    assert flags["high_acquiescence"] == 1
    assert flags["low_variance"] == 1
    assert flags["extreme_response_bias"] == 0
    assert flags["total_flagged"] == 2


# --------------------------------------------------------------------------- #
# build_cohort top-level
# --------------------------------------------------------------------------- #
def test_build_cohort_keys_and_shape():
    sessions = _five_session_cohort()
    out = cs.build_cohort(sessions)
    expected_keys = {
        "axis_order", "participants", "cohort_summary", "dimension_stats",
        "heatmap", "outliers", "cohort_type",
        "category_distribution", "flag_summary",
    }
    assert set(out.keys()) == expected_keys
    assert out["axis_order"] == cs.COHORT_AXIS_ORDER
    assert len(out["participants"]) == 5
    assert out["cohort_summary"]["n"] == 5
    assert "Acme" in out["cohort_summary"]["organisations"]
    assert len(out["dimension_stats"]) == 6
    assert len(out["outliers"]) == 6
    # avg_session_duration: each fixture is 30 mins → 1800s
    assert out["cohort_summary"]["avg_session_duration_seconds"] == 1800


def test_build_cohort_25_sessions_does_not_blow_up():
    """Stress: ensure 25-session aggregation completes and stats stay sane."""
    sessions = []
    # Mix of profiles drifting slightly
    for i in range(25):
        scores = {dim: 3.0 + (i % 5) * 0.4 for dim in cs.COHORT_AXIS_ORDER}
        sessions.append(_mk_session(f"s{i}", f"Person {i:02d} Lastname",
                                    scores, category="High Potential"))
    out = cs.build_cohort(sessions)
    assert out["cohort_summary"]["n"] == 25
    for r in out["dimension_stats"]:
        # Mean should be (3.0+3.4+3.8+4.2+4.6)/5 = 3.8 (each value appears 5 times)
        assert math.isclose(r["mean"], 3.8, abs_tol=0.001)
        assert r["n"] == 25
