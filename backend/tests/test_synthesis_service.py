"""Unit tests for Phase 7 dimensions catalogue + synthesis service."""
from __future__ import annotations
import json
import pytest

from services import dimensions_catalogue as dims
from services import synthesis_service as syn


# --------- Dimensions catalogue invariants ---------
def test_catalogue_has_16_items():
    assert len(dims.CATALOGUE) == 16


def test_catalogue_splits_6_and_10():
    assert len(dims.assessed()) == 6
    assert len(dims.not_assessed()) == 10


def test_catalogue_weight_sums_to_100():
    total = sum(d.weight_percent for d in dims.CATALOGUE)
    assert 99.5 <= total <= 100.5


def test_catalogue_assessed_set_matches_doc19():
    expected = {"learning_agility", "tolerance_for_ambiguity", "cognitive_flexibility",
                "self_awareness_accuracy", "ai_fluency", "systems_thinking"}
    assert {d.id for d in dims.assessed()} == expected


def test_catalogue_by_id_roundtrip():
    for d in dims.CATALOGUE:
        got = dims.by_id(d.id)
        assert got.id == d.id


def test_catalogue_by_id_unknown_raises():
    with pytest.raises(KeyError):
        dims.by_id("not_a_dim")


def test_as_public_dicts_shape():
    pub = dims.as_public_dicts()
    assert set(pub.keys()) == {"assessed", "not_assessed", "total_weight_percent"}
    assert len(pub["assessed"]) == 6
    assert len(pub["not_assessed"]) == 10


# --------- Doc 23 parsing ---------
def test_system_prompt_loaded_verbatim():
    # The Doc 23 system prompt starts with this exact text.
    assert syn.SYSTEM_PROMPT.startswith("You are an expert executive assessor")
    assert "Integration Principles" in syn.SYSTEM_PROMPT
    assert "Triangulation" in syn.SYSTEM_PROMPT


def test_category_thresholds_shape():
    ts = syn.CATEGORY_THRESHOLDS
    assert len(ts) == 4
    labels = [t["category"] for t in ts]
    assert labels == ["Transformation Ready", "High Potential", "Development Required", "Limited Readiness"]
    # Ordered descending by min score
    mins = [t["min"] for t in ts]
    assert mins == sorted(mins, reverse=True)


@pytest.mark.parametrize("score,expected_label,expected_colour", [
    (5.0, "Transformation Ready", "navy"),
    (4.2, "Transformation Ready", "navy"),
    (4.19, "High Potential", "gold"),
    (3.5, "High Potential", "gold"),
    (3.49, "Development Required", "terracotta"),
    (2.8, "Development Required", "terracotta"),
    (2.79, "Limited Readiness", "terracotta"),
    (1.0, "Limited Readiness", "terracotta"),
])
def test_band_for_score(score, expected_label, expected_colour):
    b = syn.band_for_score(score)
    assert b["category"] == expected_label
    assert b["colour"] == expected_colour


# --------- Self-awareness accuracy computation ---------
def _sa_session(claimed=None, cu=None, blind_spots=None):
    scores = {}
    if claimed is not None:
        scores["psychometric"] = {"self_awareness_claimed": {"mean_1_5": claimed}}
    if cu is not None or blind_spots is not None:
        scores["ai_fluency"] = {
            "components": {"capability_understanding": {"score": cu}} if cu is not None else {},
            "blind_spots": blind_spots or [],
        }
    return {"scores": scores}


def test_self_awareness_well_calibrated():
    r = syn.compute_self_awareness_accuracy(_sa_session(claimed=4.0, cu=4, blind_spots=["one", "two"]))
    # observed = 0.5*4 + 0.5*clip(5 - 1, 1, 5) = 2 + 2 = 4.0
    # delta = 0.0 -> Well-calibrated
    assert r["status"] == "computed"
    assert r["observed"] == 4.0
    assert r["delta"] == 0.0
    assert r["band"] == "Well-calibrated"
    assert r["direction"] == "aligned"


