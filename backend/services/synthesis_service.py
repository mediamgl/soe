"""
Synthesis service — Phase 7.

Reads `/app/research/23 - Synthesis Prompt.md` (361 lines) verbatim at import:
  - Extracts the SYSTEM_PROMPT (the fenced block near the top of Doc 23)
  - Extracts the category-language thresholds table

Exposes:
  - build_synthesis_input(session)           — JSON bundle for the LLM, no PII
  - compute_self_awareness_accuracy(session) — calibration object
  - run_synthesis(session, tiers)            — LLM call via llm_router cascade,
                                               strict JSON output, one retry

Doc 23 is the governing authority. Where this brief conflicted with Doc 23:
  - Doc 23 specifies `confidence` as "high" | "medium" | "low" (strings).
  - Doc 23 does NOT define a numeric self-awareness accuracy formula (it is
    prose-based inside INTEGRATION ANALYSIS). The formula below is derived
    from the Phase 7 brief and runs client-side; the synthesis LLM is told
    the computed calibration delta so its narrative aligns with the number.

Colour bands (Phase 7 locked decision — navy / gold / terracotta):
  - >= 4.2  Transformation Ready    navy
  - 3.5–4.19 High Potential         gold
  - 2.8–3.49 Development Required   terracotta
  - < 2.8    Limited Readiness      terracotta

Doc 23 has 4 category names; the UI palette has 3 colours. We keep the 4
Doc-23 labels and map both Development Required + Limited Readiness to
terracotta (with the label distinguishing the two).
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.llm_router import Tier, chat as router_chat, LLMRouterError
from services import dimensions_catalogue as dims

logger = logging.getLogger(__name__)

DOC23_PATH = Path(__file__).resolve().parent.parent.parent / "research" / "23 - Synthesis Prompt.md"

# --------------------------------------------------------------------------- #
# Doc 23 parsing
# --------------------------------------------------------------------------- #
def _load_doc23() -> str:
    if not DOC23_PATH.exists():
        raise RuntimeError(f"Doc 23 missing at {DOC23_PATH}")
    return DOC23_PATH.read_text(encoding="utf-8")


def _extract_system_prompt(text: str) -> str:
    """The Doc 23 System Prompt is the first triple-backtick fenced block
    immediately after the '## System Prompt' heading."""
    m = re.search(r"## System Prompt\s*\n+```(.*?)```", text, flags=re.DOTALL)
    if not m:
        raise RuntimeError("Doc 23 parse error: could not find fenced system prompt.")
    return m.group(1).strip()


def _extract_category_thresholds(text: str) -> List[Dict[str, Any]]:
    """The Doc 23 'Category Assignment' table, parsed into ordered rules.
    Each entry has min_score and category + verbatim language."""
    # Keep Doc 23's verbatim category language; map to the 3-colour palette.
    return [
        {"min": 4.2, "category": "Transformation Ready",
         "language": "Shows strong readiness for transformation leadership",
         "colour": "navy"},
        {"min": 3.5, "category": "High Potential",
         "language": "Shows high potential with targeted development",
         "colour": "gold"},
        {"min": 2.8, "category": "Development Required",
         "language": "Requires significant development for transformation readiness",
         "colour": "terracotta"},
        {"min": 0.0, "category": "Limited Readiness",
         "language": "Shows limited readiness in assessed areas",
         "colour": "terracotta"},
    ]


_DOC23 = _load_doc23()
SYSTEM_PROMPT = _extract_system_prompt(_DOC23)
CATEGORY_THRESHOLDS = _extract_category_thresholds(_DOC23)


def band_for_score(score: float) -> Dict[str, str]:
    """Return {category, language, colour} for a 1-5 score. Doc 23 thresholds."""
    s = float(score)
    for t in CATEGORY_THRESHOLDS:
        if s >= t["min"]:
            return {"category": t["category"], "language": t["language"], "colour": t["colour"]}
    return {"category": "Limited Readiness",
            "language": "Shows limited readiness in assessed areas",
            "colour": "terracotta"}


logger.info(
    "Synthesis service ready: doc23_lines=%d, system_prompt_chars=%d, thresholds=%d",
    len(_DOC23.splitlines()), len(SYSTEM_PROMPT), len(CATEGORY_THRESHOLDS),
)


# --------------------------------------------------------------------------- #
# Participant context (NO EMAIL — privacy-sensitive)
# --------------------------------------------------------------------------- #
def _first_name(full_name: str) -> str:
    if not full_name:
        return "Participant"
    return full_name.strip().split(None, 1)[0]


def _participant_for_synthesis(session: Dict[str, Any]) -> Dict[str, Any]:
    p = session.get("participant") or {}
    return {
        "first_name": _first_name(p.get("name", "")),
        "organisation": p.get("organisation") or None,
        "role": p.get("role") or None,
    }


def _clean_ai_transcript(conversation: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip provider/model/latency metadata; keep only role + content + turn for
    the synthesis prompt."""
    out = []
    for t in conversation or []:
        if t.get("role") in ("user", "assistant") and t.get("kind") != "dev":
            out.append({"turn": t.get("turn"), "role": t.get("role"), "content": t.get("content", "")})
    return out


