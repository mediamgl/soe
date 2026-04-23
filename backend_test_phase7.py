"""
Phase 7 backend tests — Processing / Results / Synthesis.

Runs against http://localhost:8001/api. Reuses pre-seeded Ada Lovelace session
for most checks; mints ONE fresh seed for live synthesis verification.
"""
import json
import os
import re
import sys
import time
import uuid
import random
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASSWORD = "test1234"

ADA_SESSION = "2253141a-830f-4810-a683-890f098b5664"
ADA_RESUME = "7M7A-X5F5"

results: List[Tuple[str, bool, str]] = []


def record(letter: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    # Truncate long details
    msg = detail if len(detail) < 400 else detail[:400] + "..."
    print(f"[{status}] {letter}: {msg}")
    results.append((letter, ok, detail))


def rand_ip() -> str:
    return f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def admin_cookie() -> str:
    r = requests.post(f"{BASE}/admin/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      headers={"X-Forwarded-For": rand_ip()},
                      timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    jwt = r.cookies.get("admin_jwt") or r.cookies.get("access_token")
    if not jwt:
        # scan all Set-Cookie headers
        for k, v in r.cookies.items():
            jwt = v
            break
    # Fallback — look at raw Set-Cookie header
    if not jwt:
        sc = r.headers.get("Set-Cookie", "")
        m = re.search(r"([a-zA-Z_\-]+_?jwt|access_token)=([^;]+)", sc)
        if m:
            jwt = m.group(2)
    assert jwt, f"No JWT cookie found; headers={dict(r.headers)}"
    # find key name
    set_cookie = r.headers.get("Set-Cookie", "")
    m = re.search(r"(\w+)=([^;]+)", set_cookie)
    cname, cval = (m.group(1), m.group(2)) if m else ("admin_jwt", jwt)
    return f"{cname}={cval}"


def seed_fresh() -> Tuple[str, str]:
    """Run /app/backend/seed_phase7_test_session.py and parse session_id + resume."""
    out = subprocess.check_output(
        ["python", "/app/backend/seed_phase7_test_session.py"],
        cwd="/app/backend", timeout=30,
    ).decode().strip().splitlines()
    return out[0].strip(), out[1].strip()


def mongo_update(session_id: str, update_dict: Dict[str, Any]):
    """Run mongosh update directly to mutate a session doc."""
    # Use pymongo since motor is async
    import pymongo
    mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    # Read from backend .env if needed
    if not mongo_url or mongo_url == "mongodb://localhost:27017":
        try:
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("MONGO_URL="):
                        mongo_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if line.startswith("DB_NAME="):
                        dbname = line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    dbname = os.environ.get("DB_NAME", "soe_tra")
    try:
        with open("/app/backend/.env") as f:
            for line in f:
                if line.startswith("DB_NAME="):
                    dbname = line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    cli = pymongo.MongoClient(mongo_url)
    cli[dbname]["sessions"].update_one({"session_id": session_id}, {"$set": update_dict})
    cli.close()


def mongo_fetch(session_id: str) -> Dict[str, Any]:
    import pymongo
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    try:
        with open("/app/backend/.env") as f:
            for line in f:
                if line.startswith("MONGO_URL="):
                    mongo_url = line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    dbname = "soe_tra"
    try:
        with open("/app/backend/.env") as f:
            for line in f:
                if line.startswith("DB_NAME="):
                    dbname = line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    cli = pymongo.MongoClient(mongo_url)
    d = cli[dbname]["sessions"].find_one({"session_id": session_id})
    cli.close()
    return d


# --------------------------------------------------------------------------- #
# A. OpenAPI enumeration
# --------------------------------------------------------------------------- #
def test_A_openapi():
    r = requests.get(f"{BASE}/openapi.json", timeout=10)
    paths = [p for p in r.json()["paths"] if p.startswith("/api")]
    expect = {
        "/api/assessment/processing/start",
        "/api/assessment/processing/state",
        "/api/assessment/results",
        "/api/assessment/results/download",
    }
    missing = expect - set(paths)
    ok = len(paths) == 29 and not missing
    record("A", ok, f"total /api paths={len(paths)} (expect 29); missing new={missing}")


# --------------------------------------------------------------------------- #
# B. /processing/start — 404, 409 gates, 200 completed
# --------------------------------------------------------------------------- #
def test_B_processing_start():
    # 404
    r = requests.post(f"{BASE}/assessment/processing/start",
                      json={"session_id": "does-not-exist-xyz"}, timeout=10)
    record("B1", r.status_code == 404, f"unknown session → {r.status_code} {r.text[:200]}")

    # Against Ada (already completed) — should return 200 with completed
    r = requests.post(f"{BASE}/assessment/processing/start",
                      json={"session_id": ADA_SESSION}, timeout=10)
    j = r.json() if r.status_code < 500 else {}
    ok = r.status_code == 200 and j.get("status") == "completed" and j.get("completed_at") and j.get("poll_url")
    record("B2", ok, f"Ada /start (completed) → {r.status_code} keys={list(j)}")


def test_C_stage_gate():
    """409 when stage ∉ {processing, results}."""
    # Create a bare session at stage=identity
    r = requests.post(f"{BASE}/sessions", json={
        "name": "Gate Test", "email": f"gate.{uuid.uuid4().hex[:6]}@example.co.uk",
        "organisation": "Test Co", "role": "Dir", "consent": True,
    }, headers={"X-Forwarded-For": rand_ip()}, timeout=30)
    sid = r.json()["session_id"]
    r = requests.post(f"{BASE}/assessment/processing/start",
                      json={"session_id": sid}, timeout=10)
    detail = r.json().get("detail") if r.status_code != 500 else {}
    ok = r.status_code == 409 and isinstance(detail, dict) and detail.get("current_stage") == "identity"
    record("C1", ok, f"stage=identity → {r.status_code} detail={detail}")


def test_D_missing_scores():
    """409 when scores.{psychometric,ai_fluency,scenario} missing even at stage=processing."""
    # Seed a fresh session then strip a score block; then PATCH stage to processing.
    sid, resume = seed_fresh()
    # Strip psychometric
    mongo_update(sid, {"scores.psychometric": None})
    r = requests.post(f"{BASE}/assessment/processing/start",
                      json={"session_id": sid}, timeout=10)
    detail = r.json().get("detail") if r.status_code != 500 else {}
    ok = r.status_code == 409 and isinstance(detail, dict) and "psychometric" in (detail.get("missing") or [])
    record("D1", ok, f"missing psychometric → {r.status_code} detail={detail}")
    # Cleanup: delete the seeded doc via pymongo
    import pymongo
    try:
        mongo_url = open("/app/backend/.env").read()
        m = re.search(r"MONGO_URL=([^\n]+)", mongo_url)
        murl = m.group(1).strip().strip('"').strip("'") if m else "mongodb://localhost:27017"
        cli = pymongo.MongoClient(murl)
        cli["soe_tra"]["sessions"].delete_one({"session_id": sid})
        cli.close()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# E. Live synthesis on a fresh session (~2-3 min, 2 LLM calls)
# --------------------------------------------------------------------------- #
def test_E_live_synthesis():
    """Fresh seed → POST /start → poll /state → verify /results + /download."""
    sid, resume = seed_fresh()
    print(f"   [E] Fresh session: {sid} / {resume}")
    # POST /start
    t0 = time.time()
    r = requests.post(f"{BASE}/assessment/processing/start",
                      json={"session_id": sid}, timeout=20)
    ok = r.status_code == 202 and r.json().get("status") == "in_progress" and r.json().get("started_at")
    record("E1", ok, f"/start → {r.status_code} {r.json()}")
    if not ok:
        return sid
    start_resp = r.json()
    started_at_first = start_resp.get("started_at")

    # Idempotency: second /start while in_progress — same started_at
    time.sleep(2)
    r2 = requests.post(f"{BASE}/assessment/processing/start",
                       json={"session_id": sid}, timeout=60)
    j2 = r2.json()
    ok2 = r2.status_code == 202 and j2.get("started_at") == started_at_first
    record("E2", ok2, f"idempotent /start: {r2.status_code} same started_at={j2.get('started_at')==started_at_first}")

    # Poll /state up to 240s
    final = None
    deadline = time.time() + 240
    last = None
    while time.time() < deadline:
        try:
            rs = requests.get(f"{BASE}/assessment/processing/state",
                              params={"session_id": sid}, timeout=30)
            s = rs.json()
            last = s
            if s.get("status") in ("completed", "failed"):
                final = s
                break
        except requests.exceptions.RequestException as e:
            last = {"poll_error": str(e)}
        time.sleep(10)
    record("E3", final is not None and final.get("status") == "completed",
           f"polled to completion in {int(time.time()-t0)}s; final={last}")
    if not final or final.get("status") != "completed":
        return sid

    # After completion, subsequent /start returns 200 completed
    rc = requests.post(f"{BASE}/assessment/processing/start",
                       json={"session_id": sid}, timeout=10)
    jc = rc.json()
    record("E4", rc.status_code == 200 and jc.get("status") == "completed" and jc.get("completed_at"),
           f"/start after complete → {rc.status_code} keys={list(jc)}")

    # /state shape: must NOT contain deliverable body
    rs = requests.get(f"{BASE}/assessment/processing/state",
                      params={"session_id": sid}, timeout=10)
    sj = rs.json()
    has_deliv = any(k in sj for k in ("deliverable", "executive_summary", "dimension_profiles"))
    shape_ok = set(sj.keys()) <= {"status", "started_at", "completed_at", "error"} or not has_deliv
    record("E5", shape_ok, f"/state shape keys={list(sj)} (no deliverable body)")

    # Now verify /results deep schema on fresh session
    rr = requests.get(f"{BASE}/assessment/results", params={"session_id": sid}, timeout=10)
    rj = rr.json()
    d = rj.get("deliverable", {})
    dp = d.get("dimension_profiles", [])
    afd = d.get("ai_fluency_deep_dive", {})
    es = d.get("executive_summary", {})
    expected_ids = {"learning_agility", "tolerance_for_ambiguity", "cognitive_flexibility",
                    "self_awareness_accuracy", "ai_fluency", "systems_thinking"}
    dp_ids = {p.get("dimension_id") for p in dp}
    all_have_band_colour = all((p.get("band") or {}).get("colour") in {"navy", "gold", "terracotta"} for p in dp)
    schema_ok = (
        rj.get("status") == "ok"
        and es.get("overall_colour") in {"navy", "gold", "terracotta"}
        and es.get("overall_category")
        and es.get("prose")
        and isinstance(es.get("key_strengths"), list)
        and isinstance(es.get("development_priorities"), list)
        and es.get("bottom_line")
        and len(dp) == 6 and dp_ids == expected_ids and all_have_band_colour
        and d.get("integration_analysis")
        and len(afd.get("components_table", [])) == 5
        and len(d.get("development_recommendations", [])) == 2
        and d.get("methodology_note")
        and len(rj.get("dimensions", {}).get("assessed", [])) == 6
        and len(rj.get("dimensions", {}).get("not_assessed", [])) == 10
    )
    record("E6", schema_ok,
           f"fresh /results: es.overall_colour={es.get('overall_colour')}, dp_ids={dp_ids}, cmp_rows={len(afd.get('components_table',[]))}, devrecs={len(d.get('development_recommendations', []))}, all_band_colour_ok={all_have_band_colour}")

    # synthesis provider check: admin read
    cookie = admin_cookie()
    ar = requests.get(f"{BASE}/admin/sessions/{sid}", headers={"Cookie": cookie}, timeout=10)
    syn = (ar.json() or {}).get("synthesis", {})
    prov_ok = syn.get("status") == "completed" and syn.get("provider") == "emergent" \
              and syn.get("model") == "claude-opus-4-6" and syn.get("fallbacks_tried", 0) == 0
    record("E7", prov_ok, f"synthesis meta provider={syn.get('provider')} model={syn.get('model')} fallbacks={syn.get('fallbacks_tried')}")

    # session.stage, expires_at = completed_at + 60d
    doc = mongo_fetch(sid)
    stage_ok = doc.get("stage") == "results" and doc.get("status") == "completed" and doc.get("completed_at")
    try:
        c = datetime.fromisoformat(doc["completed_at"])
        e = datetime.fromisoformat(doc["expires_at"])
        exp_ok = 59 <= (e - c).days <= 61
    except Exception:
        exp_ok = False
    record("E8", stage_ok and exp_ok, f"stage={doc.get('stage')} status={doc.get('status')} expires-completed days={(e - c).days if exp_ok else 'N/A'}")

    return sid


# --------------------------------------------------------------------------- #
# F. /results happy path on Ada
# --------------------------------------------------------------------------- #
def test_F_results_ada():
    r = requests.get(f"{BASE}/assessment/results",
                     params={"session_id": ADA_SESSION}, timeout=10)
    j = r.json()
    d = j.get("deliverable", {})
    dp = d.get("dimension_profiles", [])
    afd = d.get("ai_fluency_deep_dive", {})
    es = d.get("executive_summary", {})
    expected_ids = {"learning_agility", "tolerance_for_ambiguity", "cognitive_flexibility",
                    "self_awareness_accuracy", "ai_fluency", "systems_thinking"}
    dp_ids = {p.get("dimension_id") for p in dp}
    all_band_colours = all((p.get("band") or {}).get("colour") in {"navy", "gold", "terracotta"} for p in dp)
    sa = j.get("self_awareness", {})
    ok = (
        r.status_code == 200
        and j.get("status") == "ok"
        and j.get("participant", {}).get("first_name") == "Ada"
        and len(dp) == 6 and dp_ids == expected_ids
        and all_band_colours
        and es.get("overall_colour") in {"navy", "gold", "terracotta"}
        and all(k in es for k in ("overall_category", "overall_colour", "prose", "key_strengths",
                                   "development_priorities", "bottom_line"))
        and d.get("integration_analysis")
        and len(afd.get("components_table", [])) == 5
        and len(d.get("development_recommendations", [])) == 2
        and d.get("methodology_note")
        and len(j.get("dimensions", {}).get("assessed", [])) == 6
        and len(j.get("dimensions", {}).get("not_assessed", [])) == 10
        and sa.get("status") == "computed"
        and j.get("strategic_scenario_scores") is not None
    )
    record("F1", ok,
           f"Ada /results schema: dp_ids={dp_ids}, cmp_rows={len(afd.get('components_table',[]))}, "
           f"es.colour={es.get('overall_colour')}, sa.band={sa.get('band')}, devrecs={len(d.get('development_recommendations',[]))}")


# --------------------------------------------------------------------------- #
# G. /results 409 when synthesis not complete, 404 on unknown
# --------------------------------------------------------------------------- #
def test_G_results_gates():
    r = requests.get(f"{BASE}/assessment/results",
                     params={"session_id": "does-not-exist-xyz"}, timeout=10)
    record("G1", r.status_code == 404, f"unknown session /results → {r.status_code}")

    # Create session at identity (synthesis never started)
    r = requests.post(f"{BASE}/sessions", json={
        "name": "Gate", "email": f"gate.{uuid.uuid4().hex[:6]}@example.co.uk",
        "organisation": "Co", "role": "Role", "consent": True,
    }, headers={"X-Forwarded-For": rand_ip()}, timeout=30)
    sid = r.json()["session_id"]
    r2 = requests.get(f"{BASE}/assessment/results",
                      params={"session_id": sid}, timeout=10)
    detail = r2.json().get("detail") if r2.status_code != 500 else {}
    ok = r2.status_code == 409 and isinstance(detail, dict) and "synthesis_status" in detail
    record("G2", ok, f"synthesis not complete /results → {r2.status_code} detail={detail}")


# --------------------------------------------------------------------------- #
# H. Downloads: PDF + Markdown
# --------------------------------------------------------------------------- #
def test_H_downloads():
    # PDF
    r = requests.get(f"{BASE}/assessment/results/download",
                     params={"session_id": ADA_SESSION, "format": "pdf"}, timeout=30)
    ct = r.headers.get("content-type", "").split(";")[0].strip()
    cd = r.headers.get("content-disposition", "")
    body_start = r.content[:5]
    fname_ok = bool(re.search(r'filename="TRA-Ada-\d{4}-\d{2}-\d{2}\.pdf"', cd))
    ok = r.status_code == 200 and ct == "application/pdf" and body_start == b"%PDF-" and fname_ok
    record("H1", ok, f"PDF: status={r.status_code} ct={ct} cd={cd} head={body_start}")

    # Markdown
    r = requests.get(f"{BASE}/assessment/results/download",
                     params={"session_id": ADA_SESSION, "format": "markdown"}, timeout=30)
    ct = r.headers.get("content-type", "")
    cd = r.headers.get("content-disposition", "")
    body = r.text
    fname_ok = bool(re.search(r'filename="TRA-Ada-\d{4}-\d{2}-\d{2}\.md"', cd))
    ok = (
        r.status_code == 200
        and ct == "text/markdown; charset=utf-8"
        and body.startswith("# Transformation Readiness Assessment")
        and fname_ok
    )
    record("H2", ok, f"MD: status={r.status_code} ct={ct} cd={cd} head='{body[:45]}...'")

    # 10 not-assessed names
    not_assessed_names = [
        "Hybrid Workforce Capability", "Generational Intelligence",
        "Political Acumen", "Stakeholder Orchestration", "Cultural Adaptability",
        "Long-Term Orientation", "Change Leadership", "Institutional Building",
        "Governance Capability", "Results Under Ambiguity",
    ]
    missing = [n for n in not_assessed_names if n not in body]
    heading_ok = "Not assessed in this preview" in body
    record("H3", not missing and heading_ok,
           f"MD contains all 10 not-assessed names + heading; missing={missing}, heading_present={heading_ok}")

    # Invalid format
    r = requests.get(f"{BASE}/assessment/results/download",
                     params={"session_id": ADA_SESSION, "format": "html"}, timeout=10)
    record("H4", r.status_code == 422, f"invalid format → {r.status_code}")

    # 404 on unknown
    r = requests.get(f"{BASE}/assessment/results/download",
                     params={"session_id": "nope-xyz", "format": "pdf"}, timeout=10)
    record("H5", r.status_code == 404, f"unknown session /download → {r.status_code}")


# --------------------------------------------------------------------------- #
# I. Graceful scoring_error path
# --------------------------------------------------------------------------- #
def test_I_scoring_error():
    """Mutate a fresh session to have scoring_error + synthesis.completed,
    then verify /results returns 200 with {status:error} and /download returns 409."""
    sid, resume = seed_fresh()
    mongo_update(sid, {
        "deliverable": {"scoring_error": True, "_error": "test injected error", "_raw": "oops"},
        "synthesis": {
            "status": "completed",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
        "stage": "results",
    })
    # /results → 200 graceful
    r = requests.get(f"{BASE}/assessment/results",
                     params={"session_id": sid}, timeout=10)
    j = r.json()
    ok = (
        r.status_code == 200
        and j.get("status") == "error"
        and j.get("scoring_error") is True
        and j.get("participant", {}).get("first_name") == "Ada"
    )
    record("I1", ok, f"/results scoring_error → {r.status_code} keys={list(j)} status={j.get('status')}")

    # /download → 409
    r = requests.get(f"{BASE}/assessment/results/download",
                     params={"session_id": sid, "format": "pdf"}, timeout=10)
    record("I2", r.status_code == 409, f"/download scoring_error → {r.status_code}")

    # Cleanup
    import pymongo
    try:
        mongo_url = "mongodb://localhost:27017"
        with open("/app/backend/.env") as f:
            for line in f:
                if line.startswith("MONGO_URL="):
                    mongo_url = line.split("=", 1)[1].strip().strip('"').strip("'")
        cli = pymongo.MongoClient(mongo_url)
        cli["soe_tra"]["sessions"].delete_one({"session_id": sid})
        cli.close()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# J. Privacy: public vs admin reads on Ada
# --------------------------------------------------------------------------- #
def test_J_privacy():
    # Public GET
    r = requests.get(f"{BASE}/sessions/{ADA_SESSION}", timeout=10)
    j = r.json()
    scores_null = j.get("scores") is None
    deliv_null = j.get("deliverable") is None
    conv = j.get("conversation") or []
    # Check no assistant turn leaks provider/model/latency/fallbacks_tried
    leaks = []
    for entry in conv:
        if entry.get("role") == "assistant":
            for k in ("provider", "model", "latency_ms", "fallbacks_tried"):
                if k in entry:
                    leaks.append(f"turn={entry.get('turn')}:{k}")
    public_ok = scores_null and deliv_null and not leaks
    record("J1", public_ok, f"public GET /sessions: scores={j.get('scores')}, deliverable={j.get('deliverable')}, conv_leaks={leaks[:5]}")

    # Admin GET exposes both
    cookie = admin_cookie()
    r = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}",
                     headers={"Cookie": cookie}, timeout=10)
    j = r.json()
    admin_ok = r.status_code == 200 and j.get("scores") is not None and j.get("deliverable") is not None
    record("J2", admin_ok, f"admin GET exposes scores+deliverable: {admin_ok}")


# --------------------------------------------------------------------------- #
# K. Regression spot-checks Phase 2-6
# --------------------------------------------------------------------------- #
def test_K_regression():
    # K1: POST /sessions
    r = requests.post(f"{BASE}/sessions", json={
        "name": "Reg Test", "email": f"reg.{uuid.uuid4().hex[:6]}@example.co.uk",
        "organisation": "Reg Co", "role": "R", "consent": True,
    }, headers={"X-Forwarded-For": rand_ip()}, timeout=30)
    sid = r.json().get("session_id") if r.status_code == 201 else None
    record("K1", r.status_code == 201 and sid, f"POST /sessions → {r.status_code}")

    # K2: admin login + /admin/settings
    cookie = admin_cookie()
    r = requests.get(f"{BASE}/admin/settings", headers={"Cookie": cookie}, timeout=10)
    j = r.json() if r.status_code == 200 else {}
    record("K2", r.status_code == 200 and "fallback_model" in j,
           f"admin/settings → {r.status_code} fallback_model={j.get('fallback_model')}")

    # K3: psychometric /next + /answer
    # Advance session to psychometric
    requests.patch(f"{BASE}/sessions/{sid}/stage", json={"stage": "context"}, timeout=10)
    requests.patch(f"{BASE}/sessions/{sid}/stage", json={"stage": "psychometric"}, timeout=10)
    ip = rand_ip()
    r = requests.get(f"{BASE}/assessment/psychometric/next",
                     params={"session_id": sid},
                     headers={"X-Forwarded-For": ip}, timeout=10)
    next_ok = r.status_code == 200 and r.json().get("item", {}).get("item_id")
    item_id = r.json()["item"]["item_id"] if next_ok else None
    r2 = requests.post(f"{BASE}/assessment/psychometric/answer",
                       json={"session_id": sid, "item_id": item_id, "value": 4,
                             "response_time_ms": 5000},
                       headers={"X-Forwarded-For": ip}, timeout=10)
    record("K3", next_ok and r2.status_code == 200, f"/next={r.status_code} /answer={r2.status_code}")

    # K4: ai-discussion /start gate (stage != ai-discussion) — should 409
    r = requests.post(f"{BASE}/assessment/ai-discussion/start",
                      json={"session_id": sid}, timeout=10)
    record("K4", r.status_code == 409, f"ai-discussion/start while stage=psychometric → {r.status_code}")

    # K5: scenario /state on a session that's nowhere near scenario
    r = requests.get(f"{BASE}/assessment/scenario/state",
                     params={"session_id": sid}, timeout=10)
    j = r.json() if r.status_code == 200 else {}
    record("K5", r.status_code == 200 and j.get("status") is None and j.get("phase") is None,
           f"scenario/state pre-unlock → {r.status_code} status={j.get('status')}")

    # K6: scenario /advance from_phase mismatch on Ada's session
    r = requests.post(f"{BASE}/assessment/scenario/advance",
                      json={"session_id": ADA_SESSION, "from_phase": "read",
                            "to_phase": "part1", "payload": {}}, timeout=10)
    # Ada is already completed — expect 409 or similar (not 500)
    record("K6", r.status_code in (409, 422) and r.status_code != 500,
           f"scenario/advance on completed session → {r.status_code}")


# --------------------------------------------------------------------------- #
# L. Log hygiene
# --------------------------------------------------------------------------- #
def test_L_logs():
    import glob
    paths = glob.glob("/var/log/supervisor/backend*.log")
    if not paths:
        record("L", False, "no backend logs found")
        return
    content = ""
    for p in paths:
        try:
            with open(p) as f:
                content += f.read()
        except Exception:
            continue
    # Needles — we want ZERO INFO-level hits
    needles = [
        "test1234",                                        # admin password
        "sk-ant-", "sk-emergent-", "sk-proj-",              # api keys
        "ada.test@example.co.uk",                           # participant email
        "smart intern",                                     # conversation content
        "over-indexed on financial stability",              # scenario content
        "executive_summary",                                # deliverable content
    ]
    # Count ONLY at INFO level
    hits = []
    for line in content.splitlines():
        if " - INFO - " not in line and " INFO " not in line:
            continue
        for needle in needles:
            if needle in line:
                hits.append((needle, line[:200]))
                break
    record("L", not hits, f"INFO-level needle hits={len(hits)}; sample={hits[:3]}")


# --------------------------------------------------------------------------- #
# Main driver
# --------------------------------------------------------------------------- #
def main():
    print("=" * 70)
    print("Phase 7 backend sweep")
    print("=" * 70)
    print()

    test_A_openapi()
    test_B_processing_start()
    test_C_stage_gate()
    test_D_missing_scores()
    test_F_results_ada()
    test_G_results_gates()
    test_H_downloads()
    test_I_scoring_error()
    test_J_privacy()
    test_K_regression()

    # Live synthesis — LAST to avoid timeouts blocking cheap checks
    live = os.environ.get("SKIP_LIVE") != "1"
    if live:
        test_E_live_synthesis()
    else:
        print("[SKIP] E: live synthesis (SKIP_LIVE=1)")

    test_L_logs()

    print()
    print("=" * 70)
    fails = [(l, d) for l, ok, d in results if not ok]
    print(f"TOTAL: {len(results) - len(fails)}/{len(results)} passed")
    if fails:
        print("FAILURES:")
        for letter, detail in fails:
            print(f"  [{letter}] {detail}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
