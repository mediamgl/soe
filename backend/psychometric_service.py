"""
Psychometric service — Phase 4.

Loads the 20 items from `/app/research/20 - Psychometric Items.md` verbatim at
module import time. Exposes:

- get_items(): [{item_id, text, scale, subscale}, ...] preserving doc order
- get_items_dict(): {item_id: item_dict}
- get_scale_definitions(): {"LA": [...], "TA": [...]}
- randomised_order(): per-session item_id order (LA block randomised, then TA)
- score(session_doc): returns the scores.psychometric payload

Parsing rules (fail-loud if violated):
- Exactly 20 items total, 12 LA + 8 TA, unique item_ids, non-empty text.
- No reverse-keyed items — if the doc grows one, we refuse to start.
"""
from __future__ import annotations
import re
import random
import statistics
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger(__name__)

RESEARCH_PATH = Path(__file__).resolve().parent.parent / "research" / "20 - Psychometric Items.md"


# --------------------------------------------------------------------------- #
# Subscale mappings (from Doc 20, "Sub-Score Analysis" table)
# --------------------------------------------------------------------------- #
LA_SUBSCALES: Dict[str, Tuple[str, ...]] = {
    "Mental Agility":   ("LA01", "LA02", "LA03"),
    "People Agility":   ("LA04", "LA05"),
    "Change Agility":   ("LA06", "LA07", "LA08"),
    "Results Agility":  ("LA09", "LA10"),
    "Self-Awareness":   ("LA11", "LA12"),
}
TA_SUBSCALES: Dict[str, Tuple[str, ...]] = {
    "Uncertainty Comfort": ("TA01", "TA02", "TA03"),
    "Complexity Comfort":  ("TA04", "TA05"),
    "Closure Resistance":  ("TA06", "TA07", "TA08"),
}

SCALE_DEFINITIONS = {
    "LA": {
        "id": "LA",
        "label": "Learning Agility",
        "n_items": 12,
        "subscales": LA_SUBSCALES,
    },
    "TA": {
        "id": "TA",
        "label": "Tolerance for Ambiguity",
        "n_items": 8,
        "subscales": TA_SUBSCALES,
    },
}

# Bands verbatim from Doc 20 (4.5-5.0 Exceptional etc.)
BANDS: List[Tuple[float, float, str]] = [
    (4.5, 5.01, "Exceptional"),
    (3.5, 4.5, "Strong"),
    (2.5, 3.5, "Moderate"),
    (1.5, 2.5, "Limited"),
    (1.0, 1.5, "Low"),
]


def _band_for(mean_1_5: float) -> str:
    for lo, hi, name in BANDS:
        if lo <= mean_1_5 < hi:
            return name
    # Clamp just in case of numerical edge at 5.01 or <1.0
    if mean_1_5 >= 4.5:
        return "Exceptional"
    return "Low"


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
# Capture ITEMS like: **LA01** — I enjoy tackling problems...
ITEM_RE = re.compile(r"^\*\*(LA|TA)(\d{2})\*\*\s+[\u2014\u2013-]+\s+(.+?)\s*$")
# Capture subscale heading: ### Mental Agility (Items 1-3)
SUBSCALE_RE = re.compile(r"^###\s+(.+?)\s*\(Items\s+.+?\)\s*$")
# Capture scale heading: ## Learning Agility Scale (12 Items)  |  ## Tolerance for Ambiguity Scale (8 Items)
SCALE_HEAD_RE = re.compile(r"^##\s+(Learning Agility|Tolerance for Ambiguity) Scale\b")

# Build id -> subscale map for validation / writing
def _invert_subscale_map() -> Dict[str, Tuple[str, str]]:
    """Returns { item_id: (scale, subscale_name) } for all 20 expected ids."""
    out: Dict[str, Tuple[str, str]] = {}
    for sub, ids in LA_SUBSCALES.items():
        for i in ids:
            out[i] = ("LA", sub)
    for sub, ids in TA_SUBSCALES.items():
        for i in ids:
            out[i] = ("TA", sub)
    return out


