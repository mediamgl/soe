"""
Phase 6 backend tests — Strategic Scenario endpoints + regression of Phases 2–5.

Runs against http://localhost:8001/api. Uses explicit Cookie headers for admin auth
(Secure cookie can't replay over http://localhost via requests.Session).

Budget: ONE live scoring call via Emergent fallback (advance part2 -> done).
"""

import json
import os
import re
import time
import uuid
import random
import string
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASSWORD = "test1234"

results: List[Tuple[str, bool, str]] = []

def record(letter: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {letter}: {detail}")
    results.append((letter, ok, detail))


def rand_ip() -> str:
    return f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def create_session(name: str = "Harriet Fenwick", email_prefix: str = "harriet") -> Dict[str, Any]:
    email = f"{email_prefix}.{uuid.uuid4().hex[:6]}@meridian-test.example.co.uk"
    headers = {"X-Forwarded-For": rand_ip()}
    r = requests.post(f"{BASE}/sessions", json={
        "name": name, "email": email, "organisation": "Meridian Energy Holdings",
        "role": "Director of Strategy", "consent": True,
    }, headers=headers, timeout=30)
    assert r.status_code == 201, f"create_session failed: {r.status_code} {r.text}"
    return r.json()


def advance_stage(sid: str, stage: str):
    r = requests.patch(f"{BASE}/sessions/{sid}/stage", json={"stage": stage}, timeout=30)
    assert r.status_code == 200, f"advance_stage {stage}: {r.status_code} {r.text}"
    return r.json()


def run_psychometric(sid: str, value: int = 4):
    """Submit 20 answers. Needs fresh X-Forwarded-For per batch to avoid 60/min rate limit."""
    # initialise + iterate
    ip = rand_ip()
    for i in range(20):
        r = requests.get(f"{BASE}/assessment/psychometric/next",
                         params={"session_id": sid}, timeout=30)
        assert r.status_code == 200, f"psych next({i}): {r.status_code} {r.text}"
        j = r.json()
        if j.get("done"):
            break
        item = j["item"]
        r2 = requests.post(f"{BASE}/assessment/psychometric/answer", json={
            "session_id": sid, "item_id": item["item_id"], "value": value,
            "response_time_ms": 1200,
        }, headers={"X-Forwarded-For": ip}, timeout=30)
        assert r2.status_code == 200, f"psych answer({i}): {r2.status_code} {r2.text}"


def run_ai_discussion(sid: str, turns: int = 3):
    r = requests.post(f"{BASE}/assessment/ai-discussion/start",
                      json={"session_id": sid}, timeout=90)
    assert r.status_code == 200, f"aidisc start: {r.status_code} {r.text}"
    for i in range(turns):
        msg = [
            "I use Claude and ChatGPT daily for drafting board papers and summarising stakeholder feedback, but I'm aware I over-trust the first draft.",
            "The governance question is the hard one — procurement didn't design its frameworks for probabilistic outputs, and our audit committee has no vocabulary for this.",
            "Agentic AI feels further off for us; the orchestration story is compelling but the accountability gap worries me more than the capability gap.",
        ][i]
        r2 = requests.post(f"{BASE}/assessment/ai-discussion/message", json={
            "session_id": sid, "content": msg,
        }, timeout=120)
        assert r2.status_code == 200, f"aidisc msg {i}: {r2.status_code} {r2.text}"
    r3 = requests.post(f"{BASE}/assessment/ai-discussion/complete",
                       json={"session_id": sid}, timeout=180)
    assert r3.status_code == 200, f"aidisc complete: {r3.status_code} {r3.text}"


def admin_login_cookie() -> str:
    r = requests.post(f"{BASE}/admin/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login: {r.status_code} {r.text}"
    set_cookie = r.headers.get("set-cookie", "")
    m = re.search(r"(tra_admin_token=[^;]+)", set_cookie)
    assert m, f"No cookie in Set-Cookie: {set_cookie!r}"
    return m.group(1)


# ============================================================================
# A. OpenAPI enumeration
# ============================================================================
def test_a_openapi():
    r = requests.get(f"{BASE}/openapi.json", timeout=15)
    assert r.status_code == 200, f"openapi: {r.status_code}"
    spec = r.json()
    paths = [p for p in spec["paths"] if p.startswith("/api")]
    scen_paths = [p for p in paths if "scenario" in p]
    expected_scen = {
        "/api/assessment/scenario/state",
        "/api/assessment/scenario/start",
        "/api/assessment/scenario/advance",
        "/api/assessment/scenario/autosave",
    }
    record("A", len(paths) == 25,
           f"openapi enumerates {len(paths)} /api paths (expected 25); scenario routes={sorted(scen_paths)}")
    record("A2", set(scen_paths) == expected_scen,
           f"all 4 scenario routes present: {set(scen_paths) == expected_scen}")


# ============================================================================
# B. Doc 22 content fidelity via state.content payload
# ============================================================================
def test_b_content_fidelity():
    # Create session, drive to scenario stage
    s = create_session(name="Imogen Carrick", email_prefix="imogen")
    sid = s["session_id"]
    advance_stage(sid, "context")
    advance_stage(sid, "psychometric")
    run_psychometric(sid)
    advance_stage(sid, "ai-discussion")
    advance_stage(sid, "scenario")

    # start
    r = requests.post(f"{BASE}/assessment/scenario/start",
                      json={"session_id": sid}, timeout=30)
    assert r.status_code == 200, f"start: {r.status_code} {r.text}"
    j = r.json()
    assert j["phase"] == "read", f"phase after start = {j['phase']}"
    content = j.get("content") or {}
    # title
    title = content.get("title")
    record("B1", title == "Meridian Energy Holdings",
           f"read.title = {title!r}")
    # body_sections: 6 entries; 1 unnamed + 5 named in order
    body = content.get("body_sections") or []
    headings = [s["heading"] for s in body]
    expected_headings = [None, "Financial Position", "Workforce",
                        "Market Dynamics", "Stakeholder Landscape", "Recent Data Points"]
    record("B2", len(body) == 6, f"body_sections len = {len(body)} (expected 6)")
    record("B3", headings == expected_headings,
           f"body_sections headings order = {headings}")

    # Advance to part1
    r2 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid, "from_phase": "read", "to_phase": "part1",
    }, timeout=30)
    assert r2.status_code == 200, f"advance read->part1: {r2.status_code} {r2.text}"
    part1 = r2.json()["content"]
    qs1 = part1.get("questions") or []
    record("B4", len(qs1) == 3, f"part1.questions len = {len(qs1)} (expected 3)")

    # Advance part1 -> curveball (with valid trio)
    r3 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid, "from_phase": "part1", "to_phase": "curveball",
        "payload": {
            "q1": "Prioritise workforce continuity and stakeholder trust — staged voluntary transition is the only path the union can live with.",
            "q2": "Sequence: union first (4 weeks), Ministry second, then public announcement; revisit in 6 months.",
            "q3": "Constraints are the debt covenant and the legacy concession; assumption is the coal plant can defer maintenance another 18 months without safety risk.",
        },
    }, timeout=30)
    assert r3.status_code == 200, f"advance part1->curveball: {r3.status_code} {r3.text}"
    curveball = r3.json()["content"]
    items = curveball.get("items") or []
    record("B5", len(items) == 3, f"curveball.items len = {len(items)}")
    all_numbered = all(isinstance(it.get("number"), int) and it.get("heading") and it.get("body")
                      for it in items)
    record("B6", all_numbered,
           f"curveball items have numbered heading+body: {all_numbered}")

    # advance curveball -> part2
    r4 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid, "from_phase": "curveball", "to_phase": "part2",
    }, timeout=30)
    assert r4.status_code == 200, f"advance curveball->part2: {r4.status_code} {r4.text}"
    part2 = r4.json()["content"]
    qs2 = part2.get("questions") or []
    record("B7", len(qs2) == 3, f"part2.questions len = {len(qs2)} (expected 3)")

    return sid  # leave session at part2 for end-to-end live scoring


