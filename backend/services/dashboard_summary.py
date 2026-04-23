"""
Admin dashboard summary — Phase 8.

Produces the aggregate metrics shown on /admin overview:
  - totals tiles (total, in_progress, completed, failed, archived, soft_deleted,
    expiring_soon within 7 days)
  - completed_this_week / completed_last_week (for the delta arrow)
  - avg_completion_duration_seconds (last 30d, completed only)
  - score_distribution: navy / gold / terracotta bands
  - dimension_averages: per-assessed-dimension mean across last-30d completed
  - activity_14d: per-day {new_sessions, completions}

60-second in-memory cache — this endpoint is hit every dashboard open.
Cache invalidates on any admin write (archive toggle, soft delete, restore).
"""
from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from services import dimensions_catalogue as dims_catalogue

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60
_cache_lock = asyncio.Lock()
_cache_value: Optional[Dict[str, Any]] = None
_cache_ts: float = 0.0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# Band colours sourced from synthesis_service to keep a single source of truth.
def _band_colour(category: str) -> str:
    from services.synthesis_service import CATEGORY_THRESHOLDS
    for t in CATEGORY_THRESHOLDS:
        if t["category"] == category:
            return t["colour"]
    return "gold"


async def invalidate_cache() -> None:
    global _cache_value, _cache_ts
    async with _cache_lock:
        _cache_value = None
        _cache_ts = 0.0


async def get_dashboard_summary(sessions_coll, force: bool = False) -> Dict[str, Any]:
    global _cache_value, _cache_ts
    now_mono = time.monotonic()
    if not force and _cache_value is not None and (now_mono - _cache_ts) < CACHE_TTL_SECONDS:
        return _cache_value

    async with _cache_lock:
        # Double-checked locking — another coroutine may have filled the cache
        # while we were awaiting the lock.
        if not force and _cache_value is not None and (time.monotonic() - _cache_ts) < CACHE_TTL_SECONDS:
            return _cache_value

        now = _now_utc()
        today_iso = _iso(now)
        week_ago_iso = _iso(now - timedelta(days=7))
        two_weeks_ago_iso = _iso(now - timedelta(days=14))
        thirty_days_ago_iso = _iso(now - timedelta(days=30))
        seven_days_hence_iso = _iso(now + timedelta(days=7))

        # Count tiles — lightweight counts only.
        total_sessions = await sessions_coll.count_documents({})
        in_progress = await sessions_coll.count_documents({"status": "active", "deleted_at": {"$in": [None]}})
        completed = await sessions_coll.count_documents({"status": "completed", "deleted_at": {"$in": [None]}})
        failed = await sessions_coll.count_documents({
            "$or": [
                {"synthesis.status": "failed"},
                {"deliverable.scoring_error": True},
            ],
            "deleted_at": {"$in": [None]},
        })
        archived = await sessions_coll.count_documents({"archived": True})
        soft_deleted = await sessions_coll.count_documents({"deleted_at": {"$ne": None}})
        expiring_soon = await sessions_coll.count_documents({
            "archived": {"$ne": True},
            "deleted_at": {"$in": [None]},
            "expires_at": {"$ne": None, "$lte": seven_days_hence_iso, "$gt": today_iso},
        })

        completed_this_week = await sessions_coll.count_documents({
            "status": "completed",
            "completed_at": {"$gte": week_ago_iso, "$lte": today_iso},
        })
        completed_last_week = await sessions_coll.count_documents({
            "status": "completed",
            "completed_at": {"$gte": two_weeks_ago_iso, "$lt": week_ago_iso},
        })

        # Avg completion duration — last 30d completed sessions only
        durations: List[float] = []
        cursor = sessions_coll.find(
            {
                "status": "completed",
                "completed_at": {"$gte": thirty_days_ago_iso, "$lte": today_iso},
                "created_at": {"$ne": None},
            },
            {"_id": 0, "created_at": 1, "completed_at": 1},
        )
        async for doc in cursor:
            start = _parse(doc.get("created_at"))
            finish = _parse(doc.get("completed_at"))
            if start and finish and finish > start:
                durations.append((finish - start).total_seconds())
        avg_completion_duration_seconds = round(sum(durations) / len(durations), 1) if durations else None

        # Score distribution by band — last 30d completed
        score_distribution = {"navy": 0, "gold": 0, "terracotta": 0, "unknown": 0}
        # Dimension averages
        dim_totals: Dict[str, List[float]] = {d.id: [] for d in dims_catalogue.assessed()}
        cursor = sessions_coll.find(
            {
                "status": "completed",
                "completed_at": {"$gte": thirty_days_ago_iso, "$lte": today_iso},
                "deliverable": {"$ne": None},
            },
            {"_id": 0, "deliverable": 1},
        )
        async for doc in cursor:
            deliv = doc.get("deliverable") or {}
            if deliv.get("scoring_error"):
                continue
            es = deliv.get("executive_summary") or {}
            cat = es.get("overall_category")
            colour = es.get("overall_colour") or (_band_colour(cat) if cat else None)
            if colour in ("navy", "gold", "terracotta"):
                score_distribution[colour] = score_distribution.get(colour, 0) + 1
            else:
                score_distribution["unknown"] += 1
            for p in deliv.get("dimension_profiles") or []:
                did = p.get("dimension_id")
                sc = p.get("score")
                if did in dim_totals and isinstance(sc, (int, float)):
                    dim_totals[did].append(float(sc))
        dimension_averages = []
        for d in dims_catalogue.assessed():
            vals = dim_totals.get(d.id) or []
            mean = round(sum(vals) / len(vals), 2) if vals else None
            dimension_averages.append({
                "dimension_id": d.id,
                "name": d.name,
                "cluster": d.cluster,
                "mean_score": mean,
                "sample_size": len(vals),
            })

        # 14-day activity line — new sessions + completions per day.
        # Build buckets keyed by YYYY-MM-DD in UTC.
        activity = {}
        for i in range(13, -1, -1):
            day = (now - timedelta(days=i)).date()
            activity[day.isoformat()] = {"date": day.isoformat(), "new_sessions": 0, "completions": 0}

        cursor = sessions_coll.find(
            {"created_at": {"$gte": _iso(now - timedelta(days=14)), "$lte": today_iso}},
            {"_id": 0, "created_at": 1, "completed_at": 1},
        )
        async for doc in cursor:
            c = _parse(doc.get("created_at"))
            if c:
                key = c.date().isoformat()
                if key in activity:
                    activity[key]["new_sessions"] += 1
            done = _parse(doc.get("completed_at"))
            if done:
                key = done.date().isoformat()
                if key in activity:
                    activity[key]["completions"] += 1
        activity_14d = list(activity.values())

        summary = {
            "totals": {
                "total_sessions": total_sessions,
                "in_progress": in_progress,
                "completed": completed,
                "failed": failed,
                "archived": archived,
                "soft_deleted": soft_deleted,
                "expiring_soon": expiring_soon,
            },
            "completed_this_week": completed_this_week,
            "completed_last_week": completed_last_week,
            "avg_completion_duration_seconds": avg_completion_duration_seconds,
            "score_distribution": score_distribution,
            "dimension_averages": dimension_averages,
            "activity_14d": activity_14d,
            "generated_at": today_iso,
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
        }

        _cache_value = summary
        _cache_ts = time.monotonic()
        return summary