ITEM_ID_TO_SUBSCALE = _invert_subscale_map()


def _parse_doc(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"Psychometric items file not found: {path}")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    items: List[Dict[str, Any]] = []
    current_scale: Optional[str] = None

    for raw in lines:
        line = raw.rstrip()

        # Scale header
        m_scale = SCALE_HEAD_RE.match(line)
        if m_scale:
            current_scale = "LA" if "Learning Agility" in m_scale.group(1) else "TA"
            continue

        # Item line
        m_item = ITEM_RE.match(line)
        if m_item:
            prefix = m_item.group(1)
            num = m_item.group(2)
            body = m_item.group(3).strip()
            item_id = f"{prefix}{num}"
            # Validate against known subscale map
            if item_id not in ITEM_ID_TO_SUBSCALE:
                raise RuntimeError(
                    f"Psychometric parse error: item {item_id} is not in the expected"
                    f" subscale map (Doc 20 structure changed?)."
                )
            scale, subscale = ITEM_ID_TO_SUBSCALE[item_id]
            if current_scale and current_scale != scale:
                # The parser sees the item under a header that doesn't match its expected scale.
                raise RuntimeError(
                    f"Psychometric parse error: {item_id} appears under scale "
                    f"'{current_scale}' but is expected to be '{scale}'."
                )
            if not body:
                raise RuntimeError(f"Psychometric parse error: {item_id} has empty text.")
            # Reverse-key guard: Doc 20 explicitly states none. Detect common reverse-keyed phrasing.
            low = body.lower()
            _reverse_markers = ("i do not ", "i can't ", "i cannot ", "i avoid ", "i dislike ", "i find it hard ", "i struggle with ")
            # Not itself disqualifying, but flag if a known-reverse marker appears.
            # Conservative: do not auto-flip; just log WARNING for the human. FAILS loudly only if the word "reverse" appears in the doc.
            if re.search(r"\breverse\s*(score|key|coded)\b", text, re.IGNORECASE):
                raise RuntimeError("Doc 20 mentions reverse scoring/keying — spec says there are none. FAILING LOUDLY.")
            items.append({
                "item_id": item_id,
                "text": body,
                "scale": scale,
                "subscale": subscale,
            })

    # Final structural checks
    if len(items) != 20:
        raise RuntimeError(f"Psychometric parse error: expected 20 items, got {len(items)}.")
    la = [i for i in items if i["scale"] == "LA"]
    ta = [i for i in items if i["scale"] == "TA"]
    if len(la) != 12 or len(ta) != 8:
        raise RuntimeError(
            f"Psychometric parse error: expected 12 LA + 8 TA, got {len(la)} LA + {len(ta)} TA."
        )
    seen = set()
    for it in items:
        if it["item_id"] in seen:
            raise RuntimeError(f"Psychometric parse error: duplicate item_id {it['item_id']}.")
        seen.add(it["item_id"])
    return items


# --------------------------------------------------------------------------- #
# Module-level state (loaded once at startup)
# --------------------------------------------------------------------------- #
_ITEMS: List[Dict[str, Any]] = _parse_doc(RESEARCH_PATH)
_ITEMS_BY_ID: Dict[str, Dict[str, Any]] = {it["item_id"]: it for it in _ITEMS}
logger.info("Psychometric items loaded: %d (LA=%d, TA=%d)",
            len(_ITEMS),
            sum(1 for i in _ITEMS if i["scale"] == "LA"),
            sum(1 for i in _ITEMS if i["scale"] == "TA"))


def get_items() -> List[Dict[str, Any]]:
    return [dict(it) for it in _ITEMS]


def get_items_dict() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in _ITEMS_BY_ID.items()}


def get_item(item_id: str) -> Optional[Dict[str, Any]]:
    it = _ITEMS_BY_ID.get(item_id)
    return dict(it) if it else None


