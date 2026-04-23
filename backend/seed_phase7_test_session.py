#!/usr/bin/env python
"""Seed a complete assessment session for Phase 7 testing.

Inserts a session with realistic, canned:
  - participant (Ada Lovelace, Analytical Engine Co, Chief Mathematician)
  - full psychometric scores (LA 4.1, TA 3.6)
  - full ai_fluency scores with components, blind_spots, strengths, key_quotes
  - a full ai_discussion conversation (12+ turns, provider/model stripped-ready)
  - scenario.part1_response + part2_response + scores.scenario
  - stage set to 'processing' so /processing/start is allowed

Prints the session_id and resume_code on stdout.
"""
import asyncio
import os
import uuid
import secrets
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "soe_tra")

CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def gen_code():
    a = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    b = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    return f"{a}-{b}"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


CONVERSATION = [
    {"turn": 0, "role": "assistant", "content": "To kick us off — what's the most useful thing AI has done for you recently, professionally or personally?"},
    {"turn": 1, "role": "user", "content": "I use Claude for drafting board papers and summarising long reports. I've probably tried six different AI tools this year — some worked, most didn't, but I learned something each time."},
    {"turn": 1, "role": "assistant", "content": "That's a useful pattern — experimenting to find fit. When you say 'didn't work', what do you mean? A capability ceiling, or something about how the tool was deployed?"},
    {"turn": 2, "role": "user", "content": "Mix of both. Some tools hallucinated figures I couldn't verify. Others were fine technically but nobody on my team adopted them because the workflow was awkward."},
    {"turn": 2, "role": "assistant", "content": "Stepping back — how do you think about what AI is actually good at today, versus where it'll be in three years?"},
    {"turn": 3, "role": "user", "content": "Today it's a smart intern — useful but needs supervision. In three years I expect it'll be more autonomous but I honestly haven't thought about it deeply."},
    {"turn": 3, "role": "assistant", "content": "That 'smart intern' framing is common and it captures a lot. Have you engaged with the idea of agentic AI — systems that can plan and execute multi-step tasks without a human at every turn?"},
    {"turn": 4, "role": "user", "content": "Not really, not beyond headlines. I'd want to understand it before deploying it at scale. The governance questions around that keep me up — who's accountable when the AI gets it wrong?"},
    {"turn": 4, "role": "assistant", "content": "That accountability question is important. How do you reason about it today — is it a question your board has started asking?"},
    {"turn": 5, "role": "user", "content": "We've haven't really figured out who's accountable when the AI gets it wrong. The board asks about it in governance committees but we default to 'the approver'. I'm not sure that scales."},
    {"turn": 5, "role": "assistant", "content": "Fair. Pivoting slightly — there are different AI paradigms. Are you familiar with the distinction between Anthropic's and OpenAI's approaches?"},
    {"turn": 6, "role": "user", "content": "I know Anthropic is big on safety and 'constitutional AI' and OpenAI is more product-driven. Beyond that, honestly no."},
    {"turn": 6, "role": "assistant", "content": "That captures the surface accurately. Final topic — what's your personal cadence with AI tools right now, day-to-day?"},
    {"turn": 7, "role": "user", "content": "Daily. I use Claude for drafting, NotebookLM for reading, ChatGPT for quick reasoning. I'm probably behind on understanding where this is all going but I'm using it."},
    {"turn": 7, "role": "assistant", "content": "Thank you — that's enough signal. I appreciate your candour; this has been a rich exchange. (end of discussion)"},
]