def test_self_awareness_slight_over_claiming():
    r = syn.compute_self_awareness_accuracy(_sa_session(claimed=4.4, cu=4, blind_spots=["a", "b"]))
    # observed = 4.0, delta = +0.4 -> well-calibrated (|Δ|<0.5)
    # push to 4.6: delta = 0.6 -> slightly miscalibrated
    r2 = syn.compute_self_awareness_accuracy(_sa_session(claimed=4.6, cu=4, blind_spots=["a", "b"]))
    assert r["band"] == "Well-calibrated"
    assert r2["band"] == "Slightly miscalibrated"
    assert r2["direction"] == "over_claiming"


def test_self_awareness_significant_under_claiming():
    # observed will be high; claimed low
    r = syn.compute_self_awareness_accuracy(_sa_session(claimed=2.5, cu=5, blind_spots=[]))
    # observed = 0.5*5 + 0.5*5 = 5.0; delta = -2.5 -> Significantly miscalibrated, under_claiming
    assert r["band"] == "Significantly miscalibrated"
    assert r["direction"] == "under_claiming"


def test_self_awareness_incomplete_when_missing_inputs():
    r = syn.compute_self_awareness_accuracy(_sa_session(claimed=4.0))  # no ai_fluency
    assert r["status"] == "incomplete"
    r2 = syn.compute_self_awareness_accuracy(_sa_session(cu=4))  # no psychometric
    assert r2["status"] == "incomplete"


def test_self_awareness_many_blind_spots_floors_to_one():
    # 20 blind spots would drive the proxy below 1 without the floor
    r = syn.compute_self_awareness_accuracy(_sa_session(claimed=3.0, cu=3, blind_spots=["b"] * 20))
    # proxy = clip(5 - 10, 1, 5) = 1, observed = 0.5*3 + 0.5*1 = 2.0, delta = 1.0 -> slight
    assert r["observed"] == 2.0
    assert r["band"] == "Slightly miscalibrated"


# --------- Synthesis bundle builder ---------
def test_build_synthesis_input_excludes_email():
    session = {
        "participant": {"name": "Ada Lovelace", "email": "ada@example.co.uk",
                        "organisation": "Analytical Engine Co", "role": "Chief Mathematician"},
        "conversation": [
            {"turn": 0, "role": "assistant", "content": "Hi", "provider": "emergent", "model": "X"},
            {"turn": 1, "role": "user", "content": "Hello"},
        ],
        "scores": {
            "psychometric": {"self_awareness_claimed": {"mean_1_5": 4.0}},
            "ai_fluency": {
                "overall_score": 4.0,
                "components": {"capability_understanding": {"score": 4}},
                "blind_spots": ["x"],
            },
            "scenario": {"cognitive_flexibility": {"score": 4}},
        },
        "scenario": {"part1_response": {"q1": "p1"}, "part2_response": {"q1": "p2"}},
    }
    bundle = syn.build_synthesis_input(session)
    assert bundle["participant"]["first_name"] == "Ada"
    assert "email" not in bundle["participant"]
    # Transcript cleaned — no provider/model internals
    for t in bundle["ai_discussion_transcript"]:
        assert "provider" not in t
        assert "model" not in t
    assert bundle["scenario"]["part1_response"] == {"q1": "p1"}
    assert bundle["self_awareness_calibration"]["status"] == "computed"


# --------- Strict JSON extractor ---------
def test_extract_json_block_strips_fences():
    raw = "Here is the output:\n```json\n{\"a\":1}\n```"
    block = syn._extract_json_block(raw)
    assert block == '{"a":1}'


def test_extract_json_block_handles_nested_braces():
    raw = '{"a":{"b":{"c":1}},"d":2}'
    block = syn._extract_json_block(raw)
    assert json.loads(block)["a"]["b"]["c"] == 1


def test_extract_json_block_returns_none_for_non_json():
    assert syn._extract_json_block("no object here") is None


