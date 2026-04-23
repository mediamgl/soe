"""
Lifecycle service — Phase 8.

Handles the two-stage session retention policy:

  1. SOFT DELETE at 60 days after `completed_at` (or whatever `expires_at`
     carries). Strips PII from the `participant` sub-document and sets
     `deleted_at`, `hard_delete_at = deleted_at + 30d`, `redacted=true`.
     Keeps scores / conversation / scenario / deliverable intact — the
     analytics value survives, only the identity goes.

  2. HARD DELETE at `hard_delete_at` (30 days after soft-delete). The
     Mongo document is removed entirely.

Archive shield: sessions with `archived=true` are protected from BOTH
stages — their `expires_at` is cleared by the admin PATCH, so they never
become eligible for soft-delete.

Idempotency: `run_cleanup_cycle()` is safe to call repeatedly. A
lightweight in-process "last ran" guard avoids accidental back-to-back
runs from cron + a manual trigger ping within 5 minutes of each other.

Crash safety: per-session try/except so a single malformed doc cannot
stop the sweep.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SIXTY_DAYS = timedelta(days=60)
THIRTY_DAYS = timedelta(days=30)
MIN_RUN_INTERVAL = timedelta(minutes=5)

_last_run_at: Optional[datetime] = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def _soft_delete_one(sessions_coll, doc: Dict[str, Any], now: datetime) -> None:
    """Scrub PII and mark for hard-delete in 30d. Keeps analytics payload."""
    sid = doc.get("session_id") or doc.get("_id")
    hard_at = now + THIRTY_DAYS
    await sessions_coll.update_one(
        {"_id": sid},
        {
            "$set": {
                "deleted_at": _iso(now),
                "hard_delete_at": _iso(hard_at),
                "redacted": True,
                "updated_at": _iso(now),
                # PII scrub — keep the participant sub-document shape so
                # downstream renderers still work (they already tolerate
                # missing fields and display "Participant").
                "participant.name": "(redacted)",
                "participant.email": None,
                "participant.organisation": None,
                "participant.role": None,
            }
        },
    )
    logger.info("Soft-deleted session %s (hard_delete_at=%s)", sid, _iso(hard_at))


async def _hard_delete_one(sessions_coll, doc: Dict[str, Any]) -> None:
    sid = doc.get("session_id") or doc.get("_id")
    await sessions_coll.delete_one({"_id": sid})
    logger.info("Hard-deleted session %s", sid)


async def run_cleanup_cycle(sessions_coll, force: bool = False) -> Dict[str, Any]:
    """Scan sessions, soft-delete expired non-archived ones, hard-delete the
    ones past `hard_delete_at`. Returns a counts summary."""
    global _last_run_at
    now = _now_utc()
    if not force and _last_run_at and (now - _last_run_at) < MIN_RUN_INTERVAL:
        return {
            "skipped": True,
            "reason": "ran_recently",
            "last_run_at": _iso(_last_run_at),
            "scanned_at": _iso(now),
        }
    _last_run_at = now

    soft_count = 0
    hard_count = 0
    errors = 0
    now_iso = _iso(now)

    # -------- SOFT DELETE pass --------
    # Candidates: not archived, not already soft-deleted, expires_at set and in the past.
    soft_cursor = sessions_coll.find({
        "archived": {"$ne": True},
        "deleted_at": {"$in": [None]},
        "expires_at": {"$ne": None, "$lte": now_iso},
    })
    async for doc in soft_cursor:
        try:
            await _soft_delete_one(sessions_coll, doc, now)
            soft_count += 1
        except Exception as exc:  # pragma: no cover — per-doc safety
            errors += 1
            logger.exception(
                "Soft-delete failed for session %s: %s",
                doc.get("session_id") or doc.get("_id"), exc,
            )

    # -------- HARD DELETE pass --------
    hard_cursor = sessions_coll.find({
        "hard_delete_at": {"$ne": None, "$lte": now_iso},
    })
    async for doc in hard_cursor:
        try:
            await _hard_delete_one(sessions_coll, doc)
            hard_count += 1
        except Exception as exc:  # pragma: no cover — per-doc safety
            errors += 1
            logger.exception(
                "Hard-delete failed for session %s: %s",
                doc.get("session_id") or doc.get("_id"), exc,
            )

    return {
        "skipped": False,
        "soft_deleted": soft_count,
        "hard_deleted": hard_count,
        "errors": errors,
        "scanned_at": now_iso,
    }


async def soft_delete_session(sessions_coll, session_id: str) -> Dict[str, Any]:
    """Admin-initiated immediate soft-delete (doesn't wait for expiry)."""
    doc = await sessions_coll.find_one({"session_id": session_id})
    if not doc:
        return {"ok": False, "reason": "not_found"}
    if doc.get("deleted_at"):
        return {"ok": True, "reason": "already_soft_deleted",
                "deleted_at": doc["deleted_at"], "hard_delete_at": doc.get("hard_delete_at")}
    now = _now_utc()
    await _soft_delete_one(sessions_coll, doc, now)
    return {"ok": True, "soft_deleted": True,
            "deleted_at": _iso(now),
            "hard_delete_at": _iso(now + THIRTY_DAYS)}


async def restore_session(sessions_coll, session_id: str) -> Dict[str, Any]:
    """Admin restore: clears deleted_at + hard_delete_at if still within the
    30-day grace window. PII is not recoverable — flag returned to the UI."""
    doc = await sessions_coll.find_one({"session_id": session_id})
    if not doc:
        return {"ok": False, "status_code": 404, "reason": "not_found"}
    if not doc.get("deleted_at"):
        return {"ok": False, "status_code": 409, "reason": "not_soft_deleted"}
    hard_at = _parse_iso(doc.get("hard_delete_at"))
    now = _now_utc()
    if hard_at and now > hard_at:
        return {"ok": False, "status_code": 409, "reason": "past_hard_delete_window"}

    # Restore — keep redacted=true because PII was irrecoverably lost.
    # If session was previously completed we optionally re-hydrate expires_at
    # to completed_at + 60d so the lifecycle can run again naturally.
    update: Dict[str, Any] = {
        "deleted_at": None,
        "hard_delete_at": None,
        "updated_at": _iso(now),
    }
    completed_at = _parse_iso(doc.get("completed_at"))
    if completed_at:
        update["expires_at"] = _iso(completed_at + SIXTY_DAYS)

    await sessions_coll.update_one({"_id": doc["_id"]}, {"$set": update})
    return {"ok": True, "restored": True, "pii_recoverable": False}


def last_run_at() -> Optional[str]:
    return _iso(_last_run_at) if _last_run_at else None


# Test-only helper used by fixtures to reset in-process state between tests.
def _reset_last_run_for_tests() -> None:  # pragma: no cover
    global _last_run_at
    _last_run_at = None
