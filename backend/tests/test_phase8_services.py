"""Unit tests for lifecycle + conversation_export + dashboard aggregations."""
from __future__ import annotations
import asyncio
import copy
import json
import pytest
from datetime import datetime, timezone, timedelta

from services import lifecycle_service as lc
from services import conversation_export as ce
from services import dashboard_summary as ds


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------- Fake in-memory sessions collection ----------
class FakeCollection:
    """Minimal async-compatible stand-in for a motor collection."""
    def __init__(self, docs):
        self.docs = {d.get("_id") or d.get("session_id"): copy.deepcopy(d) for d in docs}

    def find_one(self, query):  # returns coroutine-ish
        async def _inner():
            for d in self.docs.values():
                if self._match(d, query):
                    return copy.deepcopy(d)
            return None
        return _inner()

    def find(self, query, proj=None):
        matches = [copy.deepcopy(d) for d in self.docs.values() if self._match(d, query)]
        return _AsyncCursor(matches)

    async def count_documents(self, query):
        return sum(1 for d in self.docs.values() if self._match(d, query))

    async def update_one(self, query, update):
        for d in self.docs.values():
            if self._match(d, query):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        _dotset(d, k, v)
                return {"matched": 1}
        return {"matched": 0}

    async def delete_one(self, query):
        for k, d in list(self.docs.items()):
            if self._match(d, query):
                del self.docs[k]
                return {"deleted": 1}
        return {"deleted": 0}

    async def insert_one(self, d):
        self.docs[d.get("_id") or d.get("session_id")] = copy.deepcopy(d)

    @staticmethod
    def _match(doc, query):
        for k, v in query.items():
            actual = _dotget(doc, k)
            if isinstance(v, dict):
                for op, arg in v.items():
                    if op == "$ne" and actual == arg:
                        return False
                    elif op == "$eq" and actual != arg:
                        return False
                    elif op == "$lte" and not (actual is not None and actual <= arg):
                        return False
                    elif op == "$gte" and not (actual is not None and actual >= arg):
                        return False
                    elif op == "$gt" and not (actual is not None and actual > arg):
                        return False
                    elif op == "$lt" and not (actual is not None and actual < arg):
                        return False
                    elif op == "$in" and actual not in arg:
                        return False
            else:
                if actual != v:
                    return False
        return True


class _AsyncCursor:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._items):
            raise StopAsyncIteration
        v = self._items[self._i]
        self._i += 1
        return v


def _dotget(doc, key):
    parts = key.split(".")
    cur = doc
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _dotset(doc, key, value):
    parts = key.split(".")
    cur = doc
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


# ---------- Lifecycle behaviour ----------
@pytest.fixture(autouse=True)
def reset_lc_state():
    lc._reset_last_run_for_tests()
    yield
    lc._reset_last_run_for_tests()


@pytest.mark.asyncio
async def test_soft_deletes_expired_non_archived():
    now = datetime.now(timezone.utc)
    past = _iso(now - timedelta(days=1))
    coll = FakeCollection([
        {"_id": "a", "session_id": "a", "archived": False, "deleted_at": None, "expires_at": past,
         "participant": {"name": "A", "email": "a@x"}},
    ])
    r = await lc.run_cleanup_cycle(coll, force=True)
    assert r["soft_deleted"] == 1
    assert r["hard_deleted"] == 0
    doc = await coll.find_one({"session_id": "a"})
    assert doc["deleted_at"] is not None
    assert doc["hard_delete_at"] is not None
    assert doc["redacted"] is True
    assert doc["participant"]["name"] == "(redacted)"
    assert doc["participant"]["email"] is None


@pytest.mark.asyncio
async def test_skips_archived_even_if_expired():
    now = datetime.now(timezone.utc)
    past = _iso(now - timedelta(days=1))
    coll = FakeCollection([
        {"_id": "arch", "session_id": "arch", "archived": True, "deleted_at": None, "expires_at": past,
         "participant": {"name": "B", "email": "b@x"}},
    ])
    r = await lc.run_cleanup_cycle(coll, force=True)
    assert r["soft_deleted"] == 0
    doc = await coll.find_one({"session_id": "arch"})
    assert doc["deleted_at"] is None
    assert doc["participant"]["name"] == "B"


