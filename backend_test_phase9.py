#!/usr/bin/env python3
"""Phase 9 hotfix backend verification sweep.

Covers:
  A. /api/openapi.json enumerates exactly 36 /api/* paths and includes
     POST /api/admin/sessions/{session_id}/resynthesize.
  B. POST /api/assessment/processing/start now returns
     detail.reason ∈ {"stage_mismatch", "missing_inputs"} on 409.
  C. POST /api/admin/sessions/{id}/resynthesize:
       C1. 401 unauthenticated.
       C2. 404 unknown session.
       C3. 409 missing_inputs with detail.missing list.
       C4. 202 happy path: clears deliverable, sets synthesis to
           {status:in_progress, started_at, restarted_by, restarted_at},
           stage=processing, returns poll_url.
  D. Regression spot-checks across Phases 2-8.
  E. Privacy: public GET /api/sessions/{id} strips admin-only fields and
     reduces synthesis to {status, started_at, completed_at}.
  F. Log hygiene during the resynthesize call.

Run: python /app/backend_test_phase9.py
"""
import asyncio
import json
import os
import re
import sys
import time
from typing import Any, Dict, Optional

import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASSWORD = "test1234"
ADA_SID = "2253141a-830f-4810-a683-890f098b5664"

PASS, FAIL = 0, 0
FAILURES = []


