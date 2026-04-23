"""
AI Fluency Discussion service — Phase 5.

Responsibilities:
  - Build prompts per Doc 21 (system prompt verbatim, opener selection, closing note).
  - Build LLM Tiers from admin_settings (primary → secondary → Emergent fallback).
  - Invoke the Phase-3 llm_router for each assistant turn.
  - On end of interview, run a separate scoring call and return a structured JSON
    payload conforming to Doc 21's output schema.

Doc 21 governs: wherever Doc 21 conflicts with the phase brief, Doc 21 wins.
Notable conflict (resolved): Doc 21 uses string confidence values ('high'|'medium'|'low');
the brief mentioned 0..1 or 1..5 — we follow Doc 21.

Turn-numbering convention persisted in session.conversation[]:
  • The opening assistant turn uses turn = 0.
  • User turn N uses turn = N (where N is 1..12).
  • The assistant reply to user turn N carries turn = N as well.
  • user_turn_count is the count of role=='user' messages (i.e. the highest user turn).
"""
from __future__ import annotations
import os
import re
import json
import logging
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from services.llm_router import (
    Tier,
    chat as router_chat,
    build_tier,
    build_fallback_tier,
    LLMRouterError,
    ProviderCall,
)
from llm_providers import DEFAULT_FALLBACK_MODEL
from crypto_utils import decrypt_str

logger = logging.getLogger(__name__)

MAX_USER_TURNS = 12
MAX_OUTPUT_TOKENS_PER_TURN = 4000
MAX_USER_INPUT_CHARS = 2000


# --------------------------------------------------------------------------- #
# Prompt assembly (Doc 21 verbatim)
# --------------------------------------------------------------------------- #
# System prompt — copied exactly from Doc 21, lines 12–95.
SYSTEM_PROMPT = """You are an expert executive assessor conducting an AI Fluency assessment as part of a leadership transformation readiness evaluation. Your role is to have a natural, probing conversation that reveals the participant's genuine understanding of AI—not to teach or correct them.

## Your Persona
- Senior, experienced, professionally warm but direct
- Genuinely curious about their perspective
- Not impressed by buzzwords; interested in real understanding
- Comfortable with silence; let them think

## Your Objectives
Assess the participant across five components of AI Fluency:
1. Capability Understanding — Do they know what AI can and cannot do?
2. Paradigm Awareness — Do they understand different AI approaches exist?
3. Orchestration Concepts — Do they grasp multi-agent/agentic AI?
4. Governance Thinking — Do they think about AI accountability?
5. Personal Usage — Do they actually use AI themselves?

## Conversation Structure
You have approximately 10-12 exchanges. Move through these phases:

**Opening (1-2 exchanges)**
Warm up with current AI usage. Get them talking comfortably.

**Capability Probe (2-3 exchanges)**
Explore their understanding of what AI can and cannot do. Listen for nuance vs. hype.

**Paradigm/Orchestration Probe (2-3 exchanges)**
See if they're aware of different AI approaches. Probe agentic AI understanding.

**Governance Probe (2-3 exchanges)**
Explore how they think about AI accountability and risk.

**Close (1 exchange)**
Thank them and transition to next assessment component.

## Conversation Guidelines

DO:
- Ask open-ended questions
- Follow up on interesting or vague statements
- Probe beneath surface-level answers
- Note specific examples they give
- Acknowledge their points briefly before moving on

DO NOT:
- Teach or correct them
- Show approval or disapproval of their views
- Accept buzzwords without probing ("What do you mean by that?")
- Rush past interesting threads
- Make them feel tested or judged

## Probing Techniques

When they give a surface answer:
- "Can you say more about that?"
- "What makes you think that?"
- "Can you give me an example?"
- "How would that actually work in practice?"

When they use jargon:
- "What do you mean by [term]?"
- "How would you explain that to your board?"

When they seem uncertain:
- "That's fine—what's your instinct?"
- "You can think aloud here."

When they're clearly wrong:
- Don't correct. Note it internally. Move on or probe deeper.

## Internal Tracking

As you converse, mentally score each component (1-5):
- Note specific quotes that demonstrate understanding or gaps
- Track whether they speak from personal experience or theory
- Notice if they acknowledge limitations/uncertainty (good sign)
- Notice if they're overconfident or dismissive (concerning)

## Ending the Conversation

After ~10-12 exchanges, wrap up:
"Thank you—that's really helpful. I've got a good sense of how you're thinking about AI. We'll move to the next component now."

Do not summarise or give feedback during the assessment."""

# The three opening probes from Doc 21 (lines 103, 105, 107), verbatim.
OPENING_PROBES: List[str] = [
    "Let's start with how you're engaging with AI today. How are you personally using AI tools in your work or life right now?",
    "To kick us off—what's the most useful thing AI has done for you recently, either personally or in your organisation?",
    "Tell me about your current relationship with AI tools. How often are you using them, and for what?",
]


def select_opener(session_id: str) -> str:
    """Deterministic opener selection keyed on session_id so the same session always
    gets the same opening probe (even after a restart before any turns have happened)."""
    h = hashlib.sha256((session_id or "").encode("utf-8")).digest()
    idx = h[0] % len(OPENING_PROBES)
    return OPENING_PROBES[idx]


