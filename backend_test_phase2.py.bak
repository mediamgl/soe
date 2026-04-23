"""
Backend API tests for Phase 2 — Transformation Readiness Assessment.

Tests the sessions API: POST/GET/PATCH + resume + validation + rate limiting + logs + docs.
Uses REACT_APP_BACKEND_URL from /app/frontend/.env so we hit the public ingress URL.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
FRONTEND_ENV = Path("/app/frontend/.env")
BACKEND_URL: Optional[str] = None
for line in FRONTEND_ENV.read_text().splitlines():
    if line.startswith("REACT_APP_BACKEND_URL="):
        BACKEND_URL = line.split("=", 1)[1].strip()
        break

assert BACKEND_URL, "REACT_APP_BACKEND_URL not found in /app/frontend/.env"
API = f"{BACKEND_URL}/api"

RESUME_CODE_RE = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

# --------------------------------------------------------------------------- #
# Tiny test harness
# --------------------------------------------------------------------------- #
results: List[Tuple[str, bool, str]] = []


def record(name: str, ok: bool, evidence: str = "") -> None:
    results.append((name, ok, evidence))
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name} :: {evidence}")


def _xff_headers(suffix: str) -> Dict[str, str]:
    """Unique X-Forwarded-For to avoid rate-limit collisions between tests."""
    # Use 203.0.113.x range (TEST-NET-3, safe to use in docs/tests)
    # suffix: deterministic-ish octet derived from name to spread across tests
    octet = (sum(ord(c) for c in suffix) % 250) + 2
    return {"X-Forwarded-For": f"203.0.113.{octet}"}


def _valid_payload(email_tag: str = "") -> Dict[str, Any]:
    tag = email_tag or uuid.uuid4().hex[:8]
    return {
        "name": "Alice Whittaker",
        "email": f"alice.whittaker+{tag}@example.com",
        "organisation": "Northstar Analytics",
        "role": "Head of People Operations",
        "consent": True,
    }


# --------------------------------------------------------------------------- #
# H. Docs
# --------------------------------------------------------------------------- #
def test_docs() -> None:
    r = requests.get(f"{API}/docs", timeout=15)
    ok = r.status_code == 200 and "swagger" in r.text.lower()
    record("H1 GET /api/docs returns 200 with Swagger UI", ok,
           f"status={r.status_code} len={len(r.text)}")

    r2 = requests.get(f"{API}/openapi.json", timeout=15)
    data = r2.json() if r2.ok else {}
    paths = data.get("paths", {}) if isinstance(data, dict) else {}
    required = [
        ("POST", "/api/sessions"),
        ("GET", "/api/sessions/resume/{resume_code}"),
        ("PATCH", "/api/sessions/{session_id}/stage"),
        ("GET", "/api/sessions/{session_id}"),
    ]
    missing = []
    for method, path in required:
        node = paths.get(path) or {}
        if method.lower() not in {k.lower() for k in node.keys()}:
            missing.append(f"{method} {path}")
    record(
        "H2 openapi.json lists the 4 session endpoints",
        len(missing) == 0,
        f"missing={missing}" if missing else f"all 4 present",
    )


# --------------------------------------------------------------------------- #
# A. Happy path: create session
# --------------------------------------------------------------------------- #
def test_create_session_happy() -> Dict[str, Any]:
    r = requests.post(
        f"{API}/sessions",
        json=_valid_payload("happy"),
        headers=_xff_headers("happy"),
        timeout=15,
    )
    ok = r.status_code == 201
    body = {}
    try:
        body = r.json()
    except Exception:
        pass
    record("A1 POST /api/sessions valid -> 201", ok,
           f"status={r.status_code} body={body}")

    sid = body.get("session_id", "")
    code = body.get("resume_code", "")
    stage = body.get("stage", "")

    record("A2 response has UUID session_id",
           bool(UUID_RE.match(sid)), f"session_id={sid}")
    record("A3 resume_code matches ^[A-Z0-9]{4}-[A-Z0-9]{4}$",
           bool(RESUME_CODE_RE.match(code)), f"resume_code={code}")
    record("A4 stage == 'identity'", stage == "identity", f"stage={stage}")
    return body


# --------------------------------------------------------------------------- #
# B. Input validation
# --------------------------------------------------------------------------- #
def test_validation() -> None:
    cases = [
        ("B1 missing consent", {k: v for k, v in _valid_payload("b1").items() if k != "consent"}),
        ("B2 consent=false",   {**_valid_payload("b2"), "consent": False}),
        ("B3 name missing",    {k: v for k, v in _valid_payload("b3").items() if k != "name"}),
        ("B4 name empty str",  {**_valid_payload("b4"), "name": ""}),
        ("B5 name whitespace", {**_valid_payload("b5"), "name": "   "}),
        ("B6 email no @",      {**_valid_payload("b6"), "email": "not-an-email"}),
    ]
    for label, payload in cases:
        r = requests.post(
            f"{API}/sessions",
            json=payload,
            headers=_xff_headers(label),
            timeout=15,
        )
        ok422 = r.status_code == 422
        body = {}
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:200]}
        has_detail = isinstance(body, dict) and "detail" in body
        record(
            f"{label} -> 422 with detail",
            ok422 and has_detail,
            f"status={r.status_code} detail_keys={list(body.keys()) if isinstance(body, dict) else 'n/a'}",
        )

    # Bad JSON body
    r = requests.post(
        f"{API}/sessions",
        data="{not valid json,,,}",
        headers={"Content-Type": "application/json", **_xff_headers("B7")},
        timeout=15,
    )
    ok = r.status_code in (400, 422)
    record("B7 bad JSON body -> 400/422 (not 500)", ok,
           f"status={r.status_code}")


# --------------------------------------------------------------------------- #
# C. Resume flow
# --------------------------------------------------------------------------- #
def test_resume(happy_session: Dict[str, Any]) -> None:
    code = happy_session.get("resume_code", "")
    sid = happy_session.get("session_id", "")

    # C1 valid code with dash
    r = requests.get(f"{API}/sessions/resume/{code}", timeout=15)
    body = r.json() if r.ok else {}
    ok = (
        r.status_code == 200
        and body.get("session_id") == sid
        and body.get("stage") == "identity"
        and isinstance(body.get("participant"), dict)
        and body["participant"].get("email", "").startswith("alice.whittaker+happy")
    )
    record("C1 GET /sessions/resume/{code} with dash -> 200", ok,
           f"status={r.status_code} body_keys={list(body.keys())}")

    # C2 code without dash normalises
    code_nodash = code.replace("-", "")
    r = requests.get(f"{API}/sessions/resume/{code_nodash}", timeout=15)
    body = r.json() if r.ok else {}
    ok = r.status_code == 200 and body.get("session_id") == sid
    record("C2 code without dash normalises -> 200", ok,
           f"status={r.status_code} session_id_match={body.get('session_id') == sid}")

    # C3 unknown code -> 404
    r = requests.get(f"{API}/sessions/resume/ZZZZ-ZZZZ", timeout=15)
    body = r.json() if r.ok or r.status_code == 404 else {}
    ok = r.status_code == 404 and body.get("detail") == "Resume code not found."
    record("C3 unknown code -> 404 with 'Resume code not found.'", ok,
           f"status={r.status_code} body={body}")


# --------------------------------------------------------------------------- #
# D. Stage transitions
# --------------------------------------------------------------------------- #
def _patch_stage(sid: str, stage: str, xff_key: str = "d") -> requests.Response:
    return requests.patch(
        f"{API}/sessions/{sid}/stage",
        json={"stage": stage},
        headers=_xff_headers(xff_key),
        timeout=15,
    )


def test_stage_transitions() -> None:
    # Create a fresh session for the happy forward-path walk
    create = requests.post(
        f"{API}/sessions",
        json=_valid_payload("walk"),
        headers=_xff_headers("walk-create"),
        timeout=15,
    )
    assert create.status_code == 201, f"setup failed: {create.status_code} {create.text}"
    sid = create.json()["session_id"]

    # D1 Walk forward through all stages
    path = ["context", "psychometric", "ai-discussion", "scenario", "processing", "results"]
    all_ok = True
    evidence = []
    for stg in path:
        r = _patch_stage(sid, stg, xff_key=f"walk-{stg}")
        if r.status_code != 200:
            all_ok = False
            evidence.append(f"{stg}:status={r.status_code}:{r.text[:120]}")
            break
        body = r.json()
        if body.get("stage") != stg or "updated_at" not in body:
            all_ok = False
            evidence.append(f"{stg}:bad_body:{body}")
            break
        evidence.append(f"{stg}:ok")
    record("D1 Walk identity->context->...->results (all 200, stage+updated_at)",
           all_ok, "; ".join(evidence))

    # D2 Session record shows completed+expires_at=completed_at+60d
    r = requests.get(f"{API}/sessions/{sid}", timeout=15)
    ok = r.status_code == 200
    body = r.json() if ok else {}
    completed_at = body.get("completed_at")
    expires_at = body.get("expires_at")
    status = body.get("status")
    exp_ok = False
    delta_evidence = ""
    if completed_at and expires_at:
        try:
            c_dt = datetime.fromisoformat(completed_at)
            e_dt = datetime.fromisoformat(expires_at)
            delta = e_dt - c_dt
            # Allow +-1s tolerance
            exp_ok = abs((delta - timedelta(days=60)).total_seconds()) < 2
            delta_evidence = f"delta={delta}"
        except Exception as exc:
            delta_evidence = f"parse_err={exc}"
    d2_ok = (
        ok
        and status == "completed"
        and completed_at is not None
        and expires_at is not None
        and exp_ok
    )
    record(
        "D2 Reaching 'results' sets status=completed, completed_at, expires_at=completed_at+60d",
        d2_ok,
        f"status={status} completed_at={completed_at} expires_at={expires_at} {delta_evidence}",
    )

    # D3 Back by 1 stage allowed — fresh session
    create2 = requests.post(f"{API}/sessions", json=_valid_payload("back"),
                            headers=_xff_headers("back-create"), timeout=15)
    sid2 = create2.json()["session_id"]
    # advance to psychometric
    assert _patch_stage(sid2, "context", "back-a").status_code == 200
    assert _patch_stage(sid2, "psychometric", "back-b").status_code == 200
    r = _patch_stage(sid2, "context", "back-c")
    record("D3 back by one stage (psychometric->context) -> 200",
           r.status_code == 200, f"status={r.status_code} body={r.text[:120]}")

    # D4 Stay allowed (context -> context)
    r = _patch_stage(sid2, "context", "stay")
    record("D4 stay at same stage (context->context) -> 200",
           r.status_code == 200, f"status={r.status_code}")

    # D5 Skip stages rejected (context -> scenario)
    r = _patch_stage(sid2, "scenario", "skip")
    body = r.json() if r.status_code == 400 else {}
    record("D5 skip forward (context->scenario) -> 400",
           r.status_code == 400 and "detail" in body,
           f"status={r.status_code} detail={body.get('detail', '')[:160]}")

    # D6 Unknown stage value -> 422 with literal_error
    r = _patch_stage(sid2, "bananas", "bad-stage")
    body = r.json() if r.status_code == 422 else {}
    # body.detail is list of error dicts
    literal_err = False
    if isinstance(body, dict):
        det = body.get("detail")
        if isinstance(det, list):
            for e in det:
                if isinstance(e, dict) and "literal_error" in (e.get("type") or ""):
                    literal_err = True
                    break
    record("D6 unknown stage 'bananas' -> 422 with literal_error",
           r.status_code == 422 and literal_err,
           f"status={r.status_code} body={str(body)[:240]}")

    # D7 PATCH on non-existent session id -> 404
    bogus = str(uuid.uuid4())
    r = _patch_stage(bogus, "context", "nope")
    body = r.json() if r.status_code == 404 else {}
    record("D7 PATCH on non-existent session -> 404",
           r.status_code == 404 and body.get("detail") == "Session not found.",
           f"status={r.status_code} body={body}")


# --------------------------------------------------------------------------- #
# E. GET /api/sessions/{id}
# --------------------------------------------------------------------------- #
def test_get_session(happy_session: Dict[str, Any]) -> None:
    sid = happy_session.get("session_id", "")
    r = requests.get(f"{API}/sessions/{sid}", timeout=15)
    ok = r.status_code == 200
    body = r.json() if ok else {}
    expected_keys = {
        "session_id", "resume_code", "stage", "status", "participant",
        "answers", "conversation", "scenario_responses", "deliverable",
        "scores", "archived", "created_at", "updated_at", "completed_at", "expires_at",
    }
    missing = expected_keys - set(body.keys()) if isinstance(body, dict) else expected_keys
    record("E1 GET /sessions/{id} returns full dict with expected keys",
           ok and not missing,
           f"status={r.status_code} missing_keys={missing}")

    # Value checks
    part = body.get("participant", {}) if isinstance(body, dict) else {}
    participant_ok = (
        isinstance(part, dict)
        and part.get("name") == "Alice Whittaker"
        and part.get("email", "").startswith("alice.whittaker+happy")
        and part.get("organisation") == "Northstar Analytics"
        and part.get("role") == "Head of People Operations"
    )
    record("E2 participant{name,email,organisation,role} matches",
           participant_ok, f"participant={part}")

    defaults_ok = (
        body.get("answers") == []
        and body.get("conversation") == []
        and body.get("scenario_responses") == {}
        and body.get("deliverable") is None
        and body.get("scores") is None
        and body.get("archived") is False
    )
    record("E3 defaults answers=[], conversation=[], scenario_responses={}, "
           "deliverable=null, scores=null, archived=false",
           defaults_ok,
           f"answers={body.get('answers')} conv={body.get('conversation')} "
           f"scen={body.get('scenario_responses')} del={body.get('deliverable')} "
           f"scores={body.get('scores')} archived={body.get('archived')}")

    # E4 bogus id -> 404
    r = requests.get(f"{API}/sessions/{uuid.uuid4()}", timeout=15)
    body = r.json() if r.status_code == 404 else {}
    record("E4 GET /sessions/{bogus} -> 404",
           r.status_code == 404 and body.get("detail") == "Session not found.",
           f"status={r.status_code} body={body}")


# --------------------------------------------------------------------------- #
# F. Rate limiting (10/hr/IP)
# --------------------------------------------------------------------------- #
def test_rate_limit() -> None:
    # Pick a brand-new XFF ip that hasn't been used so far (>250 wraps modulo)
    # Use an IP outside 203.0.113.0/24 to avoid any collisions.
    rate_headers = {"X-Forwarded-For": "198.51.100.77"}
    statuses: List[int] = []
    for i in range(10):
        r = requests.post(
            f"{API}/sessions",
            json=_valid_payload(f"rate{i}"),
            headers=rate_headers,
            timeout=15,
        )
        statuses.append(r.status_code)
    eleven = requests.post(
        f"{API}/sessions",
        json=_valid_payload("rate10"),
        headers=rate_headers,
        timeout=15,
    )
    all10_ok = all(s == 201 for s in statuses)
    eleventh_429 = eleven.status_code == 429
    try:
        body11 = eleven.json()
    except Exception:
        body11 = {}
    detail = body11.get("detail", "") if isinstance(body11, dict) else ""
    msg_ok = "Too many sessions from this IP" in detail
    record(
        "F1 first 10 POSTs from same IP -> 201",
        all10_ok,
        f"statuses={statuses}",
    )
    record(
        "F2 11th POST from same IP -> 429 'Too many sessions from this IP.'",
        eleventh_429 and msg_ok,
        f"status={eleven.status_code} detail={detail!r}",
    )


# --------------------------------------------------------------------------- #
# G. Hygiene: no participant PII in backend.out.log at INFO
# --------------------------------------------------------------------------- #
def test_no_pii_in_logs() -> None:
    log_path = "/var/log/supervisor/backend.out.log"
    if not os.path.exists(log_path):
        record("G1 backend.out.log exists", False, f"missing: {log_path}")
        return
    try:
        data = subprocess.check_output(["tail", "-n", "2000", log_path],
                                       stderr=subprocess.STDOUT, text=True)
    except Exception as exc:
        record("G1 tail backend.out.log", False, f"err={exc}")
        return

    # Look for emails and specific name of participant used in tests
    email_hits = re.findall(r"[\w\.+-]+@[\w\.-]+\.\w+", data)
    name_hits = [l for l in data.splitlines() if "Alice Whittaker" in l]

    # Our create_session uses logger.info without PII. Presence of our test
    # participant's email or name on an INFO line would be a failure. We're
    # lenient about emails that appear only on DEBUG lines (filter those out).
    info_lines_with_email: List[str] = []
    for line in data.splitlines():
        if " INFO " in line or " - INFO - " in line:
            for em in re.findall(r"[\w\.+-]+@[\w\.-]+\.\w+", line):
                # only flag emails from our test domain to avoid false positives
                if em.endswith("@example.com"):
                    info_lines_with_email.append(line.strip())
                    break

    info_lines_with_name: List[str] = []
    for line in data.splitlines():
        if ("Alice Whittaker" in line) and (" INFO " in line or " - INFO - " in line):
            info_lines_with_name.append(line.strip())

    clean = not info_lines_with_email and not info_lines_with_name
    record(
        "G1 No participant email/name at INFO level in backend.out.log",
        clean,
        f"info_lines_with_email={len(info_lines_with_email)} "
        f"info_lines_with_name={len(info_lines_with_name)} "
        f"(sample_email_lines={info_lines_with_email[:2]}, "
        f"sample_name_lines={info_lines_with_name[:2]})",
    )


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def main() -> int:
    print(f"API = {API}")
    # Sanity ping first
    r = requests.get(f"{API}/health", timeout=15)
    record("API /health reachable", r.status_code == 200,
           f"status={r.status_code}")

    test_docs()

    happy = test_create_session_happy()

    test_validation()

    if happy.get("session_id"):
        test_resume(happy)
        test_get_session(happy)

    test_stage_transitions()

    test_rate_limit()

    test_no_pii_in_logs()

    # Summary
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print("\n" + "=" * 70)
    print(f"TOTAL: {passed}/{total} passed")
    print("=" * 70)
    failed = [(n, e) for (n, ok, e) in results if not ok]
    if failed:
        print("\nFAILURES:")
        for n, e in failed:
            print(f"  - {n}\n      {e}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