def _ok(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    mark = "✓" if ok else "✗"
    msg = f"  {mark} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if ok:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(label + (f" — {detail}" if detail else ""))


def admin_login() -> str:
    r = requests.post(
        f"{BASE}/admin/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Admin login failed: {r.status_code} {r.text}")
    sc = r.headers.get("Set-Cookie", "")
    m = re.search(r"tra_admin_token=([^;]+)", sc)
    if not m:
        raise RuntimeError(f"No tra_admin_token in Set-Cookie: {sc}")
    return m.group(1)


def admin_headers(token: str) -> Dict[str, str]:
    return {"Cookie": f"tra_admin_token={token}"}


# ---------------------------------------------------------------------------
# A. OpenAPI surface
# ---------------------------------------------------------------------------
def test_openapi():
    print("\n[A] OpenAPI /api/* surface (expect 36 paths inc. resynthesize)")
    r = requests.get(f"{BASE}/openapi.json", timeout=10)
    _ok("A0 200 OK", r.status_code == 200)
    paths = [p for p in r.json().get("paths", {}) if p.startswith("/api/")]
    _ok("A1 exactly 36 /api/* paths", len(paths) == 36, f"got {len(paths)}")
    _ok(
        "A2 /api/admin/sessions/{session_id}/resynthesize present",
        "/api/admin/sessions/{session_id}/resynthesize" in paths,
    )


# ---------------------------------------------------------------------------
# B. /processing/start 409 reason shape
# ---------------------------------------------------------------------------
def test_processing_start_reasons(token: str):
    print("\n[B] /processing/start 409 detail.reason shape")
    # B1 stage_mismatch — fresh session (stage=identity)
    r = requests.post(
        f"{BASE}/sessions",
        json={
            "consent": True,
            "name": "Grace Hopper",
            "email": "grace.test@navy-mil.example",
            "organisation": "USN",
            "role": "Rear Admiral",
        },
        headers={"X-Forwarded-For": "203.0.113.50"},
        timeout=10,
    )
    fresh_sid = r.json().get("session_id") if r.status_code == 201 else None
    _ok("B0 fresh session created", fresh_sid is not None,
        f"status={r.status_code}")

    if fresh_sid:
        r = requests.post(
            f"{BASE}/assessment/processing/start",
            json={"session_id": fresh_sid},
            timeout=10,
        )
        _ok("B1 409 returned", r.status_code == 409, f"got {r.status_code}")
        try:
            detail = r.json().get("detail", {})
        except Exception:
            detail = {}
        _ok(
            "B1.1 detail.reason == 'stage_mismatch'",
            isinstance(detail, dict) and detail.get("reason") == "stage_mismatch",
            f"detail={detail}",
        )
        _ok(
            "B1.2 detail.current_stage == 'identity'",
            isinstance(detail, dict) and detail.get("current_stage") == "identity",
        )

    # B2 missing_inputs — mutate a fresh session into stage=processing with
    # one score block missing.  Use the session seeded by
    # seed_phase7_test_session.py (full scores, stage=processing) and
    # temporarily strip scores.scenario.
    return fresh_sid


async def _mutate_remove_score_block(sid: str, key: str) -> Dict[str, Any]:
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = cli[os.environ.get("DB_NAME", "soe_tra")]
    backup = await db.sessions.find_one({"session_id": sid}, {"_id": 0})
    await db.sessions.update_one(
        {"session_id": sid}, {"$unset": {f"scores.{key}": ""}}
    )
    return backup or {}


async def _restore_doc(sid: str, backup: Dict[str, Any]) -> None:
    if not backup:
        return
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = cli[os.environ.get("DB_NAME", "soe_tra")]
    await db.sessions.replace_one({"session_id": sid}, backup)


def test_processing_start_missing_inputs(seeded_sid: str):
    print("\n[B-cont] /processing/start 409 missing_inputs")
    backup = asyncio.run(_mutate_remove_score_block(seeded_sid, "scenario"))
    try:
        r = requests.post(
            f"{BASE}/assessment/processing/start",
            json={"session_id": seeded_sid},
            timeout=10,
        )
        _ok("B2 409 returned", r.status_code == 409, f"got {r.status_code}")
        detail = r.json().get("detail", {}) if r.status_code == 409 else {}
        _ok(
            "B2.1 detail.reason == 'missing_inputs'",
            isinstance(detail, dict) and detail.get("reason") == "missing_inputs",
            f"detail={detail}",
        )
        missing = detail.get("missing") if isinstance(detail, dict) else None
        _ok(
            "B2.2 detail.missing is list with 'scenario'",
            isinstance(missing, list) and "scenario" in missing,
            f"missing={missing}",
        )
    finally:
        asyncio.run(_restore_doc(seeded_sid, backup))


# ---------------------------------------------------------------------------
# C. /admin/sessions/{id}/resynthesize
# ---------------------------------------------------------------------------
def test_resynthesize_unauth():
    print("\n[C1] resynthesize 401 unauthenticated")
    r = requests.post(
        f"{BASE}/admin/sessions/{ADA_SID}/resynthesize", timeout=10
    )
    _ok("C1 401", r.status_code == 401, f"got {r.status_code}")


def test_resynthesize_404(token: str):
    print("\n[C2] resynthesize 404 unknown session")
    r = requests.post(
        f"{BASE}/admin/sessions/00000000-0000-0000-0000-000000000000/resynthesize",
        headers=admin_headers(token),
        timeout=10,
    )
    _ok("C2 404", r.status_code == 404, f"got {r.status_code}")


def test_resynthesize_missing_inputs(token: str):
    print("\n[C3] resynthesize 409 missing_inputs")
    # Find any session in Mongo that already has at least one score block
    # missing; failing that, mutate a fresh one.

    async def _find():
        cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "soe_tra")]
        # Look for any session missing scores.scenario.
        async for d in db.sessions.find(
            {"$or": [
                {"scores.scenario": {"$exists": False}},
                {"scores.scenario": None},
            ]},
            {"_id": 0, "session_id": 1, "scores": 1},
        ):
            return d.get("session_id")
        return None

    sid = asyncio.run(_find())
    _ok("C3.0 candidate session found", sid is not None, f"sid={sid}")
    if not sid:
        return
    r = requests.post(
        f"{BASE}/admin/sessions/{sid}/resynthesize",
        headers=admin_headers(token),
        timeout=10,
    )
    _ok("C3 409 returned", r.status_code == 409, f"got {r.status_code}")
    detail = r.json().get("detail", {}) if r.status_code == 409 else {}
    _ok(
        "C3.1 detail.reason == 'missing_inputs'",
        isinstance(detail, dict) and detail.get("reason") == "missing_inputs",
        f"detail={detail}",
    )
    missing = detail.get("missing") if isinstance(detail, dict) else None
    _ok(
        "C3.2 detail.missing is list",
        isinstance(missing, list) and len(missing) > 0,
        f"missing={missing}",
    )


