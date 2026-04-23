from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Cookie
from fastapi.responses import JSONResponse, Response as FAResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import asyncio
import logging
import re
import uuid
import secrets
import string
import time
from collections import defaultdict, deque

# Local modules
from auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    JWT_COOKIE_NAME,
    JWT_EXPIRES_HOURS,
)
from crypto_utils import encrypt_str, decrypt_str
from llm_providers import (
    PROVIDERS,
    FALLBACK_MODELS,
    DEFAULT_FALLBACK_MODEL,
    provider_known,
    model_known,
    mask_key,
    public_providers_for_ui,
)
from services.llm_router import (
    build_tier,
    build_fallback_tier,
    chat as router_chat,
    LLMRouterError,
    categorise_exception,
    Tier,
)
from services import ai_discussion_service as ai_svc
from services import scenario_service as scn_svc
from services import synthesis_service as syn_svc
from services import dimensions_catalogue as dims_catalogue
from services import results_render
from services import lifecycle_service as lifecycle
from services import conversation_export
from services import dashboard_summary as dashboard
import psychometric_service

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# --------------------------------------------------------------------------- #
# Mongo
# --------------------------------------------------------------------------- #
mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get("DB_NAME", "soe_tra")]
sessions_coll = db["sessions"]
admin_users_coll = db["admin_users"]
admin_settings_coll = db["admin_settings"]

# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
app = FastAPI(
    title="Transformation Readiness Assessment API",
    description="Backend for the SOE Transformation Readiness Assessment demo.",
    version="0.3.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
api_router = APIRouter(prefix="/api")

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants / domain
# --------------------------------------------------------------------------- #
STAGE_ORDER: List[str] = [
    "identity", "context", "psychometric", "ai-discussion",
    "scenario", "processing", "results",
]
STAGE_SET = set(STAGE_ORDER)
SIXTY_DAYS = timedelta(days=60)
SETTINGS_DOC_ID = "global"

# Rate limits (sliding-window token buckets).
RATE_LIMIT_SESSIONS_MAX = 10
RATE_LIMIT_SESSIONS_WINDOW = 60 * 60  # 1 hour
RATE_LIMIT_LOGIN_MAX = 10
RATE_LIMIT_LOGIN_WINDOW = 15 * 60  # 15 min
RATE_LIMIT_ANSWER_MAX = 60
RATE_LIMIT_ANSWER_WINDOW = 60  # per minute
RATE_LIMIT_AIMSG_MAX = 30
RATE_LIMIT_AIMSG_WINDOW = 60  # per minute
RATE_LIMIT_SCN_AUTOSAVE_MAX = 30
RATE_LIMIT_SCN_AUTOSAVE_WINDOW = 60  # per minute
_sessions_ip_hits: Dict[str, deque] = defaultdict(deque)
_login_ip_hits: Dict[str, deque] = defaultdict(deque)
_answer_ip_hits: Dict[str, deque] = defaultdict(deque)
_aimsg_ip_hits: Dict[str, deque] = defaultdict(deque)
_scn_autosave_hits: Dict[str, deque] = defaultdict(deque)


def _rate_limit_check(bucket: Dict[str, deque], ip: str, max_hits: int, window_sec: int) -> bool:
    now = time.time()
    q = bucket[ip]
    while q and now - q[0] > window_sec:
        q.popleft()
    if len(q) >= max_hits:
        return False
    q.append(now)
    return True


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _generate_resume_code() -> str:
    a = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
    b = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
    return f"{a}-{b}"


async def _unique_resume_code(max_attempts: int = 10) -> str:
    for _ in range(max_attempts):
        code = _generate_resume_code()
        existing = await sessions_coll.find_one({"resume_code": code}, {"_id": 1})
        if not existing:
            return code
    return _generate_resume_code() + "-" + secrets.token_hex(2).upper()


# --------------------------------------------------------------------------- #
# Pydantic models (participant sessions — from Phase 2)
# --------------------------------------------------------------------------- #
class SessionCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    organisation: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, max_length=200)
    consent: bool

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("consent")
    @classmethod
    def _consent_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consent must be accepted (true) to create a session")
        return v


class SessionCreateOut(BaseModel):
    session_id: str
    resume_code: str
    stage: str


class SessionStageUpdateIn(BaseModel):
    stage: Literal[
        "identity", "context", "psychometric", "ai-discussion",
        "scenario", "processing", "results",
    ]


class SessionStageUpdateOut(BaseModel):
    stage: str
    updated_at: str


class SessionResumeOut(BaseModel):
    session_id: str
    stage: str
    participant: Dict[str, Any]


