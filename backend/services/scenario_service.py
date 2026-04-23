"""
Strategic Scenario service — Phase 6.

Parses /app/research/22 - Strategic Scenario.md at import time and exposes:
  - get_read_content()  — title + structured body (sections of paragraphs / bullets)
  - get_part1()         — preamble + 3 questions + duration_target_minutes
  - get_curveball()     — preamble + 3 numbered items + duration_target_minutes
  - get_part2()         — preamble + 3 questions + duration_target_minutes
  - get_scoring_prompt(), get_dimension_rubrics()
  - run_scoring(...)    — invokes llm_router for Cognitive Flexibility + Systems Thinking

Fails loudly on doc-shape violations:
  - body must be non-empty
  - exactly 3 Part 1 questions
  - exactly 3 curveball items
  - exactly 3 Part 2 questions

Doc 22 governs: where it conflicts with the phase brief, Doc 22 wins.
Notable conflict (resolved): Doc 22 `evidence` is a STRUCTURED OBJECT
(part1_position/part2_revision/key_quote for CF; connections_identified/
connections_missed/key_quote for ST) — the phase brief asked for list-of-strings.
We honour Doc 22. An `additional_observations` object replaces the brief's
`part1_analysis / part2_analysis / cross_part_analysis` fields.
"""
from __future__ import annotations
import re
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.llm_router import Tier, chat as router_chat, LLMRouterError

logger = logging.getLogger(__name__)

DOC_PATH = Path(__file__).resolve().parent.parent.parent / "research" / "22 - Strategic Scenario.md"

# Duration targets, picked from Doc 22 ranges (use the higher end so participants
# aren't rushed; the timer goes to "+" overrun after that, no auto-submit).
DURATION_READ_MIN = 4
DURATION_PART1_MIN = 5
DURATION_CURVEBALL_MIN = 4
DURATION_PART2_MIN = 4

MAX_ANSWER_CHARS = 4000


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def _load_text() -> str:
    if not DOC_PATH.exists():
        raise RuntimeError(f"Scenario doc not found: {DOC_PATH}")
    return DOC_PATH.read_text(encoding="utf-8")


