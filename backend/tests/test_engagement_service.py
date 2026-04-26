"""Phase 11B — engagement_service unit tests."""
from __future__ import annotations
from services import engagement_service as eng


# --------------------------------------------------------------------------- #
# psychometric_engagement
# --------------------------------------------------------------------------- #
def _build_psy_session(rts):
    """Helper: build a session doc with `rts` ms list across 8 LA + 12 TA items."""
    item_ids = (
        ["LA01", "LA02", "LA03", "LA04", "LA05", "LA06", "LA07", "LA08",
         "LA09", "LA10", "LA11", "LA12",
         "TA01", "TA02", "TA03", "TA04", "TA05", "TA06", "TA07", "TA08"]
    )
    answers = []
    for iid, rt in zip(item_ids, rts):
        answers.append({
            "item_id": iid, "value": 4, "response_time_ms": rt,
            "answered_at": "2026-04-26T00:00:00+00:00",
        })
    return {"psychometric": {"order": item_ids, "answers": answers}}


def test_psychometric_engagement_empty_when_no_answers():
    out = eng.psychometric_engagement({"psychometric": {}})
    assert out == {"items": [], "summary": None}
    out2 = eng.psychometric_engagement({})
    assert out2 == {"items": [], "summary": None}


def test_psychometric_engagement_bands_relative_to_median():
    # Median of 20 will be 10000ms. Banding at 5000 / 15000 / 25000 borders.
    rts = [1000, 4000, 4900,                # < 0.5×median -> fast
           5000, 7000, 9000, 10000, 11000, 13000, 14000, 14999,  # normal
           15000, 18000, 20000, 24000, 24999,                 # slow
           25000, 30000, 60000, 90000]                          # deliberated
    s = _build_psy_session(rts)
    out = eng.psychometric_engagement(s)
    assert len(out["items"]) == 20
    # Median should be 14000 (between rts[9]=14000 and rts[10]=14999, average 14499.5
    # actually but Python statistics.median of even length returns mean of two middle).
    # Our sorted list (rts is ALREADY sorted) has middle two = 14000, 14999.
    # median = (14000+14999)/2 = 14499.5
    assert 14000 < out["summary"]["median_ms"] < 14600 or out["summary"]["median_ms"] == 14499
    # Verify p25 / p75 bands
    s_med = out["summary"]["median_ms"]
    bands = {it["item_id"]: it["response_time_band"] for it in out["items"]}
    # First three items had 1000/4000/4900 → ratio < 0.5 -> fast
    assert bands["LA01"] == "fast"
    assert bands["LA02"] == "fast"
    assert bands["LA03"] == "fast"
    # Last item (90000ms) is > 2.5× median (14499.5×2.5=36248) → deliberated
    assert bands["TA08"] == "deliberated"
    # Median range items (around 14499) should be normal
    assert bands["LA10"] == "normal"
    # Verify summary structure
    assert isinstance(out["summary"]["fastest_3"], list) and len(out["summary"]["fastest_3"]) == 3
    assert isinstance(out["summary"]["slowest_3"], list) and len(out["summary"]["slowest_3"]) == 3
    assert out["summary"]["fastest_3"][0] == "LA01"  # 1000ms is fastest
    assert out["summary"]["slowest_3"][0] == "TA08"  # 90000ms is slowest
    # deliberated_count uses p75 + 1.5×IQR threshold — verify it's >= 1 here
    assert out["summary"]["deliberated_count"] >= 1


def test_psychometric_engagement_meta_carried():
    rts = [5000] * 20
    s = _build_psy_session(rts)
    out = eng.psychometric_engagement(s)
    # All items have the meta from psychometric_service: scale, subscale, text
    for it in out["items"]:
        assert it["scale"] in ("LA", "TA")
        assert it["subscale"]
        assert it["text"]
        # All bands == "normal" because every rt == median
        assert it["response_time_band"] == "normal"


# --------------------------------------------------------------------------- #
# ai_discussion_engagement
# --------------------------------------------------------------------------- #
def test_ai_discussion_engagement_empty():
    out = eng.ai_discussion_engagement({"conversation": []})
    assert out == {"turns": [], "user_summary": None, "assistant_summary": None}