# --------- Validator ---------
def _valid_payload():
    return {
        "executive_summary": {
            "overall_category": "High Potential",
            "category_statement": "Shows high potential with targeted development",
            "prose": "P",
            "key_strengths": [{"heading": "A", "evidence": "E"}],
            "development_priorities": [{"heading": "B", "evidence": "F"}],
            "bottom_line": "BL",
        },
        "dimension_profiles": [
            {"dimension_id": did, "score": 4.0, "confidence": "high",
             "observed": "o", "transformation_relevance": "t", "evidence_quotes": ["q"]}
            for did in ("learning_agility", "tolerance_for_ambiguity", "cognitive_flexibility",
                        "self_awareness_accuracy", "ai_fluency", "systems_thinking")
        ],
        "integration_analysis": {
            "patterns": "P", "contradictions": None,
            "self_awareness_accuracy_narrative": "S", "emergent_themes": "E",
        },
        "ai_fluency_deep_dive": {
            "overview": "O",
            "components_table": [
                {"component": n, "score": 4, "confidence": "high", "notes": "n"}
                for n in ("Capability Understanding", "Paradigm Awareness",
                          "Orchestration Concepts", "Governance Thinking", "Personal Usage")
            ],
            "what_excellent_looks_like": "W",
            "participant_gap": "G",
            "illustrative_quotes": ["q"],
        },
        "development_recommendations": [
            {"title": "T1", "what": "w", "why": "y", "how": "h", "expectation": "e"},
            {"title": "T2", "what": "w", "why": "y", "how": "h", "expectation": "e"},
        ],
        "methodology_note": "MN",
    }


def test_validator_accepts_valid_payload():
    ok, reason = syn.validate_synthesis_payload(_valid_payload())
    assert ok, reason


def test_validator_rejects_missing_dimension():
    p = _valid_payload()
    p["dimension_profiles"].pop()  # 5 instead of 6
    ok, reason = syn.validate_synthesis_payload(p)
    assert not ok
    assert "dimension_profiles" in reason


def test_validator_rejects_duplicate_dimension():
    p = _valid_payload()
    p["dimension_profiles"][1]["dimension_id"] = p["dimension_profiles"][0]["dimension_id"]
    ok, reason = syn.validate_synthesis_payload(p)
    assert not ok


def test_validator_rejects_unknown_category():
    p = _valid_payload()
    p["executive_summary"]["overall_category"] = "Hurrah!"
    ok, reason = syn.validate_synthesis_payload(p)
    assert not ok
    assert "overall_category" in reason


def test_validator_rejects_out_of_range_score():
    p = _valid_payload()
    p["dimension_profiles"][0]["score"] = 6.0
    ok, reason = syn.validate_synthesis_payload(p)
    assert not ok
    assert "score" in reason


def test_validator_normalises_confidence_case():
    p = _valid_payload()
    p["dimension_profiles"][0]["confidence"] = "HIGH"
    ok, reason = syn.validate_synthesis_payload(p)
    assert ok, reason
    assert p["dimension_profiles"][0]["confidence"] == "high"


def test_validator_rejects_wrong_component_table_length():
    p = _valid_payload()
    p["ai_fluency_deep_dive"]["components_table"].pop()
    ok, reason = syn.validate_synthesis_payload(p)
    assert not ok


# --------- annotate_deliverable attaches bands + colours ---------
def test_annotate_deliverable_attaches_bands():
    p = _valid_payload()
    p["executive_summary"]["overall_category"] = "Transformation Ready"
    p["dimension_profiles"][0]["score"] = 4.5
    p["dimension_profiles"][1]["score"] = 3.7
    p["dimension_profiles"][2]["score"] = 3.0
    ann = syn.annotate_deliverable(p)
    assert ann["executive_summary"]["overall_colour"] == "navy"
    assert ann["dimension_profiles"][0]["band"]["colour"] == "navy"
    assert ann["dimension_profiles"][1]["band"]["colour"] == "gold"
    assert ann["dimension_profiles"][2]["band"]["colour"] == "terracotta"


