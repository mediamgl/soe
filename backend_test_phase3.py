"""
Phase 3 backend tests — admin auth + LLM settings + LLM router regression.
Runs against http://localhost:8001/api per the review brief.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests

API = "http://localhost:8001/api"

ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASSWORD = "test1234"
TEST_ANTHROPIC_KEY = "sk-ant-testkey-ABC123XYZ"

results: List[Tuple[str, bool, str]] = []


def record(name: str, ok: bool, evidence: str = "") -> None:
    results.append((name, ok, evidence))
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name} :: {evidence}")


# ---------------------------------------------------------------- #
# A-C. Login happy + bad password + unknown email
# ---------------------------------------------------------------- #
def test_login_flows() -> Optional[requests.Session]:
    s = requests.Session()
    r = requests.post(f"{API}/admin/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    # Extract the token from Set-Cookie manually because the cookie is marked
    # Secure; requests.Session won't replay Secure cookies over http://localhost,
    # which is the *correct* server behaviour in production. We carry the token
    # manually here so we can still exercise authed endpoints over http.
    sc = r.headers.get("set-cookie", "")
    m = re.search(r"tra_admin_token=([^;]+);", sc)
    if m:
        s.headers.update({"Cookie": f"tra_admin_token={m.group(1)}"})
    body = r.json() if r.ok else {}
    ok = (
        r.status_code == 200
        and body.get("email") == ADMIN_EMAIL
        and body.get("role") == "admin"
    )
    record("A1 POST /admin/auth/login correct creds -> 200 {email,role}",
           ok, f"status={r.status_code} body={body}")

    # Check set-cookie attributes
    sc = r.headers.get("set-cookie", "")
    cookie_ok = (
        "tra_admin_token=" in sc
        and "HttpOnly" in sc
        and "Secure" in sc
        and "SameSite=lax" in sc.lower().replace("samesite=lax", "SameSite=lax")
        and ("Max-Age=28800" in sc or "max-age=28800" in sc.lower())
    )
    # normalise check
    sc_lower = sc.lower()
    cookie_ok = (
        "tra_admin_token=" in sc
        and "httponly" in sc_lower
        and "secure" in sc_lower
        and "samesite=lax" in sc_lower
        and "max-age=28800" in sc_lower
    )
    record("A2 Set-Cookie has HttpOnly+Secure+SameSite=Lax+Max-Age=28800",
           cookie_ok, f"set-cookie={sc}")

    # B. Wrong password (use a fresh session to avoid accumulating rate-limits)
    r2 = requests.post(f"{API}/admin/auth/login",
                       json={"email": ADMIN_EMAIL, "password": "wrongpass"},
                       timeout=15)
    b2 = r2.json() if r2.status_code == 401 else {}
    record("B1 Wrong password -> 401 'Invalid credentials.'",
           r2.status_code == 401 and b2.get("detail") == "Invalid credentials.",
           f"status={r2.status_code} body={b2}")

    # C. Unknown email -> same 401, same body
    r3 = requests.post(f"{API}/admin/auth/login",
                       json={"email": "ghost@nowhere.io", "password": "whatever"},
                       timeout=15)
    b3 = r3.json() if r3.status_code == 401 else {}
    record("C1 Unknown email -> 401 'Invalid credentials.' (no user-exists leak)",
           r3.status_code == 401 and b3.get("detail") == "Invalid credentials.",
           f"status={r3.status_code} body={b3}")

    return s if ok else None


# ---------------------------------------------------------------- #
# D/E/F/G. auth/me unauth, authed, logout, after-logout
# ---------------------------------------------------------------- #
def test_me_logout(s: requests.Session) -> None:
    # D: no cookie
    r = requests.get(f"{API}/admin/auth/me", timeout=15)
    record("D1 GET /admin/auth/me without cookie -> 401",
           r.status_code == 401,
           f"status={r.status_code} body={r.text[:120]}")

    # E: with cookie
    r = s.get(f"{API}/admin/auth/me", timeout=15)
    body = r.json() if r.ok else {}
    ok = (
        r.status_code == 200
        and body.get("email") == ADMIN_EMAIL
        and body.get("role") == "admin"
    )
    record("E1 GET /admin/auth/me with cookie -> 200 {email,role}",
           ok, f"status={r.status_code} body={body}")


def test_logout_and_post(s: requests.Session) -> None:
    # F: logout (carry cookie manually)
    r = requests.post(f"{API}/admin/auth/logout",
                      headers={"Cookie": s.headers.get("Cookie", "")}, timeout=15)
    body = r.json() if r.ok else {}
    record("F1 POST /admin/auth/logout -> 200 {ok:true}",
           r.status_code == 200 and body.get("ok") is True,
           f"status={r.status_code} body={body}")

    # Browser behaviour: after delete_cookie + the session has no cookie.
    # requests.Session keeps a "deleted" cookie only if the server sends a
    # Max-Age=0 response; confirm server cleared it.
    sc = r.headers.get("set-cookie", "")
    record("F2 logout response clears tra_admin_token cookie",
           "tra_admin_token=" in sc and ('Max-Age=0' in sc or 'max-age=0' in sc.lower() or 'expires=' in sc.lower()),
           f"set-cookie={sc}")

    # G: auth/me after logout — drop the manual cookie header
    s.headers.pop("Cookie", None)
    s.cookies.clear()
    r = requests.get(f"{API}/admin/auth/me", timeout=15)
    record("G1 GET /admin/auth/me after logout -> 401",
           r.status_code == 401, f"status={r.status_code}")


# ---------------------------------------------------------------- #
# H/I. settings unauth + authed shape
# ---------------------------------------------------------------- #
def test_settings_get(s: requests.Session) -> None:
    r = requests.get(f"{API}/admin/settings", timeout=15)
    record("H1 GET /admin/settings without cookie -> 401",
           r.status_code == 401, f"status={r.status_code}")

    r = s.get(f"{API}/admin/settings", timeout=15)
    body = r.json() if r.ok else {}
    required_keys = {"primary", "secondary", "fallback_model",
                     "updated_at", "updated_by", "catalog"}
    missing = required_keys - set(body.keys()) if isinstance(body, dict) else required_keys
    record("I1 GET /admin/settings authed -> 200 with all required keys",
           r.status_code == 200 and not missing,
           f"status={r.status_code} missing={missing} keys={list(body.keys()) if isinstance(body, dict) else 'n/a'}")

    catalog = body.get("catalog", {}) if isinstance(body, dict) else {}
    providers = catalog.get("providers", {}) if isinstance(catalog, dict) else {}
    want = {"anthropic", "openai", "openrouter", "straico", "grok"}
    missing_p = want - set(providers.keys())
    record("I2 catalog.providers contains anthropic/openai/openrouter/straico/grok",
           not missing_p, f"providers={list(providers.keys())} missing={missing_p}")


# ---------------------------------------------------------------- #
# J/K/L/M/N. PUT settings variants
# ---------------------------------------------------------------- #
def test_settings_put(s: requests.Session) -> None:
    # J: write valid primary
    payload = {
        "primary": {
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "api_key": TEST_ANTHROPIC_KEY,
            "label": "T1",
        }
    }
    r = s.put(f"{API}/admin/settings", json=payload, timeout=15)
    body = r.json() if r.ok else {}
    record("J1 PUT /admin/settings primary valid -> 200",
           r.status_code == 200, f"status={r.status_code} body_keys={list(body.keys()) if isinstance(body, dict) else 'n/a'}")

    raw_key_in_put_body = TEST_ANTHROPIC_KEY in r.text
    record("J2 Raw api_key NOT present in PUT response body",
           not raw_key_in_put_body,
           f"raw_key_present={raw_key_in_put_body}")

    # Subsequent GET: expect masked hint, not raw key
    r = s.get(f"{API}/admin/settings", timeout=15)
    body = r.json() if r.ok else {}
    prim = body.get("primary") or {}
    has_key = prim.get("has_key") is True
    key_hint = prim.get("key_hint", "")
    raw_in_get = TEST_ANTHROPIC_KEY in r.text
    record("J3 GET shows masked key_hint, raw key absent from response",
           has_key and key_hint and TEST_ANTHROPIC_KEY not in key_hint and not raw_in_get,
           f"has_key={has_key} key_hint={key_hint!r} raw_in_body={raw_in_get}")

    # K: clear primary with api_key=""
    r = s.put(f"{API}/admin/settings",
              json={"primary": {"api_key": ""}}, timeout=15)
    record("K1 PUT primary.api_key='' -> 200",
           r.status_code == 200, f"status={r.status_code}")

    r = s.get(f"{API}/admin/settings", timeout=15)
    body = r.json() if r.ok else {}
    record("K2 GET shows primary=null after clear",
           body.get("primary") is None,
           f"primary={body.get('primary')}")

    # Re-populate for later test (Q / test-fallback doesn't need primary but test/invalid needs save)
    s.put(f"{API}/admin/settings", json={
        "primary": {
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "api_key": TEST_ANTHROPIC_KEY,
            "label": "T1",
        }
    }, timeout=15)

    # L: unknown provider -> 400
    r = s.put(f"{API}/admin/settings",
              json={"primary": {"provider": "bogusco", "model": "x", "api_key": "k"}},
              timeout=15)
    record("L1 PUT unknown provider -> 400",
           r.status_code == 400, f"status={r.status_code} body={r.text[:160]}")

    # M: unknown model for known provider -> 400
    r = s.put(f"{API}/admin/settings",
              json={"primary": {"provider": "anthropic", "model": "claude-not-real",
                                "api_key": "k"}},
              timeout=15)
    record("M1 PUT unknown model for known provider -> 400",
           r.status_code == 400, f"status={r.status_code} body={r.text[:160]}")

    # N: unknown fallback_model -> 400
    r = s.put(f"{API}/admin/settings",
              json={"fallback_model": "claude-moon-42"}, timeout=15)
    record("N1 PUT unknown fallback_model -> 400",
           r.status_code == 400, f"status={r.status_code} body={r.text[:160]}")


# ---------------------------------------------------------------- #
# O/P. settings/test
# ---------------------------------------------------------------- #
def test_settings_test(s: requests.Session) -> None:
    # O: adhoc with invalid Anthropic key -> ok:false with auth/4xx/model_not_found
    r = s.post(f"{API}/admin/settings/test",
               json={"slot": "adhoc", "provider": "anthropic",
                     "model": "claude-opus-4-6", "api_key": TEST_ANTHROPIC_KEY},
               timeout=30)
    body = r.json() if r.ok else {}
    cat = body.get("error_category", "")
    acceptable = {"auth", "4xx", "model_not_found"}
    record("O1 POST /settings/test adhoc bad anthropic key -> ok:false with auth/4xx/model_not_found",
           r.status_code == 200 and body.get("ok") is False and cat in acceptable,
           f"status={r.status_code} ok={body.get('ok')} error_category={cat} body={str(body)[:220]}")

    # Confirm the raw key is not echoed back in the error body
    record("O2 Raw api_key not present in test response body",
           TEST_ANTHROPIC_KEY not in r.text,
           f"raw_key_in_body={TEST_ANTHROPIC_KEY in r.text}")

    # P: unknown provider adhoc -> ok:false
    r = s.post(f"{API}/admin/settings/test",
               json={"slot": "adhoc", "provider": "nobody",
                     "model": "x", "api_key": "y"},
               timeout=30)
    # Server returns either 400 (validation in _resolve_test_target keeps going)
    # or 200 with ok:false. Accept either so long as there's no success.
    body = {}
    try:
        body = r.json()
    except Exception:
        pass
    ok = (
        r.status_code == 200 and body.get("ok") is False
    ) or r.status_code == 400
    record("P1 POST /settings/test adhoc unknown provider -> ok:false (or 400)",
           ok, f"status={r.status_code} body={str(body)[:160]}")


# ---------------------------------------------------------------- #
# Q. test-fallback (REAL round-trip)
# ---------------------------------------------------------------- #
def test_fallback(s: requests.Session) -> None:
    started = time.time()
    r = s.post(f"{API}/admin/settings/test-fallback", timeout=30)
    elapsed = time.time() - started
    body = r.json() if r.ok else {}
    # We may need to know configured fallback_model from GET to assert model match
    g = s.get(f"{API}/admin/settings", timeout=15)
    gbody = g.json() if g.ok else {}
    configured_fallback = gbody.get("fallback_model")

    ok = (
        r.status_code == 200
        and body.get("ok") is True
        and isinstance(body.get("latency_ms"), int)
        and body["latency_ms"] > 0
        and body.get("provider") == "emergent"
        and body.get("model") == configured_fallback
    )
    record("Q1 POST /settings/test-fallback real round-trip -> ok:true",
           ok,
           f"status={r.status_code} elapsed={elapsed:.1f}s ok={body.get('ok')} "
           f"latency_ms={body.get('latency_ms')} provider={body.get('provider')} "
           f"model={body.get('model')} configured={configured_fallback} "
           f"error={body.get('error','')[:200]}")


# ---------------------------------------------------------------- #
# R. Regression: sessions POST + resume still work
# ---------------------------------------------------------------- #
def test_regression_sessions() -> None:
    r = requests.post(f"{API}/sessions", json={
        "name": "Priya Subramanian",
        "email": f"priya.sub+{uuid.uuid4().hex[:6]}@example.com",
        "organisation": "Meridian Partners",
        "role": "Chief of Staff",
        "consent": True,
    }, headers={"X-Forwarded-For": "192.0.2.55"}, timeout=15)
    body = r.json() if r.ok else {}
    sid = body.get("session_id", "")
    code = body.get("resume_code", "")
    record("R1 POST /api/sessions still 201 with session_id+resume_code",
           r.status_code == 201 and sid and code and body.get("stage") == "identity",
           f"status={r.status_code} body={body}")

    if code:
        r2 = requests.get(f"{API}/sessions/resume/{code}", timeout=15)
        b2 = r2.json() if r2.ok else {}
        record("R2 GET /api/sessions/resume/{code} still works",
               r2.status_code == 200 and b2.get("session_id") == sid,
               f"status={r2.status_code} body_keys={list(b2.keys())}")


# ---------------------------------------------------------------- #
# S. Raw key not present anywhere after saving
# ---------------------------------------------------------------- #
def test_secret_hygiene(s: requests.Session) -> None:
    # GET settings -> no raw
    r = s.get(f"{API}/admin/settings", timeout=15)
    raw_in_settings = TEST_ANTHROPIC_KEY in r.text
    record("S1 GET /admin/settings response does NOT contain raw api_key",
           not raw_in_settings,
           f"raw_in_body={raw_in_settings}")

    # openapi.json -> no raw
    r = requests.get(f"{API}/openapi.json", timeout=15)
    record("S2 /api/openapi.json does NOT contain raw api_key",
           TEST_ANTHROPIC_KEY not in r.text,
           f"raw_in_openapi={TEST_ANTHROPIC_KEY in r.text}")


# ---------------------------------------------------------------- #
# T. Password not in backend logs
# ---------------------------------------------------------------- #
def test_log_hygiene() -> None:
    paths = ["/var/log/supervisor/backend.out.log",
             "/var/log/supervisor/backend.err.log"]
    hits: List[str] = []
    raw_key_hits: List[str] = []
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            data = subprocess.check_output(["tail", "-n", "4000", p], text=True,
                                           stderr=subprocess.STDOUT)
        except Exception:
            continue
        for line in data.splitlines():
            if ADMIN_PASSWORD in line:
                # Filter out innocuous mentions that don't leak the actual
                # password — here we need exact presence. Any presence is bad.
                hits.append(line.strip()[:200])
            if TEST_ANTHROPIC_KEY in line:
                raw_key_hits.append(line.strip()[:200])
    record("T1 password 'test1234' does NOT appear in backend logs",
           not hits, f"hits={len(hits)} sample={hits[:2]}")
    record("T2 raw anthropic api_key does NOT appear in backend logs",
           not raw_key_hits, f"hits={len(raw_key_hits)} sample={raw_key_hits[:2]}")


# ---------------------------------------------------------------- #
# U. /api/docs + openapi lists all expected endpoints
# ---------------------------------------------------------------- #
def test_openapi() -> None:
    r = requests.get(f"{API}/docs", timeout=15)
    record("U1 /api/docs returns 200 with Swagger UI",
           r.status_code == 200 and "swagger" in r.text.lower(),
           f"status={r.status_code} len={len(r.text)}")

    r = requests.get(f"{API}/openapi.json", timeout=15)
    data = r.json() if r.ok else {}
    paths = data.get("paths", {}) if isinstance(data, dict) else {}
    required = [
        ("POST", "/api/admin/auth/login"),
        ("POST", "/api/admin/auth/logout"),
        ("GET",  "/api/admin/auth/me"),
        ("GET",  "/api/admin/settings"),
        ("PUT",  "/api/admin/settings"),
        ("POST", "/api/admin/settings/test"),
        ("POST", "/api/admin/settings/test-fallback"),
        # session endpoints (regression)
        ("POST", "/api/sessions"),
        ("GET",  "/api/sessions/resume/{resume_code}"),
        ("PATCH","/api/sessions/{session_id}/stage"),
        ("GET",  "/api/sessions/{session_id}"),
    ]
    missing = []
    for m, p in required:
        node = paths.get(p) or {}
        if m.lower() not in {k.lower() for k in node.keys()}:
            missing.append(f"{m} {p}")
    record("U2 openapi.json lists all 7 admin + 4 session endpoints",
           not missing, f"missing={missing}" if missing else "all 11 present")


# ---------------------------------------------------------------- #
# Runner
# ---------------------------------------------------------------- #
def main() -> int:
    print(f"API = {API}")

    # Health ping
    r = requests.get(f"{API}/health", timeout=10)
    record("ping /api/health", r.status_code == 200, f"status={r.status_code}")

    s = test_login_flows()
    if not s:
        print("Login failed; cannot continue with authed tests.")
        _summary()
        return 1

    test_me_logout(s)
    test_settings_get(s)
    test_settings_put(s)
    test_settings_test(s)
    test_fallback(s)
    test_secret_hygiene(s)
    test_openapi()
    test_regression_sessions()
    test_log_hygiene()

    # Logout now at the very end so earlier cookie-bearing tests worked.
    test_logout_and_post(s)

    return _summary()


def _summary() -> int:
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
