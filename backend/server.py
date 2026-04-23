from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Cookie
from fastapi.responses import JSONResponse
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
import logging
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
)

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
_sessions_ip_hits: Dict[str, deque] = defaultdict(deque)
_login_ip_hits: Dict[str, deque] = defaultdict(deque)


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
                summary="Get the current state of a session")
async def get_session(session_id: str):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SessionOut(**doc)


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
@app.on_event("startup")
async def _on_startup():
    # Sessions indexes (Phase 2)
    await sessions_coll.create_index([("resume_code", ASCENDING)], unique=True, name="uniq_resume_code")
    await sessions_coll.create_index([("status", ASCENDING), ("expires_at", ASCENDING)], name="status_expires")
    # Admin users index
    await admin_users_coll.create_index([("email", ASCENDING)], unique=True, name="uniq_admin_email")
    # Seed
    await _seed_admin_if_empty()
    logger.info("Mongo indexes ensured on sessions + admin_users.")


@app.on_event("shutdown")
async def shutdown_db_client():
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