# --------- run_synthesis via a fake router (no live LLM) ---------
def _split_valid_payload(full):
    """Split a full _valid_payload() into the PART A / PART B halves that
    the two-call synthesis now expects from the LLM."""
    part_a = {
        "executive_summary": full["executive_summary"],
        "integration_analysis": full["integration_analysis"],
        "ai_fluency_deep_dive": {k: v for k, v in full["ai_fluency_deep_dive"].items()
                                  if k != "components_table"},
        "development_recommendations": full["development_recommendations"],
        "methodology_note": full["methodology_note"],
    }
    part_b = {
        "dimension_profiles": full["dimension_profiles"],
        "components_table": full["ai_fluency_deep_dive"]["components_table"],
    }
    return part_a, part_b


@pytest.mark.asyncio
async def test_run_synthesis_happy_path(monkeypatch):
    full = _valid_payload()
    # Exec summary only needs 2 items in each list to satisfy the trimmed schema.
    full["executive_summary"]["key_strengths"] = [
        {"heading": "a", "evidence": "x"}, {"heading": "b", "evidence": "y"},
    ]
    full["executive_summary"]["development_priorities"] = [
        {"heading": "c", "evidence": "z"}, {"heading": "d", "evidence": "w"},
    ]
    part_a, part_b = _split_valid_payload(full)

    call_idx = {"n": 0}

    async def fake_chat(*, messages, tiers, system, max_tokens, purpose):
        call_idx["n"] += 1
        payload = part_a if call_idx["n"] == 1 else part_b
        return {"text": json.dumps(payload), "provider": "test", "model": "fake", "fallbacks_tried": 0}

    monkeypatch.setattr(syn, "router_chat", fake_chat)
    session = {
        "participant": {"name": "Ada Lovelace"},
        "scores": {
            "psychometric": {"self_awareness_claimed": {"mean_1_5": 4.0}},
            "ai_fluency": {"components": {"capability_understanding": {"score": 4}}, "blind_spots": []},
            "scenario": {},
        },
        "conversation": [],
        "scenario": {},
    }
    res = await syn.run_synthesis(session, tiers=[])
    assert res["ok"] is True, res
    assert res["provider"] == "test"
    assert "dimension_profiles" in res["payload"]
    assert len(res["payload"]["dimension_profiles"]) == 6
    assert len(res["payload"]["ai_fluency_deep_dive"]["components_table"]) == 5
    assert call_idx["n"] == 2  # two calls


@pytest.mark.asyncio
async def test_run_synthesis_retries_on_bad_json(monkeypatch):
    full = _valid_payload()
    full["executive_summary"]["key_strengths"] = [
        {"heading": "a", "evidence": "x"}, {"heading": "b", "evidence": "y"},
    ]
    full["executive_summary"]["development_priorities"] = [
        {"heading": "c", "evidence": "z"}, {"heading": "d", "evidence": "w"},
    ]
    part_a, part_b = _split_valid_payload(full)
    call_idx = {"n": 0}

    async def fake_chat(*, messages, tiers, system, max_tokens, purpose):
        call_idx["n"] += 1
        # First Part-A call: garbage. Retry (2nd) returns part_a. Then part_b.
        if call_idx["n"] == 1:
            return {"text": "not json", "provider": "x", "model": "y", "fallbacks_tried": 0}
        payload = part_a if call_idx["n"] == 2 else part_b
        return {"text": json.dumps(payload), "provider": "x", "model": "y", "fallbacks_tried": 0}

    monkeypatch.setattr(syn, "router_chat", fake_chat)
    session = {"participant": {"name": "X"}, "scores": {}, "conversation": [], "scenario": {}}
    res = await syn.run_synthesis(session, tiers=[])
    assert res["ok"] is True
    assert call_idx["n"] == 3  # Part A retry then Part B succeeds


@pytest.mark.asyncio
async def test_run_synthesis_double_fail_returns_graceful(monkeypatch):
    async def fake_chat(**kwargs):
        return {"text": "still not json", "provider": "x", "model": "y", "fallbacks_tried": 0}

    monkeypatch.setattr(syn, "router_chat", fake_chat)
    session = {"participant": {"name": "X"}, "scores": {}, "conversation": [], "scenario": {}}
    res = await syn.run_synthesis(session, tiers=[])
    assert res["ok"] is False
    assert res["scoring_error"] is True
