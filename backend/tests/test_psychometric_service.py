"""Unit tests for the psychometric service — parsing + scoring.

v2 (April 2026): updated to reflect the 6 reverse-keyed items
(LA03, LA07, LA10, LA12, TA02, TA08) and the response-pattern detector.
The OLD v1 expectations (e.g. all-6s → mean=6/Exceptional) are preserved
in test_score_unchanged_when_no_reverse_items as a monkey-patched
regression check on the algorithm itself.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import pytest

import psychometric_service as p


# --------------------------------------------------------------------------- #
# Parsing & catalogue (unchanged from v1)
# --------------------------------------------------------------------------- #
def test_exactly_20_items():
    items = p.get_items()
    assert len(items) == 20
    assert sum(1 for i in items if i["scale"] == "LA") == 12
    assert sum(1 for i in items if i["scale"] == "TA") == 8


def test_item_ids_unique_and_nonempty():
    items = p.get_items()
    ids = [i["item_id"] for i in items]
    assert len(set(ids)) == 20
    for it in items:
        assert it["text"] and it["text"].strip() != ""


def test_subscale_coverage():
    """Every item belongs to exactly one known subscale."""
    items = p.get_items()
    la_subs = set()
    ta_subs = set()
    for it in items:
        if it["scale"] == "LA":
            la_subs.add(it["subscale"])
        else:
            ta_subs.add(it["subscale"])
    assert la_subs == set(p.LA_SUBSCALES.keys())
    assert ta_subs == set(p.TA_SUBSCALES.keys())


def test_randomised_order_la_then_ta():
    import random
    r = random.Random(42)
    order = p.randomised_order(r)
    assert len(order) == 20
    assert all(i.startswith("LA") for i in order[:12])
    assert all(i.startswith("TA") for i in order[12:])
    assert order[:12] != sorted(order[:12])


def test_v2_has_six_reverse_keyed_items_in_expected_subscales():
    """v2 parser assertion: exactly 6 reverse items, one per expected subscale."""
    rev_items = [i for i in p.get_items() if i["is_reverse_keyed"]]
    assert len(rev_items) == 6
    rev_by_subscale = {it["subscale"]: it["item_id"] for it in rev_items}
    assert rev_by_subscale == {
        "Mental Agility": "LA03",
        "Change Agility": "LA07",
        "Results Agility": "LA10",
        "Self-Awareness": "LA12",
        "Uncertainty Comfort": "TA02",
        "Closure Resistance": "TA08",
    }
    # Ensure [REVERSE] token was stripped from displayed text.
    for it in rev_items:
        assert "[REVERSE]" not in it["text"]


# --------------------------------------------------------------------------- #
# Scoring with v2 reverse-keying applied (LIVE Doc 20)
# --------------------------------------------------------------------------- #
def test_score_all_sixes_yields_strong_band_and_acquiescence_flag():
    """All-6s under v2:
       LA: 8 positive @ 6 + 4 reverse @ (7-6=1) = 52/12 = 4.333 -> 3.667 -> Strong
       TA: 6 positive @ 6 + 2 reverse @ 1       = 38/8  = 4.75  -> 4.0   -> Strong
       Pattern: 20/20 are 6 -> high_acquiescence.
    """
    items = p.get_items()
    answers = [{"item_id": i["item_id"], "value": 6, "response_time_ms": 1000} for i in items]
    s = p.score({"psychometric": {"answers": answers}})
    assert s["learning_agility"]["raw_sum"] == 52
    assert s["learning_agility"]["mean_6pt"] == 4.3333
    assert s["learning_agility"]["mean_1_5"] == 3.6667
    assert s["learning_agility"]["band"] == "Strong"
    assert s["tolerance_for_ambiguity"]["raw_sum"] == 38
    assert s["tolerance_for_ambiguity"]["mean_6pt"] == 4.75
    assert s["tolerance_for_ambiguity"]["mean_1_5"] == 4.0
    assert s["tolerance_for_ambiguity"]["band"] == "Strong"
    assert s["response_pattern_flag"] == "high_acquiescence"


def test_score_all_ones_yields_limited_band():
    """All-1s under v2:
       LA: 8 positive @ 1 + 4 reverse @ (7-1=6) = 32/12 = 2.667 -> 2.333 -> Limited
       TA: 6 positive @ 1 + 2 reverse @ 6       = 18/8  = 2.25  -> 2.0   -> Limited
       Pattern: low variance + extreme; high_acquiescence does NOT fire (no 5/6 majority on raw).
    """
    items = p.get_items()
    answers = [{"item_id": i["item_id"], "value": 1, "response_time_ms": 1000} for i in items]
    s = p.score({"psychometric": {"answers": answers}})
    assert s["learning_agility"]["raw_sum"] == 32
    assert s["learning_agility"]["mean_1_5"] == 2.3333
    assert s["learning_agility"]["band"] == "Limited"
    assert s["tolerance_for_ambiguity"]["mean_1_5"] == 2.0
    assert s["tolerance_for_ambiguity"]["band"] == "Limited"
    # All-1s is low_variance (sd=0) and would also qualify for extreme,
    # but low_variance wins (high_acquiescence doesn't apply since no 5/6).
    assert s["response_pattern_flag"] == "low_variance"


def test_score_all_bands_via_split_pattern():
    """v2: with reverse items, no all-same-value pattern can hit Exceptional or
    Low. To exercise each band, set positives at value `p_v` and reverses at
    value `r_v` (untransformed) so that after transform they all end up at the
    same uniform target value `t`. That requires r_v = 7 - t and p_v = t.
    """
    items = p.get_items()

    cases = [
        (6, "Exceptional"),  # uniform t=6 -> mean_1_5=5.0
        (5, "Strong"),       # uniform t=5 -> mean_1_5=4.2
        (4, "Moderate"),     # uniform t=4 -> mean_1_5=3.4
        (2, "Limited"),      # uniform t=2 -> mean_1_5=1.8
        (1, "Low"),          # uniform t=1 -> mean_1_5=1.0
    ]
    for t, expected_band in cases:
        # Positives at t; reverses at 7 - t (so transform brings them to t too).
        answers = []
        for it in items:
            v = (7 - t) if it["is_reverse_keyed"] else t
            answers.append({"item_id": it["item_id"], "value": v, "response_time_ms": 500})
        s = p.score({"psychometric": {"answers": answers}})
        assert s["learning_agility"]["band"] == expected_band, \
            f"target_t={t} expected band={expected_band}, got {s['learning_agility']['band']}"
        assert s["tolerance_for_ambiguity"]["band"] == expected_band, \
            f"target_t={t} expected band={expected_band}, got {s['tolerance_for_ambiguity']['band']}"


def test_score_mixed_subscales_with_reverse_aware_bands():
    """Subscale-level bands under v2:
       Mental Agility @ 6: 2 positive @ 6 + 1 reverse (LA03) @ 6 -> reverse becomes 1
                          mean_6 = (6+6+1)/3 = 4.333 -> 3.667 -> Strong
       Change Agility @ 2: 2 positive @ 2 + 1 reverse (LA07) @ 2 -> reverse becomes 5
                          mean_6 = (2+2+5)/3 = 3.0 -> 2.6 -> Moderate
    """
    items = p.get_items()
    answers = []
    for it in items:
        if it["subscale"] == "Mental Agility":
            answers.append({"item_id": it["item_id"], "value": 6, "response_time_ms": 1000})
        elif it["subscale"] == "Change Agility":
            answers.append({"item_id": it["item_id"], "value": 2, "response_time_ms": 1000})
        else:
            answers.append({"item_id": it["item_id"], "value": 4, "response_time_ms": 1000})
    s = p.score({"psychometric": {"answers": answers}})
    subs = s["learning_agility"]["subscales"]
    assert subs["Mental Agility"]["band"] == "Strong"
    assert subs["Change Agility"]["band"] == "Moderate"


def test_score_timing():
    items = p.get_items()
    answers = []
    for idx, it in enumerate(items):
        answers.append({"item_id": it["item_id"], "value": 4, "response_time_ms": 1000 + idx * 100})
    s = p.score({"psychometric": {"answers": answers}})
    assert s["timing"]["n_items"] == 20
    assert s["timing"]["overall_response_time_ms"] == sum(1000 + i * 100 for i in range(20))


def test_self_awareness_claimed_uses_la11_la12_with_reverse_keying():
    """Under v2, LA12 is reverse-keyed.
       Set LA11 = 6 (positive, raw=transformed=6) and LA12 = 6 (raw=6 -> transformed=1).
       self_awareness_claimed = (6 + 1) / 2 = 3.5 -> 3.0 -> Moderate.
    """
    items = p.get_items()
    answers = []
    for it in items:
        v = 6 if it["item_id"] in ("LA11", "LA12") else 2
        answers.append({"item_id": it["item_id"], "value": v, "response_time_ms": 1000})
    s = p.score({"psychometric": {"answers": answers}})
    assert s["self_awareness_claimed"]["mean_6pt"] == 3.5
    assert s["self_awareness_claimed"]["mean_1_5"] == 3.0
    assert s["self_awareness_claimed"]["band"] == "Moderate"


def test_rescale_formula():
    assert p._rescale_6_to_5(1.0) == 1.0
    assert p._rescale_6_to_5(6.0) == 5.0
    assert abs(p._rescale_6_to_5(3.5) - 3.0) < 1e-9


# =========================================================================== #
# v2 NEW TESTS (9 per Steven's spec)
# =========================================================================== #

# 1. Regression — algorithm produces identical v1 output when no items are
#    reverse-keyed. Monkey-patches _REVERSE_KEYED_IDS to an empty frozenset.
def test_score_unchanged_when_no_reverse_items(monkeypatch):
    monkeypatch.setattr(p, "_REVERSE_KEYED_IDS", frozenset())
    items = p.get_items()
    answers = [{"item_id": i["item_id"], "value": 6, "response_time_ms": 1000} for i in items]
    s = p.score({"psychometric": {"answers": answers}})
    assert s["learning_agility"]["raw_sum"] == 72
    assert s["learning_agility"]["mean_6pt"] == 6.0
    assert s["learning_agility"]["mean_1_5"] == 5.0
    assert s["learning_agility"]["band"] == "Exceptional"
    assert s["tolerance_for_ambiguity"]["raw_sum"] == 48
    assert s["tolerance_for_ambiguity"]["mean_1_5"] == 5.0
    assert s["tolerance_for_ambiguity"]["band"] == "Exceptional"
    # The detector still runs and still flags the all-6s pattern.
    assert s["response_pattern_flag"] == "high_acquiescence"


# 2. Single-item invert: _apply_reverse_keying is the surface for the math.
def test_score_inverts_reverse_keyed_correctly():
    # Reverse-keyed item: 1↔6, 2↔5, 3↔4
    assert p._apply_reverse_keying("LA03", 1) == 6
    assert p._apply_reverse_keying("LA03", 2) == 5
    assert p._apply_reverse_keying("LA03", 3) == 4
    assert p._apply_reverse_keying("LA03", 4) == 3
    assert p._apply_reverse_keying("LA03", 5) == 2
    assert p._apply_reverse_keying("LA03", 6) == 1
    # Non-reverse item: untouched
    for v in range(1, 7):
        assert p._apply_reverse_keying("LA01", v) == v


# 3. Full mixed set: 14 positive @ 5, 6 reverse @ 2 -> after transform all = 5.
#    Hand-computed: every item contributes 5; LA mean=5 -> 1_5=4.2 -> Strong;
#    TA mean=5 -> 1_5=4.2 -> Strong.
def test_score_full_mixed_set_hand_computed():
    items = p.get_items()
    answers = []
    for it in items:
        v = 2 if it["is_reverse_keyed"] else 5
        answers.append({"item_id": it["item_id"], "value": v, "response_time_ms": 800})
    s = p.score({"psychometric": {"answers": answers}})
    assert s["learning_agility"]["raw_sum"] == 60   # 12 items * 5
    assert s["learning_agility"]["mean_6pt"] == 5.0
    assert s["learning_agility"]["mean_1_5"] == 4.2
    assert s["learning_agility"]["band"] == "Strong"
    assert s["tolerance_for_ambiguity"]["raw_sum"] == 40   # 8 items * 5
    assert s["tolerance_for_ambiguity"]["mean_6pt"] == 5.0
    assert s["tolerance_for_ambiguity"]["mean_1_5"] == 4.2
    assert s["tolerance_for_ambiguity"]["band"] == "Strong"
    # Raw is 14× 5 + 6× 2 — high_count = 14 (≥5), not ≥18; sd well >0.5;
    # extreme_count = 0. Flag should be None.
    assert s["response_pattern_flag"] is None


# 4–6. Detector triggers — direct tests on _compute_response_pattern_flag.
def test_response_pattern_flag_high_acquiescence():
    # 18 of 20 are 5 or 6, the other two are 3.
    raw = [6] * 12 + [5] * 6 + [3, 3]
    assert p._compute_response_pattern_flag(raw) == "high_acquiescence"
    # Edge: exactly 17 high -> not flagged.
    raw_edge = [6] * 12 + [5] * 5 + [3] * 3
    assert p._compute_response_pattern_flag(raw_edge) is None


def test_response_pattern_flag_low_variance():
    # All 4s -> sd=0 -> low_variance.
    raw = [4] * 20
    assert p._compute_response_pattern_flag(raw) == "low_variance"
    # Edge: a single 5 in 19 4s -> sd ≈ 0.218 (still <0.5) -> low_variance.
    raw_edge = [4] * 19 + [5]
    assert p._compute_response_pattern_flag(raw_edge) == "low_variance"


def test_response_pattern_flag_extreme_response_bias():
    # 16 of 20 are 1 or 6, mixed enough to NOT trigger high_acquiescence
    # and sd > 0.5 to skip low_variance.
    # Use 8x6 + 8x1 + 4x3 = sd > 0.5, extremes=16, high_count=8 (no high_acq).
    raw = [6] * 8 + [1] * 8 + [3] * 4
    flag = p._compute_response_pattern_flag(raw)
    assert flag == "extreme_response_bias", f"got {flag!r}"


# 7. Null for normal patterns.
def test_response_pattern_flag_null_for_normal():
    # Realistic mixed pattern: spread across 1..6 with reasonable variance.
    raw = [3, 5, 2, 6, 4, 5, 3, 4, 5, 2, 4, 6, 3, 4, 5, 3, 4, 5, 4, 5]
    assert p._compute_response_pattern_flag(raw) is None
    # Partial sets (n<20) always return None.
    assert p._compute_response_pattern_flag([6] * 19) is None
    assert p._compute_response_pattern_flag([]) is None


# 8. Tiebreak order — all 20 = 6 qualifies for high_acquiescence (priority),
#    AND for low_variance (sd=0), AND extreme_response_bias (all 6s).
#    Must return high_acquiescence (most actionable signal first).
def test_response_pattern_tiebreak_order_all_sixes():
    raw = [6] * 20
    assert p._compute_response_pattern_flag(raw) == "high_acquiescence"
    raw_ones = [1] * 20
    # All 1s: high_count=0 (no high_acq), sd=0 -> low_variance wins over
    # extreme_response_bias (next priority after low_variance).
    assert p._compute_response_pattern_flag(raw_ones) == "low_variance"


# 9. Synthesis integration — bundle carries the flag through, schema
#    instruction text contains the conditional caveat sentence, and a
#    stubbed LLM that emits a caveat ends up in the final deliverable.
def test_synthesis_caveat_when_flag_present(monkeypatch):
    from services import synthesis_service as syn

    # Schema instruction should contain the caveat sentence statically.
    assert "psychometric.response_pattern_flag" in syn.OUTPUT_SCHEMA_INSTRUCTIONS_PART_A
    assert "aspirational self-presentation" in syn.OUTPUT_SCHEMA_INSTRUCTIONS_PART_A

    # build_synthesis_input should pass the flag straight through inside
    # scores.psychometric (it's already a passthrough; test the contract).
    session_with_flag = {
        "participant": {"name": "Test", "email": "t@x"},
        "scores": {
            "psychometric": {
                "self_awareness_claimed": {"mean_1_5": 4.0},
                "response_pattern_flag": "high_acquiescence",
            },
            "ai_fluency": {"components": {"capability_understanding": {"score": 4}}, "blind_spots": []},
            "scenario": {},
        },
        "conversation": [],
        "scenario": {},
    }
    bundle = syn.build_synthesis_input(session_with_flag)
    assert (bundle["psychometric"] or {}).get("response_pattern_flag") == "high_acquiescence"

    # End-to-end: stub LLM emits a caveat in exec_summary.prose; assert it
    # survives validation + annotation into the deliverable.
    full = _valid_full_payload_with_caveat()
    part_a, part_b = _split_payload_v2(full)

    call_idx = {"n": 0}

    async def fake_chat(*, messages, tiers, system, max_tokens, purpose):
        call_idx["n"] += 1
        # Defensive: the Part A call MUST carry the caveat instruction in its
        # system prompt. Part B does not (it generates only structured fields).
        if call_idx["n"] == 1:
            assert "aspirational self-presentation" in system
            assert "response_pattern_flag" in system
        payload = part_a if call_idx["n"] == 1 else part_b
        return {"text": json.dumps(payload), "provider": "test", "model": "fake", "fallbacks_tried": 0}

    monkeypatch.setattr(syn, "router_chat", fake_chat)

    import asyncio
    res = asyncio.run(syn.run_synthesis(session_with_flag, tiers=[]))
    assert res["ok"] is True, res
    prose = res["payload"]["executive_summary"]["prose"]
    assert "aspirational" in prose.lower() or "self-presentation" in prose.lower()


# Helpers for test 9
def _valid_full_payload_with_caveat():
    """A minimal-but-valid v2 deliverable where exec_summary.prose contains
    the caveat phrase the LLM is supposed to produce when the flag is set."""
    return {
        "executive_summary": {
            "overall_category": "High Potential",
            "category_statement": "Shows high potential with targeted development.",
            "prose": (
                "The participant presents as engaged and thoughtful across the assessment. "
                "Their self-report leans uniformly positive across nearly every item, "
                "which may reflect aspirational self-presentation more than current state, "
                "so the development priorities below should be read in that light."
            ),
            "key_strengths": [
                {"heading": "Engagement", "evidence": "Sustained participation across 11 turns."},
                {"heading": "Reflection", "evidence": "Articulates rationale clearly."},
            ],
            "development_priorities": [
                {"heading": "Calibration", "evidence": "Self-report uniformly high; verify via 360."},
                {"heading": "Stretch", "evidence": "Seek genuinely novel assignments."},
            ],
            "bottom_line": "High potential, gated by self-calibration.",
        },
        "integration_analysis": {
            "patterns": "The participant's responses are consistent and self-confident across instruments.",
            "contradictions": None,
            "self_awareness_accuracy_narrative": "Claimed self-awareness exceeds observed evidence.",
            "emergent_themes": "Aspirational framing dominates the self-report. Behavioural data more nuanced.",
        },
        "ai_fluency_deep_dive": {
            "overview": "Solid working knowledge.",
            "what_excellent_looks_like": "Anticipating second-order effects.",
            "participant_gap": "Relies on familiar applications.",
            "illustrative_quotes": ["I use it every day."],
            "components_table": [
                {"component": "Capability Understanding", "score": 4, "confidence": "high", "notes": "Clear."},
                {"component": "Paradigm Awareness",      "score": 3, "confidence": "medium", "notes": "Partial."},
                {"component": "Orchestration Concepts", "score": 3, "confidence": "medium", "notes": "Emerging."},
                {"component": "Governance Thinking",    "score": 3, "confidence": "medium", "notes": "Generic."},
                {"component": "Personal Usage",         "score": 4, "confidence": "high", "notes": "Daily."},
            ],
        },
        "dimension_profiles": [
            {"dimension_id": did, "score": 3.7, "confidence": "medium",
             "observed": "Evidence sentence.", "transformation_relevance": "Relevance sentence.",
             "evidence_quotes": ["A quote."]} for did in (
                "learning_agility", "tolerance_for_ambiguity", "cognitive_flexibility",
                "self_awareness_accuracy", "ai_fluency", "systems_thinking",
            )
        ],
        "development_recommendations": [
            {"title": "First", "what": "Do this.", "why": "Because.", "how": "By doing.", "expectation": "Improvement."},
            {"title": "Second", "what": "Do that.", "why": "Because.", "how": "By doing.", "expectation": "Improvement."},
        ],
        "methodology_note": "This profile assesses 6 of 16 dimensions. Synthesis combines instruments.",
    }


def _split_payload_v2(full):
    """Split into Part A / Part B halves matching the synthesis service's two-call structure."""
    part_a = {
        "executive_summary": full["executive_summary"],
        "integration_analysis": full["integration_analysis"],
        "ai_fluency_deep_dive": {k: v for k, v in full["ai_fluency_deep_dive"].items() if k != "components_table"},
        "development_recommendations": full["development_recommendations"],
        "methodology_note": full["methodology_note"],
    }
    part_b = {
        "dimension_profiles": full["dimension_profiles"],
        "components_table": full["ai_fluency_deep_dive"]["components_table"],
    }
    return part_a, part_b