def build_participant_context(participant: Dict[str, Any], psychometric_scores: Optional[Dict[str, Any]]) -> str:
    """One-line developer note injected before the first user turn.

    First name only (extract first word of name), organisation/role if present,
    and a one-line psychometric summary using BANDS (not raw scores) so the
    interviewer is aware but doesn't probe around numbers.
    """
    name = (participant or {}).get("name") or ""
    first_name = name.strip().split()[0] if name.strip() else "the participant"
    org = (participant or {}).get("organisation")
    role = (participant or {}).get("role")

    bits: List[str] = [f"Participant first name: {first_name}."]
    if role:
        bits.append(f"Role: {role}.")
    if org:
        bits.append(f"Organisation: {org}.")
    if psychometric_scores:
        la = (psychometric_scores.get("learning_agility") or {}).get("band")
        ta = (psychometric_scores.get("tolerance_for_ambiguity") or {}).get("band")
        if la and ta:
            bits.append(
                f"Prior psychometric result: Learning Agility {la}, Tolerance for Ambiguity {ta}. "
                "Use this as background only — do not probe around numbers."
            )
    return " ".join(bits)


FINAL_TURN_NOTE = (
    "Developer note: This is the final user turn. Emit ONLY the closing line per the "
    "Doc 21 exit protocol ("
    "\"Thank you—that's really helpful. I've got a good sense of how you're thinking about AI. "
    "We'll move to the next component now.\""
    ") — a short, warm, human-readable acknowledgement. Do NOT emit JSON. Do NOT summarise. "
    "You will be called again separately to produce the structured JSON."
)


def build_messages_for_turn(
    conversation: List[Dict[str, Any]],
    participant_ctx: str,
    final_turn: bool = False,
) -> List[Dict[str, str]]:
    """Convert persisted conversation[] into the router's message list.

    Filters out system-only rows; only user/assistant are sent as chat turns.
    Developer notes (participant context, final-turn instruction) are prepended
    as additional "user" role messages tagged as dev notes — a common pattern
    for providers that only accept user/assistant messages (most do).
    """
    msgs: List[Dict[str, str]] = []
    # Participant context as a dev user note (only once, at top).
    if participant_ctx:
        msgs.append({"role": "user", "content": f"[Developer note] {participant_ctx}"})
        # Acknowledge to keep the chain well-formed for some providers
        msgs.append({"role": "assistant", "content": "Understood. I will keep that in mind."})

    for turn in conversation:
        role = turn.get("role")
        content = turn.get("content") or ""
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})

    if final_turn:
        msgs.append({"role": "user", "content": FINAL_TURN_NOTE})
    return msgs


# --------------------------------------------------------------------------- #
# Tier construction (primary → secondary → Emergent fallback)
# --------------------------------------------------------------------------- #
async def build_tiers_from_admin_settings(admin_settings_doc: Optional[Dict[str, Any]]) -> List[Tier]:
    tiers: List[Tier] = []
    if admin_settings_doc:
        primary = admin_settings_doc.get("primary")
        if primary and primary.get("api_key_encrypted") and primary.get("provider") and primary.get("model"):
            try:
                key = decrypt_str(primary["api_key_encrypted"])
                if key:
                    tiers.append(await build_tier("primary", primary["provider"], primary["model"], key))
            except Exception as exc:
                logger.warning("Could not build primary tier: %s", exc)
        secondary = admin_settings_doc.get("secondary")
        if secondary and secondary.get("api_key_encrypted") and secondary.get("provider") and secondary.get("model"):
            try:
                key = decrypt_str(secondary["api_key_encrypted"])
                if key:
                    tiers.append(await build_tier("secondary", secondary["provider"], secondary["model"], key))
            except Exception as exc:
                logger.warning("Could not build secondary tier: %s", exc)
    fallback_model = (admin_settings_doc or {}).get("fallback_model") or DEFAULT_FALLBACK_MODEL
    tiers.append(await build_fallback_tier(fallback_model))
    return tiers


# --------------------------------------------------------------------------- #
# Scoring (end-of-interview)
# --------------------------------------------------------------------------- #
SCORING_INSTRUCTION = """You have just conducted an AI Fluency assessment conversation as described in the Doc 21 interviewer spec.

Now produce the structured assessment output. Score each component on a 1-5 scale per the Doc 21 rubric:

- Capability Understanding (Doc 21 §Component 1)
- Paradigm Awareness (Doc 21 §Component 2)
- Orchestration Concepts (Doc 21 §Component 3)
- Governance Thinking (Doc 21 §Component 4)
- Personal Usage (Doc 21 §Component 5)

For each component provide:
- score: integer 1-5
- confidence: one of "high", "medium", "low"
- evidence: 2-3 short strings quoting or paraphrasing what the participant said

Also produce:
- overall_score: float, weighted mean rounded to 1 decimal place
- key_quotes: 2-4 short direct quotes from the transcript that were most revealing
- blind_spots: 1-3 short strings
- strengths: 1-3 short strings

Return ONLY a JSON object with exactly this shape (no prose, no markdown, no code fence):

{
  "ai_fluency": {
    "overall_score": 3.6,
    "components": {
      "capability_understanding": {"score": 4, "confidence": "high", "evidence": ["...", "..."]},
      "paradigm_awareness":        {"score": 3, "confidence": "medium", "evidence": ["..."]},
      "orchestration_concepts":    {"score": 3, "confidence": "medium", "evidence": ["..."]},
      "governance_thinking":       {"score": 4, "confidence": "high", "evidence": ["..."]},
      "personal_usage":            {"score": 4, "confidence": "high", "evidence": ["..."]}
    },
    "key_quotes": ["...", "..."],
    "blind_spots": ["..."],
    "strengths": ["..."]
  }
}

Do not include the transcript in your response — the caller already has it.
"""