# ============================================================================
# C. state: 404 for unknown, pre-start, idempotency of start
# ============================================================================
def test_c_state_and_start():
    # unknown session
    r = requests.get(f"{BASE}/assessment/scenario/state",
                     params={"session_id": "does-not-exist-uuid"}, timeout=10)
    record("C1", r.status_code == 404, f"state unknown session -> {r.status_code}")

    # pre-start (fresh session at identity)
    s = create_session(name="Colin Ashworth", email_prefix="colin")
    sid = s["session_id"]
    r2 = requests.get(f"{BASE}/assessment/scenario/state",
                      params={"session_id": sid}, timeout=10)
    assert r2.status_code == 200, r2.text
    j = r2.json()
    pre_ok = (j.get("status") is None and j.get("phase") is None
              and j.get("part1_response") == {} and j.get("part2_response") == {}
              and j.get("content") == {})
    record("C2", pre_ok, f"pre-start state shape: {j}")

    # 409 on POST /start when stage != scenario
    r3 = requests.post(f"{BASE}/assessment/scenario/start",
                       json={"session_id": sid}, timeout=10)
    ok_409 = False
    gate_msg = ""
    try:
        detail = r3.json().get("detail") or {}
        gate_msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
        ok_409 = (r3.status_code == 409
                  and isinstance(detail, dict)
                  and "Scenario not yet unlocked" in detail.get("message", ""))
    except Exception:
        pass
    record("C3", ok_409,
           f"start gate 409 + 'Scenario not yet unlocked...': {r3.status_code} msg={gate_msg!r}")

    # unknown session POST start -> 404
    r4 = requests.post(f"{BASE}/assessment/scenario/start",
                       json={"session_id": "bogus-id"}, timeout=10)
    record("C4", r4.status_code == 404, f"start unknown session -> {r4.status_code}")