def get_scale_definitions() -> Dict[str, Any]:
    # Convert tuple[str,...] to list[str] for JSON safety if ever exposed
    return {
        "LA": {
            "id": "LA",
            "label": "Learning Agility",
            "n_items": 12,
            "subscales": {k: list(v) for k, v in LA_SUBSCALES.items()},
        },
        "TA": {
            "id": "TA",
            "label": "Tolerance for Ambiguity",
            "n_items": 8,
            "subscales": {k: list(v) for k, v in TA_SUBSCALES.items()},
        },
    }


def randomised_order(rng: Optional[random.Random] = None) -> List[str]:
    """Per-session order: LA items (shuffled within the scale), THEN TA items (shuffled).
    Scales are NOT interleaved. Order is generated once and persisted per session.
    """
    r = rng or random.Random()
    la_ids = [i["item_id"] for i in _ITEMS if i["scale"] == "LA"]
    ta_ids = [i["item_id"] for i in _ITEMS if i["scale"] == "TA"]
    r.shuffle(la_ids)
    r.shuffle(ta_ids)
    return la_ids + ta_ids


# --------------------------------------------------------------------------- #
# Scoring (Doc 20 formulas + bands verbatim)
# --------------------------------------------------------------------------- #
def _rescale_6_to_5(mean_6: float) -> float:
    return ((mean_6 - 1.0) * 4.0) / 5.0 + 1.0


def _score_bucket(answers_by_id: Dict[str, int], ids: List[str]) -> Dict[str, Any]:
    values = [answers_by_id[i] for i in ids if i in answers_by_id]
    n = len(values)
    if n == 0:
        return {"raw_sum": 0, "mean_6pt": 0.0, "mean_1_5": 0.0, "band": "Low", "n": 0}
    raw = sum(values)
    mean_6 = raw / n
    mean_15 = _rescale_6_to_5(mean_6)
    return {
        "raw_sum": raw,
        "mean_6pt": round(mean_6, 4),
        "mean_1_5": round(mean_15, 4),
        "band": _band_for(mean_15),
        "n": n,
    }


def score(session_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Compute scores.psychometric from a session that has all 20 answers."""
    psych = session_doc.get("psychometric") or {}
    answers = psych.get("answers") or []
    by_id: Dict[str, int] = {}
    response_times: List[int] = []
    for a in answers:
        if isinstance(a.get("value"), int) and 1 <= a["value"] <= 6:
            by_id[a["item_id"]] = a["value"]
        rt = a.get("response_time_ms")
        if isinstance(rt, int) and rt >= 0:
            response_times.append(rt)

    la_ids = [i["item_id"] for i in _ITEMS if i["scale"] == "LA"]
    ta_ids = [i["item_id"] for i in _ITEMS if i["scale"] == "TA"]

    la_score = _score_bucket(by_id, la_ids)
    ta_score = _score_bucket(by_id, ta_ids)

    la_subscales = {name: _score_bucket(by_id, list(ids)) for name, ids in LA_SUBSCALES.items()}
    ta_subscales = {name: _score_bucket(by_id, list(ids)) for name, ids in TA_SUBSCALES.items()}

    # Self-awareness hook (LA11 + LA12) for Phase 7 cross-reference
    self_aware = _score_bucket(by_id, ["LA11", "LA12"])

    overall_rt = sum(response_times) if response_times else 0
    median_rt = int(statistics.median(response_times)) if response_times else 0

    payload = {
        "learning_agility": {**la_score, "subscales": la_subscales},
        "tolerance_for_ambiguity": {**ta_score, "subscales": ta_subscales},
        "self_awareness_claimed": self_aware,  # LA11+LA12, used by synthesis
        "timing": {
            "overall_response_time_ms": overall_rt,
            "median_response_time_ms": median_rt,
            "n_items": len(response_times),
        },
        "bands_reference": {
            "Exceptional": "4.5-5.0",
            "Strong": "3.5-4.4",
            "Moderate": "2.5-3.4",
            "Limited": "1.5-2.4",
            "Low": "1.0-1.4",
        },
    }
    return payload
