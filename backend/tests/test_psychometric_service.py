"""Unit tests for the psychometric service — parsing + scoring."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psychometric_service as p


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
    # First 12 must all be LA items, last 8 must all be TA items (no interleave)
    assert all(i.startswith("LA") for i in order[:12])
    assert all(i.startswith("TA") for i in order[12:])
    # With seed 42, shuffle should produce a non-trivial permutation (not sorted)
    assert order[:12] != sorted(order[:12])


def test_score_all_sixes():
    """All 6s should produce mean_6=6, mean_1_5=5.0, band 'Exceptional'."""
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


def test_score_all_ones():
    items = p.get_items()
    answers = [{"item_id": i["item_id"], "value": 1, "response_time_ms": 1000} for i in items]
    s = p.score({"psychometric": {"answers": answers}})
    assert s["learning_agility"]["raw_sum"] == 12
    assert s["learning_agility"]["mean_1_5"] == 1.0
    assert s["learning_agility"]["band"] == "Low"
    assert s["tolerance_for_ambiguity"]["band"] == "Low"


def test_score_all_bands():
    """Pick values that land in each of the 5 bands."""
    cases = [
        (6, "Exceptional"),   # mean_6=6 -> mean_1_5=5.0
        (5, "Strong"),        # mean_6=5 -> mean_1_5=4.2
        (4, "Moderate"),      # mean_6=4 -> mean_1_5=3.4 -> Moderate (2.5-3.4 inclusive)
        (2, "Limited"),       # mean_6=2 -> mean_1_5=1.8 -> Limited (1.5-2.4)
        (1, "Low"),           # mean_6=1 -> mean_1_5=1.0 -> Low
    ]
    items = p.get_items()
    for value, expected_band in cases:
        answers = [{"item_id": i["item_id"], "value": value, "response_time_ms": 500} for i in items]
        s = p.score({"psychometric": {"answers": answers}})
        assert s["learning_agility"]["band"] == expected_band, \
            f"value={value} expected band={expected_band}, got {s['learning_agility']['band']}"


def test_score_mixed_subscales():
    """Different values by subscale produces different per-subscale bands."""
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
    assert subs["Mental Agility"]["band"] == "Exceptional"
    assert subs["Change Agility"]["band"] == "Limited"


def test_score_timing():
    items = p.get_items()
    answers = []
    for idx, it in enumerate(items):
        answers.append({"item_id": it["item_id"], "value": 4, "response_time_ms": 1000 + idx * 100})
    s = p.score({"psychometric": {"answers": answers}})
    assert s["timing"]["n_items"] == 20
    assert s["timing"]["overall_response_time_ms"] == sum(1000 + i * 100 for i in range(20))


def test_self_awareness_claimed_uses_la11_la12():
    items = p.get_items()
    answers = []
    for it in items:
        v = 6 if it["item_id"] in ("LA11", "LA12") else 2
        answers.append({"item_id": it["item_id"], "value": v, "response_time_ms": 1000})
    s = p.score({"psychometric": {"answers": answers}})
    # Self-awareness subset should be 6 (both items at 6)
    assert s["self_awareness_claimed"]["mean_6pt"] == 6.0
    assert s["self_awareness_claimed"]["band"] == "Exceptional"


def test_rescale_formula():
    # Doc 20 rescale: (mean_6 - 1) * 4/5 + 1
    # Key waypoints
    assert p._rescale_6_to_5(1.0) == 1.0
    assert p._rescale_6_to_5(6.0) == 5.0
    assert abs(p._rescale_6_to_5(3.5) - 3.0) < 1e-9   # (2.5)*0.8+1 = 3.0