def test_c5_idempotency():
    """Dedicated session that reaches 'scenario' stage, verify start idempotency."""
    s = create_session(name="Marcus Llewellyn", email_prefix="marcus")
    sid = s["session_id"]
    advance_stage(sid, "context")
    advance_stage(sid, "psychometric")
    run_psychometric(sid)
    advance_stage(sid, "ai-discussion")
    advance_stage(sid, "scenario")

    r1 = requests.post(f"{BASE}/assessment/scenario/start",
                       json={"session_id": sid}, timeout=30)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    r2 = requests.post(f"{BASE}/assessment/scenario/start",
                       json={"session_id": sid}, timeout=30)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()

    same = (j1["status"] == j2["status"] == "in_progress"
            and j1["phase"] == j2["phase"] == "read"
            and j1["phase_entered_at"].get("read") == j2["phase_entered_at"].get("read"))
    record("C5", same, f"start idempotent: phase_entered_at.read preserved; j1.phase={j1['phase']} j2.phase={j2['phase']}")
    return sid


# ============================================================================
# D. /advance validation: 422 on invalid trios, 409 on phase/order
# ============================================================================
def test_d_advance_validation(sid_at_read: str):
    # Try to advance from part1 while actually at read -> 409 out-of-order
    r = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid_at_read,
        "from_phase": "part1", "to_phase": "curveball",
        "payload": {"q1": "a", "q2": "b", "q3": "c"},
    }, timeout=15)
    record("D1", r.status_code == 409,
           f"advance from wrong phase -> {r.status_code} body={r.text[:120]}")

    # Skip: read -> curveball (not adjacent) -> 409
    r2 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid_at_read,
        "from_phase": "read", "to_phase": "curveball",
    }, timeout=15)
    record("D2", r2.status_code == 409,
           f"advance read->curveball skip -> {r2.status_code}")

    # Now legit: read -> part1
    r3 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid_at_read,
        "from_phase": "read", "to_phase": "part1",
    }, timeout=15)
    assert r3.status_code == 200, r3.text

    # Invalid trio: missing q3
    r4 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid_at_read,
        "from_phase": "part1", "to_phase": "curveball",
        "payload": {"q1": "abc", "q2": "def"},
    }, timeout=15)
    record("D3", r4.status_code == 422, f"missing q3 -> {r4.status_code}")

    # Invalid trio: empty string q2
    r5 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid_at_read,
        "from_phase": "part1", "to_phase": "curveball",
        "payload": {"q1": "a", "q2": "   ", "q3": "c"},
    }, timeout=15)
    record("D4", r5.status_code == 422, f"empty q2 -> {r5.status_code}")

    # Invalid trio: non-string
    r6 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid_at_read,
        "from_phase": "part1", "to_phase": "curveball",
        "payload": {"q1": 123, "q2": "b", "q3": "c"},
    }, timeout=15)
    record("D5", r6.status_code == 422, f"non-string q1 -> {r6.status_code}")

    # Invalid trio: >4000 chars
    long_val = "x" * 4001
    r7 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid_at_read,
        "from_phase": "part1", "to_phase": "curveball",
        "payload": {"q1": long_val, "q2": "b", "q3": "c"},
    }, timeout=15)
    record("D6", r7.status_code == 422, f">4000 char q1 -> {r7.status_code}")

    # Unknown session advance
    r8 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": "nope-id",
        "from_phase": "read", "to_phase": "part1",
    }, timeout=10)
    record("D7", r8.status_code == 404, f"advance unknown session -> {r8.status_code}")