AI_FLUENCY_SCORES = {
    "overall_score": 3.6,
    "components": {
        "capability_understanding": {
            "score": 4, "confidence": "high",
            "evidence": ["Distinguishes signal from hallucination", "Recognises adoption friction"],
        },
        "paradigm_awareness": {
            "score": 3, "confidence": "medium",
            "evidence": ["Named Anthropic vs OpenAI at surface level", "Acknowledged own gap"],
        },
        "orchestration_concepts": {
            "score": 3, "confidence": "medium",
            "evidence": ["Hasn't engaged with agentic AI beyond headlines"],
        },
        "governance_thinking": {
            "score": 4, "confidence": "high",
            "evidence": ["Accountability question 'keeps me up'", "Board governance committee context"],
        },
        "personal_usage": {
            "score": 4, "confidence": "high",
            "evidence": ["Daily AI use across Claude, NotebookLM, ChatGPT"],
        },
    },
    "key_quotes": [
        "I've probably tried six different AI tools this year — some worked, most didn't, but I learned something each time.",
        "Today it's a smart intern — useful but needs supervision.",
        "We haven't really figured out who's accountable when the AI gets it wrong.",
        "I'm probably behind on understanding where this is all going but I'm using it.",
    ],
    "strengths": [
        "Daily AI usage with clear mental model of strengths/weaknesses.",
        "Proactive governance instincts around accountability.",
        "Learning-oriented approach — experiments and integrates results.",
    ],
    "blind_spots": [
        "Agentic AI / multi-agent orchestration.",
        "Paradigm depth beyond headlines.",
    ],
    "_meta": {"provider": "emergent", "model": "claude-opus-4-6", "fallbacks_tried": 0},
}


PSYCH_SCORES = {
    "learning_agility": {
        "raw_sum": 48, "mean_6pt": 4.0, "mean_1_5": 4.1,
        "band": "High Potential",
        "subscales": {
            "mental_agility": {"mean_1_5": 4.3},
            "people_agility": {"mean_1_5": 3.8},
            "change_agility": {"mean_1_5": 4.2},
            "results_agility": {"mean_1_5": 4.0},
            "self_awareness": {"mean_1_5": 4.2},
        },
    },
    "tolerance_for_ambiguity": {
        "raw_sum": 32, "mean_6pt": 4.0, "mean_1_5": 3.6,
        "band": "Moderate",
        "subscales": {
            "uncertainty_comfort": {"mean_1_5": 3.8},
            "complexity_comfort": {"mean_1_5": 3.7},
            "closure_resistance": {"mean_1_5": 3.2},
        },
    },
    "self_awareness_claimed": {"mean_1_5": 4.2},
    "timing": {"median_response_time_ms": 18000},
    "bands_reference": "Doc 20 mapping: 1.0-2.4 Low · 2.5-3.4 Moderate · 3.5-4.4 High Potential · 4.5-5.0 High",
}


SCENARIO_SCORES = {
    "cognitive_flexibility": {
        "score": 4, "confidence": "high",
        "evidence": {
            "part1_position": "A gradualist three-step plan: bond renegotiation, workforce transition to renewables, Bangladesh tolling partnership.",
            "part2_revision": "Reordered priorities around governance and reputational risk. Paused the Bangladesh tolling deal, accelerated union engagement, led with proactive cyber disclosure.",
            "revision_quality": "Participant explicitly named their Part 1 blind spot ('over-indexed on financial stability') and reconceived three issues as a single reputation system.",
            "key_quote": "I was over-indexed on financial stability in my Part 1 answer; I under-weighted governance risk and political optics.",
        },
    },
    "systems_thinking": {
        "score": 4, "confidence": "high",
        "evidence": {
            "connections_identified": [
                "Union confidence vote cascading into bond rating review.",
                "Cyber disclosure as material to offtaker relationships and partnership timing.",
                "Union, Ministry, and cyber breach forming a single reputation system.",
            ],
            "connections_missed": [
                "How 15% customer defection threat interacts with bond covenant metrics.",
                "No explicit mapping of how proactive cyber disclosure might strengthen customer retention negotiations.",
            ],
            "key_quote": "I now see the union, the Ministry and the cyber disclosure as a single reputation system, not three separate issues.",
        },
    },
    "additional_observations": {
        "stakeholder_awareness": "Strong across both parts; recognised union, MoF, offtake customers, and later the Minister of Labour and political stakeholders.",
        "ethical_reasoning": "Chose proactive over reactive cyber disclosure without hedging; framed as both ethical obligation and strategic advantage.",
        "analytical_quality": "Concise, well-structured, comfortable with ambiguity; the move from financial-first to governance-and-reputation frame is well-justified.",
    },
    "_meta": {"provider": "emergent", "model": "claude-opus-4-6", "fallbacks_tried": 0},
}


