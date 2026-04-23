from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone
from pathlib import Path
import os
import logging
import uuid
import secrets
import string
import time
from collections import defaultdict, deque


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# --------------------------------------------------------------------------- #
# Mongo
# --------------------------------------------------------------------------- #
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'soe_tra')]
sessions_coll = db['sessions']


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
app = FastAPI(
    title="Transformation Readiness Assessment API",
    description="Backend for the SOE Transformation Readiness Assessment demo.",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

api_router = APIRouter(prefix="/api")

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Do not log PII at INFO. Use .debug(...) for anything that contains email.

# --------------------------------------------------------------------------- #
# Constants / domain
# --------------------------------------------------------------------------- #
STAGE_ORDER: List[str] = [
    "identity",
    "context",
    "psychometric",
    "ai-discussion",
    "scenario",
    "processing",
    "results",
]
STAGE_SET = set(STAGE_ORDER)

# Rate limit: 10 session creations per hour per IP.
RATE_LIMIT_WINDOW_SECONDS = 60 * 60
RATE_LIMIT_MAX = 10
_ip_hits: Dict[str, deque] = defaultdict(deque)


def _rate_limit_check(ip: str) -> bool:
    """Token-bucket-ish sliding-window limiter. Returns True if allowed."""
    now = time.time()
    bucket = _ip_hits[ip]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX:
        return False
    bucket.append(now)
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


# Human-friendly resume code: XXXX-XXXX using a 32-char alphabet
# (excludes 0/O/1/I/L to avoid ambiguity).
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
    # Fallback: append a random suffix. Extremely unlikely to reach.
    return _generate_resume_code() + "-" + secrets.token_hex(2).upper()


def _strip_internal(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Remove MongoDB internal fields before returning to the client."""
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# --------------------------------------------------------------------------- #
# Pydantic models
# --------------------------------------------------------------------------- #
class Participant(BaseModel):
    name: str
    email: EmailStr
    organisation: Optional[str] = None
    role: Optional[str] = None


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
    participant: Dict[str, Any]  # participant PII lookup — intentional for resume


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
# Routes
# --------------------------------------------------------------------------- #
@api_router.get("/")
async def root():
    return {"message": "Transformation Readiness Assessment API"}


@api_router.get("/health")
async def health():
    return {"status": "ok"}


@api_router.post(
    "/sessions",
    response_model=SessionCreateOut,
    status_code=201,
    summary="Create a new assessment session",
)
async def create_session(payload: SessionCreateIn, request: Request):
    ip = _client_ip(request)
    if not _rate_limit_check(ip):
        raise HTTPException(
            status_code=429,
            detail=f"Too many sessions from this IP. Limit is {RATE_LIMIT_MAX} per hour.",
        )

    session_id = str(uuid.uuid4())
    resume_code = await _unique_resume_code()
    now = _now_iso()

    doc = {
        "_id": session_id,
        "session_id": session_id,
        "resume_code": resume_code,
        "participant": {
            "name": payload.name,
            "email": str(payload.email),
            "organisation": payload.organisation,
            "role": payload.role,
        },
        "consent": {"accepted": True, "accepted_at": now},
        "status": "in_progress",
        "stage": "identity",
        "answers": [],
        "conversation": [],
        "scenario_responses": {},
        "deliverable": None,
        "scores": None,
        "archived": False,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "expires_at": None,
    }

    await sessions_coll.insert_one(doc)
    logger.info("Created session id=%s stage=%s", session_id, doc["stage"])  # no PII
    logger.debug("Session participant: %s", doc["participant"])  # DEBUG only

    return SessionCreateOut(
        session_id=session_id, resume_code=resume_code, stage=doc["stage"]
    )


@api_router.get(
    "/sessions/resume/{resume_code}",
    response_model=SessionResumeOut,
    summary="Resume a session by its resume code",
)
async def resume_session(resume_code: str):
    # Normalise: uppercase and strip stray spaces; accept with or without dash.
    code = resume_code.strip().upper()
    if len(code) == 8 and "-" not in code:
        code = code[:4] + "-" + code[4:]
    doc = await sessions_coll.find_one({"resume_code": code}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Resume code not found.")
    return SessionResumeOut(
        session_id=doc["session_id"],
        stage=doc["stage"],
        participant=doc["participant"],
    )


@api_router.patch(
    "/sessions/{session_id}/stage",
    response_model=SessionStageUpdateOut,
    summary="Update the current stage of a session (advance, stay, or go back one step)",
)
async def update_stage(session_id: str, payload: SessionStageUpdateIn):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0, "stage": 1, "status": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    current_stage = doc["stage"]
    next_stage = payload.stage

    current_idx = STAGE_ORDER.index(current_stage)
    next_idx = STAGE_ORDER.index(next_stage)
    delta = next_idx - current_idx

    # Allowed: advance by 1 (delta == +1), stay (0), or go back by 1 (-1).
    if delta not in (-1, 0, 1):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid stage transition '{current_stage}' -> '{next_stage}'. "
                "Only move one stage forward, stay, or go back one stage."
            ),
        )

    now = _now_iso()
    update: Dict[str, Any] = {"stage": next_stage, "updated_at": now}

    # If completing to 'results', mark session completed with 60d expiry.
    if next_stage == "results":
        update["status"] = "completed"
        update["completed_at"] = now
        # completed_at + 60 days
        expiry_dt = datetime.fromisoformat(now) + _sixty_days()
        update["expires_at"] = expiry_dt.isoformat()

    await sessions_coll.update_one(
        {"session_id": session_id}, {"$set": update}
    )
    return SessionStageUpdateOut(stage=next_stage, updated_at=now)


def _sixty_days():
    from datetime import timedelta
    return timedelta(days=60)


@api_router.get(
    "/sessions/{session_id}",
    response_model=SessionOut,
    summary="Get the current state of a session",
)
async def get_session(session_id: str):
    doc = await sessions_coll.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SessionOut(**doc)


# --------------------------------------------------------------------------- #
# Exception handler for validation errors -> 422 with helpful message
# --------------------------------------------------------------------------- #
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())},
    )


# --------------------------------------------------------------------------- #
# Startup: create indexes
# --------------------------------------------------------------------------- #
@app.on_event("startup")
async def _on_startup():
    await sessions_coll.create_index(
        [("resume_code", ASCENDING)], unique=True, name="uniq_resume_code"
    )
    await sessions_coll.create_index(
        [("status", ASCENDING), ("expires_at", ASCENDING)], name="status_expires"
    )
    logger.info("Mongo indexes ensured on sessions.")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# --------------------------------------------------------------------------- #
# Wire up
# --------------------------------------------------------------------------- #
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