# ============================================================================
# E. /autosave: phase mismatch, unknown keys, non-string, merge behaviour
# ============================================================================
def test_e_autosave(sid_at_part1: str):
    """sid must currently be at phase='part1'."""
    # sanity: verify phase
    r0 = requests.get(f"{BASE}/assessment/scenario/state",
                      params={"session_id": sid_at_part1}, timeout=10)
    phase = r0.json().get("phase")
    if phase != "part1":
        record("E0", False, f"precondition: session phase={phase}, expected part1")
        return

    # phase mismatch: claim phase=part2
    r = requests.post(f"{BASE}/assessment/scenario/autosave", json={
        "session_id": sid_at_part1, "phase": "part2",
        "partial": {"q1": "draft"},
    }, timeout=10)
    record("E1", r.status_code == 409, f"autosave phase mismatch -> {r.status_code}")

    # unknown key
    r2 = requests.post(f"{BASE}/assessment/scenario/autosave", json={
        "session_id": sid_at_part1, "phase": "part1",
        "partial": {"q1": "draft", "q99": "nope"},
    }, timeout=10)
    record("E2", r2.status_code == 422, f"autosave unknown key -> {r2.status_code}")

    # non-string value
    r3 = requests.post(f"{BASE}/assessment/scenario/autosave", json={
        "session_id": sid_at_part1, "phase": "part1",
        "partial": {"q1": 42},
    }, timeout=10)
    record("E3", r3.status_code == 422, f"autosave non-string -> {r3.status_code}")

    # >4000 chars
    r4 = requests.post(f"{BASE}/assessment/scenario/autosave", json={
        "session_id": sid_at_part1, "phase": "part1",
        "partial": {"q2": "x" * 4001},
    }, timeout=10)
    record("E4", r4.status_code == 422, f"autosave >4000 chars -> {r4.status_code}")

    # merge: save only q1, confirm q2/q3 absent
    r5 = requests.post(f"{BASE}/assessment/scenario/autosave", json={
        "session_id": sid_at_part1, "phase": "part1",
        "partial": {"q1": "first draft value"},
    }, timeout=10)
    record("E5", r5.status_code == 200 and "saved_at" in r5.json(),
           f"autosave q1 only -> {r5.status_code}")

    # save q2, confirm q1 preserved
    r6 = requests.post(f"{BASE}/assessment/scenario/autosave", json={
        "session_id": sid_at_part1, "phase": "part1",
        "partial": {"q2": "second answer"},
    }, timeout=10)
    assert r6.status_code == 200, r6.text
    # fetch state, verify part1_response has both
    r7 = requests.get(f"{BASE}/assessment/scenario/state",
                      params={"session_id": sid_at_part1}, timeout=10)
    p1 = r7.json().get("part1_response") or {}
    merged_ok = p1.get("q1") == "first draft value" and p1.get("q2") == "second answer"
    record("E6", merged_ok,
           f"autosave merge preserves absent keys: part1_response={p1}")

    # autosave unknown session
    r8 = requests.post(f"{BASE}/assessment/scenario/autosave", json={
        "session_id": "no-such", "phase": "part1",
        "partial": {"q1": "x"},
    }, timeout=10)
    record("E7", r8.status_code == 404, f"autosave unknown session -> {r8.status_code}")