class SessionOut(BaseModel):
    model_config = ConfigDict(extra="allow")  # tolerate future Phase fields
    session_id: str
    resume_code: str
    stage: str
    status: str
    participant: Dict[str, Any]
    answers: List[Any]
    conversation: List[Any]
    scenario_responses: Dict[str, Any]
    deliverable: Optional[Any]
    scores: Optional[Any]
    archived: bool
    created_at: str
    updated_at: str
    completed_at: Optional[str]
    expires_at: Optional[str]
    psychometric: Optional[Dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# Pydantic models (admin)
# --------------------------------------------------------------------------- #
class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class AdminMeOut(BaseModel):
    email: EmailStr
    role: str


class SlotIn(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None  # empty string = clear; missing = keep existing
    label: Optional[str] = None


class SettingsPutIn(BaseModel):
    primary: Optional[SlotIn] = None
    secondary: Optional[SlotIn] = None
    fallback_model: Optional[str] = None


class SettingsTestIn(BaseModel):
    slot: Literal["primary", "secondary", "adhoc"]
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


# --------------------------------------------------------------------------- #
# Auth dependency
# --------------------------------------------------------------------------- #
async def require_admin(request: Request) -> Dict[str, Any]:
    token = request.cookies.get(JWT_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    payload = decode_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return payload


def _is_secure_cookie() -> bool:
    # Behind TLS in Emergent preview; https is the only ingress.
    return True


# --------------------------------------------------------------------------- #
# Routes — public
# --------------------------------------------------------------------------- #
@api_router.get("/")
async def root():
    return {"message": "Transformation Readiness Assessment API"}


@api_router.get("/health")
async def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Routes — participant sessions (Phase 2, unchanged)
# --------------------------------------------------------------------------- #
@api_router.post(
    "/sessions", response_model=SessionCreateOut, status_code=201,
    summary="Create a new assessment session",
)
async def create_session(payload: SessionCreateIn, request: Request):
    ip = _client_ip(request)
    if not _rate_limit_check(_sessions_ip_hits, ip, RATE_LIMIT_SESSIONS_MAX, RATE_LIMIT_SESSIONS_WINDOW):
        raise HTTPException(
            status_code=429,
            detail=f"Too many sessions from this IP. Limit is {RATE_LIMIT_SESSIONS_MAX} per hour.",
        )
    session_id = str(uuid.uuid4())
    resume_code = await _unique_resume_code()
    now = _now_iso()
    doc = {
        "_id": session_id, "session_id": session_id, "resume_code": resume_code,
        "participant": {
            "name": payload.name, "email": str(payload.email),
            "organisation": payload.organisation, "role": payload.role,
        },
        "consent": {"accepted": True, "accepted_at": now},
        "status": "in_progress", "stage": "identity",
        "answers": [], "conversation": [], "scenario_responses": {},
        "deliverable": None, "scores": None, "archived": False,
        "created_at": now, "updated_at": now, "completed_at": None, "expires_at": None,
    }
    await sessions_coll.insert_one(doc)
    logger.info("Created session id=%s stage=%s", session_id, doc["stage"])
    logger.debug("Session participant: %s", doc["participant"])
    return SessionCreateOut(session_id=session_id, resume_code=resume_code, stage=doc["stage"])


@api_router.get("/sessions/resume/{resume_code}", response_model=SessionResumeOut,
                summary="Resume a session by its resume code")
async def resume_session(resume_code: str):
    code = resume_code.strip().upper()
    if len(code) == 8 and "-" not in code:
        code = code[:4] + "-" + code[4:]
    doc = await sessions_coll.find_one({"resume_code": code}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Resume code not found.")
    return SessionResumeOut(session_id=doc["session_id"], stage=doc["stage"], participant=doc["participant"])


@api_router.patch("/sessions/{session_id}/stage", response_model=SessionStageUpdateOut,
                  summary="Update the current stage of a session")
async def update_stage(session_id: str, payload: SessionStageUpdateIn):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0, "stage": 1, "status": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    current_stage = doc["stage"]
    next_stage = payload.stage
    delta = STAGE_ORDER.index(next_stage) - STAGE_ORDER.index(current_stage)
    if delta not in (-1, 0, 1):
        raise HTTPException(
            status_code=400,
            detail=(f"Invalid stage transition '{current_stage}' -> '{next_stage}'. "
                    "Only move one stage forward, stay, or go back one stage."),
        )
    now = _now_iso()
    update: Dict[str, Any] = {"stage": next_stage, "updated_at": now}
    if next_stage == "results":
        update["status"] = "completed"
        update["completed_at"] = now
        update["expires_at"] = (datetime.fromisoformat(now) + SIXTY_DAYS).isoformat()
    await sessions_coll.update_one({"session_id": session_id}, {"$set": update})
    return SessionStageUpdateOut(stage=next_stage, updated_at=now)


@api_router.get("/sessions/{session_id}", response_model=SessionOut,
                summary="Get the current state of a session (participant-safe; no scores)")
async def get_session(session_id: str):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    # Participant-safe: never expose scores, deliverable, or assistant-turn provider internals.
    doc["scores"] = None
    doc["deliverable"] = None
    doc["conversation"] = _public_conversation(doc.get("conversation") or [])
    return SessionOut(**doc)


# --------------------------------------------------------------------------- #
# Routes — psychometric assessment (Phase 4)
# --------------------------------------------------------------------------- #
class PsychometricAnswerIn(BaseModel):
    session_id: str
    item_id: str
    value: int = Field(..., ge=1, le=6)
    response_time_ms: int = Field(..., ge=0)


def _next_expected_item(order: List[str], answered_ids: List[str]) -> Optional[str]:
    """First item in order that has not yet been answered."""
    answered_set = set(answered_ids)
    for iid in order:
        if iid not in answered_set:
            return iid
    return None


def _progress(order: List[str], answered_ids: List[str]) -> Dict[str, Any]:
    answered = len(answered_ids)
    total = len(order) if order else 20
    # current_index is 1-based position of the next unanswered item (capped to total)
    idx = min(answered + 1, total) if answered < total else total
    # Scale counts
    la_total = 12
    ta_total = 8
    la_answered = sum(1 for i in answered_ids if i.startswith("LA"))
    ta_answered = sum(1 for i in answered_ids if i.startswith("TA"))
    return {
        "answered": answered,
        "total": total,
        "current_index_1based": idx,
        "done": answered >= total,
        "scale_counts": {
            "LA": {"answered": la_answered, "total": la_total},
            "TA": {"answered": ta_answered, "total": ta_total},
        },
    }


async def _ensure_psychometric_initialised(session_id: str) -> Dict[str, Any]:
    """Ensure session.psychometric has `order` and `started_at`.
    Idempotent: if already initialised, returns the existing doc.
    """
    doc = await sessions_coll.find_one({"session_id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    psych = doc.get("psychometric") or {}
    if psych.get("order"):
        return doc
    order = psychometric_service.randomised_order()
    now = _now_iso()
    update = {
        "psychometric": {
            "order": order,
            "answers": [],
            "started_at": now,
            "completed_at": None,
        },
        "stage": "psychometric",
        "updated_at": now,
    }
    # Don't clobber any older answers array (shouldn't exist at this point).
    await sessions_coll.update_one({"session_id": session_id}, {"$set": update})
    doc = await sessions_coll.find_one({"session_id": session_id})
    logger.info("Psychometric initialised for session=%s", session_id)
    return doc


@api_router.get(
    "/assessment/psychometric/next",
    summary="Get the next psychometric item for this session",
)
async def psychometric_next(session_id: str):
    doc = await _ensure_psychometric_initialised(session_id)
    psych = doc.get("psychometric") or {}
    order: List[str] = psych.get("order") or []
    answers = psych.get("answers") or []
    answered_ids = [a["item_id"] for a in answers]
    progress = _progress(order, answered_ids)
    next_id = _next_expected_item(order, answered_ids)
    if next_id is None:
        return {"done": True, "progress": progress}
    item = psychometric_service.get_item(next_id)
    if not item:
        raise HTTPException(status_code=500,
                            detail=f"Internal: item {next_id} missing from catalog.")
    return {
        "done": False,
        "item": item,
        "progress": progress,
    }


@api_router.get(
    "/assessment/psychometric/progress",
    summary="Get psychometric progress for this session",
)
async def psychometric_progress(session_id: str):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    psych = doc.get("psychometric") or {}
    order = psych.get("order") or []
    answered_ids = [a["item_id"] for a in (psych.get("answers") or [])]
    return _progress(order, answered_ids)


@api_router.post(
    "/assessment/psychometric/answer",
    summary="Submit an answer for the current psychometric item",
)
async def psychometric_answer(payload: PsychometricAnswerIn, request: Request):
    ip = _client_ip(request)
    if not _rate_limit_check(_answer_ip_hits, ip, RATE_LIMIT_ANSWER_MAX, RATE_LIMIT_ANSWER_WINDOW):
        raise HTTPException(status_code=429, detail="Too many answers. Please slow down.")

    # Validate item_id is known
    if not psychometric_service.get_item(payload.item_id):
        raise HTTPException(status_code=422, detail=f"Unknown item_id '{payload.item_id}'.")

    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    psych = doc.get("psychometric") or {}
    order: List[str] = psych.get("order") or []
    if not order:
        # Client hasn't initialised — do it now (e.g. POST without GET /next first).
        doc = await _ensure_psychometric_initialised(payload.session_id)
        psych = doc.get("psychometric") or {}
        order = psych.get("order") or []

    answers: List[Dict[str, Any]] = psych.get("answers") or []
    answered_ids = [a["item_id"] for a in answers]

    # Idempotency window: if the last answer was the same item_id within 2s and same value, 200 w/o dupe
    if answers:
        last = answers[-1]
        if last.get("item_id") == payload.item_id and last.get("value") == payload.value:
            try:
                last_t = datetime.fromisoformat(last["answered_at"])
                delta = (datetime.now(timezone.utc) - last_t).total_seconds()
                if 0 <= delta <= 2.0:
                    logger.debug("Idempotent duplicate for item=%s within 2s", payload.item_id)
                    return {
                        "progress": _progress(order, answered_ids),
                        "done": _progress(order, answered_ids)["done"],
                        "idempotent": True,
                    }
            except Exception:
                pass

    # Already answered (no back button) → 409 (unless within idempotency window above)
    if payload.item_id in answered_ids:
        raise HTTPException(status_code=409, detail={
            "message": "Item already answered.",
            "item_id": payload.item_id,
        })

    # Out-of-order guard: item_id must match the next expected
    expected = _next_expected_item(order, answered_ids)
    if expected != payload.item_id:
        raise HTTPException(status_code=409, detail={
            "message": "Out-of-order answer.",
            "expected_item_id": expected,
            "received_item_id": payload.item_id,
        })

    # Append answer
    now = _now_iso()
    new_answer = {
        "item_id": payload.item_id,
        "value": payload.value,
        "response_time_ms": payload.response_time_ms,
        "answered_at": now,
    }
    answers.append(new_answer)
    psych["answers"] = answers

    update: Dict[str, Any] = {
        "psychometric.answers": answers,
        "updated_at": now,
    }

    # If this was the 20th answer, finalise + score
    if len(answers) >= len(order):
        update["psychometric.completed_at"] = now
        # Build a synthetic session doc for scoring (only needs psychometric.answers)
        score_payload = psychometric_service.score({"psychometric": {"answers": answers}})
        update["scores"] = {**(doc.get("scores") or {}), "psychometric": score_payload}

    await sessions_coll.update_one({"session_id": payload.session_id}, {"$set": update})
    progress = _progress(order, [a["item_id"] for a in answers])
    logger.info("Psychometric answer session=%s item=%s (%d/%d)",
                payload.session_id, payload.item_id, progress["answered"], progress["total"])
    return {"progress": progress, "done": progress["done"]}


# --------------------------------------------------------------------------- #
# Routes — AI Fluency Discussion (Phase 5)
# --------------------------------------------------------------------------- #
class AIDiscStartIn(BaseModel):
    session_id: str


class AIDiscMessageIn(BaseModel):
    session_id: str
    content: str = Field(..., min_length=1, max_length=ai_svc.MAX_USER_INPUT_CHARS)


class AIDiscCompleteIn(BaseModel):
    session_id: str


def _public_conversation(conversation: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip developer notes and provider/model internals from the participant view."""
    out = []
    for t in conversation or []:
        if t.get("role") in ("user", "assistant") and t.get("kind") != "dev":
            out.append({
                "turn": t.get("turn"),
                "role": t.get("role"),
                "content": t.get("content", ""),
                "timestamp": t.get("timestamp"),
            })
    return out


def _user_turn_count(conversation: List[Dict[str, Any]]) -> int:
    return sum(1 for t in (conversation or []) if t.get("role") == "user" and t.get("kind") != "dev")


async def _build_session_tiers() -> List[Tier]:
    """Load admin_settings and build a 3-tier cascade (primary → secondary → Emergent fallback)."""
    doc = await admin_settings_coll.find_one({"_id": SETTINGS_DOC_ID})
    return await ai_svc.build_tiers_from_admin_settings(doc)


def _participant_ctx_for(doc: Dict[str, Any]) -> str:
    participant = doc.get("participant") or {}
    psych_scores = ((doc.get("scores") or {}).get("psychometric")) or None
    return ai_svc.build_participant_context(participant, psych_scores)


@api_router.post("/assessment/ai-discussion/start",
                 summary="Start the AI Fluency Discussion (produces the opening assistant turn)")
async def ai_discussion_start(payload: AIDiscStartIn, request: Request):
    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Gate: must be at ai-discussion stage, not already completed
    if doc.get("stage") != "ai-discussion":
        raise HTTPException(status_code=409, detail={
            "message": "AI discussion not yet unlocked. Complete the psychometric first.",
            "current_stage": doc.get("stage"),
        })
    ai_disc = doc.get("ai_discussion") or {}
    if ai_disc.get("status") == "completed":
        # Idempotent: just return the existing state.
        return {
            "messages": _public_conversation(doc.get("conversation") or []),
            "user_turn_count": _user_turn_count(doc.get("conversation") or []),
            "can_submit": False,
            "at_cap": True,
            "status": "completed",
        }
    if ai_disc.get("status") == "in_progress":
        # Already started — return current state instead of duplicating the opener.
        return {
            "messages": _public_conversation(doc.get("conversation") or []),
            "user_turn_count": _user_turn_count(doc.get("conversation") or []),
            "can_submit": True,
            "at_cap": _user_turn_count(doc.get("conversation") or []) >= ai_svc.MAX_USER_TURNS,
            "status": "in_progress",
        }

    # First start — generate opener, call the LLM
    opener = ai_svc.select_opener(payload.session_id)
    participant_ctx = _participant_ctx_for(doc)
    tiers = await _build_session_tiers()
    now = _now_iso()

    # Opener: we don't call the model for the opener — the probe text is verbatim from Doc 21.
    # Just persist it as the assistant's opening turn (turn=0).
    opening_turn = {
        "turn": 0,
        "role": "assistant",
        "content": opener,
        "timestamp": now,
        "provider": "doc21",
        "model": "doc21-opener",
        "latency_ms": 0,
        "fallbacks_tried": 0,
    }

    # Persist
    update = {
        "conversation": [opening_turn],
        "ai_discussion": {
            "started_at": now,
            "completed_at": None,
            "status": "in_progress",
            "user_turn_count": 0,
            "exit_reason": None,
            "opener": opener,
        },
        "updated_at": now,
    }
    await sessions_coll.update_one({"session_id": payload.session_id}, {"$set": update})
    logger.info("AI-Disc start session=%s opener_idx=%d tiers=%d",
                payload.session_id, ai_svc.OPENING_PROBES.index(opener), len(tiers))

    return {
        "messages": _public_conversation([opening_turn]),
        "user_turn_count": 0,
        "can_submit": True,
        "at_cap": False,
        "status": "in_progress",
    }


@api_router.post("/assessment/ai-discussion/message",
                 summary="Send a user message in the AI Fluency Discussion")
async def ai_discussion_message(payload: AIDiscMessageIn, request: Request):
    ip = _client_ip(request)
    if not _rate_limit_check(_aimsg_ip_hits, ip, RATE_LIMIT_AIMSG_MAX, RATE_LIMIT_AIMSG_WINDOW):
        raise HTTPException(status_code=429, detail="Too many messages. Please slow down.")

    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    ai_disc = doc.get("ai_discussion") or {}
    if ai_disc.get("status") != "in_progress":
        raise HTTPException(status_code=409, detail={
            "message": "AI discussion is not in progress.",
            "status": ai_disc.get("status"),
        })
    conversation = list(doc.get("conversation") or [])
    turn_count = _user_turn_count(conversation)
    if turn_count >= ai_svc.MAX_USER_TURNS:
        raise HTTPException(status_code=409, detail={
            "message": "User turn cap reached.",
            "user_turn_count": turn_count,
        })

    # Append user turn
    user_turn_number = turn_count + 1
    now = _now_iso()
    user_turn = {
        "turn": user_turn_number,
        "role": "user",
        "content": payload.content.strip(),
        "timestamp": now,
    }
    conversation.append(user_turn)

    # Is this the final user turn?
    final_turn = user_turn_number >= ai_svc.MAX_USER_TURNS

    # Build messages for router
    participant_ctx = _participant_ctx_for(doc)
    router_messages = ai_svc.build_messages_for_turn(conversation, participant_ctx, final_turn=final_turn)
    tiers = await _build_session_tiers()

    try:
        result = await router_chat(
            messages=router_messages,
            tiers=tiers,
            system=ai_svc.SYSTEM_PROMPT,
            max_tokens=ai_svc.MAX_OUTPUT_TOKENS_PER_TURN,
            purpose="ai-fluency-turn",
        )
    except LLMRouterError as exc:
        # Persist the user turn even if the model failed — we can retry
        await sessions_coll.update_one(
            {"session_id": payload.session_id},
            {"$set": {
                "conversation": conversation,
                "ai_discussion": {**ai_disc, "status": "failed",
                                  "user_turn_count": user_turn_number,
                                  "last_error": [f.category for f in exc.failures]},
                "updated_at": now,
            }},
        )
        raise HTTPException(status_code=503, detail={
            "message": "We couldn't reach the model. You can retry in a moment.",
            "retry": True,
            "category": [f.category for f in exc.failures],
        })

    # Persist assistant turn
    assistant_turn = {
        "turn": user_turn_number,
        "role": "assistant",
        "content": result.get("text") or "",
        "timestamp": _now_iso(),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "latency_ms": result.get("latency_ms"),
        "fallbacks_tried": result.get("fallbacks_tried", 0),
    }
    conversation.append(assistant_turn)

    update: Dict[str, Any] = {
        "conversation": conversation,
        "ai_discussion.user_turn_count": user_turn_number,
        "ai_discussion.status": "in_progress",
        "updated_at": _now_iso(),
    }

    status_after = "in_progress"
    # If that was the 12th user turn, run scoring and mark completed
    if final_turn:
        score_result = await ai_svc.run_scoring(conversation, participant_ctx, tiers)
        score_payload: Dict[str, Any] = {}
        if score_result.get("ok"):
            sp = score_result["payload"]["ai_fluency"]
            sp["_meta"] = {
                "provider": score_result.get("provider"),
                "model": score_result.get("model"),
                "fallbacks_tried": score_result.get("fallbacks_tried", 0),
            }
            score_payload = sp
        else:
            score_payload = {
                "_raw": score_result.get("raw"),
                "_error": score_result.get("error"),
                "scoring_error": True,
            }
        scores = doc.get("scores") or {}
        scores["ai_fluency"] = score_payload
        update["scores"] = scores
        update["ai_discussion.status"] = "completed"
        update["ai_discussion.completed_at"] = _now_iso()
        update["ai_discussion.exit_reason"] = "turn_cap"
        status_after = "completed"

    await sessions_coll.update_one({"session_id": payload.session_id}, {"$set": update})
    logger.info("AI-Disc turn session=%s turn=%d provider=%s model=%s latency=%sms status_after=%s",
                payload.session_id, user_turn_number,
                assistant_turn.get("provider"), assistant_turn.get("model"),
                assistant_turn.get("latency_ms"), status_after)
    logger.debug("AI-Disc content user=%r assistant=%r",
                 user_turn["content"][:80], assistant_turn["content"][:80])

    return {
        "messages": _public_conversation(conversation),
        "user_turn_count": user_turn_number,
        "at_cap": user_turn_number >= ai_svc.MAX_USER_TURNS,
        "can_submit": (status_after == "in_progress") and (user_turn_number < ai_svc.MAX_USER_TURNS),
        "status": status_after,
    }


@api_router.post("/assessment/ai-discussion/complete",
                 summary="End the AI discussion early and finalise scoring")
async def ai_discussion_complete(payload: AIDiscCompleteIn):
    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    ai_disc = doc.get("ai_discussion") or {}
    if ai_disc.get("status") == "completed":
        return {
            "status": "completed",
            "user_turn_count": _user_turn_count(doc.get("conversation") or []),
        }
    if ai_disc.get("status") not in ("in_progress", "failed"):
        raise HTTPException(status_code=409, detail="AI discussion has not started.")
    conversation = list(doc.get("conversation") or [])
    turn_count = _user_turn_count(conversation)
    if turn_count < 3:
        raise HTTPException(status_code=409, detail={
            "message": "Please complete at least three exchanges before ending.",
            "user_turn_count": turn_count,
        })

    # Run scoring now
    participant_ctx = _participant_ctx_for(doc)
    tiers = await _build_session_tiers()
    score_result = await ai_svc.run_scoring(conversation, participant_ctx, tiers)
    if score_result.get("ok"):
        sp = score_result["payload"]["ai_fluency"]
        sp["_meta"] = {
            "provider": score_result.get("provider"),
            "model": score_result.get("model"),
            "fallbacks_tried": score_result.get("fallbacks_tried", 0),
        }
        score_payload = sp
    else:
        score_payload = {
            "_raw": score_result.get("raw"),
            "_error": score_result.get("error"),
            "scoring_error": True,
        }
    scores = doc.get("scores") or {}
    scores["ai_fluency"] = score_payload
    now = _now_iso()
    await sessions_coll.update_one({"session_id": payload.session_id}, {"$set": {
        "scores": scores,
        "ai_discussion.status": "completed",
        "ai_discussion.completed_at": now,
        "ai_discussion.exit_reason": "participant_exit",
        "updated_at": now,
    }})
    logger.info("AI-Disc complete-early session=%s turns=%d", payload.session_id, turn_count)
    return {"status": "completed", "user_turn_count": turn_count}


@api_router.get("/assessment/ai-discussion/state",
                summary="Get the AI discussion state for this session")
async def ai_discussion_state(session_id: str):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    ai_disc = doc.get("ai_discussion") or {}
    status = ai_disc.get("status")
    turn_count = _user_turn_count(doc.get("conversation") or [])
    return {
        "status": status,
        "messages": _public_conversation(doc.get("conversation") or []),
        "user_turn_count": turn_count,
        "at_cap": turn_count >= ai_svc.MAX_USER_TURNS,
        "can_submit": (status == "in_progress") and (turn_count < ai_svc.MAX_USER_TURNS),
    }


@api_router.post("/assessment/ai-discussion/retry",
                 summary="Retry the last assistant turn after a router failure")
async def ai_discussion_retry(payload: AIDiscCompleteIn):
    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    ai_disc = doc.get("ai_discussion") or {}
    conversation = list(doc.get("conversation") or [])
    if ai_disc.get("status") != "failed":
        raise HTTPException(status_code=409, detail="Nothing to retry — discussion is not in failed state.")
    # Last turn must be a user turn awaiting reply
    if not conversation or conversation[-1].get("role") != "user":
        raise HTTPException(status_code=409, detail="No awaiting user turn to retry.")
    turn_count = _user_turn_count(conversation)
    final_turn = turn_count >= ai_svc.MAX_USER_TURNS
    participant_ctx = _participant_ctx_for(doc)
    router_messages = ai_svc.build_messages_for_turn(conversation, participant_ctx, final_turn=final_turn)
    tiers = await _build_session_tiers()
    try:
        result = await router_chat(
            messages=router_messages,
            tiers=tiers,
            system=ai_svc.SYSTEM_PROMPT,
            max_tokens=ai_svc.MAX_OUTPUT_TOKENS_PER_TURN,
            purpose="ai-fluency-turn-retry",
        )
    except LLMRouterError as exc:
        raise HTTPException(status_code=503, detail={
            "message": "Still cannot reach the model. Try again shortly.",
            "category": [f.category for f in exc.failures],
        })
    assistant_turn = {
        "turn": turn_count,
        "role": "assistant",
        "content": result.get("text") or "",
        "timestamp": _now_iso(),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "latency_ms": result.get("latency_ms"),
        "fallbacks_tried": result.get("fallbacks_tried", 0),
    }
    conversation.append(assistant_turn)
    update = {
        "conversation": conversation,
        "ai_discussion.status": "in_progress",
        "ai_discussion.last_error": None,
        "updated_at": _now_iso(),
    }
    await sessions_coll.update_one({"session_id": payload.session_id}, {"$set": update})
    return {
        "messages": _public_conversation(conversation),
        "user_turn_count": turn_count,
        "at_cap": final_turn,
        "can_submit": not final_turn,
        "status": "in_progress",
    }




# --------------------------------------------------------------------------- #
# Routes — Strategic Scenario (Phase 6)
# --------------------------------------------------------------------------- #
SCENARIO_PHASE_ORDER = ["read", "part1", "curveball", "part2", "done"]


class ScnStartIn(BaseModel):
    session_id: str


class ScnAdvanceIn(BaseModel):
    session_id: str
    from_phase: Literal["read", "part1", "curveball", "part2"]
    to_phase: Literal["part1", "curveball", "part2", "done"]
    payload: Optional[Dict[str, Any]] = None


class ScnAutosaveIn(BaseModel):
    session_id: str
    phase: Literal["part1", "part2"]
    partial: Dict[str, Any]


def _scn_content_for_phase(phase: str) -> Dict[str, Any]:
    if phase == "read":
        return scn_svc.get_read_content()
    if phase == "part1":
        return scn_svc.get_part1()
    if phase == "curveball":
        return scn_svc.get_curveball()
    if phase == "part2":
        return scn_svc.get_part2()
    return {}


def _scn_public_state(doc: Dict[str, Any]) -> Dict[str, Any]:
    scn = doc.get("scenario") or {}
    phase = scn.get("phase")
    return {
        "status": scn.get("status"),
        "phase": phase,
        "phase_entered_at": scn.get("phase_entered_at") or {},
        "time_on_phase_ms": scn.get("time_on_phase_ms") or {},
        "part1_response": scn.get("part1_response") or {},
        "part2_response": scn.get("part2_response") or {},
        "content": _scn_content_for_phase(phase) if phase else {},
    }


def _validate_trio(payload: Any) -> Dict[str, str]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="payload must be an object with q1,q2,q3")
    out: Dict[str, str] = {}
    for k in ("q1", "q2", "q3"):
        v = payload.get(k, "")
        if not isinstance(v, str):
            raise HTTPException(status_code=422, detail=f"payload.{k} must be a string")
        v = v.strip()
        if not v:
            raise HTTPException(status_code=422, detail=f"payload.{k} must not be empty")
        if len(v) > scn_svc.MAX_ANSWER_CHARS:
            raise HTTPException(status_code=422,
                                detail=f"payload.{k} exceeds {scn_svc.MAX_ANSWER_CHARS} characters")
        out[k] = v
    return out


async def _scn_build_tiers():
    doc = await admin_settings_coll.find_one({"_id": SETTINGS_DOC_ID})
    return await ai_svc.build_tiers_from_admin_settings(doc)


@api_router.get("/assessment/scenario/state",
                summary="Get the scenario state for this session")
async def scenario_state(session_id: str):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    return _scn_public_state(doc)


@api_router.post("/assessment/scenario/start",
                 summary="Start the strategic scenario (enters phase 'read')")
async def scenario_start(payload: ScnStartIn):
    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    if doc.get("stage") != "scenario":
        raise HTTPException(status_code=409, detail={
            "message": "Scenario not yet unlocked. Complete the AI Fluency discussion first.",
            "current_stage": doc.get("stage"),
        })
    scn = doc.get("scenario") or {}
    if scn.get("status") == "completed":
        return _scn_public_state(doc)
    if scn.get("status") == "in_progress":
        return _scn_public_state(doc)

    now = _now_iso()
    update = {
        "scenario": {
            "started_at": now,
            "completed_at": None,
            "status": "in_progress",
            "phase": "read",
            "phase_entered_at": {"read": now},
            "part1_response": {},
            "part2_response": {},
            "time_on_phase_ms": {},
            "exit_reason": None,
        },
        "updated_at": now,
    }
    await sessions_coll.update_one({"session_id": payload.session_id}, {"$set": update})
    doc = await sessions_coll.find_one({"session_id": payload.session_id}, {"_id": 0})
    logger.info("Scenario start session=%s", payload.session_id)
    return _scn_public_state(doc)


@api_router.post("/assessment/scenario/advance",
                 summary="Advance the scenario phase")
async def scenario_advance(payload: ScnAdvanceIn):
    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    scn = doc.get("scenario") or {}
    if scn.get("status") != "in_progress":
        raise HTTPException(status_code=409, detail="Scenario not in progress.")
    current = scn.get("phase")
    if current != payload.from_phase:
        raise HTTPException(status_code=409, detail={
            "message": "Out-of-order advance.",
            "expected_from_phase": current,
            "received_from_phase": payload.from_phase,
        })
    # Strict forward transitions only
    try:
        i_from = SCENARIO_PHASE_ORDER.index(payload.from_phase)
        i_to = SCENARIO_PHASE_ORDER.index(payload.to_phase)
    except ValueError:
        raise HTTPException(status_code=422, detail="unknown phase")
    if i_to != i_from + 1:
        raise HTTPException(status_code=409, detail={
            "message": "Invalid phase transition. Must advance exactly one step forward.",
        })

    # Payload validation per-phase
    persist_part1 = None
    persist_part2 = None
    if payload.from_phase == "part1":
        persist_part1 = _validate_trio(payload.payload)
    if payload.from_phase == "part2":
        persist_part2 = _validate_trio(payload.payload)

    now = _now_iso()
    entered_at = (scn.get("phase_entered_at") or {}).get(payload.from_phase)
    delta_ms = 0
    if entered_at:
        try:
            t0 = datetime.fromisoformat(entered_at)
            delta_ms = max(0, int((datetime.now(timezone.utc) - t0).total_seconds() * 1000))
        except Exception:
            delta_ms = 0

    time_on_phase = dict(scn.get("time_on_phase_ms") or {})
    time_on_phase[payload.from_phase] = delta_ms
    phase_entered_at = dict(scn.get("phase_entered_at") or {})
    phase_entered_at[payload.to_phase] = now

    set_fields: Dict[str, Any] = {
        "scenario.phase": payload.to_phase,
        "scenario.phase_entered_at": phase_entered_at,
        "scenario.time_on_phase_ms": time_on_phase,
        "updated_at": now,
    }
    if persist_part1 is not None:
        set_fields["scenario.part1_response"] = persist_part1
    if persist_part2 is not None:
        set_fields["scenario.part2_response"] = persist_part2

    # End-of-scenario? (advancing from part2 to done)
    if payload.from_phase == "part2":
        # Pull latest in case of autosaves; then ensure the payload values overwrite
        current_part1 = (scn.get("part1_response") or {})
        tiers = await _scn_build_tiers()
        score_result = await scn_svc.run_scoring(current_part1, persist_part2, tiers)
        if score_result.get("ok"):
            sa = score_result["payload"]["scenario_analysis"]
            sa["_meta"] = {
                "provider": score_result.get("provider"),
                "model": score_result.get("model"),
                "fallbacks_tried": score_result.get("fallbacks_tried", 0),
            }
            score_payload = sa
        else:
            score_payload = {
                "_raw": score_result.get("raw"),
                "_error": score_result.get("error"),
                "scoring_error": True,
            }
        scores = dict(doc.get("scores") or {})
        scores["scenario"] = score_payload
        set_fields["scores"] = scores
        set_fields["scenario.status"] = "completed"
        set_fields["scenario.completed_at"] = now
        # Advance the session stage to "processing" (the next stage, per existing STAGE_ORDER)
        set_fields["stage"] = "processing"

    await sessions_coll.update_one({"session_id": payload.session_id}, {"$set": set_fields})
    doc = await sessions_coll.find_one({"session_id": payload.session_id}, {"_id": 0})
    logger.info("Scenario advance session=%s from=%s to=%s delta_ms=%d",
                payload.session_id, payload.from_phase, payload.to_phase, delta_ms)
    return _scn_public_state(doc)


@api_router.post("/assessment/scenario/autosave",
                 summary="Autosave partial answers in the current writing phase")
async def scenario_autosave(payload: ScnAutosaveIn, request: Request):
    ip = _client_ip(request)
    if not _rate_limit_check(_scn_autosave_hits, ip, RATE_LIMIT_SCN_AUTOSAVE_MAX, RATE_LIMIT_SCN_AUTOSAVE_WINDOW):
        raise HTTPException(status_code=429, detail="Too many autosave writes. Please slow down.")

    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    scn = doc.get("scenario") or {}
    if scn.get("status") != "in_progress":
        raise HTTPException(status_code=409, detail="Scenario not in progress.")
    if scn.get("phase") != payload.phase:
        raise HTTPException(status_code=409, detail={
            "message": "Autosave phase mismatch.",
            "expected_phase": scn.get("phase"),
            "received_phase": payload.phase,
        })
    partial = payload.partial or {}
    allowed_keys = {"q1", "q2", "q3"}
    extra = set(partial.keys()) - allowed_keys
    if extra:
        raise HTTPException(status_code=422, detail=f"Unknown keys in partial: {sorted(extra)}")

    # Merge into existing response trio (strings only, trimmed, capped)
    field = "scenario.part1_response" if payload.phase == "part1" else "scenario.part2_response"
    current = dict(scn.get(
        "part1_response" if payload.phase == "part1" else "part2_response"
    ) or {})
    for k, v in partial.items():
        if v is None:
            continue
        if not isinstance(v, str):
            raise HTTPException(status_code=422, detail=f"partial.{k} must be a string")
        if len(v) > scn_svc.MAX_ANSWER_CHARS:
            raise HTTPException(status_code=422,
                                detail=f"partial.{k} exceeds {scn_svc.MAX_ANSWER_CHARS} characters")
        current[k] = v
    now = _now_iso()
    await sessions_coll.update_one(
        {"session_id": payload.session_id},
        {"$set": {field: current, "updated_at": now}},
    )
    logger.debug("Scenario autosave session=%s phase=%s keys=%s",
                 payload.session_id, payload.phase, sorted(partial.keys()))
    return {"saved_at": now}


# --------------------------------------------------------------------------- #
# Routes — Processing / Synthesis / Results (Phase 7)
# --------------------------------------------------------------------------- #
SYNTHESIS_STUCK_AFTER_SEC = 120  # restart if in_progress without updates for 2 min


class ProcessingStartIn(BaseModel):
    session_id: str


async def _syn_build_tiers() -> List[Tier]:
    doc = await admin_settings_coll.find_one({"_id": SETTINGS_DOC_ID})
    return await ai_svc.build_tiers_from_admin_settings(doc)


async def _run_synthesis_task(session_id: str) -> None:
    """Background worker: runs the synthesis LLM call and writes deliverable.
    Always terminal — sets synthesis.status to 'completed' or 'failed'."""
    try:
        doc = await sessions_coll.find_one({"session_id": session_id})
        if not doc:
            logger.warning("Synthesis worker: session %s vanished", session_id)
            return
        tiers = await _syn_build_tiers()
        result = await syn_svc.run_synthesis(doc, tiers)
        now = _now_iso()
        if result.get("ok"):
            annotated = syn_svc.annotate_deliverable(result["payload"])
            completed_at = now
            expires_at = (datetime.fromisoformat(now) + SIXTY_DAYS).isoformat()
            update = {
                "deliverable": annotated,
                "synthesis.status": "completed",
                "synthesis.completed_at": now,
                "synthesis.provider": result.get("provider"),
                "synthesis.model": result.get("model"),
                "synthesis.fallbacks_tried": result.get("fallbacks_tried", 0),
                "stage": "results",
                "status": "completed",
                "completed_at": completed_at,
                "expires_at": expires_at,
                "updated_at": now,
            }
            await sessions_coll.update_one({"session_id": session_id}, {"$set": update})
            logger.info(
                "Synthesis completed session=%s provider=%s model=%s fallbacks=%d",
                session_id, result.get("provider"), result.get("model"),
                result.get("fallbacks_tried", 0),
            )
        else:
            update = {
                "deliverable": {
                    "scoring_error": True,
                    "_error": result.get("error"),
                    "_raw": result.get("raw"),
                },
                "synthesis.status": "failed",
                "synthesis.completed_at": now,
                "synthesis.error": result.get("error"),
                "updated_at": now,
            }
            await sessions_coll.update_one({"session_id": session_id}, {"$set": update})
            logger.warning("Synthesis failed session=%s error=%s", session_id, result.get("error"))
    except Exception as exc:  # pragma: no cover — safety net
        logger.exception("Synthesis worker crashed session=%s: %s", session_id, exc)
        try:
            await sessions_coll.update_one(
                {"session_id": session_id},
                {"$set": {
                    "synthesis.status": "failed",
                    "synthesis.error": f"worker_crashed: {exc}",
                    "synthesis.completed_at": _now_iso(),
                    "updated_at": _now_iso(),
                }},
            )
        except Exception:
            pass


def _syn_is_stuck(synthesis: Dict[str, Any]) -> bool:
    if (synthesis or {}).get("status") != "in_progress":
        return False
    started = (synthesis or {}).get("started_at")
    if not started:
        return False
    try:
        t0 = datetime.fromisoformat(started)
        delta = (datetime.now(timezone.utc) - t0).total_seconds()
        return delta > SYNTHESIS_STUCK_AFTER_SEC
    except Exception:
        return False


@api_router.post("/assessment/processing/start",
                 summary="Kick off synthesis; returns 202 + poll URL")
async def processing_start(payload: ProcessingStartIn):
    doc = await sessions_coll.find_one({"session_id": payload.session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    if doc.get("stage") not in ("processing", "results"):
        raise HTTPException(status_code=409, detail={
            "message": "Synthesis cannot start yet. Complete the scenario first.",
            "current_stage": doc.get("stage"),
        })

    # Guardrail: required score inputs must be present.
    scores = doc.get("scores") or {}
    missing = [k for k in ("psychometric", "ai_fluency", "scenario") if not scores.get(k)]
    if missing:
        raise HTTPException(status_code=409, detail={
            "message": "Synthesis cannot run: missing score blocks.",
            "missing": missing,
        })

    synthesis = doc.get("synthesis") or {}
    status = synthesis.get("status")

    # Already completed → return 200 with same shape
    if status == "completed":
        return {
            "status": "completed",
            "started_at": synthesis.get("started_at"),
            "completed_at": synthesis.get("completed_at"),
            "poll_url": f"/api/assessment/processing/state?session_id={payload.session_id}",
        }

    # In-progress + fresh → idempotent 202
    if status == "in_progress" and not _syn_is_stuck(synthesis):
        return JSONResponse(
            status_code=202,
            content={
                "status": "in_progress",
                "started_at": synthesis.get("started_at"),
                "poll_url": f"/api/assessment/processing/state?session_id={payload.session_id}",
            },
        )

    # Start (or restart) the job
    now = _now_iso()
    await sessions_coll.update_one(
        {"session_id": payload.session_id},
        {"$set": {
            "stage": "processing",
            "synthesis.status": "in_progress",
            "synthesis.started_at": now,
            "synthesis.completed_at": None,
            "synthesis.error": None,
            "updated_at": now,
        }},
    )
    # Fire-and-forget coroutine — survives the response
    asyncio.create_task(_run_synthesis_task(payload.session_id))
    logger.info("Synthesis started session=%s", payload.session_id)
    return JSONResponse(
        status_code=202,
        content={
            "status": "in_progress",
            "started_at": now,
            "poll_url": f"/api/assessment/processing/state?session_id={payload.session_id}",
        },
    )


@api_router.get("/assessment/processing/state",
                summary="Poll synthesis state (no deliverable body)")
async def processing_state(session_id: str):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    syn = doc.get("synthesis") or {}
    return {
        "status": syn.get("status"),   # "in_progress" | "completed" | "failed" | None
        "started_at": syn.get("started_at"),
        "completed_at": syn.get("completed_at"),
        "error": syn.get("error"),
    }


@api_router.get("/assessment/results",
                summary="Return the synthesised participant deliverable (gated by synthesis.status)")
async def get_results(session_id: str):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    syn = doc.get("synthesis") or {}
    if syn.get("status") != "completed":
        raise HTTPException(status_code=409, detail={
            "message": "Synthesis not yet complete.",
            "synthesis_status": syn.get("status"),
        })
    deliverable = doc.get("deliverable") or {}
    if deliverable.get("scoring_error"):
        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "message": "The synthesis could not be produced. An assessor will review your session.",
                "participant": {
                    "first_name": (doc.get("participant") or {}).get("name", "").split(" ", 1)[0] or "Participant",
                },
                "scoring_error": True,
            },
        )
    self_awareness = syn_svc.compute_self_awareness_accuracy(doc)
    return {
        "status": "ok",
        "participant": {
            "first_name": (doc.get("participant") or {}).get("name", "").split(" ", 1)[0] or "Participant",
            "organisation": (doc.get("participant") or {}).get("organisation"),
            "role": (doc.get("participant") or {}).get("role"),
        },
        "completed_at": doc.get("completed_at"),
        "resume_code": doc.get("resume_code"),
        "deliverable": deliverable,
        "self_awareness": self_awareness,
        "strategic_scenario_scores": (doc.get("scores") or {}).get("scenario"),
        "dimensions": dims_catalogue.as_public_dicts(),
    }


@api_router.get("/assessment/results/download",
                summary="Download the deliverable as PDF or Markdown")
async def download_results(session_id: str, format: Literal["pdf", "markdown"] = "pdf"):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    syn = doc.get("synthesis") or {}
    if syn.get("status") != "completed":
        raise HTTPException(status_code=409, detail={
            "message": "Synthesis not yet complete.",
            "synthesis_status": syn.get("status"),
        })
    deliverable = doc.get("deliverable") or {}
    if deliverable.get("scoring_error"):
        raise HTTPException(status_code=409, detail={
            "message": "The synthesis is not available for download. An assessor will review your session.",
        })

    self_awareness = syn_svc.compute_self_awareness_accuracy(doc)
    context = results_render.build_context(doc, deliverable, self_awareness)

    first_name = context["participant"]["first_name"]
    if format == "pdf":
        pdf_bytes = results_render.render_pdf(context)
        filename = results_render.safe_filename(first_name, "pdf")
        return FAResponse(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    # markdown
    md_str = results_render.render_markdown(context)
    filename = results_render.safe_filename(first_name, "md")
    return FAResponse(
        content=md_str,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Routes — admin auth
# --------------------------------------------------------------------------- #
admin_router = APIRouter(prefix="/admin")


@admin_router.post("/auth/login", summary="Admin login (sets HTTP-only cookie)")
async def admin_login(payload: AdminLoginIn, request: Request, response: Response):
    ip = _client_ip(request)
    if not _rate_limit_check(_login_ip_hits, ip, RATE_LIMIT_LOGIN_MAX, RATE_LIMIT_LOGIN_WINDOW):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please wait and try again.")
    email = str(payload.email).lower().strip()
    user = await admin_users_coll.find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        # Generic error — do not leak whether email exists
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    token = create_access_token(subject=email, role=user.get("role", "admin"))
    response.set_cookie(
        key=JWT_COOKIE_NAME, value=token,
        httponly=True, secure=_is_secure_cookie(), samesite="lax",
        max_age=JWT_EXPIRES_HOURS * 60 * 60, path="/",
    )
    await admin_users_coll.update_one(
        {"email": email}, {"$set": {"last_login_at": _now_iso(), "updated_at": _now_iso()}}
    )
    logger.info("Admin login succeeded for user=%s", email)
    return {"email": email, "role": user.get("role", "admin")}


@admin_router.post("/auth/logout", summary="Admin logout (clears cookie)")
async def admin_logout(response: Response):
    response.delete_cookie(JWT_COOKIE_NAME, path="/")
    return {"ok": True}


@admin_router.get("/auth/me", response_model=AdminMeOut, summary="Current admin identity")
async def admin_me(current=Depends(require_admin)):
    return AdminMeOut(email=current["sub"], role=current.get("role", "admin"))


# --------------------------------------------------------------------------- #
# Routes — admin settings
# --------------------------------------------------------------------------- #
def _load_settings_doc_sync(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Shape normaliser for display."""
    if not doc:
        return {
            "primary": None, "secondary": None,
            "fallback_model": DEFAULT_FALLBACK_MODEL,
            "updated_at": None, "updated_by": None,
        }
    out = {k: v for k, v in doc.items() if k != "_id"}
    out.setdefault("fallback_model", DEFAULT_FALLBACK_MODEL)
    return out


def _public_slot(slot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Strip encrypted key, return a masked hint instead."""
    if not slot:
        return None
    key_enc = slot.get("api_key_encrypted")
    has_key = bool(key_enc)
    key_hint = ""
    if has_key:
        try:
            plain = decrypt_str(key_enc)
            key_hint = mask_key(plain) if plain else ""
        except Exception:
            key_hint = ""
    return {
        "provider": slot.get("provider"),
        "model": slot.get("model"),
        "label": slot.get("label"),
        "has_key": has_key,
        "key_hint": key_hint,
        "updated_at": slot.get("updated_at"),
    }


@admin_router.get("/settings", summary="Get admin LLM-settings (masked)")
async def get_admin_settings(current=Depends(require_admin)):
    doc = await admin_settings_coll.find_one({"_id": SETTINGS_DOC_ID})
    settings = _load_settings_doc_sync(doc)
    return {
        "primary": _public_slot(settings.get("primary")),
        "secondary": _public_slot(settings.get("secondary")),
        "fallback_model": settings.get("fallback_model") or DEFAULT_FALLBACK_MODEL,
        "updated_at": settings.get("updated_at"),
        "updated_by": settings.get("updated_by"),
        "catalog": public_providers_for_ui(),
    }


async def _resolve_slot_for_write(
    existing: Optional[Dict[str, Any]], payload: Optional[SlotIn]
) -> Optional[Dict[str, Any]]:
    if payload is None:
        return existing  # not in body at all — keep as is
    # Validate provider/model
    provider = payload.provider or (existing or {}).get("provider")
    model = payload.model or (existing or {}).get("model")
    if not provider and payload.api_key is None:
        return existing
    if provider and not provider_known(provider):
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")
    if provider and model and not model_known(provider, model):
        raise HTTPException(status_code=400,
                            detail=f"Unknown model '{model}' for provider '{provider}'.")
    # api_key handling
    if payload.api_key is None:
        # keep existing encrypted key
        key_enc = (existing or {}).get("api_key_encrypted")
    elif payload.api_key == "":
        # clear the slot entirely
        return None
    else:
        key_enc = encrypt_str(payload.api_key)
    now = _now_iso()
    slot = {
        "provider": provider,
        "model": model,
        "label": payload.label if payload.label is not None else (existing or {}).get("label"),
        "api_key_encrypted": key_enc,
        "updated_at": now,
    }
    return slot


@admin_router.put("/settings", summary="Update admin LLM-settings (upsert)")
async def put_admin_settings(payload: SettingsPutIn, current=Depends(require_admin)):
    doc = await admin_settings_coll.find_one({"_id": SETTINGS_DOC_ID})
    settings = _load_settings_doc_sync(doc)

    # "payload.primary is None" means the caller didn't include that field at all
    primary_raw = payload.model_dump().get("primary", None)
    secondary_raw = payload.model_dump().get("secondary", None)

    new_primary = settings.get("primary")
    new_secondary = settings.get("secondary")
    if primary_raw is not None:
        new_primary = await _resolve_slot_for_write(settings.get("primary"), payload.primary)
    if secondary_raw is not None:
        new_secondary = await _resolve_slot_for_write(settings.get("secondary"), payload.secondary)

    fallback = payload.fallback_model or settings.get("fallback_model") or DEFAULT_FALLBACK_MODEL
    if fallback not in {m["id"] for m in FALLBACK_MODELS}:
        raise HTTPException(status_code=400, detail=f"Unknown fallback model '{fallback}'.")

    now = _now_iso()
    new_doc = {
        "_id": SETTINGS_DOC_ID,
        "primary": new_primary,
        "secondary": new_secondary,
        "fallback_model": fallback,
        "updated_at": now,
        "updated_by": current["sub"],
    }
    await admin_settings_coll.replace_one({"_id": SETTINGS_DOC_ID}, new_doc, upsert=True)
    logger.info("Admin settings updated by=%s", current["sub"])

    return {
        "primary": _public_slot(new_primary),
        "secondary": _public_slot(new_secondary),
        "fallback_model": fallback,
        "updated_at": now,
        "updated_by": current["sub"],
    }


async def _resolve_test_target(payload: SettingsTestIn) -> Dict[str, Any]:
    """Figure out which (provider, model, api_key) to test."""
    if payload.slot == "adhoc":
        if not (payload.provider and payload.model and payload.api_key):
            raise HTTPException(status_code=400,
                                detail="adhoc test requires provider, model, and api_key.")
        return {
            "provider": payload.provider,
            "model": payload.model,
            "api_key": payload.api_key,
        }
    # primary / secondary
    doc = await admin_settings_coll.find_one({"_id": SETTINGS_DOC_ID})
    settings = _load_settings_doc_sync(doc)
    saved = settings.get(payload.slot)
    provider = payload.provider or (saved or {}).get("provider")
    model = payload.model or (saved or {}).get("model")
    api_key = payload.api_key
    if not api_key:
        if not saved or not saved.get("api_key_encrypted"):
            raise HTTPException(status_code=400, detail=f"No API key saved for {payload.slot}.")
        api_key = decrypt_str(saved["api_key_encrypted"])
    if not (provider and model and api_key):
        raise HTTPException(status_code=400, detail="Missing provider/model/api_key for test.")
    return {"provider": provider, "model": model, "api_key": api_key}


@admin_router.post("/settings/test", summary="Test a provider round-trip")
async def test_settings(payload: SettingsTestIn, current=Depends(require_admin)):
    target = await _resolve_test_target(payload)
    provider = target["provider"]
    model = target["model"]
    api_key = target["api_key"]

    # Short, deterministic round-trip.
    test_prompt = [{"role": "user", "content": "Reply with exactly: OK"}]
    started = time.time()
    try:
        tier = await build_tier("test", provider, model, api_key)
        text = await tier.call(test_prompt, None, 16, model)
        latency_ms = int((time.time() - started) * 1000)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "provider": provider,
            "model": model,
            "model_echo": (text or "").strip()[:120],
        }
    except Exception as exc:  # noqa: BLE001
        category, msg = categorise_exception(exc)
        # Never leak raw exception text that could contain the key.
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "provider": provider,
                "model": model,
                "error_category": category if category != "4xx" else "model_not_found",
                "error": _short_error_text(exc, api_key),
            },
        )


def _short_error_text(exc: Exception, api_key: str) -> str:
    s = str(exc)
    # Sanitise any stray occurrences of the key
    if api_key and api_key in s:
        s = s.replace(api_key, "<redacted>")
    return s[:240]


@admin_router.post("/settings/test-fallback", summary="Test the Emergent-key fallback round-trip")
async def test_fallback(current=Depends(require_admin)):
    doc = await admin_settings_coll.find_one({"_id": SETTINGS_DOC_ID})
    settings = _load_settings_doc_sync(doc)
    model = settings.get("fallback_model") or DEFAULT_FALLBACK_MODEL
    started = time.time()
    try:
        tier = await build_fallback_tier(model)
        text = await tier.call([{"role": "user", "content": "Reply with exactly: OK"}], None, 16, model)
        latency_ms = int((time.time() - started) * 1000)
        return {
            "ok": True, "latency_ms": latency_ms,
            "provider": "emergent", "model": model,
            "model_echo": (text or "").strip()[:120],
        }
    except Exception as exc:  # noqa: BLE001
        category, _ = categorise_exception(exc)
        return JSONResponse(
            status_code=200,
            content={
                "ok": False, "provider": "emergent", "model": model,
                "error_category": category, "error": str(exc)[:240],
            },
        )



# --------------------------------------------------------------------------- #
# Routes — admin sessions (read only, Phase 4)
# --------------------------------------------------------------------------- #
@admin_router.get("/sessions", summary="List sessions (admin, search + filter + pagination)")
async def admin_list_sessions(
    q: Optional[str] = None,
    status: Optional[str] = None,
    include_deleted: bool = True,
    archived: Optional[str] = None,  # "only" | "exclude" | None
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "-created_at",
    current=Depends(require_admin),
):
    page = max(1, int(page))
    page_size = max(1, min(100, int(page_size)))
    query: Dict[str, Any] = {}

    # --- status filter (comma-separated whitelist)
    if status:
        status_list = [s.strip() for s in status.split(",") if s.strip()]
        if status_list:
            query["status"] = {"$in": status_list}

    # --- deleted toggle
    if not include_deleted:
        query["deleted_at"] = {"$in": [None]}

    # --- archived toggle
    if archived == "only":
        query["archived"] = True
    elif archived == "exclude":
        query["archived"] = {"$ne": True}

    # --- date range on created_at
    if date_from or date_to:
        date_clause: Dict[str, str] = {}
        if date_from:
            date_clause["$gte"] = date_from
        if date_to:
            date_clause["$lte"] = date_to
        query["created_at"] = date_clause

    # --- search — substring over name/email/organisation
    if q:
        qs = q.strip()
        if qs:
            escaped = re.escape(qs)
            query["$or"] = [
                {"participant.name": {"$regex": escaped, "$options": "i"}},
                {"participant.email": {"$regex": escaped, "$options": "i"}},
                {"participant.organisation": {"$regex": escaped, "$options": "i"}},
                {"session_id": {"$regex": escaped, "$options": "i"}},
            ]

    # --- sort parse
    if sort.startswith("-"):
        sort_field, direction = sort[1:], -1
    else:
        sort_field, direction = sort, 1
    allowed_sort = {"created_at", "completed_at", "participant.name", "status", "stage"}
    if sort_field not in allowed_sort:
        sort_field = "created_at"

    total = await sessions_coll.count_documents(query)
    skip = (page - 1) * page_size
    cursor = sessions_coll.find(query, {
        "_id": 0,
        "session_id": 1, "participant": 1, "stage": 1, "status": 1,
        "created_at": 1, "started_at": 1, "completed_at": 1,
        "archived": 1, "deleted_at": 1, "hard_delete_at": 1, "redacted": 1,
        "synthesis": 1,
        "deliverable.executive_summary.overall_category": 1,
        "deliverable.executive_summary.overall_colour": 1,
        "deliverable.scoring_error": 1,
    }).sort(sort_field, direction).skip(skip).limit(page_size)

    items: List[Dict[str, Any]] = []
    async for doc in cursor:
        synth = doc.get("synthesis") or {}
        deliv = doc.get("deliverable") or {}
        es = (deliv.get("executive_summary") or {})
        created_at = doc.get("created_at")
        completed_at = doc.get("completed_at")
        dur_sec = None
        if created_at and completed_at:
            try:
                dur_sec = int((datetime.fromisoformat(completed_at) - datetime.fromisoformat(created_at)).total_seconds())
            except Exception:
                dur_sec = None
        items.append({
            "session_id": doc.get("session_id"),
            "participant": doc.get("participant") or {},
            "stage": doc.get("stage"),
            "status": doc.get("status"),
            "created_at": created_at,
            "started_at": doc.get("started_at"),
            "completed_at": completed_at,
            "archived": bool(doc.get("archived")),
            "deleted_at": doc.get("deleted_at"),
            "hard_delete_at": doc.get("hard_delete_at"),
            "redacted": bool(doc.get("redacted")),
            "overall_category": es.get("overall_category"),
            "overall_colour": es.get("overall_colour"),
            "synthesis_status": synth.get("status"),
            "has_scoring_error": bool(deliv.get("scoring_error")),
            "duration_seconds": dur_sec,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "filters_applied": {
            "q": q, "status": status, "archived": archived,
            "include_deleted": include_deleted,
            "date_from": date_from, "date_to": date_to,
            "sort": sort,
        },
    }


@admin_router.get("/sessions/{session_id}", summary="Get a full session (admin)")
async def admin_get_session(session_id: str, current=Depends(require_admin)):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    # Stamp last_admin_viewed_at — used by future "new since your last visit" UX.
    now = _now_iso()
    await sessions_coll.update_one(
        {"session_id": session_id},
        {"$set": {"last_admin_viewed_at": now}},
    )
    doc["last_admin_viewed_at"] = now
    return doc


class AdminSessionPatchIn(BaseModel):
    archived: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("notes")
    @classmethod
    def _notes_length(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) > 2000:
            raise ValueError("notes must be ≤2000 characters")
        return v


@admin_router.patch("/sessions/{session_id}", summary="Archive toggle + admin notes")
async def admin_patch_session(session_id: str, payload: AdminSessionPatchIn, current=Depends(require_admin)):
    doc = await sessions_coll.find_one({"session_id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")

    update: Dict[str, Any] = {"updated_at": _now_iso()}

    if payload.archived is not None:
        update["archived"] = bool(payload.archived)
        if payload.archived is True:
            # Archiving PROTECTS from lifecycle cleanup — clear expiry markers.
            update["expires_at"] = None
            update["hard_delete_at"] = None
        else:
            # Unarchiving restores the 60-day expiry when the session has a
            # completion timestamp. If it's not completed, leave expires_at null.
            completed_at = doc.get("completed_at")
            if completed_at:
                try:
                    ca = datetime.fromisoformat(completed_at)
                    update["expires_at"] = (ca + SIXTY_DAYS).isoformat()
                except Exception:
                    update["expires_at"] = None

    if payload.notes is not None:
        update["admin_notes"] = payload.notes

    await sessions_coll.update_one({"session_id": session_id}, {"$set": update})
    await dashboard.invalidate_cache()
    refreshed = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    return refreshed


@admin_router.delete("/sessions/{session_id}", summary="Admin-initiated soft delete (PII scrub, 30d grace)")
async def admin_soft_delete_session(session_id: str, current=Depends(require_admin)):
    result = await lifecycle.soft_delete_session(sessions_coll, session_id)
    if not result.get("ok") and result.get("reason") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found.")
    await dashboard.invalidate_cache()
    return result


@admin_router.post("/sessions/{session_id}/restore", summary="Restore a soft-deleted session (within 30d)")
async def admin_restore_session(session_id: str, current=Depends(require_admin)):
    result = await lifecycle.restore_session(sessions_coll, session_id)
    if not result.get("ok"):
        code = result.get("status_code", 409)
        reason = result.get("reason", "cannot_restore")
        detail_map = {
            "not_found": ("Session not found.", 404),
            "not_soft_deleted": ("Session is not soft-deleted.", 409),
            "past_hard_delete_window": ("Restore window has passed.", 409),
        }
        msg, hc = detail_map.get(reason, (reason, code))
        raise HTTPException(status_code=hc, detail=msg)
    await dashboard.invalidate_cache()
    return result


@admin_router.get("/sessions/{session_id}/conversation/download", summary="Download conversation (MD or JSON)")
async def admin_download_conversation(
    session_id: str,
    format: Literal["markdown", "json"] = "markdown",
    current=Depends(require_admin),
):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    if format == "json":
        body = conversation_export.to_json(doc)
        media_type = "application/json"
        filename = conversation_export.filename_for(doc, "json")
    else:
        body = conversation_export.to_markdown(doc)
        media_type = "text/markdown; charset=utf-8"
        filename = conversation_export.filename_for(doc, "md")
    return FAResponse(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_router.get("/sessions/{session_id}/deliverable/download", summary="Admin download of the deliverable (PDF/MD)")
async def admin_download_deliverable(
    session_id: str,
    format: Literal["pdf", "markdown"] = "pdf",
    current=Depends(require_admin),
):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    deliverable = doc.get("deliverable") or {}
    if not deliverable or deliverable.get("scoring_error"):
        raise HTTPException(status_code=409, detail="Deliverable not available for this session.")
    self_awareness = syn_svc.compute_self_awareness_accuracy(doc)
    context = results_render.build_context(doc, deliverable, self_awareness)
    first_name = context["participant"]["first_name"]
    if format == "pdf":
        pdf_bytes = results_render.render_pdf(context)
        filename = results_render.safe_filename(first_name, "pdf")
        return FAResponse(
            content=pdf_bytes, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    md_str = results_render.render_markdown(context)
    filename = results_render.safe_filename(first_name, "md")
    return FAResponse(
        content=md_str, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_router.get("/dashboard/summary", summary="Aggregate metrics for the admin overview")
async def admin_dashboard_summary(current=Depends(require_admin)):
    return await dashboard.get_dashboard_summary(sessions_coll)


@admin_router.post("/lifecycle/run", summary="Manually run the soft/hard delete cleanup cycle")
async def admin_lifecycle_run(current=Depends(require_admin)):
    summary = await lifecycle.run_cleanup_cycle(sessions_coll, force=True)
    await dashboard.invalidate_cache()
    return summary


# --------------------------------------------------------------------------- #
# Admin startup: seed default admin + indexes
# --------------------------------------------------------------------------- #
DEFAULT_ADMIN_EMAIL = "steve@org-logic.io"
DEFAULT_ADMIN_PASSWORD = "test1234"


async def _seed_admin_if_empty():
    count = await admin_users_coll.count_documents({})
    if count > 0:
        return
    now = _now_iso()
    doc = {
        "_id": str(uuid.uuid4()),
        "email": DEFAULT_ADMIN_EMAIL,
        "password_hash": hash_password(DEFAULT_ADMIN_PASSWORD),
        "role": "admin",
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    await admin_users_coll.insert_one(doc)
    logger.info("Seeded default admin: %s", DEFAULT_ADMIN_EMAIL)


# --------------------------------------------------------------------------- #
# Exception handler for validation errors
# --------------------------------------------------------------------------- #
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


# --------------------------------------------------------------------------- #
# Startup
# --------------------------------------------------------------------------- #
_scheduler: Optional[Any] = None


async def _lifecycle_cron_tick() -> None:
    """APScheduler tick — swallows errors (so the scheduler stays alive)."""
    try:
        summary = await lifecycle.run_cleanup_cycle(sessions_coll)
        if not summary.get("skipped"):
            logger.info(
                "Lifecycle cron: soft=%d hard=%d errors=%d scanned_at=%s",
                summary.get("soft_deleted", 0), summary.get("hard_deleted", 0),
                summary.get("errors", 0), summary.get("scanned_at"),
            )
            # Any change invalidates the dashboard cache.
            if (summary.get("soft_deleted", 0) + summary.get("hard_deleted", 0)) > 0:
                await dashboard.invalidate_cache()
    except Exception as exc:  # pragma: no cover — safety net
        logger.exception("Lifecycle cron tick failed: %s", exc)


@app.on_event("startup")
async def _on_startup():
    # Sessions indexes (Phase 2 + 8)
    await sessions_coll.create_index([("resume_code", ASCENDING)], unique=True, name="uniq_resume_code")
    await sessions_coll.create_index([("status", ASCENDING), ("expires_at", ASCENDING)], name="status_expires")
    # Phase 8 indexes — drive the lifecycle cron + admin list filters + search.
    await sessions_coll.create_index([("archived", ASCENDING), ("expires_at", ASCENDING)], name="archived_expires")
    await sessions_coll.create_index([("hard_delete_at", ASCENDING)], name="hard_delete_at")
    await sessions_coll.create_index([("status", ASCENDING), ("created_at", ASCENDING)], name="status_created")
    await sessions_coll.create_index([("participant.email", ASCENDING)], name="participant_email", sparse=True)
    # Admin users index
    await admin_users_coll.create_index([("email", ASCENDING)], unique=True, name="uniq_admin_email")
    # Seed
    await _seed_admin_if_empty()
    logger.info("Mongo indexes ensured on sessions + admin_users.")

    # Lifecycle cron — APScheduler AsyncIOScheduler, every 6h.
    global _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        _scheduler = AsyncIOScheduler(timezone="UTC")
        _scheduler.add_job(_lifecycle_cron_tick, "interval", hours=6, id="lifecycle_cron",
                           next_run_time=datetime.now(timezone.utc) + timedelta(minutes=5))
        _scheduler.start()
        logger.info("Lifecycle cron scheduled every 6h (first tick in ~5 min).")
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to start APScheduler lifecycle cron: %s", exc)


@app.on_event("shutdown")
async def shutdown_db_client():
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
    client.close()


# --------------------------------------------------------------------------- #
# Wire up
# --------------------------------------------------------------------------- #
api_router.include_router(admin_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origin_regex=".*",
    allow_methods=["*"],
    allow_headers=["*"],
)