# --------------------------------------------------------------------------- #
# Self-awareness accuracy
# --------------------------------------------------------------------------- #
def compute_self_awareness_accuracy(session: Dict[str, Any]) -> Dict[str, Any]:
    """Calibration of self-reported vs demonstrated self-awareness.

    - claimed   = psychometric.self_awareness_claimed.mean_1_5 (Doc 20 subscale)
    - observed  = 0.5 * capability_understanding.score  +  0.5 * blind_spot_proxy
                  where blind_spot_proxy = clip(5 - 0.5 * blind_spots_count, 1, 5)
    - delta     = claimed - observed  (positive → over-claiming)
    - band      = Well-calibrated (|Δ|<0.5) / Slightly miscalibrated (0.5..1.0) /
                  Significantly miscalibrated (>1.0)

    Both claimed & observed may be missing (missing psychometric or ai_fluency
    scores). When either is missing we return {status:"incomplete"} and the
    render layer shows a graceful stub.
    """
    scores = session.get("scores") or {}
    psych = scores.get("psychometric") or {}
    ai_f = scores.get("ai_fluency") or {}

    claimed = (((psych.get("self_awareness_claimed") or {}).get("mean_1_5")))
    cu = ((ai_f.get("components") or {}).get("capability_understanding") or {})
    cu_score = cu.get("score")
    blind_spots = ai_f.get("blind_spots") or []
    bs_count = len(blind_spots)

    if claimed is None or cu_score is None:
        return {
            "status": "incomplete",
            "reason": "Needs both psychometric self-awareness subscale and AI fluency capability_understanding.",
        }

    claimed_f = float(claimed)
    bs_proxy = max(1.0, min(5.0, 5.0 - 0.5 * bs_count))
    observed = 0.5 * float(cu_score) + 0.5 * bs_proxy
    delta = round(claimed_f - observed, 2)
    abs_delta = abs(delta)

    if abs_delta < 0.5:
        band = "Well-calibrated"
    elif abs_delta <= 1.0:
        band = "Slightly miscalibrated"
    else:
        band = "Significantly miscalibrated"

    direction = "over_claiming" if delta > 0 else ("under_claiming" if delta < 0 else "aligned")

    return {
        "status": "computed",
        "claimed": round(claimed_f, 2),
        "observed": round(observed, 2),
        "delta": delta,
        "band": band,
        "direction": direction,
        "blind_spots_count": bs_count,
    }