def test_resynthesize_happy_path(token: str):
    print("\n[C4] resynthesize 202 happy path on Ada session")

    async def _snapshot(sid):
        cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "soe_tra")]
        return await db.sessions.find_one({"session_id": sid}, {"_id": 0})

    async def _state(sid):
        cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "soe_tra")]
        return await db.sessions.find_one(
            {"session_id": sid},
            {"_id": 0, "stage": 1, "synthesis": 1, "deliverable": 1},
        )

    snapshot_before = asyncio.run(_snapshot(ADA_SID))
    if not snapshot_before:
        _ok("C4.0 Ada session exists", False, "snapshot is None")
        return
    _ok("C4.0 Ada session exists", True)

    t0 = time.time()
    r = requests.post(
        f"{BASE}/admin/sessions/{ADA_SID}/resynthesize",
        headers=admin_headers(token),
        timeout=10,
    )
    elapsed = time.time() - t0
    _ok("C4.1 202 status", r.status_code == 202,
        f"got {r.status_code} body={r.text[:200]}")
    body = r.json() if r.status_code == 202 else {}
    _ok("C4.2 status='in_progress'", body.get("status") == "in_progress",
        f"body={body}")
    _ok("C4.3 started_at present", isinstance(body.get("started_at"), str),
        f"started_at={body.get('started_at')}")
    _ok("C4.4 poll_url present", isinstance(body.get("poll_url"), str)
        and body.get("poll_url", "").startswith("/api/"),
        f"poll_url={body.get('poll_url')}")
    _ok("C4.5 endpoint returned within 3s", elapsed < 3.0,
        f"elapsed={elapsed:.2f}s")

    # Inspect DB state within ~1s of the call
    state = asyncio.run(_state(ADA_SID))
    _ok("C4.6 deliverable cleared to None", state.get("deliverable") is None,
        f"deliverable={type(state.get('deliverable')).__name__}")
    syn = state.get("synthesis") or {}
    _ok("C4.7 synthesis.status == 'in_progress'",
        syn.get("status") == "in_progress", f"synthesis={syn}")
    _ok("C4.8 synthesis.started_at present",
        isinstance(syn.get("started_at"), str), f"started_at={syn.get('started_at')}")
    _ok("C4.9 synthesis.restarted_by == admin email",
        syn.get("restarted_by") == ADMIN_EMAIL,
        f"restarted_by={syn.get('restarted_by')}")
    _ok("C4.10 synthesis.restarted_at present",
        isinstance(syn.get("restarted_at"), str),
        f"restarted_at={syn.get('restarted_at')}")
    _ok("C4.11 stage == 'processing'", state.get("stage") == "processing",
        f"stage={state.get('stage')}")

    return snapshot_before