# ============================================================================
# F. Live end-to-end happy path (ONE live scoring call)
# ============================================================================
def test_f_live_happy_path():
    s = create_session(name="Priya Ashworth-Wainwright", email_prefix="priya")
    sid = s["session_id"]
    advance_stage(sid, "context")
    advance_stage(sid, "psychometric")
    run_psychometric(sid)
    advance_stage(sid, "ai-discussion")
    run_ai_discussion(sid, turns=3)
    advance_stage(sid, "scenario")

    # start
    r = requests.post(f"{BASE}/assessment/scenario/start",
                      json={"session_id": sid}, timeout=30)
    assert r.status_code == 200, r.text

    # read -> part1
    r1 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid, "from_phase": "read", "to_phase": "part1",
    }, timeout=15)
    assert r1.status_code == 200, r1.text
    time.sleep(0.3)

    # part1 -> curveball with rich trio
    part1_trio = {
        "q1": "Balance workforce protection against debt-covenant risk. I'd opt for a staged voluntary-separation programme aligned to the coal plant retirement curve, while ring-fencing the cybersecurity-critical roles until the Ministry's review lands. The alternative — a forced restructure — breaks our social licence with the union and the coalition partner.",
        "q2": "Week 1: brief the union leadership off-record; Week 2: board paper with three options; Week 4: public announcement; Month 3-6: voluntary scheme opens; revisit in Q4 with a covenant-compliance dashboard. The order matters — if the Ministry announcement leaks first we lose the union.",
        "q3": "Constraints: debt covenant, legacy-concession obligation to the eastern province, and the fact we can't afford another year of capex deferral on the grid. Assumptions: the coal plant stays safe with another 18 months of deferred overhaul, the union will accept voluntary separation if we fund it, and the Ministry review won't mandate divestment.",
    }
    r2 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid, "from_phase": "part1", "to_phase": "curveball",
        "payload": part1_trio,
    }, timeout=15)
    assert r2.status_code == 200, r2.text

    # curveball -> part2
    r3 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid, "from_phase": "curveball", "to_phase": "part2",
    }, timeout=15)
    assert r3.status_code == 200, r3.text

    # part2 -> done (LIVE scoring call)
    part2_trio = {
        "q1": "The three new items change my sequencing materially. The cybersecurity breach reframes the Ministry review — we now need to lead with disclosure, not manage around it. The competitor move neutralises our 'time' advantage, so the voluntary scheme has to move up a quarter. And the covenant tightening means we can't fund both the scheme and the grid capex at once.",
        "q2": "What changed: I was optimising for workforce continuity and ministerial relations; I underweighted the cyber-governance gap and the pace of the competitive field. My Part 1 read the coal plant as the binding constraint; actually the capital stack is now the binding constraint. I'd revise my public disclosure posture from 'managed reveal' to 'immediate notification with remediation plan'.",
        "q3": "Ethically, we must notify the regulator about the breach this week — concealing it to protect the Ministry timeline is not defensible. Operationally, we triage: (a) disclose + remediate cyber; (b) renegotiate covenants with the consortium on the back of a credible turnaround plan; (c) accelerate voluntary separation by one quarter; (d) defer non-safety-critical grid capex. The union conversation stays first in sequence; the Ministry conversation becomes honest instead of managed.",
    }
    print("\n>>> Calling live Emergent scoring via advance part2->done (this will take ~10-30s)...")
    started = time.time()
    r4 = requests.post(f"{BASE}/assessment/scenario/advance", json={
        "session_id": sid, "from_phase": "part2", "to_phase": "done",
        "payload": part2_trio,
    }, timeout=240)
    elapsed = int((time.time() - started) * 1000)
    print(f">>> advance part2->done returned {r4.status_code} in {elapsed}ms")
    assert r4.status_code == 200, r4.text
    jfinal = r4.json()
    # status completed, phase=done
    f1 = jfinal.get("status") == "completed" and jfinal.get("phase") == "done"
    record("F1", f1, f"after part2->done: status={jfinal.get('status')} phase={jfinal.get('phase')}")
    # time_on_phase contains part2
    top = jfinal.get("time_on_phase_ms") or {}
    f2 = isinstance(top.get("part2"), int) and top["part2"] >= 0
    record("F2", f2, f"time_on_phase_ms.part2 populated: {top.get('part2')}")

    # Check session.stage via GET /sessions/{id}
    r5 = requests.get(f"{BASE}/sessions/{sid}", timeout=10)
    assert r5.status_code == 200, r5.text
    sess = r5.json()
    record("F3", sess.get("stage") == "processing",
           f"session.stage advanced to 'processing': {sess.get('stage')}")
    # Public must hide scores/deliverable
    record("F4", sess.get("scores") is None and sess.get("deliverable") is None,
           f"public scores={sess.get('scores')}, deliverable={sess.get('deliverable')}")

    # Admin view: fetch full scores
    cookie = admin_login_cookie()
    ra = requests.get(f"{BASE}/admin/sessions/{sid}",
                      headers={"Cookie": cookie}, timeout=15)
    assert ra.status_code == 200, f"admin sessions: {ra.status_code} {ra.text}"
    full = ra.json()
    scores = full.get("scores") or {}
    scn_score = scores.get("scenario") or {}
    has_err = scn_score.get("scoring_error")
    record("F5", not has_err, f"no scoring_error in scores.scenario (scoring_error={has_err})")

    cf = scn_score.get("cognitive_flexibility") or {}
    st = scn_score.get("systems_thinking") or {}
    obs = scn_score.get("additional_observations") or {}
    meta = scn_score.get("_meta") or {}

    # Cognitive flexibility schema
    cf_ok = (isinstance(cf.get("score"), int) and 1 <= cf["score"] <= 5
             and cf.get("confidence") in ("high", "medium", "low")
             and isinstance(cf.get("evidence"), dict)
             and all(isinstance(cf["evidence"].get(k), str) and cf["evidence"].get(k)
                     for k in ("part1_position", "part2_revision", "revision_quality", "key_quote")))
    record("F6", cf_ok,
           f"cognitive_flexibility schema-valid: score={cf.get('score')} conf={cf.get('confidence')}")

    # Systems thinking schema
    st_ev = st.get("evidence") or {}
    st_ok = (isinstance(st.get("score"), int) and 1 <= st["score"] <= 5
             and st.get("confidence") in ("high", "medium", "low")
             and isinstance(st_ev.get("connections_identified"), list)
             and all(isinstance(x, str) for x in st_ev.get("connections_identified", []))
             and isinstance(st_ev.get("connections_missed"), list)
             and all(isinstance(x, str) for x in st_ev.get("connections_missed", []))
             and isinstance(st_ev.get("key_quote"), str))
    record("F7", st_ok,
           f"systems_thinking schema-valid: score={st.get('score')} conf={st.get('confidence')}")

    # Additional observations: all 3 fields
    obs_ok = all(isinstance(obs.get(k), str) and obs.get(k)
                 for k in ("stakeholder_awareness", "ethical_reasoning", "analytical_quality"))
    record("F8", obs_ok,
           f"additional_observations 3 fields populated: keys={sorted(obs.keys())}")

    # Meta
    meta_ok = (meta.get("provider") == "emergent"
               and meta.get("fallbacks_tried") == 0
               and isinstance(meta.get("model"), str) and meta.get("model"))
    record("F9", meta_ok,
           f"_meta provider/model/fallbacks_tried: {meta}")

    # Verify fallback_model matches admin_settings
    cookie2 = admin_login_cookie()
    rs = requests.get(f"{BASE}/admin/settings",
                      headers={"Cookie": cookie2}, timeout=15)
    configured_fb = rs.json().get("fallback_model") if rs.status_code == 200 else None
    record("F10", meta.get("model") == configured_fb,
           f"scoring model ({meta.get('model')}) matches admin.fallback_model ({configured_fb})")

    # scenario node: status=completed, completed_at set
    scn_state = full.get("scenario") or {}
    record("F11", scn_state.get("status") == "completed" and scn_state.get("completed_at"),
           f"scenario.status={scn_state.get('status')}, completed_at={scn_state.get('completed_at')}")

    return sid