@pytest.mark.asyncio
async def test_hard_deletes_past_hard_delete_at():
    now = datetime.now(timezone.utc)
    past = _iso(now - timedelta(days=1))
    coll = FakeCollection([
        {"_id": "done", "session_id": "done", "archived": False,
         "deleted_at": _iso(now - timedelta(days=31)),
         "hard_delete_at": past},
    ])
    r = await lc.run_cleanup_cycle(coll, force=True)
    assert r["hard_deleted"] == 1
    assert await coll.find_one({"session_id": "done"}) is None


@pytest.mark.asyncio
async def test_admin_soft_delete_then_restore_within_grace():
    now = datetime.now(timezone.utc)
    coll = FakeCollection([
        {"_id": "x", "session_id": "x", "archived": False,
         "participant": {"name": "Eve", "email": "e@x"},
         "completed_at": _iso(now - timedelta(days=1))},
    ])
    r1 = await lc.soft_delete_session(coll, "x")
    assert r1["ok"] and r1["soft_deleted"]
    doc1 = await coll.find_one({"session_id": "x"})
    assert doc1["redacted"] and doc1["participant"]["name"] == "(redacted)"

    r2 = await lc.restore_session(coll, "x")
    assert r2["ok"] and r2["restored"]
    assert r2["pii_recoverable"] is False
    doc2 = await coll.find_one({"session_id": "x"})
    assert doc2["deleted_at"] is None
    assert doc2["hard_delete_at"] is None
    # PII is NOT restored
    assert doc2["participant"]["name"] == "(redacted)"


@pytest.mark.asyncio
async def test_restore_returns_409_past_hard_delete_window():
    now = datetime.now(timezone.utc)
    coll = FakeCollection([
        {"_id": "x", "session_id": "x",
         "deleted_at": _iso(now - timedelta(days=40)),
         "hard_delete_at": _iso(now - timedelta(days=1))},
    ])
    r = await lc.restore_session(coll, "x")
    assert r["ok"] is False
    assert r["status_code"] == 409


@pytest.mark.asyncio
async def test_run_cycle_skipped_within_5_minutes():
    now = datetime.now(timezone.utc)
    past = _iso(now - timedelta(days=1))
    coll = FakeCollection([
        {"_id": "a", "session_id": "a", "archived": False, "deleted_at": None, "expires_at": past,
         "participant": {"name": "A"}},
    ])
    r1 = await lc.run_cleanup_cycle(coll, force=True)
    assert r1["soft_deleted"] == 1
    # Second call NOT forced: should skip
    r2 = await lc.run_cleanup_cycle(coll, force=False)
    assert r2.get("skipped") is True


@pytest.mark.asyncio
async def test_per_session_error_does_not_halt_sweep(monkeypatch):
    now = datetime.now(timezone.utc)
    past = _iso(now - timedelta(days=1))
    coll = FakeCollection([
        {"_id": "bad", "session_id": "bad", "archived": False, "deleted_at": None, "expires_at": past,
         "participant": {"name": "A"}},
        {"_id": "good", "session_id": "good", "archived": False, "deleted_at": None, "expires_at": past,
         "participant": {"name": "B"}},
    ])
    original = lc._soft_delete_one
    call_count = {"n": 0}

    async def boom(coll, doc, now):
        call_count["n"] += 1
        if doc.get("session_id") == "bad":
            raise RuntimeError("synthetic")
        return await original(coll, doc, now)
    monkeypatch.setattr(lc, "_soft_delete_one", boom)
    r = await lc.run_cleanup_cycle(coll, force=True)
    assert r["soft_deleted"] == 1
    assert r["errors"] == 1


