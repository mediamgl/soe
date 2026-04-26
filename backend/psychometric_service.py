"""
Psychometric service — Phase 4 (v2: reverse-keyed items + response-pattern detector).

Loads the 20 items from `/app/research/20 - Psychometric Items.md` verbatim at
module import time. Exposes:

- get_items(): [{item_id, text, scale, subscale, is_reverse_keyed}, ...] preserving doc order
- get_items_dict(): {item_id: item_dict}
- get_scale_definitions(): {"LA": [...], "TA": [...]}
- randomised_order(): per-session item_id order (LA block randomised, then TA)
- score(session_doc): returns the scores.psychometric payload

Parsing rules (fail-loud if violated):
- Exactly 20 items total, 12 LA + 8 TA, unique item_ids, non-empty text.
- Item ids may have a trailing 'R' marker (e.g. LA03R) for reverse-keyed items.
- Items end with the literal token "[REVERSE]" iff they are reverse-keyed.
- Exactly 6 reverse-keyed items, distributed one per expected subscale
  (Mental Agility, Change Agility, Results Agility, Self-Awareness LA;
   Uncertainty Comfort, Closure Resistance TA). Asserted at startup.
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
# Item ids here use the BASE form (LA01, LA03, LA10, etc). The parser strips
# any trailing 'R' from the source doc before mapping, so LA03R loads as LA03
# with is_reverse_keyed=True. This keeps the rest of the system (Mongo
# psychometric.order, frontend, scoring buckets) using stable canonical ids
# regardless of whether the live instrument is v1 or v2.
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

# Subscales that MUST contain exactly one reverse-keyed item in v2.
EXPECTED_REVERSE_SUBSCALES: Dict[str, str] = {
    "Mental Agility": "LA03",
    "Change Agility": "LA07",
    "Results Agility": "LA10",
    "Self-Awareness": "LA12",
    "Uncertainty Comfort": "TA02",
    "Closure Resistance": "TA08",
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
# Capture ITEMS like:
#   **LA01** — I enjoy tackling problems...
#   **LA03R** — When I'm weighing two strong ... [REVERSE]
# The optional trailing 'R' marks the item visually in the doc; the [REVERSE]
# token at the end is the canonical machine-readable flag we parse.
ITEM_RE = re.compile(r"^\*\*(LA|TA)(\d{2})(R?)\*\*\s+[\u2014\u2013-]+\s+(.+?)\s*$")
# Capture subscale heading: ### Mental Agility (Items 1-3)
SUBSCALE_RE = re.compile(r"^###\s+(.+?)\s*\(Items\s+.+?\)\s*$")
# Capture scale heading: ## Learning Agility Scale (12 Items)  |  ## Tolerance for Ambiguity Scale (8 Items)
SCALE_HEAD_RE = re.compile(r"^##\s+(Learning Agility|Tolerance for Ambiguity) Scale\b")
# Reverse-keyed token: must appear at the end of the item line.
REVERSE_TOKEN_RE = re.compile(r"\s*\[REVERSE\]\s*$")

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

        # Item line — only inside a scale section
        m_item = ITEM_RE.match(line)
        if m_item:
            prefix = m_item.group(1)
            num = m_item.group(2)
            r_suffix = m_item.group(3)  # 'R' or ''
            body = m_item.group(4).strip()
            item_id = f"{prefix}{num}"  # canonical (no R suffix in stored id)

            # Reverse-keyed detection — must end with the literal [REVERSE] token.
            # The 'R' suffix on the item id is a doc-level visual cue; the token
            # is the source of truth. We accept either as long as both agree.
            is_reverse = bool(REVERSE_TOKEN_RE.search(body))
            if is_reverse and not r_suffix:
                raise RuntimeError(
                    f"Psychometric parse error: item {item_id} has [REVERSE] token "
                    f"but its id is not marked with trailing R. Fix Doc 20 so the "
                    f"id reads {item_id}R for consistency."
                )
            if r_suffix and not is_reverse:
                raise RuntimeError(
                    f"Psychometric parse error: item id {item_id}R is marked R "
                    f"but the line is missing the trailing [REVERSE] token."
                )
            # Strip the token from the displayed text.
            body = REVERSE_TOKEN_RE.sub("", body).strip()

            # Validate against known subscale map
            if item_id not in ITEM_ID_TO_SUBSCALE:
                raise RuntimeError(
                    f"Psychometric parse error: item {item_id} is not in the expected"
                    f" subscale map (Doc 20 structure changed?)."
                )
            scale, subscale = ITEM_ID_TO_SUBSCALE[item_id]
            if current_scale and current_scale != scale:
                raise RuntimeError(
                    f"Psychometric parse error: {item_id} appears under scale "
                    f"'{current_scale}' but is expected to be '{scale}'."
                )
            if not body:
                raise RuntimeError(f"Psychometric parse error: {item_id} has empty text.")
            items.append({
                "item_id": item_id,
                "text": body,
                "scale": scale,
                "subscale": subscale,
                "is_reverse_keyed": is_reverse,
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

    # Reverse-keyed structural assertion (v2 instrument):
    # exactly 6 reverse items, one per expected subscale at the expected id.
    rev = {it["item_id"]: it for it in items if it["is_reverse_keyed"]}
    if len(rev) != 6:
        raise RuntimeError(
            f"Psychometric parse error: v2 expects exactly 6 reverse-keyed items, "
            f"got {len(rev)} ({sorted(rev.keys())}). Doc 20 / EXPECTED_REVERSE_SUBSCALES drift?"
        )
    for sub_name, expected_id in EXPECTED_REVERSE_SUBSCALES.items():
        if expected_id not in rev:
            raise RuntimeError(
                f"Psychometric parse error: v2 expects {expected_id} reverse-keyed "
                f"in subscale {sub_name!r}, but it is missing or not marked [REVERSE]."
            )
        if rev[expected_id]["subscale"] != sub_name:
            raise RuntimeError(
                f"Psychometric parse error: {expected_id} is marked reverse but "
                f"belongs to subscale {rev[expected_id]['subscale']!r}, not "
                f"{sub_name!r}. Doc 20 ↔ subscale-map drift?"
            )
    return items


# --------------------------------------------------------------------------- #
# Module-level state (loaded once at startup)
# --------------------------------------------------------------------------- #
_ITEMS: List[Dict[str, Any]] = _parse_doc(RESEARCH_PATH)
_ITEMS_BY_ID: Dict[str, Dict[str, Any]] = {it["item_id"]: it for it in _ITEMS}
_REVERSE_KEYED_IDS: frozenset = frozenset(
    it["item_id"] for it in _ITEMS if it["is_reverse_keyed"]
)
logger.info(
    "Psychometric items loaded: %d (LA=%d, TA=%d, reverse-keyed=%d: %s)",
    len(_ITEMS),
    sum(1 for i in _ITEMS if i["scale"] == "LA"),
    sum(1 for i in _ITEMS if i["scale"] == "TA"),
    len(_REVERSE_KEYED_IDS),
    sorted(_REVERSE_KEYED_IDS),
)


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
# Reverse-key transform + response-pattern detector
# --------------------------------------------------------------------------- #
def _apply_reverse_keying(item_id: str, raw_value: int) -> int:
    """Return the value used for scale aggregation. Reverse-keyed items map
    `v -> 7 - v` so 1↔6, 2↔5, 3↔4. Raw values are preserved upstream
    (caller passes raw and we transform here)."""
    if item_id in _REVERSE_KEYED_IDS:
        return 7 - raw_value
    return raw_value


def _compute_response_pattern_flag(raw_values: List[int]) -> Optional[str]:
    """Detect acquiescence / straight-lining / extreme-response patterns on
    RAW responses (NOT the reverse-keyed-transformed values).

    Trigger conditions (operating on a 20-item set):
      - "high_acquiescence":      >=18 of 20 responses are 5 or 6
      - "low_variance":           pstdev(raw_values) < 0.5
      - "extreme_response_bias":  >=16 of 20 are 1 or 6

    Tie-break order: high_acquiescence > low_variance > extreme_response_bias.
    Returns None when responses look normal or when fewer than 20 values are
    available (we don't fire on partial sets).
    """
    n = len(raw_values)
    if n < 20:
        return None
    high_count = sum(1 for v in raw_values if v >= 5)
    if high_count >= 18:
        return "high_acquiescence"
    sd = statistics.pstdev(raw_values)
    if sd < 0.5:
        return "low_variance"
    extreme_count = sum(1 for v in raw_values if v in (1, 6))
    if extreme_count >= 16:
        return "extreme_response_bias"
    return None


# --------------------------------------------------------------------------- #
# Scoring (Doc 20 formulas + bands verbatim)
# --------------------------------------------------------------------------- #
def _rescale_6_to_5(mean_6: float) -> float:
    return ((mean_6 - 1.0) * 4.0) / 5.0 + 1.0


def _score_bucket(transformed_by_id: Dict[str, int], ids: List[str]) -> Dict[str, Any]:
    """Aggregate over already-transformed values. Caller is responsible for
    applying _apply_reverse_keying before passing the dict in."""
    values = [transformed_by_id[i] for i in ids if i in transformed_by_id]
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
    """Compute scores.psychometric from a session that has all 20 answers.

    Two-pass design:
      Pass 1 — collect raw values exactly as the participant clicked them.
               Used for the response-pattern detector.
      Pass 2 — apply reverse-keying inversion, then aggregate into scale
               and subscale buckets.

    The session document's `psychometric.answers` array is NEVER mutated; the
    transform happens in memory only. This means a Doc 20 edit (e.g. a new
    reverse-keyed item) can be applied retroactively to old sessions by
    re-running this function — see migrations/rescore_v2.py.
    """
    psych = session_doc.get("psychometric") or {}
    answers = psych.get("answers") or []

    raw_by_id: Dict[str, int] = {}
    response_times: List[int] = []
    for a in answers:
        if isinstance(a.get("value"), int) and 1 <= a["value"] <= 6:
            raw_by_id[a["item_id"]] = a["value"]
        rt = a.get("response_time_ms")
        if isinstance(rt, int) and rt >= 0:
            response_times.append(rt)

    # Pass 2 — transform via reverse-keying
    transformed_by_id: Dict[str, int] = {
        item_id: _apply_reverse_keying(item_id, val)
        for item_id, val in raw_by_id.items()
    }

    la_ids = [i["item_id"] for i in _ITEMS if i["scale"] == "LA"]
    ta_ids = [i["item_id"] for i in _ITEMS if i["scale"] == "TA"]

    la_score = _score_bucket(transformed_by_id, la_ids)
    ta_score = _score_bucket(transformed_by_id, ta_ids)

    la_subscales = {name: _score_bucket(transformed_by_id, list(ids)) for name, ids in LA_SUBSCALES.items()}
    ta_subscales = {name: _score_bucket(transformed_by_id, list(ids)) for name, ids in TA_SUBSCALES.items()}

    # Self-awareness hook (LA11 + LA12) for Phase 7 cross-reference.
    # Note: LA12 is reverse-keyed in v2, so this bucket scores the transformed
    # value (1↔6) for LA12, which is the correct construct interpretation —
    # endorsing LA12R ("articulate why feedback doesn't fit") indicates LOW
    # self-awareness, contributing LESS to the claimed-self-awareness mean.
    self_aware = _score_bucket(transformed_by_id, ["LA11", "LA12"])

    overall_rt = sum(response_times) if response_times else 0
    median_rt = int(statistics.median(response_times)) if response_times else 0

    # Response-pattern flag — computed on RAW values (un-inverted).
    # We deliberately use the raw stream because the detector is looking for
    # signs of yea-saying / straight-lining / extreme-response bias, which
    # express themselves in the raw clickstream. With reverse-keyed items in
    # the mix, an honest responder naturally produces variance because the
    # reverse items invert direction; a yea-sayer's raw stream stays high.
    response_pattern_flag = _compute_response_pattern_flag(list(raw_by_id.values()))

    payload = {
        "learning_agility": {**la_score, "subscales": la_subscales},
        "tolerance_for_ambiguity": {**ta_score, "subscales": ta_subscales},
        "self_awareness_claimed": self_aware,  # LA11+LA12, used by synthesis
        "response_pattern_flag": response_pattern_flag,
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