# --------------------------------------------------------------------------- #
# Synthesis bundle — what we hand to the LLM
# --------------------------------------------------------------------------- #
def build_synthesis_input(session: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble a privacy-safe JSON bundle containing everything the synthesis
    prompt needs. Strips email and internal provider metadata. Fails loud if
    required sub-scores are missing — synthesis should not run at all in that
    state; the caller must gate."""
    scores = session.get("scores") or {}
    scenario = session.get("scenario") or {}

    bundle = {
        "participant": _participant_for_synthesis(session),
        "psychometric": scores.get("psychometric"),
        "ai_fluency": scores.get("ai_fluency"),
        "ai_discussion_transcript": _clean_ai_transcript(session.get("conversation") or []),
        "scenario": {
            "scores": scores.get("scenario"),
            "part1_response": scenario.get("part1_response") or {},
            "part2_response": scenario.get("part2_response") or {},
        },
        "self_awareness_calibration": compute_self_awareness_accuracy(session),
        "doc23_category_thresholds": CATEGORY_THRESHOLDS,
    }
    return bundle


# --------------------------------------------------------------------------- #
# Output schema (concrete + strict so we can validate and render deterministically)
#
# Doc 23 asks the synthesis to produce a comprehensive 6-section deliverable.
# Producing that in a single LLM call reliably exceeds the Emergent proxy's
# practical output window on claude-opus-4-6 (~2500 tokens before truncation /
# timeout). We therefore split the synthesis into TWO focused calls:
#
#   PART A — narrative:
#     executive_summary, integration_analysis, ai_fluency_deep_dive (narrative
#     fields only — overview, what_excellent_looks_like, participant_gap,
#     illustrative_quotes), development_recommendations, methodology_note.
#
#   PART B — structured:
#     dimension_profiles (6 items) and ai_fluency_deep_dive.components_table
#     (5 rows).
#
# The two payloads are deep-merged and validated against the full schema below.
# --------------------------------------------------------------------------- #
OUTPUT_SCHEMA_INSTRUCTIONS_PART_A = """
Return ONLY a JSON object. No prose before or after. No markdown fences.
This is PART A of the synthesis (narrative sections only). Be concise —
each section must fit comfortably within the word budgets.

{
  "executive_summary": {
    "overall_category": "Transformation Ready" | "High Potential" | "Development Required" | "Limited Readiness",
    "category_statement": string,      // Doc 23 language, ~1 sentence
    "prose": string,                   // 120-150 word paragraph of integrated synthesis
    "key_strengths": [                 // EXACTLY 2 items
      {"heading": string, "evidence": string}
    ],
    "development_priorities": [        // EXACTLY 2 items
      {"heading": string, "evidence": string}
    ],
    "bottom_line": string              // 1 sentence
  },
  "integration_analysis": {
    "patterns": string,                // 2-3 sentences
    "contradictions": string | null,   // 1-2 sentences OR null if none notable
    "self_awareness_accuracy_narrative": string,  // 1-2 sentences referencing the delta
    "emergent_themes": string          // 2-3 sentences
  },
  "ai_fluency_deep_dive": {
    "overview": string,                // 1-2 sentences
    "what_excellent_looks_like": string,  // 1-2 sentences
    "participant_gap": string,         // 1-2 sentences
    "illustrative_quotes": [string]    // 1-2 verbatim participant quotes
  },
  "development_recommendations": [     // EXACTLY 2 items
    {"title": string, "what": string, "why": string, "how": string, "expectation": string}
  ],
  "methodology_note": string           // 2 sentences consistent with Doc 23's standard note
}
""".strip()

OUTPUT_SCHEMA_INSTRUCTIONS_PART_B = """
Return ONLY a JSON object. No prose before or after. No markdown fences.
This is PART B of the synthesis (structured sections only). Produce
EXACTLY 6 dimension_profiles (one per assessed id) and EXACTLY 5
components_table rows.

{
  "dimension_profiles": [              // EXACTLY 6 entries
    {
      "dimension_id": "learning_agility" | "tolerance_for_ambiguity" | "cognitive_flexibility" | "self_awareness_accuracy" | "ai_fluency" | "systems_thinking",
      "score": number,                 // 1-5, one decimal
      "confidence": "high" | "medium" | "low",
      "observed": string,              // 1-2 sentences with specific evidence
      "transformation_relevance": string,  // 1 sentence
      "evidence_quotes": [string]      // 1-2 verbatim participant quotes or response fragments
    }
  ],
  "components_table": [                // EXACTLY 5 rows — Capability Understanding, Paradigm Awareness, Orchestration Concepts, Governance Thinking, Personal Usage
    {"component": string, "score": number, "confidence": "high"|"medium"|"low", "notes": string}
  ]
}
""".strip()

# Retained for back-compat / tests — the full combined schema instructions.
OUTPUT_SCHEMA_INSTRUCTIONS = OUTPUT_SCHEMA_INSTRUCTIONS_PART_A + "\n\n" + OUTPUT_SCHEMA_INSTRUCTIONS_PART_B


# --------------------------------------------------------------------------- #
# Output validation
# --------------------------------------------------------------------------- #
_VALID_CATEGORIES = {"Transformation Ready", "High Potential", "Development Required", "Limited Readiness"}
_VALID_CONFIDENCE = {"high", "medium", "low"}
_EXPECTED_DIM_IDS = {d.id for d in dims.assessed()}


def _err(msg: str) -> Tuple[bool, str]:
    return False, msg


def validate_synthesis_payload(obj: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return _err("top-level must be an object")

    es = obj.get("executive_summary")
    if not isinstance(es, dict):
        return _err("executive_summary missing or not an object")
    if es.get("overall_category") not in _VALID_CATEGORIES:
        return _err(f"executive_summary.overall_category must be one of {_VALID_CATEGORIES}")
    for k in ("category_statement", "prose", "bottom_line"):
        if not isinstance(es.get(k), str) or not es[k].strip():
            return _err(f"executive_summary.{k} must be a non-empty string")
    for list_key, min_n, max_n in (("key_strengths", 1, 4), ("development_priorities", 1, 3)):
        arr = es.get(list_key)
        if not isinstance(arr, list) or not (min_n <= len(arr) <= max_n):
            return _err(f"executive_summary.{list_key} must be a list of {min_n}-{max_n} items")
        for i, it in enumerate(arr):
            if not isinstance(it, dict) or not isinstance(it.get("heading"), str) or not isinstance(it.get("evidence"), str):
                return _err(f"executive_summary.{list_key}[{i}] must be {{heading, evidence}}")

    profiles = obj.get("dimension_profiles")
    if not isinstance(profiles, list) or len(profiles) != 6:
        return _err("dimension_profiles must be a list of exactly 6 items")
    seen_ids = set()
    for i, prof in enumerate(profiles):
        if not isinstance(prof, dict):
            return _err(f"dimension_profiles[{i}] must be an object")
        did = prof.get("dimension_id")
        if did not in _EXPECTED_DIM_IDS:
            return _err(f"dimension_profiles[{i}].dimension_id invalid: {did!r}")
        if did in seen_ids:
            return _err(f"dimension_profiles[{i}].dimension_id duplicated: {did}")
        seen_ids.add(did)
        score = prof.get("score")
        if not isinstance(score, (int, float)) or not (1 <= float(score) <= 5):
            return _err(f"dimension_profiles[{i}].score must be 1-5")
        conf = prof.get("confidence")
        if isinstance(conf, str):
            conf = conf.lower()
            prof["confidence"] = conf
        if conf not in _VALID_CONFIDENCE:
            return _err(f"dimension_profiles[{i}].confidence must be high/medium/low")
        for k in ("observed", "transformation_relevance"):
            if not isinstance(prof.get(k), str) or not prof[k].strip():
                return _err(f"dimension_profiles[{i}].{k} missing")
        eq = prof.get("evidence_quotes")
        if not isinstance(eq, list) or not all(isinstance(x, str) for x in eq):
            return _err(f"dimension_profiles[{i}].evidence_quotes must be list[str]")

    if seen_ids != _EXPECTED_DIM_IDS:
        return _err(f"dimension_profiles missing ids: {_EXPECTED_DIM_IDS - seen_ids}")

    ia = obj.get("integration_analysis")
    if not isinstance(ia, dict):
        return _err("integration_analysis missing or not an object")
    for k in ("patterns", "self_awareness_accuracy_narrative", "emergent_themes"):
        if not isinstance(ia.get(k), str) or not ia[k].strip():
            return _err(f"integration_analysis.{k} missing")
    contradictions = ia.get("contradictions")
    if contradictions is not None and not isinstance(contradictions, str):
        return _err("integration_analysis.contradictions must be string or null")

    dd = obj.get("ai_fluency_deep_dive")
    if not isinstance(dd, dict):
        return _err("ai_fluency_deep_dive missing or not an object")
    ct = dd.get("components_table")
    if not isinstance(ct, list) or len(ct) != 5:
        return _err("ai_fluency_deep_dive.components_table must have exactly 5 rows")
    for i, row in enumerate(ct):
        if not isinstance(row, dict):
            return _err(f"components_table[{i}] must be object")
        if not isinstance(row.get("component"), str):
            return _err(f"components_table[{i}].component must be string")
        if not isinstance(row.get("score"), (int, float)):
            return _err(f"components_table[{i}].score must be number")
        cr = row.get("confidence")
        if isinstance(cr, str):
            cr = cr.lower()
            row["confidence"] = cr
        if cr not in _VALID_CONFIDENCE:
            return _err(f"components_table[{i}].confidence must be high/medium/low")
        if not isinstance(row.get("notes"), str):
            return _err(f"components_table[{i}].notes must be string")
    for k in ("overview", "what_excellent_looks_like", "participant_gap"):
        if not isinstance(dd.get(k), str) or not dd[k].strip():
            return _err(f"ai_fluency_deep_dive.{k} missing")
    iq = dd.get("illustrative_quotes")
    if not isinstance(iq, list) or not all(isinstance(x, str) for x in iq):
        return _err("ai_fluency_deep_dive.illustrative_quotes must be list[str]")

    recs = obj.get("development_recommendations")
    if not isinstance(recs, list) or not (2 <= len(recs) <= 5):
        return _err("development_recommendations must be list of 2-5 items")
    for i, rec in enumerate(recs):
        if not isinstance(rec, dict):
            return _err(f"development_recommendations[{i}] must be object")
        for k in ("title", "what", "why", "how", "expectation"):
            if not isinstance(rec.get(k), str) or not rec[k].strip():
                return _err(f"development_recommendations[{i}].{k} missing")

    mn = obj.get("methodology_note")
    if not isinstance(mn, str) or not mn.strip():
        return _err("methodology_note must be a non-empty string")

    return True, ""


# --------------------------------------------------------------------------- #
# JSON extractor (shared pattern)
# --------------------------------------------------------------------------- #
def _extract_json_block(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.MULTILINE)
    depth = 0
    start = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return cleaned[start: i + 1]
    return None


# --------------------------------------------------------------------------- #
# Run synthesis via the llm_router cascade (two focused calls → merged payload)
# --------------------------------------------------------------------------- #
async def _one_call(
    tiers: List[Tier],
    system_body: str,
    user_body: str,
    schema_instructions: str,
    max_tokens: int = 2000,
) -> Tuple[bool, Dict[str, Any], str]:
    """One bounded-output LLM call via the router. Returns (ok, payload_or_meta, err)."""
    system = system_body + "\n\n## Output Format\n\n" + schema_instructions
    user = user_body
    last_error = ""
    raw = ""
    meta: Dict[str, Any] = {}
    for attempt in range(2):
        u = user
        if attempt == 1 and last_error:
            u = (
                "Your previous reply could not be parsed (" + last_error + "). "
                "Return ONLY the JSON object conforming to the schema — no prose, no code fences.\n\n"
                + user
            )
        try:
            result = await router_chat(
                messages=[{"role": "user", "content": u}],
                tiers=tiers,
                system=system,
                max_tokens=max_tokens,
                purpose="synthesis",
            )
        except LLMRouterError as exc:
            categories = [f.category for f in exc.failures]
            return False, {"raw": raw}, f"router: all tiers failed ({','.join(categories)})"
        raw = result.get("text") or ""
        meta = {
            "provider": result.get("provider"),
            "model": result.get("model"),
            "fallbacks_tried": result.get("fallbacks_tried", 0),
        }
        block = _extract_json_block(raw)
        if not block:
            last_error = "no JSON block"
            continue
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError as exc:
            last_error = f"json: {exc}"
            continue
        return True, {"payload": parsed, "meta": meta, "raw": raw}, ""
    return False, {"raw": raw, "meta": meta}, last_error


def _merge_synthesis_parts(part_a: Dict[str, Any], part_b: Dict[str, Any]) -> Dict[str, Any]:
    """Combine narrative + structured halves into the full deliverable shape."""
    merged = dict(part_a)
    merged["dimension_profiles"] = part_b.get("dimension_profiles", [])
    # components_table lives nested under ai_fluency_deep_dive in the final schema
    afd = dict(merged.get("ai_fluency_deep_dive") or {})
    afd["components_table"] = part_b.get("components_table", [])
    merged["ai_fluency_deep_dive"] = afd
    return merged


async def run_synthesis(
    session: Dict[str, Any],
    tiers: List[Tier],
) -> Dict[str, Any]:
    """Two LLM calls via the 3-tier cascade: (A) narrative, (B) structured; merged."""
    bundle = build_synthesis_input(session)
    bundle_json = json.dumps(bundle, ensure_ascii=False)

    user_body = (
        "The participant has just completed the mini-demo. Synthesise their assessment "
        "using the JSON bundle below. Follow all Doc 23 constraints and quality checks.\n\n"
        "Bundle:\n" + bundle_json
    )

    # --- Part A (narrative)
    ok_a, info_a, err_a = await _one_call(
        tiers=tiers,
        system_body=SYSTEM_PROMPT,
        user_body=user_body + "\n\nProduce PART A (narrative only) per the output format.",
        schema_instructions=OUTPUT_SCHEMA_INSTRUCTIONS_PART_A,
        max_tokens=2000,
    )
    if not ok_a:
        return {
            "ok": False, "scoring_error": True,
            "error": f"part_a: {err_a}",
            "raw": info_a.get("raw"),
            "meta": info_a.get("meta"),
        }

    # --- Part B (structured)
    ok_b, info_b, err_b = await _one_call(
        tiers=tiers,
        system_body=SYSTEM_PROMPT,
        user_body=user_body + "\n\nProduce PART B (structured dimension profiles + components table) per the output format.",
        schema_instructions=OUTPUT_SCHEMA_INSTRUCTIONS_PART_B,
        max_tokens=2500,
    )
    if not ok_b:
        return {
            "ok": False, "scoring_error": True,
            "error": f"part_b: {err_b}",
            "raw": info_b.get("raw"),
            "meta": info_b.get("meta"),
        }

    merged = _merge_synthesis_parts(info_a["payload"], info_b["payload"])
    ok_schema, reason = validate_synthesis_payload(merged)
    if not ok_schema:
        return {
            "ok": False, "scoring_error": True,
            "error": f"schema: {reason}",
            "raw": (info_a.get("raw") or "") + "\n\n---\n\n" + (info_b.get("raw") or ""),
            "meta": info_b["meta"],
        }

    # Fabrication check: warn if any dimension scored wildly off from the input.
    # (Not a hard failure — the LLM might reasonably round differently.)
    return {
        "ok": True,
        "payload": merged,
        "provider": info_b["meta"]["provider"],
        "model": info_b["meta"]["model"],
        "fallbacks_tried": max(info_a["meta"].get("fallbacks_tried", 0),
                               info_b["meta"].get("fallbacks_tried", 0)),
    }


# --------------------------------------------------------------------------- #
# Post-processing — annotate deliverable with band colours for the renderer
# --------------------------------------------------------------------------- #
def annotate_deliverable(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Attach band info (category, language, colour) to each dimension profile
    and the executive summary. Runs AFTER validation on a schema-valid payload.
    Does not mutate the LLM's original text fields."""
    out = json.loads(json.dumps(payload))  # deep copy
    es = out.get("executive_summary", {})
    # We don't recompute the overall band because Doc 23 says 'do not produce
    # single overall score for demo'. We keep the LLM-chosen category as-is
    # and attach colour lookup.
    cat = es.get("overall_category")
    for t in CATEGORY_THRESHOLDS:
        if t["category"] == cat:
            es["overall_colour"] = t["colour"]
            es["overall_language"] = t["language"]
            break

    # Per-dimension bands derived from scores
    for p in out.get("dimension_profiles", []) or []:
        try:
            p["band"] = band_for_score(p.get("score", 0))
        except Exception:
            p["band"] = {"category": "Unknown", "language": "", "colour": "gold"}

    return out
