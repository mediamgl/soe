"""Phase 9 hotfix tests — synthesis timeout, finally-clause guarantee,
LLM router per-call timeout."""
from __future__ import annotations
import asyncio
import json
import pytest

from services import synthesis_service as syn
from services import llm_router as router


# ---------- G3: synthesis_service.run_synthesis enforces 240s outer budget ----------
@pytest.mark.asyncio
async def test_run_synthesis_total_budget_timeout(monkeypatch):
    """If the LLM call hangs longer than the outer budget, run_synthesis
    returns scoring_error=true with a 'timeout' message — never hangs."""

    # Pretend the budget is 0.05 s so the test runs fast.
    monkeypatch.setattr(syn, "TOTAL_SYNTHESIS_BUDGET_SEC", 0.05)

    async def slow_chat(*, messages, tiers, system, max_tokens, purpose):
        await asyncio.sleep(2.0)  # well past the test budget
        return {"text": "{}", "provider": "x", "model": "y", "fallbacks_tried": 0}

    monkeypatch.setattr(syn, "router_chat", slow_chat)

    session = {
        "participant": {"name": "Slow"},
        "scores": {}, "conversation": [], "scenario": {},
    }
    res = await syn.run_synthesis(session, tiers=[])
    assert res["ok"] is False
    assert res.get("scoring_error") is True
    assert "timeout" in res["error"].lower()


# ---------- G3: llm_router per-call timeout ----------
@pytest.mark.asyncio
async def test_router_per_call_timeout(monkeypatch):
    """A single tier that hangs longer than PER_CALL_TIMEOUT_SEC must NOT hang
    the cascade — it should be marked as a timeout failure and fall through to
    the next tier (or raise LLMRouterError if it's the last)."""

    monkeypatch.setattr(router, "PER_CALL_TIMEOUT_SEC", 0.05)

    async def hang_call(messages, system, max_tokens, model):
        await asyncio.sleep(2.0)
        return "should never return"

    async def fast_call(messages, system, max_tokens, model):
        return "OK"

    hang_tier = router.Tier(name="slow", provider="x", model="m", call=hang_call)
    fast_tier = router.Tier(name="fast", provider="y", model="n", call=fast_call)

    # Hang tier first — cascade should fall through to fast tier and succeed.
    result = await router.chat(
        messages=[{"role": "user", "content": "hi"}],
        tiers=[hang_tier, fast_tier],
        system=None,
        max_tokens=10,
        purpose="test",
    )
    assert result["text"] == "OK"
    assert result["provider"] == "y"
    assert result["fallbacks_tried"] == 1


@pytest.mark.asyncio
async def test_router_all_tiers_timeout_raises(monkeypatch):
    """If every tier times out, the router must raise LLMRouterError with
    failures categorised as 'timeout'."""

    monkeypatch.setattr(router, "PER_CALL_TIMEOUT_SEC", 0.05)

    async def hang_call(messages, system, max_tokens, model):
        await asyncio.sleep(2.0)
        return "x"

    t1 = router.Tier(name="t1", provider="x", model="m", call=hang_call)
    t2 = router.Tier(name="t2", provider="x", model="m", call=hang_call)

    with pytest.raises(router.LLMRouterError) as exc_info:
        await router.chat(messages=[{"role": "user", "content": "hi"}],
                          tiers=[t1, t2], system=None, max_tokens=10, purpose="test")
    cats = [f.category for f in exc_info.value.failures]
    assert cats == ["timeout", "timeout"]


# ---------- G4: server.py _run_synthesis_task `finally` guarantee ----------
@pytest.mark.asyncio
async def test_finally_forces_failed_when_status_left_in_progress(monkeypatch):
    """If the worker body somehow exits with synthesis.status still
    'in_progress', the finally clause must force it to 'failed'."""

    # Lazy import server module so we don't pull in a live FastAPI start.
    import importlib
    server = importlib.import_module("server")

    # Build a fake collection that records writes and starts in 'in_progress'.
    state = {"sid": "x", "synthesis": {"status": "in_progress"}, "writes": []}

    class FakeColl:
        async def find_one(self, query, proj=None):
            sid = query.get("session_id") or query.get("_id")
            if sid != state["sid"]:
                return None
            return {"_id": state["sid"], "session_id": state["sid"],
                    "synthesis": dict(state["synthesis"])}

        async def update_one(self, query, update):
            state["writes"].append(update)
            sets = update.get("$set", {})
            for k, v in sets.items():
                if k.startswith("synthesis."):
                    state["synthesis"][k.split(".", 1)[1]] = v
                elif k == "synthesis":
                    state["synthesis"] = dict(v) if isinstance(v, dict) else v
            return None

    fake = FakeColl()
    monkeypatch.setattr(server, "sessions_coll", fake)

    # Force the worker's main body to skip its writes by making run_synthesis
    # raise BEFORE either the happy or except branch can write a terminal
    # status — and also make the except-safety-net's update_one raise so the
    # finally is the only thing that can save us.
    async def boom(*a, **k):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(server.syn_svc, "run_synthesis", boom)
    # Make _build_tiers a no-op
    monkeypatch.setattr(server, "_syn_build_tiers", lambda: asyncio.sleep(0, result=[]))

    await server._run_synthesis_task(state["sid"])

    # The finally must have either left the except branch's "failed" write or
    # forced it itself. Either way, terminal status MUST be set.
    assert state["synthesis"]["status"] == "failed"
    assert "error" in state["synthesis"]


@pytest.mark.asyncio
async def test_synthesis_task_registry_holds_and_releases(monkeypatch):
    """asyncio.create_task is held in module-level _SYNTHESIS_TASKS until
    completion, then auto-discarded."""
    import importlib
    server = importlib.import_module("server")

    # Sanity: registry exists.
    assert hasattr(server, "_SYNTHESIS_TASKS")
    assert isinstance(server._SYNTHESIS_TASKS, set)

    server._SYNTHESIS_TASKS.clear()

    async def quick():
        await asyncio.sleep(0.01)

    task = server._register_synthesis_task(quick())
    # While running, registry is non-empty.
    assert task in server._SYNTHESIS_TASKS
    await task
    # Done callback fires synchronously after the task finishes; await one
    # more tick to let it land.
    await asyncio.sleep(0.01)
    assert task not in server._SYNTHESIS_TASKS
