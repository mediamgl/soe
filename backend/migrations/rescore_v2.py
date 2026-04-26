"""One-shot migration: re-score existing completed sessions under v2
(reverse-keyed items + response-pattern detector).

Run from /app/backend:
    python -m migrations.rescore_v2

Rules:
- Only touches sessions where `scores.psychometric` is already populated.
- Looks up each item_id in the session's psychometric.order against the v2
  catalogue. If any item_id is unknown to the catalogue, log + skip (don't
  crash). This keeps very old sessions from before the catalogue stabilised
  out of harm's way.
- Recomputes scoring on the raw responses (psychometric.answers, never
  mutated) and updates scores.psychometric in place.
- Writes audit metadata: scores.psychometric._rescored_at,
  scores.psychometric._rescored_v = "v2-revkey".
- Does NOT touch session.deliverable. Admins can manually re-run synthesis
  on individual sessions via the /admin/.../resynthesize endpoint if they
  want a refreshed deliverable.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

# Allow running as `python -m migrations.rescore_v2` from /app/backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

import psychometric_service as p


RESCORE_VERSION = "v2-revkey"


def _session_item_ids(session: Dict[str, Any]) -> List[str]:
    """Return the set of item_ids the session was answered against. Prefer
    the `order` array (the canonical source) and fall back to the answers
    array if order is missing."""
    psych = session.get("psychometric") or {}
    order = psych.get("order") or []
    if order:
        return list(order)
    return [a.get("item_id") for a in (psych.get("answers") or []) if a.get("item_id")]


def _all_ids_known(item_ids: List[str]) -> bool:
    catalogue_ids = {it["item_id"] for it in p.get_items()}
    return all(iid in catalogue_ids for iid in item_ids if iid)


async def main() -> int:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "soe_tra")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    coll = db["sessions"]

    rescored = 0
    skipped_unknown_ids = 0
    skipped_no_scores = 0
    skipped_already_v2 = 0
    errors = 0

    cursor = coll.find(
        {"scores.psychometric": {"$ne": None}},
        # Only the fields the rescorer needs.
        {"_id": 0, "session_id": 1, "psychometric": 1, "scores.psychometric": 1},
    )
    async for doc in cursor:
        sid = doc.get("session_id") or "(no-sid)"
        sc_psy = (doc.get("scores") or {}).get("psychometric") or {}
        # Idempotency guard.
        if sc_psy.get("_rescored_v") == RESCORE_VERSION:
            skipped_already_v2 += 1
            continue
        ids = _session_item_ids(doc)
        if not ids:
            skipped_no_scores += 1
            continue
        if not _all_ids_known(ids):
            unknown = [iid for iid in ids if iid not in {it["item_id"] for it in p.get_items()}]
            print(f"  [skip] {sid}: unknown item ids in order/answers: {unknown[:5]}{'…' if len(unknown) > 5 else ''}")
            skipped_unknown_ids += 1
            continue

        try:
            new_scores = p.score(doc)  # operates on doc.psychometric.answers
            # Preserve any non-canonical fields on the existing block by
            # merging old over new (new wins for anything we recompute).
            merged = {**sc_psy, **new_scores}
            # Audit fields
            merged["_rescored_at"] = datetime.now(timezone.utc).isoformat()
            merged["_rescored_v"] = RESCORE_VERSION
            await coll.update_one(
                {"session_id": doc["session_id"]},
                {"$set": {"scores.psychometric": merged}},
            )
            rescored += 1
            band_la = (new_scores.get("learning_agility") or {}).get("band")
            band_ta = (new_scores.get("tolerance_for_ambiguity") or {}).get("band")
            flag = new_scores.get("response_pattern_flag")
            print(f"  [ok]   {sid}  LA={band_la}  TA={band_ta}  flag={flag}")
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"  [err]  {sid}: {type(e).__name__}: {e}")

    client.close()

    print()
    print("=" * 70)
    print(f"Migration complete  ({RESCORE_VERSION})")
    print(f"  Rescored:               {rescored}")
    print(f"  Already at v2 (skip):   {skipped_already_v2}")
    print(f"  No scores (skip):       {skipped_no_scores}")
    print(f"  Unknown item ids (skip):{skipped_unknown_ids}")
    print(f"  Errors:                 {errors}")
    print("=" * 70)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
