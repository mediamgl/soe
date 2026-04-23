"""Unit tests for scenario_service — Phase 6 (no network)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import AsyncMock

from services import scenario_service as s
from services.llm_router import Tier


# ---------- content parsing ----------
def test_read_has_title_and_sections():
    read = s.get_read_content()
    assert read["title"] == "Meridian Energy Holdings"
    assert read["duration_target_minutes"] == s.DURATION_READ_MIN
    sections = read["body_sections"]
    # 1 unnamed intro + 5 named
    assert len(sections) == 6
    named = [x["heading"] for x in sections if x["heading"] is not None]
    assert named == [
        "Financial Position", "Workforce", "Market Dynamics",
        "Stakeholder Landscape", "Recent Data Points",
    ]
    # Non-empty content
    for sec in sections:
        assert sec["lines"], f"section {sec['heading']!r} has no lines"


def test_part1_has_exactly_3_questions():
    p1 = s.get_part1()
    assert len(p1["questions"]) == 3
    for q in p1["questions"]:
        assert isinstance(q, str) and len(q) > 10
    assert p1["duration_target_minutes"] == s.DURATION_PART1_MIN
    assert p1["max_answer_chars"] == s.MAX_ANSWER_CHARS


def test_curveball_has_exactly_3_numbered_items():
    cb = s.get_curveball()
    assert len(cb["items"]) == 3
    for i, it in enumerate(cb["items"], start=1):
        assert it["number"] == i
        assert it["heading"].strip()
        assert it["body"].strip()


def test_part2_has_exactly_3_questions():
    p2 = s.get_part2()
    assert len(p2["questions"]) == 3
    for q in p2["questions"]:
        assert isinstance(q, str) and len(q) > 10


def test_get_content_all_bundle_shape():
    bundle = s.get_content_all()
    assert set(bundle.keys()) == {"read", "part1", "curveball", "part2"}


def test_scoring_prompt_has_rubrics_and_schema():
    prompt = s.get_scoring_prompt()
    assert "cognitive_flexibility" in prompt
    assert "systems_thinking" in prompt
    assert "Return ONLY a JSON" in prompt
    assert "additional_observations" in prompt
    assert "high" in prompt and "medium" in prompt and "low" in prompt


# ---------- validator ----------
def _valid_payload():
    return {
        "scenario_analysis": {
            "cognitive_flexibility": {
                "score": 4, "confidence": "high",
                "evidence": {
                    "part1_position": "ok", "part2_revision": "ok",
                    "revision_quality": "ok", "key_quote": "ok",
                },
            },
            "systems_thinking": {
                "score": 3, "confidence": "medium",
                "evidence": {
                    "connections_identified": ["a", "b"],
                    "connections_missed": ["c"],
                    "key_quote": "ok",
                },
            },
            "additional_observations": {
                "stakeholder_awareness": "ok",
                "ethical_reasoning": "ok",
                "analytical_quality": "ok",
            },
        }
    }


def test_validator_passes_well_formed():
    ok, _ = s.validate_scoring_payload(_valid_payload())
    assert ok


def test_validator_normalises_confidence_case():
    p = _valid_payload()
    p["scenario_analysis"]["cognitive_flexibility"]["confidence"] = "HIGH"
    ok, _ = s.validate_scoring_payload(p)
    assert ok
    assert p["scenario_analysis"]["cognitive_flexibility"]["confidence"] == "high"


def test_validator_rejects_bad_score():
    p = _valid_payload()
    p["scenario_analysis"]["cognitive_flexibility"]["score"] = 99
    ok, reason = s.validate_scoring_payload(p)
    assert not ok
    assert "score" in reason


def test_validator_rejects_bad_confidence():
    p = _valid_payload()
    p["scenario_analysis"]["systems_thinking"]["confidence"] = "certain"
    ok, _ = s.validate_scoring_payload(p)
    assert not ok


def test_validator_rejects_missing_evidence_key():
    p = _valid_payload()
    del p["scenario_analysis"]["cognitive_flexibility"]["evidence"]["revision_quality"]
    ok, reason = s.validate_scoring_payload(p)
    assert not ok
    assert "revision_quality" in reason


def test_validator_rejects_connections_identified_not_list():
    p = _valid_payload()
    p["scenario_analysis"]["systems_thinking"]["evidence"]["connections_identified"] = "oops"
    ok, _ = s.validate_scoring_payload(p)
    assert not ok


def test_validator_rejects_missing_additional_observations():
    p = _valid_payload()
    del p["scenario_analysis"]["additional_observations"]
    ok, _ = s.validate_scoring_payload(p)
    assert not ok


def test_extract_json_with_fence_and_prose():
    raw = 'Sure! Here is the JSON.\n```json\n{"scenario_analysis": {"x": 1}}\n```\nThanks!'
    block = s._extract_json_block(raw)
    assert block.startswith('{') and block.endswith('}')


# ---------- run_scoring with injected fake tier ----------
def _make_tier(text_responses):
    queue = list(text_responses)
    async def _call(messages, system, max_tokens, model):
        return queue.pop(0) if len(queue) > 1 else queue[0]
    return Tier(name="fake", provider="fake", model="m", call=_call)


@pytest.mark.asyncio
async def test_run_scoring_happy_path():
    import json as _json
    tier = _make_tier([_json.dumps(_valid_payload())])
    p1 = {"q1": "a", "q2": "b", "q3": "c"}
    p2 = {"q1": "x", "q2": "y", "q3": "z"}
    result = await s.run_scoring(p1, p2, tiers=[tier])
    assert result["ok"] is True
    assert result["payload"]["scenario_analysis"]["cognitive_flexibility"]["score"] == 4


@pytest.mark.asyncio
async def test_run_scoring_retries_on_bad_then_succeeds():
    import json as _json
    bad = "cannot"
    good = _json.dumps(_valid_payload())
    tier = _make_tier([bad, good])
    result = await s.run_scoring({"q1":"a","q2":"b","q3":"c"}, {"q1":"a","q2":"b","q3":"c"}, tiers=[tier])
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_run_scoring_fails_gracefully_after_two_bad():
    tier = _make_tier(["nope", "still nope"])
    result = await s.run_scoring({"q1":"a","q2":"b","q3":"c"}, {"q1":"a","q2":"b","q3":"c"}, tiers=[tier])
    assert result["ok"] is False
    assert result["scoring_error"] is True