# ============================================================================
# G. Regression: Phase 2/3/4/5 endpoints
# ============================================================================
def test_g_regression():
    # Sessions CRUD smoke
    s = create_session(name="Nigel Pemberton", email_prefix="nigel")
    sid = s["session_id"]
    resume = s["resume_code"]
    r = requests.get(f"{BASE}/sessions/resume/{resume}", timeout=10)
    record("G1", r.status_code == 200, f"GET /sessions/resume/{{code}} -> {r.status_code}")

    # Admin login + settings
    cookie = admin_login_cookie()
    r2 = requests.get(f"{BASE}/admin/settings", headers={"Cookie": cookie}, timeout=10)
    record("G2", r2.status_code == 200 and "fallback_model" in r2.json(),
           f"admin /settings -> {r2.status_code}")

    # psychometric /next gating (no stage required; lazy-init fine)
    r3 = requests.get(f"{BASE}/assessment/psychometric/next",
                      params={"session_id": sid}, timeout=10)
    record("G3", r3.status_code == 200 and "item" in r3.json(),
           f"psychometric /next -> {r3.status_code}")

    # Answer one item (new IP to avoid rate limit)
    item = r3.json()["item"]
    r4 = requests.post(f"{BASE}/assessment/psychometric/answer", json={
        "session_id": sid, "item_id": item["item_id"], "value": 4,
        "response_time_ms": 1000,
    }, headers={"X-Forwarded-For": rand_ip()}, timeout=10)
    record("G4", r4.status_code == 200, f"psychometric /answer -> {r4.status_code}")

    # ai-discussion start gate (session is still at identity) -> 409
    r5 = requests.post(f"{BASE}/assessment/ai-discussion/start",
                       json={"session_id": sid}, timeout=10)
    record("G5", r5.status_code == 409,
           f"ai-discussion /start gate -> {r5.status_code}")