def _parse_body_sections(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Extract the scenario title + body sections between 'Scenario: Meridian Energy Holdings'
    and '**Your Task (Part 1)**'. Sections keyed on bold headings: Financial Position, Workforce,
    Market Dynamics, Stakeholder Landscape, Recent Data Points."""
    start = text.find("**Scenario: Meridian Energy Holdings**")
    task_marker = text.find("**Your Task (Part 1)**")
    if start == -1 or task_marker == -1:
        raise RuntimeError("Scenario parse error: could not find scenario block.")
    block = text[start:task_marker].strip()

    # Title = the bold line at the top
    title_match = re.match(r"\*\*Scenario:\s*(.+?)\*\*", block)
    if not title_match:
        raise RuntimeError("Scenario parse error: title not found.")
    title = title_match.group(1).strip()

    # Remove title line
    rest = block[title_match.end():].lstrip("\n")

    # Find the intro paragraph (up to first blank line) and "The situation:" marker
    # Then parse each **heading** section.
    lines = rest.split("\n")

    # Intro paragraphs: collect ALL non-empty lines before "**The situation:**" marker,
    # split on blank lines into separate paragraph blocks.
    intro_paragraphs: List[str] = []
    idx = 0
    cur_para_lines: List[str] = []

    def _flush_para():
        nonlocal cur_para_lines
        if cur_para_lines:
            intro_paragraphs.append(" ".join(cur_para_lines))
            cur_para_lines = []

    while idx < len(lines):
        line = lines[idx].strip()
        if line == "**The situation:**":
            _flush_para()
            idx += 1
            break
        if line == "" or line == "---":
            _flush_para()
        else:
            cur_para_lines.append(line)
        idx += 1

    # Section headings in order, verbatim from Doc 22
    section_headings = [
        "Financial Position",
        "Workforce",
        "Market Dynamics",
        "Stakeholder Landscape",
        "Recent Data Points",
    ]

    sections: List[Dict[str, Any]] = []
    # Opening paragraphs (could be 1 or 2 per Doc 22)
    if intro_paragraphs:
        sections.append({
            "heading": None,
            "lines": [{"type": "paragraph", "text": p} for p in intro_paragraphs],
        })

    # Now walk remaining and bucket into sections by heading.
    current_heading: Optional[str] = None
    current_lines: List[Dict[str, Any]] = []

    def flush():
        nonlocal current_heading, current_lines
        if current_heading is not None or current_lines:
            sections.append({"heading": current_heading, "lines": current_lines})
        current_heading = None
        current_lines = []

    for line in lines[idx:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "---":
            continue  # horizontal rule divider
        # Heading: "**Financial Position**" on its own
        m = re.match(r"^\*\*(.+?)\*\*$", stripped)
        if m and m.group(1).strip() in section_headings:
            # flush previous
            flush()
            current_heading = m.group(1).strip()
            continue
        # Bullet
        if stripped.startswith("- "):
            if current_heading is None and not current_lines:
                # bullets before any heading? skip safety
                continue
            current_lines.append({"type": "bullet", "text": stripped[2:].strip()})
        else:
            # paragraph
            current_lines.append({"type": "paragraph", "text": stripped})
    flush()

    # Keep only valid sections: one unnamed intro + 5 named sections
    named = [s for s in sections if s["heading"] is not None]
    if len(named) != len(section_headings):
        raise RuntimeError(
            f"Scenario parse error: expected {len(section_headings)} named sections, got {len(named)}."
        )
    ordered_expected = section_headings
    actual_order = [s["heading"] for s in named]
    if actual_order != ordered_expected:
        raise RuntimeError(
            f"Scenario parse error: section order {actual_order} != expected {ordered_expected}."
        )

    return title, sections


def _parse_part_questions(text: str, part_label: str, start_marker: str, end_marker: str) -> List[str]:
    """Extract the 3 numbered questions under a **Your Task (Part N)** block."""
    s = text.find(start_marker)
    e = text.find(end_marker, s) if s != -1 else -1
    if s == -1 or e == -1:
        raise RuntimeError(f"Scenario parse error: could not find {part_label} block.")
    block = text[s:e]
    # Numbered items: "1. ...", "2. ...", "3. ..."
    items = re.findall(r"^\s*(\d+)\.\s+(.+?)\s*$", block, flags=re.MULTILINE)
    qs = [txt.strip() for num, txt in sorted(items, key=lambda x: int(x[0])) if int(num) in (1, 2, 3)]
    if len(qs) != 3:
        raise RuntimeError(
            f"Scenario parse error: expected 3 questions in {part_label}, got {len(qs)}."
        )
    return qs


def _parse_curveball(text: str) -> List[Dict[str, str]]:
    """Extract the 3 bolded curveball items between '**New Development**' and '**Your Task (Part 2)**'."""
    s = text.find("**New Development**")
    e = text.find("**Your Task (Part 2)**", s) if s != -1 else -1
    if s == -1 or e == -1:
        raise RuntimeError("Scenario parse error: could not find curveball block.")
    block = text[s:e]

    # Items: "1. **<heading>** <body...>", spanning multiple lines via the blank-line delimiter.
    items: List[Dict[str, str]] = []
    # Split on lines starting with "N. **..." preceded by optional blank lines
    chunks = re.split(r"(?m)^\s*(\d+)\.\s+\*\*", block)
    # chunks[0] is pre-content; then pairs of (num, rest)
    pairs = []
    i = 1
    while i + 1 <= len(chunks) - 1:
        num = chunks[i].strip()
        rest = chunks[i + 1]
        pairs.append((num, rest))
        i += 2
    if len(pairs) != 3:
        raise RuntimeError(f"Scenario parse error: expected 3 curveball items, got {len(pairs)}.")

    for num, rest in pairs:
        # rest is like "Ministry of Finance** has privately indicated ..."
        # Extract heading (up to next "**") and body
        m = re.match(r"(.+?)\*\*\s*(.+)", rest, flags=re.DOTALL)
        if not m:
            raise RuntimeError(f"Scenario parse error: curveball item {num} malformed.")
        heading = m.group(1).strip()
        body = re.sub(r"\s+", " ", m.group(2)).strip()
        items.append({"number": int(num), "heading": heading, "body": body})
    # Stable sort by number
    items.sort(key=lambda d: d["number"])
    return items


# --------------------------------------------------------------------------- #
# Module-level state
# --------------------------------------------------------------------------- #
_DOC_TEXT = _load_text()
_TITLE, _BODY_SECTIONS = _parse_body_sections(_DOC_TEXT)

_PART1_QUESTIONS = _parse_part_questions(
    _DOC_TEXT,
    "Part 1",
    "**Your Task (Part 1)**",
    "### Part 2: The Curveball",
)

_CURVEBALL_ITEMS = _parse_curveball(_DOC_TEXT)

_PART2_QUESTIONS = _parse_part_questions(
    _DOC_TEXT,
    "Part 2",
    "**Your Task (Part 2)**",
    "## Scoring Criteria",
)

# Verbatim preambles
_PART1_PREAMBLE = (
    "Write your strategic recommendation for the board. Address:"
)
_PART1_POSTAMBLE = (
    "You have 4–5 minutes. Write in whatever format works for you — bullet points, prose, "
    "however you think best."
)
_CURVEBALL_PREAMBLE = (
    "Two days before your board meeting, you receive the following:"
)
_PART2_PREAMBLE = (
    "Revise your strategic recommendation in light of this new information. Specifically:"
)
_PART2_POSTAMBLE = "You have 3–4 minutes."

logger.info(
    "Scenario loaded: title=%r, body_sections=%d, part1_qs=%d, curveball_items=%d, part2_qs=%d",
    _TITLE, len(_BODY_SECTIONS), len(_PART1_QUESTIONS), len(_CURVEBALL_ITEMS), len(_PART2_QUESTIONS),
)


# --------------------------------------------------------------------------- #
# Public accessors
# --------------------------------------------------------------------------- #
def get_read_content() -> Dict[str, Any]:
    return {
        "title": _TITLE,
        "body_sections": [
            {"heading": s["heading"], "lines": list(s["lines"])}
            for s in _BODY_SECTIONS
        ],
        "duration_target_minutes": DURATION_READ_MIN,
    }


def get_part1() -> Dict[str, Any]:
    return {
        "preamble": _PART1_PREAMBLE,
        "questions": list(_PART1_QUESTIONS),
        "postamble": _PART1_POSTAMBLE,
        "duration_target_minutes": DURATION_PART1_MIN,
        "max_answer_chars": MAX_ANSWER_CHARS,
    }


def get_curveball() -> Dict[str, Any]:
    return {
        "preamble": _CURVEBALL_PREAMBLE,
        "items": [dict(it) for it in _CURVEBALL_ITEMS],
        "duration_target_minutes": DURATION_CURVEBALL_MIN,
    }


def get_part2() -> Dict[str, Any]:
    return {
        "preamble": _PART2_PREAMBLE,
        "questions": list(_PART2_QUESTIONS),
        "postamble": _PART2_POSTAMBLE,
        "duration_target_minutes": DURATION_PART2_MIN,
        "max_answer_chars": MAX_ANSWER_CHARS,
    }


def get_content_all() -> Dict[str, Any]:
    return {
        "read": get_read_content(),
        "part1": get_part1(),
        "curveball": get_curveball(),
        "part2": get_part2(),
    }


# --------------------------------------------------------------------------- #
# Scoring prompt (assembled from Doc 22 verbatim)
# --------------------------------------------------------------------------- #
def get_dimension_rubrics() -> Dict[str, Any]:
    """Exact rubric text from Doc 22, lines 116–152."""
    return {
        "cognitive_flexibility": {
            "weight_pct": 8,
            "what_we_look_for": [
                "Does their Part 2 response genuinely integrate the new information?",
                "Do they revise their position where evidence warrants, or defend their original view?",
                "Can they hold complexity without collapsing to simple answers?",
            ],
            "scale": [
                {"score": 5, "description": "Sophisticated adaptation", "evidence":
                 "Materially revises approach based on new info; explains what changed in their thinking; comfortable with 'I was focused on wrong thing'"},
                {"score": 4, "description": "Clear adaptation", "evidence":
                 "Incorporates new info meaningfully; adjusts priorities; some revision to original view"},
                {"score": 3, "description": "Moderate adaptation", "evidence":
                 "Acknowledges new info; makes some adjustments; partly defensive of original"},
                {"score": 2, "description": "Limited adaptation", "evidence":
                 "Mentions new info but doesn't substantively change approach; 'this doesn't change my view'"},
                {"score": 1, "description": "No adaptation", "evidence":
                 "Ignores or dismisses new info; rigid adherence to original position"},
            ],
            "positive_signals": [
                "\"This changes my sequencing because...\"",
                "\"I hadn't weighted [X] correctly\"",
            ],
            "concerning_signals": [
                "\"My original plan handles this\"",
                "\"This is noise, I'm staying course\"",
            ],
        },
        "systems_thinking": {
            "weight_pct": 6,
            "what_we_look_for": [
                "Do they identify connections between elements?",
                "Do they anticipate second/third-order effects?",
                "Do they map stakeholder interdependencies?",
            ],
            "scale": [
                {"score": 5, "description": "Sophisticated systems view", "evidence":
                 "Identifies non-obvious connections; anticipates how action A affects B/C; maps feedback loops; sees stakeholder interdependencies"},
                {"score": 4, "description": "Good systems view", "evidence":
                 "Sees key connections; considers downstream effects; understands stakeholder dynamics"},
                {"score": 3, "description": "Moderate systems view", "evidence":
                 "Some connection-making; may miss important interdependencies; linear thinking in places"},
                {"score": 2, "description": "Limited systems view", "evidence":
                 "Treats issues in isolation; surprised by obvious connections; stakeholder blind spots"},
                {"score": 1, "description": "No systems view", "evidence":
                 "Completely siloed thinking; no interdependency recognition"},
            ],
            "positive_signals": [
                "\"If we do X, the union will interpret it as Y, which affects our position with Z...\"",
            ],
            "concerning_signals": [
                "\"Let's handle the customer issue, then separately deal with the workforce...\"",
            ],
        },
    }


def get_scoring_prompt() -> str:
    """Scoring instruction composed from Doc 22 Scoring Criteria + Response Analysis Guidance + Output schema."""
    rubrics = get_dimension_rubrics()

    def _scale_block(name: str, r: Dict[str, Any]) -> str:
        lines = [f"### {name.replace('_', ' ').title()} (rubric weight {r['weight_pct']}%)"]
        lines.append("What we're looking for:")
        for w in r["what_we_look_for"]:
            lines.append(f"  - {w}")
        lines.append("Score scale (score — description — evidence):")
        for s in r["scale"]:
            lines.append(f"  {s['score']}: {s['description']} — {s['evidence']}")
        lines.append("Positive signals: " + "; ".join(r["positive_signals"]))
        lines.append("Concerning signals: " + "; ".join(r["concerning_signals"]))
        return "\n".join(lines)

    parts = [
        "You are scoring a strategic scenario exercise (Meridian Energy Holdings) against two dimensions from the SOE transformation-readiness framework. Follow Doc 22 verbatim.",
        "",
        _scale_block("cognitive_flexibility", rubrics["cognitive_flexibility"]),
        "",
        _scale_block("systems_thinking", rubrics["systems_thinking"]),
        "",
        "## Response Analysis Guidance",
        "Part 1 Analysis:",
        "  - What trade-offs did they explicitly identify?",
        "  - Which stakeholders did they prioritise? Ignore?",
        "  - Did they acknowledge uncertainty and constraints?",
        "  - Was their reasoning coherent and evidence-based?",
        "  - Did they spot non-obvious connections?",
        "Part 2 Analysis:",
        "  - What specifically changed between Part 1 and Part 2?",
        "  - Did they integrate all three new elements or cherry-pick?",
        "  - Did they acknowledge where their Part 1 was incomplete?",
        "  - How did they handle the ethical dimension (cybersecurity disclosure)?",
        "  - Did new info reveal blind spots from Part 1?",
        "Cross-Part Analysis:",
        "  - Cognitive flexibility signal: degree of genuine revision",
        "  - Systems thinking signal: connections made across scenario elements",
        "  - Self-awareness signal: acknowledgment of what they missed",
        "",
        "## Output",
        "Return ONLY a JSON object conforming exactly to this schema — no prose, no markdown fences:",
        "",
        """{
  "scenario_analysis": {
    "cognitive_flexibility": {
      "score": 4,
      "confidence": "high",
      "evidence": {
        "part1_position": "<one-sentence summary of their Part 1 position>",
        "part2_revision": "<one-sentence summary of how Part 2 differs>",
        "revision_quality": "<one or two sentences describing depth of revision>",
        "key_quote": "<direct quote from their response that best demonstrates the score>"
      }
    },
    "systems_thinking": {
      "score": 4,
      "confidence": "medium",
      "evidence": {
        "connections_identified": ["<short string>", "<short string>"],
        "connections_missed":     ["<short string>", "<short string>"],
        "key_quote": "<direct quote that best demonstrates systems thinking (or its absence)>"
      }
    },
    "additional_observations": {
      "stakeholder_awareness": "<one sentence>",
      "ethical_reasoning":     "<one sentence>",
      "analytical_quality":    "<one sentence>"
    }
  }
}""",
        "",
        "Notes on confidence: use one of 'high', 'medium', 'low' (strings, lowercase).",
        "Notes on scores: integer 1-5.",
        "Do NOT echo the participant's full responses in the JSON; the caller has them.",
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Scoring validator
# --------------------------------------------------------------------------- #
ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def validate_scoring_payload(obj: Dict[str, Any]) -> Tuple[bool, str]:
    sa = obj.get("scenario_analysis") if isinstance(obj, dict) else None
    if not isinstance(sa, dict):
        return False, "missing scenario_analysis"

    for dim_key, ev_required_keys in [
        ("cognitive_flexibility", ("part1_position", "part2_revision", "revision_quality", "key_quote")),
        ("systems_thinking", ("connections_identified", "connections_missed", "key_quote")),
    ]:
        d = sa.get(dim_key)
        if not isinstance(d, dict):
            return False, f"missing {dim_key}"
        if not isinstance(d.get("score"), int) or not (1 <= d["score"] <= 5):
            return False, f"{dim_key}.score must be int 1-5"
        conf = d.get("confidence")
        if isinstance(conf, str):
            conf = conf.lower()
            d["confidence"] = conf
        if conf not in ALLOWED_CONFIDENCE:
            return False, f"{dim_key}.confidence must be high/medium/low"
        ev = d.get("evidence")
        if not isinstance(ev, dict):
            return False, f"{dim_key}.evidence must be object"
        for k in ev_required_keys:
            if k not in ev:
                return False, f"{dim_key}.evidence.{k} missing"
            val = ev[k]
            if k in ("connections_identified", "connections_missed"):
                if not isinstance(val, list) or not all(isinstance(e, str) for e in val):
                    return False, f"{dim_key}.evidence.{k} must be list[str]"
            else:
                if not isinstance(val, str):
                    return False, f"{dim_key}.evidence.{k} must be string"

    obs = sa.get("additional_observations")
    if not isinstance(obs, dict):
        return False, "additional_observations must be object"
    for k in ("stakeholder_awareness", "ethical_reasoning", "analytical_quality"):
        if not isinstance(obs.get(k), str):
            return False, f"additional_observations.{k} must be string"
    return True, ""


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
                return cleaned[start : i + 1]
    return None


# --------------------------------------------------------------------------- #
# Scoring — called by server.py on Part 2 submit
# --------------------------------------------------------------------------- #
async def run_scoring(
    part1_response: Dict[str, str],
    part2_response: Dict[str, str],
    tiers: List[Tier],
) -> Dict[str, Any]:
    """Make up to two LLM calls via the provided 3-tier cascade to produce the scenario scoring."""
    # Build a clean structured bundle for the scorer
    bundle = {
        "scenario_title": _TITLE,
        "part1_questions": _PART1_QUESTIONS,
        "part1_responses": {"q1": part1_response.get("q1", ""), "q2": part1_response.get("q2", ""), "q3": part1_response.get("q3", "")},
        "curveball_items": _CURVEBALL_ITEMS,
        "part2_questions": _PART2_QUESTIONS,
        "part2_responses": {"q1": part2_response.get("q1", ""), "q2": part2_response.get("q2", ""), "q3": part2_response.get("q3", "")},
    }
    bundle_json = json.dumps(bundle, ensure_ascii=False)

    system_prompt = get_scoring_prompt()
    base_user_message = "Here is the scenario bundle (JSON):\n\n" + bundle_json

    last_error: Optional[str] = None
    raw_text: Optional[str] = None

    for attempt in range(2):
        user_message = base_user_message
        if attempt == 1 and last_error:
            user_message = (
                "Your previous reply could not be parsed (" + last_error + "). "
                "Reply with ONLY the JSON object — no prose, no code fences.\n\n"
                + base_user_message
            )
        try:
            result = await router_chat(
                messages=[{"role": "user", "content": user_message}],
                tiers=tiers,
                system=system_prompt,
                max_tokens=4000,
                purpose="scenario-scoring",
            )
            raw_text = result.get("text") or ""
            block = _extract_json_block(raw_text)
            if not block:
                last_error = "no JSON block"
                continue
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError as exc:
                last_error = f"json: {exc}"
                continue
            ok, reason = validate_scoring_payload(parsed)
            if ok:
                return {
                    "ok": True,
                    "payload": parsed,
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "fallbacks_tried": result.get("fallbacks_tried", 0),
                }
            last_error = f"schema: {reason}"
        except LLMRouterError as exc:
            categories = [f.category for f in exc.failures]
            return {
                "ok": False,
                "scoring_error": True,
                "error": f"router: all tiers failed ({','.join(categories)})",
                "raw": raw_text,
            }

    return {
        "ok": False,
        "scoring_error": True,
        "error": last_error or "unknown",
        "raw": raw_text,
    }