async def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    session_id = str(uuid.uuid4())
    resume = gen_code()
    now = now_iso()

    # Make conversation turns carry metadata on assistant entries (then the
    # public API will strip them).
    conversation = []
    for t in CONVERSATION:
        entry = dict(t, timestamp=now, kind=None)
        if entry["role"] == "assistant" and entry["turn"] > 0:
            entry["provider"] = "emergent"
            entry["model"] = "claude-opus-4-6"
            entry["latency_ms"] = 3000
            entry["fallbacks_tried"] = 0
        conversation.append(entry)

    doc = {
        "_id": session_id,
        "session_id": session_id,
        "resume_code": resume,
        "participant": {
            "name": "Ada Lovelace",
            "email": "ada.test@example.co.uk",
            "organisation": "Analytical Engine Co",
            "role": "Chief Mathematician",
        },
        "consent": {"accepted": True, "accepted_at": now},
        "status": "active",
        "stage": "processing",
        "psychometric": {"order": [], "answers": [], "started_at": now, "completed_at": now},
        "answers": [],
        "conversation": conversation,
        "ai_discussion": {
            "status": "completed", "started_at": now, "completed_at": now,
            "user_turn_count": 7, "opener": 1,
        },
        "scenario": {
            "started_at": now, "completed_at": now, "status": "completed", "phase": "done",
            "phase_entered_at": {"read": now, "part1": now, "curveball": now, "part2": now},
            "time_on_phase_ms": {"read": 180000, "part1": 280000, "curveball": 150000, "part2": 240000},
            "exit_reason": None,
            "part1_response": {
                "q1": "I sequence three moves: a 90-day cash preservation package focused on renegotiating the October bond terms before the rating review; a workforce transition plan that shifts 1,200 roles from refining to renewables operations over 18 months with retraining; an accelerated tolling partnership in Bangladesh to backfill the lost Singapore refining margin.",
                "q2": "I would not chase the downstream expansion this cycle. The margin case is real but the timing puts us head-to-head with covenant risk and a union confidence vote. The renewables pivot is credible but needs a first-mover demonstration asset. I would stage.",
                "q3": "Union (critical — their confidence determines operational capacity for the next 18 months), Ministry of Finance (bond review, capex envelope), our three large offtake customers, and — too easy to ignore — the newer political stakeholders lobbying for domestic manufacturing content.",
            },
            "part2_response": {
                "q1": "The curveball rewires my priorities. The Ministry signal changes the sequencing — I accelerate the union engagement because losing the confidence vote in this climate would cascade into the bond review. I also re-scope the Bangladesh tolling deal because the cyber disclosure to offtakers is material and must land before any partnership signing.",
                "q2": "I was over-indexed on financial stability in my Part 1 answer; I under-weighted governance risk and political optics. I now see the union, the Ministry and the cyber disclosure as a single reputation system, not three separate issues. I would disclose the breach proactively, not reactively.",
                "q3": "Sequencing: (1) board-approved cyber disclosure this week with remediation plan, (2) union dialogue restart pre-confidence-vote with concrete retraining commitments, (3) MoF engagement on covenant relaxation while we re-stage the downstream expansion, (4) Bangladesh partnership paused pending cyber disclosure and customer audit outcomes.",
            },
        },
        "scenario_responses": {},
        "deliverable": None,
        "scores": {
            "psychometric": PSYCH_SCORES,
            "ai_fluency": AI_FLUENCY_SCORES,
            "scenario": SCENARIO_SCORES,
        },
        "archived": False,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "expires_at": None,
    }

    await db["sessions"].insert_one(doc)
    print(session_id)
    print(resume)
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