# ============================================================================
# H. Phase-5 J fix: GET /sessions/{id} conversation must strip internals
# ============================================================================
def test_h_public_conversation_stripped(sid_with_conv: str):
    """sid_with_conv must have an ai-discussion conversation[] populated."""
    r = requests.get(f"{BASE}/sessions/{sid_with_conv}", timeout=10)
    assert r.status_code == 200, r.text
    conv = r.json().get("conversation") or []
    assistant = [t for t in conv if t.get("role") == "assistant"]
    if not assistant:
        record("H", False, "no assistant turns in public conversation[] to check")
        return
    leaked_keys = {"provider", "model", "latency_ms", "fallbacks_tried"}
    violators = [t for t in assistant if any(k in t for k in leaked_keys)]
    record("H", len(violators) == 0,
           f"public assistant turns stripped: {len(assistant)} assistant turns, "
           f"{len(violators)} still carry provider/model/latency_ms/fallbacks_tried")


# ============================================================================
# I. Log hygiene
# ============================================================================
def test_i_log_hygiene():
    try:
        import glob
        log_files = glob.glob("/var/log/supervisor/backend.*.log")
        content = ""
        for lf in log_files:
            try:
                with open(lf, "r", errors="ignore") as f:
                    content += f.read()
            except Exception:
                pass
        # Look for INFO-level leaks
        needles = [
            "test1234",  # admin password
            "sk-ant-",   # anthropic keys
            "sk-emergent-",
            "@meridian-test.example.co.uk",  # test email domain
            "Priya Ashworth-Wainwright",      # participant name
            "debt covenant",                   # answer content (from F test)
        ]
        hits = {}
        for n in needles:
            # Only count INFO lines
            info_lines = [l for l in content.splitlines() if " - INFO - " in l and n in l]
            if info_lines:
                hits[n] = len(info_lines)
        record("I", len(hits) == 0, f"INFO-level leak hits: {hits}")
    except Exception as exc:
        record("I", False, f"log check exception: {exc}")


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 80)
    print("Phase 6 backend sweep")
    print("=" * 80)

    test_a_openapi()

    # B - content fidelity (leaves session at part2 stage)
    sid_b = test_b_content_fidelity()

    # C - 404/pre-start/gate
    test_c_state_and_start()
    sid_c5 = test_c5_idempotency()

    # D - advance validation (uses sid_c5 which is at phase=read)
    test_d_advance_validation(sid_c5)
    # After test_d, sid_c5 is at phase=part1 (no trio was accepted because all payloads were invalid
    # until D3 onwards all 422; the legit read->part1 succeeded)

    # E - autosave (sid_c5 is at phase=part1)
    test_e_autosave(sid_c5)

    # F - live happy path (ONE scoring call)
    sid_f = test_f_live_happy_path()

    # G - regression
    test_g_regression()

    # H - public conversation stripping
    test_h_public_conversation_stripped(sid_f)

    # I - log hygiene
    test_i_log_hygiene()

    # Summary
    print("\n" + "=" * 80)
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"RESULTS: {passed}/{total} passed")
    for letter, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {letter}: {detail[:200]}")
    print("=" * 80)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