def test_ai_discussion_engagement_5_turns():
    # 1 opener (assistant) + 2 user/assistant pairs.
    convo = [
        {"turn": 0, "role": "assistant", "content": "Tell me about AI.",
         "timestamp": "2026-04-26T10:00:00+00:00"},
        {"turn": 1, "role": "user", "content": "I use it daily for many tasks.",
         "timestamp": "2026-04-26T10:00:30+00:00"},  # 30s ttr
        {"turn": 1, "role": "assistant", "content": "Interesting — how so?",
         "timestamp": "2026-04-26T10:00:35+00:00",
         "provider": "anthropic", "model": "claude-opus-4-6",
         "latency_ms": 5000, "fallbacks_tried": 0},
        {"turn": 2, "role": "user",
         "content": "Mainly for board paper drafting and synthesis of long reports across the team.",
         "timestamp": "2026-04-26T10:01:35+00:00"},  # 60s ttr from previous assistant
        {"turn": 2, "role": "assistant", "content": "Got it.",
         "timestamp": "2026-04-26T10:01:42+00:00",
         "provider": "anthropic", "model": "claude-opus-4-6",
         "latency_ms": 7000, "fallbacks_tried": 1},
    ]
    out = eng.ai_discussion_engagement({"conversation": convo})
    assert len(out["turns"]) == 5
    # User-turn time-to-respond derivation
    user_turn_1 = out["turns"][1]
    assert user_turn_1["role"] == "user"
    assert user_turn_1["time_to_respond_ms"] == 30 * 1000
    user_turn_2 = out["turns"][3]
    assert user_turn_2["time_to_respond_ms"] == 60 * 1000
    # Word counts
    assert user_turn_1["content_length_words"] == 7  # "I use it daily for many tasks."
    assert user_turn_2["content_length_words"] == 13  # 13 words
    # Assistant meta carried
    a2 = out["turns"][4]
    assert a2["model_latency_ms"] == 7000
    assert a2["fallbacks_tried"] == 1
    assert a2["provider"] == "anthropic"
    # User summary
    us = out["user_summary"]
    assert us["total_turns"] == 2
    assert us["avg_words_per_turn"] == round((7 + 13) / 2, 1)
    assert us["longest_turn_index"] == 3
    assert us["shortest_turn_index"] == 1
    assert us["avg_time_to_respond_ms"] == int((30000 + 60000) / 2)
    # Assistant summary
    a_s = out["assistant_summary"]
    assert a_s["total_turns"] == 3  # opener + 2 replies
    assert a_s["fallbacks_total"] == 1
    # Opener has no latency_ms; only the 2 replies do. avg = (5000+7000)/2 = 6000
    assert a_s["avg_latency_ms"] == 6000
    assert a_s["max_latency_ms"] == 7000


def test_ai_discussion_engagement_skips_dev_turns():
    convo = [
        {"role": "assistant", "content": "Hi", "timestamp": "2026-04-26T10:00:00+00:00"},
        {"role": "user", "content": "Hello there world",
         "timestamp": "2026-04-26T10:00:05+00:00"},
        {"role": "assistant", "content": "DEV NOTE", "kind": "dev",
         "timestamp": "2026-04-26T10:00:06+00:00"},
    ]
    out = eng.ai_discussion_engagement({"conversation": convo})
    assert len(out["turns"]) == 2  # dev turn excluded


# --------------------------------------------------------------------------- #
# scenario_engagement
# --------------------------------------------------------------------------- #
def test_scenario_engagement_empty():
    out = eng.scenario_engagement({"scenario": {}})
    assert out == {"phases": [], "summary": None}


def test_scenario_engagement_full_with_overrun():
    # Targets: read=4min(240s), part1=5min(300s), curveball=4min(240s), part2=4min(240s)
    # Overall target = 17min = 1020s = 1_020_000 ms
    s = {"scenario": {"time_on_phase_ms": {
        "read":      120 * 1000,    # 2min — under (ratio 0.5)
        "part1":     360 * 1000,    # 6min — over (ratio 1.2)
        "curveball": 240 * 1000,    # 4min — exact (ratio 1.0)
        "part2":     480 * 1000,    # 8min — over (ratio 2.0) - most engaged
    }}}
    out = eng.scenario_engagement(s)
    assert len(out["phases"]) == 4
    by_phase = {p["phase"]: p for p in out["phases"]}
    assert by_phase["read"]["overran"] is False
    assert by_phase["read"]["ratio"] == 0.5
    assert by_phase["part1"]["overran"] is True
    assert by_phase["part1"]["ratio"] == 1.2
    assert by_phase["curveball"]["overran"] is False  # exact = not strictly greater
    assert by_phase["part2"]["overran"] is True
    assert by_phase["part2"]["ratio"] == 2.0
    # Summary
    s_summary = out["summary"]
    assert s_summary["total_actual_ms"] == (120 + 360 + 240 + 480) * 1000
    assert s_summary["total_target_ms"] == 17 * 60 * 1000
    assert s_summary["most_engaged_phase"] == "part2"
    assert s_summary["least_engaged_phase"] == "read"


def test_scenario_engagement_partial_skipped_phases():
    # Only read + part1 entered
    s = {"scenario": {"time_on_phase_ms": {"read": 120000, "part1": 60000}}}
    out = eng.scenario_engagement(s)
    # Still 4 phases (target list is fixed); curveball/part2 actual_ms == 0
    assert len(out["phases"]) == 4
    by = {p["phase"]: p for p in out["phases"]}
    assert by["curveball"]["actual_ms"] == 0
    assert by["part2"]["actual_ms"] == 0
    # most/least engaged ignore phases with actual_ms == 0
    assert out["summary"]["most_engaged_phase"] in ("read", "part1")
    assert out["summary"]["least_engaged_phase"] in ("read", "part1")


# --------------------------------------------------------------------------- #
# build_engagement convenience
# --------------------------------------------------------------------------- #
def test_build_engagement_bundle_keys():
    out = eng.build_engagement({})
    assert set(out.keys()) == {"psychometric", "ai_discussion", "scenario"}
