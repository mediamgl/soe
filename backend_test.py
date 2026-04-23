"""Phase 4 backend test harness — psychometric endpoints + scoring + admin read.
Runs against http://localhost:8001/api.

Covers letters A-Q from the review request. Prints a per-letter PASS/FAIL
report with evidence (status codes + key field values).
"""
from __future__ import annotations
import time
import sys
import re
from typing import Any, Dict, List, Optional, Tuple
import requests

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASSWORD = "test1234"

RESULTS: List[Dict[str, Any]] = []
_SESSION_SEQ = [0]


def _fresh_ip() -> str:
    _SESSION_SEQ[0] += 1
    # Use 198.51.100.0/24 (TEST-NET-2, never in routing). Unique per session.
    return f"198.51.100.{(_SESSION_SEQ[0] % 250) + 1}"


def record(letter: str, ok: bool, detail: str) -> None:
    RESULTS.append({"letter": letter, "ok": ok, "detail": detail})
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {letter}: {detail}")


def _assert(cond: bool, letter: str, detail: str, stop_on_fail: bool = False) -> bool:
    record(letter, cond, detail)
    if not cond and stop_on_fail:
        raise SystemExit(f"FATAL: {letter} failed: {detail}")
    return cond


def new_session(headers: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
    payload = {
        "name": "Harriet Locke",
        "email": f"harriet.locke+{int(time.time()*1000)}@example.co.uk",
        "organisation": "Meridian Consulting",
        "role": "Programme Director",
        "consent": True,
    }
    hdrs = dict(headers or {})
    # Avoid creation-rate-limit cross-contamination across tests.
    hdrs.setdefault("X-Forwarded-For", _fresh_ip())
    r = requests.post(f"{BASE}/sessions", json=payload, headers=hdrs, timeout=10)
    assert r.status_code == 201, f"Expected 201 creating session, got {r.status_code}: {r.text[:200]}"
    body = r.json()
    return body["session_id"], body["resume_code"]


_ADMIN_TOKEN_CACHE: List[str] = []


def admin_login_cookie() -> str:
    if _ADMIN_TOKEN_CACHE:
        return _ADMIN_TOKEN_CACHE[0]
    r = requests.post(
        f"{BASE}/admin/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Forwarded-For": _fresh_ip()},
        timeout=10,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    raw = r.headers.get("Set-Cookie", "")
    m = re.search(r"tra_admin_token=([^;]+)", raw)
    assert m, f"No admin cookie in login response: {raw}"
    _ADMIN_TOKEN_CACHE.append(m.group(1))
    return m.group(1)


def test_A() -> None:
    sid, _rc = new_session()
    r = requests.get(f"{BASE}/assessment/psychometric/next",
                     params={"session_id": sid}, timeout=10)
    _assert(r.status_code == 200, "A", f"GET /next status={r.status_code}", stop_on_fail=True)
    body = r.json()
    ok = (
        body.get("done") is False
        and "item" in body
        and {"item_id", "text", "scale", "subscale"} <= set(body["item"].keys())
        and body["progress"]["answered"] == 0
        and body["progress"]["total"] == 20
        and body["progress"]["current_index_1based"] == 1
    )
    _assert(ok, "A1", f"/next first-call shape: done={body.get('done')} "
                       f"item_id={body.get('item', {}).get('item_id')} "
                       f"progress={body.get('progress')}")

    token = admin_login_cookie()
    cookie_hdr = {"Cookie": f"tra_admin_token={token}"}
    r2 = requests.get(f"{BASE}/admin/sessions/{sid}", headers=cookie_hdr, timeout=10)
    _assert(r2.status_code == 200, "A2", f"admin GET /sessions status={r2.status_code}")
    doc = r2.json()
    order = doc.get("psychometric", {}).get("order", [])
    first_la = all(i.startswith("LA") for i in order[:12])
    last_ta = all(i.startswith("TA") for i in order[12:])
    _assert(
        len(order) == 20 and first_la and last_ta,
        "A3",
        f"order length={len(order)}, first12_all_LA={first_la}, last8_all_TA={last_ta} "
        f"(order_sample={order[:3]}...{order[-3:]})",
    )
    _assert(doc.get("stage") == "psychometric", "A4", f"session.stage={doc.get('stage')}")
    _assert(bool(doc.get("psychometric", {}).get("started_at")),
            "A5", f"started_at={doc.get('psychometric', {}).get('started_at')}")


def test_B() -> None:
    sid, _ = new_session()
    r1 = requests.get(f"{BASE}/assessment/psychometric/next", params={"session_id": sid}, timeout=10)
    r2 = requests.get(f"{BASE}/assessment/psychometric/next", params={"session_id": sid}, timeout=10)
    id1 = r1.json()["item"]["item_id"]
    id2 = r2.json()["item"]["item_id"]
    _assert(id1 == id2, "B", f"two consecutive /next return same id? {id1} vs {id2}")


def answer_all(sid: str, value_for: Any = 4,
               headers: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    hdrs = dict(headers or {})
    hdrs.setdefault("X-Forwarded-For", _fresh_ip())
    responses: List[Dict[str, Any]] = []
    for step in range(20):
        r = requests.get(f"{BASE}/assessment/psychometric/next",
                         params={"session_id": sid}, headers=hdrs, timeout=10)
        body = r.json()
        if body.get("done"):
            break
        item = body["item"]
        val = value_for(item) if callable(value_for) else value_for
        post = requests.post(f"{BASE}/assessment/psychometric/answer",
                             headers=hdrs, json={
                                 "session_id": sid,
                                 "item_id": item["item_id"],
                                 "value": val,
                                 "response_time_ms": 1200 + step * 10,
                             }, timeout=10)
        if post.status_code != 200:
            raise RuntimeError(f"Answer step {step} failed: {post.status_code} {post.text}")
        responses.append(post.json())
    return responses


def test_C_and_D() -> None:
    sid, _ = new_session()
    seen_items: List[str] = []
    responses: List[Dict[str, Any]] = []
    ip_header = {"X-Forwarded-For": _fresh_ip()}
    for step in range(20):
        nx = requests.get(f"{BASE}/assessment/psychometric/next",
                          params={"session_id": sid}, headers=ip_header, timeout=10).json()
        assert not nx["done"], f"Premature done at step {step}"
        item = nx["item"]
        if seen_items and item["item_id"] == seen_items[-1]:
            _assert(False, "C-next-diff",
                    f"next item equals previous on step {step}: {item['item_id']}")
        seen_items.append(item["item_id"])
        post = requests.post(f"{BASE}/assessment/psychometric/answer",
                             headers=ip_header, json={
                                 "session_id": sid, "item_id": item["item_id"],
                                 "value": 4, "response_time_ms": 1500,
                             }, timeout=10).json()
        answered = post["progress"]["answered"]
        expected = step + 1
        if answered != expected:
            _assert(False, "C-increment",
                    f"progress.answered not +1 at step {step}: expected {expected}, got {answered}")
            break
        responses.append(post)

    final = responses[-1] if responses else {}
    _assert(final.get("done") is True and final["progress"]["answered"] == 20,
            "C", f"final response done={final.get('done')} "
                  f"answered={final.get('progress', {}).get('answered')}")

    token = admin_login_cookie()
    cookie_hdr = {"Cookie": f"tra_admin_token={token}"}
    doc = requests.get(f"{BASE}/admin/sessions/{sid}", headers=cookie_hdr, timeout=10).json()
    scores = (doc.get("scores") or {}).get("psychometric") or {}
    keys = set(scores.keys())
    required = {"learning_agility", "tolerance_for_ambiguity",
                "self_awareness_claimed", "timing", "bands_reference"}
    _assert(required <= keys, "C-scores-keys", f"scores.psychometric keys={sorted(keys)}")

    la = scores.get("learning_agility", {})
    ta = scores.get("tolerance_for_ambiguity", {})
    d_ok = (
        la.get("raw_sum") == 48 and abs(la.get("mean_6pt", 0) - 4.0) < 1e-6
        and abs(la.get("mean_1_5", 0) - 3.4) < 0.01 and la.get("band") == "Moderate"
        and ta.get("raw_sum") == 32 and abs(ta.get("mean_6pt", 0) - 4.0) < 1e-6
        and abs(ta.get("mean_1_5", 0) - 3.4) < 0.01 and ta.get("band") == "Moderate"
    )
    _assert(d_ok, "D",
            f"LA(raw={la.get('raw_sum')}, m6={la.get('mean_6pt')}, m15={la.get('mean_1_5')}, "
            f"band={la.get('band')}) | TA(raw={ta.get('raw_sum')}, m6={ta.get('mean_6pt')}, "
            f"m15={ta.get('mean_1_5')}, band={ta.get('band')})")
    la_subs = la.get("subscales", {})
    ta_subs = ta.get("subscales", {})
    _assert(set(la_subs.keys()) == {"Mental Agility", "People Agility",
                                     "Change Agility", "Results Agility", "Self-Awareness"},
            "C-la-subscales", f"LA subscales keys={sorted(la_subs.keys())}")
    _assert(set(ta_subs.keys()) == {"Uncertainty Comfort", "Complexity Comfort", "Closure Resistance"},
            "C-ta-subscales", f"TA subscales keys={sorted(ta_subs.keys())}")


def test_E() -> None:
    sid, _ = new_session()
    requests.get(f"{BASE}/assessment/psychometric/next",
                 params={"session_id": sid}, timeout=10)
    cases = [
        ("value=0",  {"session_id": sid, "item_id": "LA01", "value": 0,   "response_time_ms": 100}),
        ("value=7",  {"session_id": sid, "item_id": "LA01", "value": 7,   "response_time_ms": 100}),
        ("value=3.5",{"session_id": sid, "item_id": "LA01", "value": 3.5, "response_time_ms": 100}),
        ("rt=-1",    {"session_id": sid, "item_id": "LA01", "value": 4,   "response_time_ms": -1}),
        ("miss sid", {                   "item_id": "LA01", "value": 4,   "response_time_ms": 100}),
        ("miss iid", {"session_id": sid,                    "value": 4,   "response_time_ms": 100}),
        ("miss val", {"session_id": sid, "item_id": "LA01",               "response_time_ms": 100}),
    ]
    all_422 = True
    details = []
    for name, body in cases:
        r = requests.post(f"{BASE}/assessment/psychometric/answer", json=body, timeout=10)
        details.append(f"{name}->{r.status_code}")
        if r.status_code != 422:
            all_422 = False
    _assert(all_422, "E", f"all should be 422: {', '.join(details)}")


def test_F() -> None:
    sid, _ = new_session()
    requests.get(f"{BASE}/assessment/psychometric/next",
                 params={"session_id": sid}, timeout=10)
    r = requests.post(f"{BASE}/assessment/psychometric/answer", json={
        "session_id": sid, "item_id": "ZZ99", "value": 4, "response_time_ms": 100,
    }, timeout=10)
    body = r.json()
    detail = body.get("detail", "")
    msg_ok = isinstance(detail, str) and "Unknown item_id" in detail
    _assert(r.status_code == 422 and msg_ok,
            "F", f"status={r.status_code} detail={detail!r}")


def test_G() -> None:
    sid, _ = new_session()
    nx = requests.get(f"{BASE}/assessment/psychometric/next",
                      params={"session_id": sid}, timeout=10).json()
    expected = nx["item"]["item_id"]
    token = admin_login_cookie()
    doc = requests.get(f"{BASE}/admin/sessions/{sid}",
                       headers={"Cookie": f"tra_admin_token={token}"}, timeout=10).json()
    order = doc["psychometric"]["order"]
    other = next(i for i in order if i != expected)
    r = requests.post(f"{BASE}/assessment/psychometric/answer", json={
        "session_id": sid, "item_id": other, "value": 3, "response_time_ms": 900,
    }, timeout=10)
    body = r.json()
    detail = body.get("detail", {})
    got_expected = isinstance(detail, dict) and detail.get("expected_item_id") == expected
    _assert(r.status_code == 409 and got_expected,
            "G", f"status={r.status_code} detail={detail} expected={expected} sent={other}")


def test_H() -> None:
    sid, _ = new_session()
    nx = requests.get(f"{BASE}/assessment/psychometric/next",
                      params={"session_id": sid}, timeout=10).json()
    iid = nx["item"]["item_id"]
    r1 = requests.post(f"{BASE}/assessment/psychometric/answer", json={
        "session_id": sid, "item_id": iid, "value": 5, "response_time_ms": 1100,
    }, timeout=10)
    r2 = requests.post(f"{BASE}/assessment/psychometric/answer", json={
        "session_id": sid, "item_id": iid, "value": 5, "response_time_ms": 1100,
    }, timeout=10)
    body2 = r2.json()
    _assert(r2.status_code == 200 and body2.get("idempotent") is True,
            "H1", f"within-2s replay status={r2.status_code} body={body2}")
    time.sleep(2.6)
    r3 = requests.post(f"{BASE}/assessment/psychometric/answer", json={
        "session_id": sid, "item_id": iid, "value": 5, "response_time_ms": 1100,
    }, timeout=10)
    body3 = r3.json()
    det = body3.get("detail", {})
    msg = det.get("message") if isinstance(det, dict) else det
    _assert(r3.status_code == 409 and (msg or "").lower().startswith("item already answered"),
            "H2", f"after-2s replay status={r3.status_code} body={body3}")
    _ = r1


def test_I() -> None:
    sid, _ = new_session()
    nx = requests.get(f"{BASE}/assessment/psychometric/next",
                      params={"session_id": sid}, timeout=10).json()
    iid = nx["item"]["item_id"]
    requests.post(f"{BASE}/assessment/psychometric/answer", json={
        "session_id": sid, "item_id": iid, "value": 5, "response_time_ms": 1100,
    }, timeout=10)
    r = requests.post(f"{BASE}/assessment/psychometric/answer", json={
        "session_id": sid, "item_id": iid, "value": 3, "response_time_ms": 1100,
    }, timeout=10)
    _assert(r.status_code == 409,
            "I", f"different-value within 2s status={r.status_code} body={r.text[:140]}")


def test_J() -> None:
    sid, _ = new_session()
    p0 = requests.get(f"{BASE}/assessment/psychometric/progress",
                      params={"session_id": sid}, timeout=10).json()
    _assert(p0["answered"] == 0 and p0["total"] == 20 and p0["done"] is False
            and p0["scale_counts"]["LA"]["total"] == 12
            and p0["scale_counts"]["TA"]["total"] == 8,
            "J-pre", f"pre-init progress={p0}")
    for step in range(5):
        nx = requests.get(f"{BASE}/assessment/psychometric/next",
                          params={"session_id": sid}, timeout=10).json()
        requests.post(f"{BASE}/assessment/psychometric/answer", json={
            "session_id": sid, "item_id": nx["item"]["item_id"],
            "value": 4, "response_time_ms": 800,
        }, timeout=10)
    p5 = requests.get(f"{BASE}/assessment/psychometric/progress",
                      params={"session_id": sid}, timeout=10).json()
    _assert(p5["answered"] == 5 and p5["scale_counts"]["LA"]["answered"] == 5
            and p5["scale_counts"]["TA"]["answered"] == 0 and p5["done"] is False,
            "J-mid", f"mid progress={p5}")


def test_K() -> None:
    sid, _ = new_session()
    for _ in range(5):
        nx = requests.get(f"{BASE}/assessment/psychometric/next",
                          params={"session_id": sid}, timeout=10).json()
        requests.post(f"{BASE}/assessment/psychometric/answer", json={
            "session_id": sid, "item_id": nx["item"]["item_id"],
            "value": 4, "response_time_ms": 700,
        }, timeout=10)
    token = admin_login_cookie()
    doc1 = requests.get(f"{BASE}/admin/sessions/{sid}",
                        headers={"Cookie": f"tra_admin_token={token}"}, timeout=10).json()
    order_persisted = doc1["psychometric"]["order"]
    expected_6 = order_persisted[5]
    nx = requests.get(f"{BASE}/assessment/psychometric/next",
                      params={"session_id": sid}, timeout=10).json()
    _assert(nx["item"]["item_id"] == expected_6,
            "K1", f"after 5 answered /next gives item 6? got={nx['item']['item_id']} "
                   f"expected={expected_6}")
    nx2 = requests.get(f"{BASE}/assessment/psychometric/next",
                       params={"session_id": sid}, timeout=10).json()
    _assert(nx2["item"]["item_id"] == expected_6,
            "K2", f"resume /next item stable? {nx2['item']['item_id']} == {expected_6}")
    doc_mid = requests.get(f"{BASE}/admin/sessions/{sid}",
                           headers={"Cookie": f"tra_admin_token={token}"}, timeout=10).json()
    _assert(doc_mid["psychometric"]["order"] == order_persisted,
            "K3", "order preserved across resumes")
    _assert(doc_mid.get("scores") is None or not (doc_mid.get("scores") or {}).get("psychometric"),
            "K4", "scores NOT yet computed mid-way")

    for _ in range(15):
        nx = requests.get(f"{BASE}/assessment/psychometric/next",
                          params={"session_id": sid}, timeout=10).json()
        if nx.get("done"):
            break
        requests.post(f"{BASE}/assessment/psychometric/answer", json={
            "session_id": sid, "item_id": nx["item"]["item_id"],
            "value": 4, "response_time_ms": 700,
        }, timeout=10)
    doc2 = requests.get(f"{BASE}/admin/sessions/{sid}",
                        headers={"Cookie": f"tra_admin_token={token}"}, timeout=10).json()
    scores = (doc2.get("scores") or {}).get("psychometric")
    _assert(scores is not None and "learning_agility" in scores,
            "K5", f"scores.psychometric computed on 20th? keys="
                   f"{sorted((scores or {}).keys())}")


def test_L() -> None:
    sid, _ = new_session()
    answer_all(sid, 4)
    r_no = requests.get(f"{BASE}/admin/sessions/{sid}", timeout=10)
    _assert(r_no.status_code == 401, "L1", f"unauth status={r_no.status_code}")
    token = admin_login_cookie()
    r = requests.get(f"{BASE}/admin/sessions/{sid}",
                     headers={"Cookie": f"tra_admin_token={token}"}, timeout=10)
    _assert(r.status_code == 200, "L2", f"authed status={r.status_code}")
    doc = r.json()
    has_scores = bool((doc.get("scores") or {}).get("psychometric"))
    has_order = bool(doc.get("psychometric", {}).get("order"))
    _assert(has_scores and has_order,
            "L3", f"admin doc has scores.psychometric={has_scores}, "
                   f"psychometric.order={has_order}")


def test_M() -> None:
    sid, _ = new_session()
    answer_all(sid, 4)
    r = requests.get(f"{BASE}/sessions/{sid}", timeout=10).json()
    scores_null = r.get("scores") is None
    deliverable_null = r.get("deliverable") is None
    has_participant = bool(r.get("participant", {}).get("email"))
    has_order = bool(r.get("psychometric", {}).get("order"))
    has_answers = bool(r.get("psychometric", {}).get("answers"))
    _assert(scores_null and deliverable_null and has_participant and has_order and has_answers,
            "M", f"scores_null={scores_null} deliverable_null={deliverable_null} "
                  f"participant={has_participant} order_present={has_order} answers_present={has_answers}")


def test_N() -> None:
    # Unique IP per run to avoid the 10/hr session creation limit.
    ip = f"192.0.2.{(int(time.time()) % 250) + 1}"
    ip_header = {"X-Forwarded-For": ip}
    sids = []
    for _ in range(3):
        # Override new_session's automatic IP with our pinned test-N IP
        payload = {
            "name": "Harriet Locke",
            "email": f"n.test+{int(time.time()*1000)}@example.co.uk",
            "organisation": "Meridian", "role": "PM", "consent": True,
        }
        r = requests.post(f"{BASE}/sessions", json=payload, headers=ip_header, timeout=10)
        assert r.status_code == 201, f"session create failed: {r.status_code} {r.text}"
        sids.append(r.json()["session_id"])
    succeeded = 0
    for sid in sids:
        for step in range(20):
            nx = requests.get(f"{BASE}/assessment/psychometric/next",
                              params={"session_id": sid},
                              headers=ip_header, timeout=10).json()
            if nx.get("done"):
                break
            r = requests.post(f"{BASE}/assessment/psychometric/answer",
                              headers=ip_header, json={
                                  "session_id": sid,
                                  "item_id": nx["item"]["item_id"],
                                  "value": 4, "response_time_ms": 700,
                              }, timeout=10)
            if r.status_code == 200:
                succeeded += 1
            else:
                _assert(False, "N-loop",
                        f"unexpected {r.status_code} after {succeeded} ok: {r.text[:150]}")
                return
    fresh_sid_payload = {
        "name": "Harriet Locke",
        "email": f"n.fresh+{int(time.time()*1000)}@example.co.uk",
        "organisation": "Meridian", "role": "PM", "consent": True,
    }
    fr = requests.post(f"{BASE}/sessions", json=fresh_sid_payload, headers=ip_header, timeout=10)
    assert fr.status_code == 201, f"fresh session create failed: {fr.status_code} {fr.text}"
    fresh_sid = fr.json()["session_id"]
    nx = requests.get(f"{BASE}/assessment/psychometric/next",
                      params={"session_id": fresh_sid},
                      headers=ip_header, timeout=10).json()
    r_over = requests.post(f"{BASE}/assessment/psychometric/answer",
                           headers=ip_header, json={
                               "session_id": fresh_sid,
                               "item_id": nx["item"]["item_id"],
                               "value": 4, "response_time_ms": 700,
                           }, timeout=10)
    _assert(succeeded == 60 and r_over.status_code == 429,
            "N", f"60 ok POSTs={succeeded}; 61st status={r_over.status_code}")


def test_O() -> None:
    d = requests.get(f"{BASE}/openapi.json", timeout=10).json()
    paths = set(d.get("paths", {}).keys())
    required = {
        "/api/assessment/psychometric/next",
        "/api/assessment/psychometric/answer",
        "/api/assessment/psychometric/progress",
        "/api/admin/sessions/{session_id}",
    }
    missing = required - paths
    _assert(not missing, "O", f"missing paths: {missing or 'none'} "
                               f"(found {len(paths)} total)")


def test_P() -> None:
    sid, code = new_session()
    r = requests.get(f"{BASE}/sessions/resume/{code}", timeout=10)
    _assert(r.status_code == 200, "P-resume", f"resume status={r.status_code}")
    r = requests.patch(f"{BASE}/sessions/{sid}/stage", json={"stage": "context"}, timeout=10)
    _assert(r.status_code == 200, "P-patch", f"patch stage status={r.status_code}")
    r = requests.get(f"{BASE}/sessions/{sid}", timeout=10)
    _assert(r.status_code == 200, "P-get", f"get session status={r.status_code}")
    login = requests.post(f"{BASE}/admin/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          headers={"X-Forwarded-For": _fresh_ip()}, timeout=10)
    _assert(login.status_code == 200, "P-login", f"login status={login.status_code}")
    raw = login.headers.get("Set-Cookie", "")
    m = re.search(r"tra_admin_token=([^;]+)", raw)
    token = m.group(1) if m else ""
    cookie = {"Cookie": f"tra_admin_token={token}"}
    r = requests.get(f"{BASE}/admin/auth/me", headers=cookie, timeout=10)
    _assert(r.status_code == 200, "P-me", f"/me status={r.status_code}")
    r = requests.get(f"{BASE}/admin/settings", headers=cookie, timeout=10)
    _assert(r.status_code == 200, "P-settings", f"/settings status={r.status_code}")
    r = requests.post(f"{BASE}/admin/auth/logout", headers=cookie, timeout=10)
    _assert(r.status_code == 200, "P-logout", f"/logout status={r.status_code}")


def test_Q() -> None:
    try:
        with open("/var/log/supervisor/backend.out.log", "r", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        _assert(False, "Q", "backend.out.log not found")
        return
    snippet = content[-500_000:]
    info_lines = [ln for ln in snippet.splitlines() if " - INFO - " in ln]
    info_joined = "\n".join(info_lines)
    email_hit = re.search(r"@example\.co\.uk", info_joined)
    password_hit = "test1234" in info_joined
    apikey_hit = bool(re.search(r"sk-(ant|emergent|proj)-[A-Za-z0-9]{6,}", info_joined))
    bad = email_hit or password_hit or apikey_hit
    _assert(not bad,
            "Q", f"email_in_INFO={bool(email_hit)}, password_in_INFO={password_hit}, "
                  f"apikey_in_INFO={apikey_hit}")


def main() -> int:
    tests = [
        ("A", test_A), ("B", test_B), ("C_D", test_C_and_D),
        ("E", test_E), ("F", test_F), ("G", test_G),
        ("H", test_H), ("I", test_I), ("J", test_J),
        ("K", test_K), ("L", test_L), ("M", test_M),
        ("N", test_N), ("O", test_O), ("P", test_P), ("Q", test_Q),
    ]
    for name, fn in tests:
        print(f"\n=== Running test {name} ===")
        try:
            fn()
        except Exception as exc:
            record(name, False, f"Exception: {type(exc).__name__}: {exc}")
    print("\n=== SUMMARY ===")
    passes = sum(1 for r in RESULTS if r["ok"])
    fails = [r for r in RESULTS if not r["ok"]]
    print(f"{passes}/{len(RESULTS)} assertions passed; {len(fails)} failures")
    for f in fails:
        print(f"  FAIL [{f['letter']}] {f['detail']}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