COMPONENT_KEYS = [
    "capability_understanding",
    "paradigm_awareness",
    "orchestration_concepts",
    "governance_thinking",
    "personal_usage",
]

ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def _extract_json_block(text: str) -> Optional[str]:
    """Find the first {...} JSON block in text. Tolerates markdown fences."""
    if not text:
        return None
    # Strip code fences
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.MULTILINE)
    # Scan for balanced braces
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


def validate_scoring_payload(obj: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (ok, reason). Mutates obj in place to normalise trivial issues."""
    af = obj.get("ai_fluency") if isinstance(obj, dict) else None
    if not isinstance(af, dict):
        return False, "missing ai_fluency"
    if not isinstance(af.get("overall_score"), (int, float)):
        return False, "overall_score must be number"
    comps = af.get("components")
    if not isinstance(comps, dict):
        return False, "components must be object"
    for key in COMPONENT_KEYS:
        c = comps.get(key)
        if not isinstance(c, dict):
            return False, f"components.{key} missing"
        if not isinstance(c.get("score"), int) or not (1 <= c["score"] <= 5):
            return False, f"components.{key}.score must be int 1-5"
        conf = c.get("confidence")
        if isinstance(conf, str):
            conf = conf.lower()
            c["confidence"] = conf
        if conf not in ALLOWED_CONFIDENCE:
            return False, f"components.{key}.confidence must be high/medium/low"
        ev = c.get("evidence")
        if not isinstance(ev, list) or not all(isinstance(e, str) for e in ev):
            return False, f"components.{key}.evidence must be list[str]"
    for list_key in ("key_quotes", "blind_spots", "strengths"):
        v = af.get(list_key)
        if not isinstance(v, list) or not all(isinstance(e, str) for e in v):
            return False, f"{list_key} must be list[str]"
    return True, ""


async def run_scoring(
    conversation: List[Dict[str, Any]],
    participant_ctx: str,
    tiers: List[Tier],
) -> Dict[str, Any]:
    """Make up to two LLM calls to produce the scoring payload.

    Returns: {ok, payload?, provider, model, fallbacks_tried, scoring_error?, raw?}
    """
    # Build a tight "messages" array: system context + entire transcript flattened
    transcript_lines: List[str] = []
    if participant_ctx:
        transcript_lines.append(f"[Participant context] {participant_ctx}")
    for t in conversation:
        role = t.get("role")
        if role not in ("user", "assistant"):
            continue
        prefix = "Participant" if role == "user" else "Interviewer"
        transcript_lines.append(f"{prefix}: {t.get('content', '')}")
    transcript = "\n\n".join(transcript_lines)

    base_messages = [
        {"role": "user", "content": SCORING_INSTRUCTION + "\n\n--- TRANSCRIPT ---\n" + transcript}
    ]

    last_error: Optional[str] = None
    raw_text: Optional[str] = None

    for attempt in range(2):
        try:
            result = await router_chat(
                messages=base_messages,
                tiers=tiers,
                system=SYSTEM_PROMPT,
                max_tokens=MAX_OUTPUT_TOKENS_PER_TURN,
                purpose="ai-fluency-scoring",
            )
            raw_text = result.get("text") or ""
            block = _extract_json_block(raw_text)
            if not block:
                last_error = "no JSON block"
            else:
                try:
                    parsed = json.loads(block)
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
                except json.JSONDecodeError as exc:
                    last_error = f"json: {exc}"
        except LLMRouterError as exc:
            categories = [f.category for f in exc.failures]
            last_error = f"router: all tiers failed ({','.join(categories)})"
            # On all-tiers-failed we cannot retry usefully
            return {
                "ok": False,
                "scoring_error": True,
                "error": last_error,
                "raw": raw_text,
            }

        # Second attempt: tighter reminder
        if attempt == 0:
            base_messages = [
                {"role": "user", "content": SCORING_INSTRUCTION
                 + "\n\n(Your previous reply could not be parsed as strict JSON — " + (last_error or "")
                 + ". Reply with ONLY the JSON object. No prose, no markdown fences.)"
                 + "\n\n--- TRANSCRIPT ---\n" + transcript}
            ]

    return {
        "ok": False,
        "scoring_error": True,
        "error": last_error or "unknown",
        "raw": raw_text,
    }