# ---------------------------------------------------------------------------
# D. Regression spot-checks Phases 2-8
# ---------------------------------------------------------------------------
def test_regressions(token: str):
    print("\n[D] Regression spot-checks Phases 2-8")
    # D1 POST /sessions
    r = requests.post(
        f"{BASE}/sessions",
        json={
            "consent": True,
            "name": "Edsger Dijkstra",
            "email": "edsger.test@cs-dept.example.nl",
            "organisation": "Eindhoven Univ",
            "role": "Professor",
        },
        headers={"X-Forwarded-For": "203.0.113.91"},
        timeout=10,
    )
    new_sid = r.json().get("session_id") if r.status_code == 201 else None
    _ok("D1 POST /sessions 201", r.status_code == 201,
        f"got {r.status_code}")
    rc = r.json().get("resume_code") if r.status_code == 201 else ""
    _ok("D1.1 resume_code matches XXXX-XXXX",
        bool(re.match(r"^[A-Z0-9]{4}-[A-Z0-9]{4}$", rc or "")),
        f"rc={rc}")

    # D2 PATCH stage transitions on the new session
    if new_sid:
        r = requests.patch(
            f"{BASE}/sessions/{new_sid}/stage", json={"stage": "context"}, timeout=10
        )
        _ok("D2 PATCH stage identity->context 200", r.status_code == 200,
            f"got {r.status_code}")
        r = requests.patch(
            f"{BASE}/sessions/{new_sid}/stage", json={"stage": "psychometric"},
            timeout=10,
        )
        _ok("D2.1 PATCH stage context->psychometric 200",
            r.status_code == 200, f"got {r.status_code}")

        # D3 psychometric next/answer
        r = requests.get(
            f"{BASE}/assessment/psychometric/next?session_id={new_sid}",
            timeout=10,
        )
        _ok("D3 GET psychometric/next 200", r.status_code == 200,
            f"got {r.status_code}")
        item_id = (r.json() or {}).get("item", {}).get("item_id")
        if item_id:
            r = requests.post(
                f"{BASE}/assessment/psychometric/answer",
                json={
                    "session_id": new_sid,
                    "item_id": item_id,
                    "value": 4,
                    "response_time_ms": 1500,
                },
                timeout=10,
            )
            _ok("D3.1 POST psychometric/answer 200",
                r.status_code == 200, f"got {r.status_code}")

    # D4 ai-discussion start / state — use Ada (her stage was reset to
    # processing by C4; ai-discussion was already complete pre-test).  Use
    # GET /state which is gated to ai-discussion or later phases.
    r = requests.get(
        f"{BASE}/assessment/ai-discussion/state?session_id={ADA_SID}",
        timeout=10,
    )
    _ok("D4 GET ai-discussion/state on Ada 200",
        r.status_code == 200, f"got {r.status_code}")

    # D5 scenario state (Ada — she's scenario-complete)
    r = requests.get(
        f"{BASE}/assessment/scenario/state?session_id={ADA_SID}",
        timeout=10,
    )
    _ok("D5 GET scenario/state on Ada 200", r.status_code == 200,
        f"got {r.status_code}")

    # D5b scenario advance read->part1 happy path on a session that's actually
    # at scenario stage — use a freshly seeded one.
    # We already have one (seeded earlier in test_processing_start_reasons).
    # Skip — not strictly required for regression coverage of the live
    # transition; we already know it works from Phase 6 tests.

    # D6 admin login + admin endpoints
    r = requests.get(
        f"{BASE}/admin/sessions/{ADA_SID}",
        headers=admin_headers(token),
        timeout=10,
    )
    _ok("D6 admin GET /admin/sessions/{ada} 200",
        r.status_code == 200, f"got {r.status_code}")
    body = r.json() if r.status_code == 200 else {}
    _ok("D6.1 admin doc has scores", isinstance(body.get("scores"), dict))
    # D7 PATCH archived toggle (true then false)
    r1 = requests.patch(
        f"{BASE}/admin/sessions/{ADA_SID}",
        json={"archived": True},
        headers=admin_headers(token),
        timeout=10,
    )
    _ok("D7 PATCH archived=true 200", r1.status_code == 200,
        f"got {r1.status_code}")
    r2 = requests.patch(
        f"{BASE}/admin/sessions/{ADA_SID}",
        json={"archived": False},
        headers=admin_headers(token),
        timeout=10,
    )
    _ok("D7.1 PATCH archived=false 200", r2.status_code == 200,
        f"got {r2.status_code}")

    # D8 dashboard/summary
    r = requests.get(
        f"{BASE}/admin/dashboard/summary",
        headers=admin_headers(token),
        timeout=10,
    )
    _ok("D8 admin/dashboard/summary 200", r.status_code == 200,
        f"got {r.status_code}")

    # D9 lifecycle/run
    r = requests.post(
        f"{BASE}/admin/lifecycle/run",
        headers=admin_headers(token),
        timeout=20,
    )
    _ok("D9 admin/lifecycle/run 200", r.status_code == 200,
        f"got {r.status_code}")