# ---------- Conversation export ----------
def _make_session_with_convo(redacted=False):
    return {
        "session_id": "abc-12345",
        "redacted": redacted,
        "participant": {"name": "(redacted)" if redacted else "Alice",
                        "organisation": None if redacted else "Acme",
                        "role": None if redacted else "CEO",
                        "email": None if redacted else "a@x.co"},
        "completed_at": "2026-04-23T18:00:00+00:00",
        "created_at": "2026-04-23T17:30:00+00:00",
        "conversation": [
            {"turn": 0, "role": "assistant", "content": "Opener.", "timestamp": "2026-04-23T17:31:00+00:00"},
            {"turn": 1, "role": "user", "content": "I use AI daily.", "timestamp": "2026-04-23T17:31:30+00:00"},
            {"turn": 1, "role": "assistant", "content": "Follow-up?", "timestamp": "2026-04-23T17:32:00+00:00",
             "provider": "emergent", "model": "claude", "latency_ms": 1200, "fallbacks_tried": 0},
        ],
        "ai_discussion": {"user_turn_count": 1},
        "scores": {"ai_fluency": {"overall_score": 3.6,
                                  "components": {"capability_understanding": {"score": 4, "confidence": "high"}},
                                  "strengths": ["daily use"], "blind_spots": ["agentic"]}},
    }


def test_markdown_export_has_both_roles_and_meta():
    s = _make_session_with_convo()
    md = ce.to_markdown(s)
    assert "Interviewer" in md
    assert "Participant" in md
    assert "`abc-12345`" in md
    assert "provider=`emergent`" in md
    assert "model=`claude`" in md
    # Scoring summary footer
    assert "Scoring summary" in md
    assert "daily use" in md


def test_markdown_export_redacted_label():
    s = _make_session_with_convo(redacted=True)
    md = ce.to_markdown(s)
    assert "(redacted)" in md
    assert "a@x.co" not in md
    assert "Acme" not in md


def test_json_export_roundtrip():
    s = _make_session_with_convo()
    out = ce.to_json(s)
    obj = json.loads(out)
    assert obj["session_id"] == "abc-12345"
    assert obj["redacted"] is False
    assert len(obj["conversation"]) == 3
    assert obj["scoring"]["overall_score"] == 3.6


def test_filename_sanitisation():
    s = _make_session_with_convo()
    name = ce.filename_for(s, "md")
    assert name.startswith("TRA-conversation-Alice-")
    assert name.endswith(".md")
    # Redacted version
    s2 = _make_session_with_convo(redacted=True)
    name2 = ce.filename_for(s2, "json")
    assert name2.startswith("TRA-conversation-session-")
    assert name2.endswith(".json")


# ---------- Dashboard summary aggregation ----------
@pytest.mark.asyncio
async def test_dashboard_summary_tiles_on_canned_dataset():
    now = datetime.now(timezone.utc)
    docs = []
    for i in range(5):
        docs.append({
            "_id": f"p{i}", "session_id": f"p{i}", "status": "active",
            "created_at": _iso(now - timedelta(days=i)), "deleted_at": None,
        })
    for i in range(3):
        docs.append({
            "_id": f"c{i}", "session_id": f"c{i}", "status": "completed",
            "created_at": _iso(now - timedelta(days=i)),
            "completed_at": _iso(now - timedelta(days=i) + timedelta(minutes=40)),
            "deleted_at": None,
            "deliverable": {
                "executive_summary": {"overall_category": "High Potential", "overall_colour": "gold"},
                "dimension_profiles": [
                    {"dimension_id": "learning_agility", "score": 4.1},
                    {"dimension_id": "ai_fluency", "score": 3.6},
                ],
            },
        })
    # One completed last week (so weekly delta is computable)
    docs.append({
        "_id": "lw", "session_id": "lw", "status": "completed",
        "created_at": _iso(now - timedelta(days=10)),
        "completed_at": _iso(now - timedelta(days=10)),
        "deleted_at": None,
        "deliverable": {"executive_summary": {"overall_category": "Transformation Ready",
                                              "overall_colour": "navy"}},
    })
    coll = FakeCollection(docs)
    await ds.invalidate_cache()
    s = await ds.get_dashboard_summary(coll, force=True)
    assert s["totals"]["total_sessions"] == 9
    assert s["totals"]["in_progress"] == 5
    assert s["totals"]["completed"] == 4
    # Score distribution from the 3 completed with deliverables in the last 30d:
    assert s["score_distribution"]["gold"] >= 2
    # dim averages contain all 6 assessed ids
    assert len(s["dimension_averages"]) == 6
    # activity_14d has 14 entries
    assert len(s["activity_14d"]) == 14
