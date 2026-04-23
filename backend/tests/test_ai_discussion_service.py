"""Unit tests for the AI Fluency Discussion service — Phase 5 (no network)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import AsyncMock

from services import ai_discussion_service as svc
from services.llm_router import Tier


# ---------- deterministic opener selection ----------
def test_opener_deterministic_by_session_id():
    sid = "abc-123"
    assert svc.select_opener(sid) == svc.select_opener(sid)


def test_opener_is_one_of_three_verbatim():
    # A range of session ids should produce opens drawn only from the 3 doc21 probes
    for i in range(30):
        op = svc.select_opener(f"sess-{i}")
        assert op in svc.OPENING_PROBES


def test_opener_distribution_covers_all_three():
    # With 200 session ids we should hit all three probes at least once
    found = {svc.select_opener(f"s-{i}") for i in range(200)}
    assert found == set(svc.OPENING_PROBES)


# ---------- participant context builder ----------
def test_participant_ctx_basic():
    ctx = svc.build_participant_context(
        {"name": "Jane Doe", "email": "j@x.com", "organisation": "Acme", "role": "CTO"},
        None,
    )
    assert "Jane" in ctx
    assert "Doe" not in ctx  # first name only
    assert "Acme" in ctx
    assert "CTO" in ctx


def test_participant_ctx_with_scores():
    ctx = svc.build_participant_context(
        {"name": "Sam"},
        {
            "learning_agility": {"band": "Strong"},
            "tolerance_for_ambiguity": {"band": "Moderate"},
        },
    )
    assert "Learning Agility Strong" in ctx
    assert "Tolerance for Ambiguity Moderate" in ctx
    # Must NOT contain raw numbers
    assert "3.4" not in ctx
    assert "mean_1_5" not in ctx


def test_participant_ctx_handles_missing_fields():
    ctx = svc.build_participant_context({}, None)
    assert "the participant" in ctx


# ---------- JSON extraction + validation ----------
def test_extract_json_strict():
    s = '{"a": 1, "b": [1,2,3]}'
    assert svc._extract_json_block(s) == s


def test_extract_json_with_fence():
    s = "```json\n{\"x\": 1}\n```"
    assert svc._extract_json_block(s) == '{"x": 1}'


def test_extract_json_with_trailing_prose():
    s = 'Here is your JSON:\n{"x": 1, "y": "ok"}\nThanks!'
    assert svc._extract_json_block(s) == '{"x": 1, "y": "ok"}'


def test_extract_json_nested():
    s = 'pre {"a": {"b": 2}, "c": [{"d": 3}]} post'
    assert svc._extract_json_block(s) == '{"a": {"b": 2}, "c": [{"d": 3}]}'


def _valid_payload():
    return {
        "ai_fluency": {
            "overall_score": 3.6,
            "components": {
                "capability_understanding": {"score": 4, "confidence": "high",   "evidence": ["a", "b"]},
                "paradigm_awareness":        {"score": 3, "confidence": "medium", "evidence": ["c"]},
                "orchestration_concepts":    {"score": 3, "confidence": "medium", "evidence": ["d"]},
                "governance_thinking":       {"score": 4, "confidence": "high",   "evidence": ["e"]},
                "personal_usage":            {"score": 4, "confidence": "high",   "evidence": ["f"]},
            },
            "key_quotes": ["q1", "q2"],
            "blind_spots": ["bs1"],
            "strengths": ["s1"],
        }
    }


def test_validate_passes():
    ok, reason = svc.validate_scoring_payload(_valid_payload())
    assert ok, reason


def test_validate_normalises_confidence_case():
    p = _valid_payload()
    p["ai_fluency"]["components"]["paradigm_awareness"]["confidence"] = "HIGH"
    ok, _ = svc.validate_scoring_payload(p)
    assert ok
    assert p["ai_fluency"]["components"]["paradigm_awareness"]["confidence"] == "high"


def test_validate_rejects_bad_score():
    p = _valid_payload()
    p["ai_fluency"]["components"]["paradigm_awareness"]["score"] = 6
    ok, reason = svc.validate_scoring_payload(p)
    assert not ok
    assert "score" in reason


def test_validate_rejects_bad_confidence():
    p = _valid_payload()
    p["ai_fluency"]["components"]["paradigm_awareness"]["confidence"] = "certain"
    ok, _ = svc.validate_scoring_payload(p)
    assert not ok


def test_validate_rejects_missing_component():
    p = _valid_payload()
    del p["ai_fluency"]["components"]["governance_thinking"]
    ok, _ = svc.validate_scoring_payload(p)
    assert not ok


# ---------- run_scoring with injected fake tier ----------
def _make_tier(text_responses):
    """Make a tier whose .call returns each text in sequence, then reuses the last."""
    queue = list(text_responses)
    async def _call(messages, system, max_tokens, model):
        return queue.pop(0) if len(queue) > 1 else queue[0]
    return Tier(name="fake", provider="fake", model="m", call=_call)


@pytest.mark.asyncio
async def test_run_scoring_happy_path():
    valid_json = '{"ai_fluency":{"overall_score":3.2,"components":{' \
        '"capability_understanding":{"score":3,"confidence":"high","evidence":["x"]},' \
        '"paradigm_awareness":{"score":3,"confidence":"medium","evidence":["y"]},' \
        '"orchestration_concepts":{"score":3,"confidence":"low","evidence":["z"]},' \
        '"governance_thinking":{"score":3,"confidence":"medium","evidence":["q"]},' \
        '"personal_usage":{"score":4,"confidence":"high","evidence":["r"]}' \
        '},"key_quotes":["a"],"blind_spots":["b"],"strengths":["c"]}}'
    tier = _make_tier([valid_json])
    conv = [
        {"role": "assistant", "content": "Opener"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Thanks"},
    ]
    result = await svc.run_scoring(conv, "ctx", tiers=[tier])
    assert result["ok"] is True
    assert result["payload"]["ai_fluency"]["overall_score"] == 3.2


@pytest.mark.asyncio
async def test_run_scoring_retries_once_on_bad_output_then_succeeds():
    bad = "sorry I cannot do that"
    good_json = '{"ai_fluency":{"overall_score":3,"components":{' \
        '"capability_understanding":{"score":3,"confidence":"high","evidence":["x"]},' \
        '"paradigm_awareness":{"score":3,"confidence":"medium","evidence":["y"]},' \
        '"orchestration_concepts":{"score":3,"confidence":"low","evidence":["z"]},' \
        '"governance_thinking":{"score":3,"confidence":"medium","evidence":["q"]},' \
        '"personal_usage":{"score":4,"confidence":"high","evidence":["r"]}' \
        '},"key_quotes":["a"],"blind_spots":["b"],"strengths":["c"]}}'
    tier = _make_tier([bad, good_json])
    conv = [{"role": "user", "content": "Hi"}]
    result = await svc.run_scoring(conv, "ctx", tiers=[tier])
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_run_scoring_fails_gracefully_after_two_bad_outputs():
    tier = _make_tier(["not JSON", "still not JSON"])
    conv = [{"role": "user", "content": "Hi"}]
    result = await svc.run_scoring(conv, "ctx", tiers=[tier])
    assert result["ok"] is False
    assert result["scoring_error"] is True
    assert result["raw"] is not None


# ---------- build_messages_for_turn ----------
def test_build_messages_includes_ctx_and_conversation():
    conv = [
        {"turn": 0, "role": "assistant", "content": "Opener"},
        {"turn": 1, "role": "user", "content": "Hello"},
        {"turn": 1, "role": "assistant", "content": "Hi back"},
    ]
    out = svc.build_messages_for_turn(conv, "Jane; CTO @ Acme; LA Strong", final_turn=False)
    # first two are dev-note + ack
    assert out[0]["role"] == "user" and "Developer note" in out[0]["content"]
    assert out[1]["role"] == "assistant"
    # then the conversation in order
    assert out[2]["content"] == "Opener"
    assert out[3]["content"] == "Hello"
    assert out[4]["content"] == "Hi back"


def test_build_messages_final_turn_appends_note():
    conv = [{"role": "user", "content": "X"}]
    out = svc.build_messages_for_turn(conv, "", final_turn=True)
    assert "final user turn" in out[-1]["content"].lower()