# ---------------------------------------------------------------------------
# E. Privacy regression: public GET /api/sessions/{id}
# ---------------------------------------------------------------------------
def test_privacy_public_session():
    print("\n[E] Privacy: public GET /api/sessions/{ada} strips admin fields")
    r = requests.get(f"{BASE}/sessions/{ADA_SID}", timeout=10)
    _ok("E0 200", r.status_code == 200, f"got {r.status_code}")
    body = r.json() if r.status_code == 200 else {}
    for forbidden in (
        "admin_notes",
        "last_admin_viewed_at",
        "deleted_at",
        "hard_delete_at",
        "redacted",
    ):
        _ok(f"E1 {forbidden} ABSENT", forbidden not in body,
            f"value={body.get(forbidden)}")
    syn = body.get("synthesis")
    _ok("E2 synthesis is dict", isinstance(syn, dict),
        f"synthesis={type(syn).__name__}")
    if isinstance(syn, dict):
        keys = set(syn.keys())
        expected = {"status", "started_at", "completed_at"}
        _ok(
            "E2.1 synthesis keys == {status, started_at, completed_at}",
            keys == expected,
            f"got {sorted(keys)}",
        )
        for forbidden in ("provider", "model", "fallbacks_tried", "error",
                          "restarted_by", "restarted_at"):
            _ok(f"E2.2 synthesis.{forbidden} ABSENT",
                forbidden not in syn,
                f"value={syn.get(forbidden)}")


# ---------------------------------------------------------------------------
# F. Log hygiene during the resynthesize call
# ---------------------------------------------------------------------------
def test_log_hygiene():
    print("\n[F] Log hygiene during resynthesize call")
    # Tail recent backend logs and check for required INFO lines + absence
    # of PII / api keys / full prompts.
    paths = [
        "/var/log/supervisor/backend.out.log",
        "/var/log/supervisor/backend.err.log",
    ]
    blob = ""
    for p in paths:
        try:
            with open(p, "r", errors="ignore") as f:
                blob += f.read()[-200000:]  # tail
        except Exception:
            pass
    _ok("F1 contains 'Admin re-synthesis triggered session=' marker",
        "Admin re-synthesis triggered session=" in blob)
    _ok("F2 contains the admin email in re-synth log",
        f"by={ADMIN_EMAIL}" in blob,
        "log line should record by=<admin_email>")
    # PII checks on Ada participant fields
    pii_needles = {
        "ada.test@example.co.uk": "Ada email",
        "Analytical Engine Co": "Ada org",
    }
    for needle, label in pii_needles.items():
        # Filter to INFO-ish lines only — check whole tail; report any hit.
        hits = [
            ln
            for ln in blob.splitlines()
            if needle in ln and ("INFO" in ln or "ERROR" in ln or "WARNING" in ln)
        ]
        _ok(f"F3 {label} not in INFO/WARN/ERROR log lines", len(hits) == 0,
            f"hits={hits[:2]}")
    # API-key fragments
    for prefix in ("sk-emergent-", "sk-ant-", "sk-proj-"):
        # only flag fragments that are not the env var name itself
        hits = [
            ln for ln in blob.splitlines()
            if prefix in ln and "EMERGENT_LLM_KEY" not in ln
        ]
        _ok(f"F4 no '{prefix}' fragments in logs",
            len(hits) == 0, f"hits={hits[:2]}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print(f"Target: {BASE}")
    token = admin_login()
    print(f"Admin JWT cookie obtained ({len(token)} chars)")

    test_openapi()

    fresh_sid = test_processing_start_reasons(token)

    # Use the seeded session for missing-inputs check
    print("\n[setup] Seeding a fresh phase-7 test session for B2 missing_inputs")
    import subprocess
    out = subprocess.check_output(
        ["python", "/app/backend/seed_phase7_test_session.py"],
        text=True,
    )
    seeded_sid = out.strip().splitlines()[-2]
    print(f"  seeded sid: {seeded_sid}")
    test_processing_start_missing_inputs(seeded_sid)

    test_resynthesize_unauth()
    test_resynthesize_404(token)
    test_resynthesize_missing_inputs(token)

    # Privacy + regression FIRST (Ada is in stable completed state)
    test_privacy_public_session()
    test_regressions(token)

    # Now trigger the resynth (this will block the event loop for ~2min while
    # the LLM call runs, but we only need the IMMEDIATE post-call DB state).
    test_resynthesize_happy_path(token)

    # Log hygiene check — should now see the "Admin re-synthesis triggered"
    # marker from the C4 call.
    time.sleep(2)
    test_log_hygiene()

    print(f"\n{'='*60}")
    print(f"SUMMARY: {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print(f"  - {f}")
    print('='*60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
