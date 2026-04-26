#!/usr/bin/env python3
"""Phase 9 hotfix bundle — TIGHT regression.

Buckets covered:
  1. POST /api/admin/sessions/{id}/resynthesize (Patch G6)
       - 401 unauthenticated
       - 404 unknown session
       - 409 detail.reason == "missing_inputs" on freshly-created session
       - 202 in_progress + restarted_by == JWT.sub on a fully-scored session
  2. POST /api/assessment/processing/start error shape (Patch G1)
       - 409 detail is OBJECT (dict) with `reason` ∈ {stage_mismatch, missing_inputs}
  3. Background-task registry (Patches G4 + G5)
       - source-evidence inspection of /app/backend/server.py
  4. Smoke regression
       - GET  /api/health
       - POST /api/sessions
       - PATCH /api/sessions/{id}/stage  (psychometric)
       - POST /api/admin/auth/login
       - GET  /api/admin/sessions  (with admin JWT)
       - GET  /api/admin/dashboard/summary

Usage: python /app/backend_test.py
"""
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(Path("/app/backend/.env"))

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASSWORD = "test1234"
ADA_SID = "2253141a-830f-4810-a683-890f098b5664"

PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES: list = []


def report(label: str, ok: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    mark = "PASS" if ok else "FAIL"
    msg = f"  [{mark}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if ok:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
        FAILURES.append(label + (f" — {detail}" if detail else ""))


def admin_login_cookie() -> str:
    """Login and extract the raw JWT cookie value (Secure cookie can't replay
    over http:// via requests.Session)."""
    r = requests.post(
        f"{BASE}/admin/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    set_cookie = r.headers.get("set-cookie", "")
    m = re.search(r"tra_admin_token=([^;]+)", set_cookie)
    assert m, f"no tra_admin_token cookie in Set-Cookie header: {set_cookie!r}"
    return m.group(1)


def auth_headers(jwt: str) -> Dict[str, str]:
    return {"Cookie": f"tra_admin_token={jwt}"}


def bucket_smoke(jwt: str) -> Optional[str]:
    print("\n=== Bucket 4: smoke regression ===")

    r = requests.get(f"{BASE}/health", timeout=10)
    report("GET /api/health → 200 + {status:'ok'}",
           r.status_code == 200 and r.json().get("status") == "ok",
           f"status={r.status_code}")

    payload = {
        "name": "Grace Hopper",
        "email": "grace.hopper.regr@navy-research.example",
        "organisation": "USS Compiler",
        "role": "Rear Admiral",
        "consent": True,
    }
    r = requests.post(f"{BASE}/sessions", json=payload, timeout=15)
    sid: Optional[str] = None
    if r.status_code in (200, 201):
        body = r.json()
        sid = body.get("session_id")
        report("POST /api/sessions → 201 + session_id + resume_code",
               bool(sid) and bool(body.get("resume_code")),
               f"session_id={sid} resume_code={body.get('resume_code')}")
    else:
        report("POST /api/sessions → 201 + session_id + resume_code", False,
               f"status={r.status_code} body={r.text[:200]}")

    if sid:
        # Stage transitions are sequential (one step at a time): identity → context → psychometric
        r1 = requests.patch(f"{BASE}/sessions/{sid}/stage",
                            json={"stage": "context"}, timeout=10)
        r2 = requests.patch(f"{BASE}/sessions/{sid}/stage",
                            json={"stage": "psychometric"}, timeout=10)
        report("PATCH /api/sessions/{id}/stage stage=psychometric → 200",
               r2.status_code == 200 and r2.json().get("stage") == "psychometric",
               f"context_status={r1.status_code} psych_status={r2.status_code} body={r2.text[:160]}")
    else:
        report("PATCH /api/sessions/{id}/stage stage=psychometric → 200", False,
               "skipped — no session_id")

    report("POST /api/admin/auth/login → 200 + cookie",
           bool(jwt),
           f"jwt_prefix={jwt[:24]}…")

    r = requests.get(f"{BASE}/admin/sessions", headers=auth_headers(jwt), timeout=15)
    if r.status_code == 200:
        body = r.json()
        # admin_list_sessions returns {items, total, page, page_size, filters_applied}
        items = body.get("items") if isinstance(body, dict) else None
        if items is None and isinstance(body, dict):
            items = body.get("sessions")
        ok = isinstance(items, list)
        report("GET /api/admin/sessions → 200 + sessions array",
               ok, f"count={len(items) if isinstance(items, list) else 'N/A'} total={body.get('total') if isinstance(body, dict) else 'N/A'}")
    else:
        report("GET /api/admin/sessions → 200 + sessions array", False,
               f"status={r.status_code} body={r.text[:160]}")

    r = requests.get(f"{BASE}/admin/dashboard/summary", headers=auth_headers(jwt), timeout=15)
    report("GET /api/admin/dashboard/summary → 200",
           r.status_code == 200,
           f"status={r.status_code}")

    return sid


def bucket_resynth(jwt: str, fresh_sid: Optional[str]) -> None:
    print("\n=== Bucket 1: POST /api/admin/sessions/{id}/resynthesize (G6) ===")

    # 1.1 — 401 without admin JWT
    r = requests.post(f"{BASE}/admin/sessions/anything/resynthesize", timeout=10)
    report("401 returned without admin JWT",
           r.status_code == 401,
           f"status={r.status_code} body={r.text[:120]}")

    # 1.2 — 404 on unknown session
    bogus = "00000000-0000-0000-0000-000000000000"
    r = requests.post(f"{BASE}/admin/sessions/{bogus}/resynthesize",
                      headers=auth_headers(jwt), timeout=10)
    report("404 returned on unknown session id",
           r.status_code == 404,
           f"status={r.status_code} body={r.text[:120]}")

    # 1.3 — 409 missing_inputs on freshly-created session
    if fresh_sid:
        r = requests.post(f"{BASE}/admin/sessions/{fresh_sid}/resynthesize",
                          headers=auth_headers(jwt), timeout=10)
        ok = r.status_code == 409
        detail_obj = False
        reason_ok = False
        if ok:
            try:
                detail = r.json().get("detail")
                detail_obj = isinstance(detail, dict)
                reason_ok = detail_obj and detail.get("reason") == "missing_inputs"
            except Exception:
                pass
        report("409 + detail.reason == 'missing_inputs' on session w/o scores",
               ok and detail_obj and reason_ok,
               f"status={r.status_code} body={r.text[:200]}")
    else:
        report("409 + detail.reason == 'missing_inputs' on session w/o scores", False,
               "skipped — no fresh session_id")

    # 1.4 — 202 happy path on fully-scored session (Ada)
    r = requests.post(f"{BASE}/admin/sessions/{ADA_SID}/resynthesize",
                      headers=auth_headers(jwt), timeout=15)
    body: Dict[str, Any] = {}
    try:
        body = r.json()
    except Exception:
        pass
    ok202 = r.status_code == 202
    shape_ok = (
        body.get("status") == "in_progress"
        and bool(body.get("started_at"))
        and bool(body.get("poll_url"))
    )
    report("202 + body shape {status:'in_progress', started_at, poll_url}",
           ok202 and shape_ok,
           f"status={r.status_code} body={body}")

    # 1.5 — Mongo verification
    async def _check_mongo() -> tuple:
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ.get("DB_NAME", "soe_tra")]
        syn: Dict[str, Any] = {}
        for _ in range(8):
            d = await db.sessions.find_one({"session_id": ADA_SID}, {"_id": 0, "synthesis": 1})
            syn = (d or {}).get("synthesis") or {}
            if syn.get("status") == "in_progress":
                return syn.get("status"), syn.get("restarted_by"), syn.get("restarted_at")
            await asyncio.sleep(0.3)
        return syn.get("status"), syn.get("restarted_by"), syn.get("restarted_at")

    status, restarted_by, _ = asyncio.run(_check_mongo())
    report("synthesis.status → 'in_progress' in Mongo after 202",
           status == "in_progress",
           f"status={status}")
    report("synthesis.restarted_by == admin email (JWT.sub claim)",
           restarted_by == ADMIN_EMAIL,
           f"restarted_by={restarted_by!r} (expected {ADMIN_EMAIL!r})")


def bucket_processing_start_shape(fresh_sid: Optional[str]) -> None:
    print("\n=== Bucket 2: POST /api/assessment/processing/start error shape (G1) ===")
    if not fresh_sid:
        report("409 detail is OBJECT with reason in {stage_mismatch,missing_inputs}",
               False, "skipped — no fresh session_id")
        return

    # Fresh session at stage=psychometric → expect 409 with reason=stage_mismatch
    r = requests.post(f"{BASE}/assessment/processing/start",
                      json={"session_id": fresh_sid}, timeout=30)
    ok = r.status_code == 409
    detail_obj = False
    reason_ok = False
    reason_val = None
    if ok:
        try:
            detail = r.json().get("detail")
            detail_obj = isinstance(detail, dict)
            if detail_obj:
                reason_val = detail.get("reason")
                reason_ok = reason_val in ("stage_mismatch", "missing_inputs")
        except Exception:
            pass
    report("409 detail is OBJECT (dict), not string",
           ok and detail_obj,
           f"status={r.status_code} body={r.text[:200]}")
    report("409 detail.reason ∈ {stage_mismatch, missing_inputs}",
           reason_ok,
           f"reason={reason_val!r}")


def bucket_registry_source() -> None:
    print("\n=== Bucket 3: background-task registry source-evidence (G4+G5) ===")
    src = Path("/app/backend/server.py").read_text()

    has_set = re.search(r"^_SYNTHESIS_TASKS\s*:\s*set\s*=\s*set\(\)", src, re.M) is not None
    report("G5: module-level _SYNTHESIS_TASKS = set() declared",
           has_set, "see server.py ~line 1266")

    reg_match = re.search(
        r"def _register_synthesis_task\(coro\):.*?return task",
        src, re.S,
    )
    has_callback = (
        reg_match is not None
        and "_SYNTHESIS_TASKS.add(task)" in reg_match.group(0)
        and "add_done_callback(_SYNTHESIS_TASKS.discard)" in reg_match.group(0)
    )
    report("G5: _register_synthesis_task adds task + wires done-callback discard",
           has_callback, "see server.py ~lines 1269-1274")

    proc_match = re.search(
        r'@api_router\.post\(\s*"/assessment/processing/start".*?(?=@api_router|@admin_router|\Z)',
        src, re.S,
    )
    proc_uses = (
        proc_match is not None
        and "_register_synthesis_task(_run_synthesis_task" in proc_match.group(0)
    )
    report("/processing/start spawns via _register_synthesis_task",
           proc_uses, "see server.py ~line 1456")

    re_match = re.search(
        r"async def admin_resynthesize\(.*?(?=@admin_router|@api_router|\Z)",
        src, re.S,
    )
    re_uses = (
        re_match is not None
        and "_register_synthesis_task(_run_synthesis_task" in re_match.group(0)
    )
    report("/admin/sessions/{id}/resynthesize spawns via _register_synthesis_task",
           re_uses, "see server.py ~line 2153")

    worker_match = re.search(r"async def _run_synthesis_task\(.*?\n\ndef ", src, re.S)
    has_finally = (
        worker_match is not None
        and "finally:" in worker_match.group(0)
        and "synthesis.status" in worker_match.group(0)
        and "failed" in worker_match.group(0)
    )
    report("G4: _run_synthesis_task has finally-clause forcing terminal status",
           has_finally, "see server.py ~lines 1340-1380")


def main() -> int:
    print(f"Phase 9 hotfix regression — base={BASE}")
    try:
        jwt = admin_login_cookie()
    except Exception as e:
        print(f"FATAL: admin login failed: {e}")
        return 2

    fresh_sid = bucket_smoke(jwt)
    # Run bucket 2 BEFORE bucket 1 — bucket 1 spawns a long-running synth worker
    # for Ada that can stall the event loop while litellm blocks. /processing/start
    # is just an instant 409 lookup; do it while the loop is idle.
    bucket_processing_start_shape(fresh_sid)
    bucket_resynth(jwt, fresh_sid)
    bucket_registry_source()

    print("\n" + "=" * 60)
    print(f"RESULT: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print(f"  - {f}")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
