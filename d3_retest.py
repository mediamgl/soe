"""
D3 privacy-leak re-verification + D1/D2 regression after the surgical fix.

Tests per the review request:
  1. PATCH /api/admin/sessions/{id} {notes:"private admin note"} on Ada session
  2. GET /api/sessions/{id} (public, no cookie)
     - No admin_notes, last_admin_viewed_at, deleted_at, hard_delete_at, redacted
     - synthesis absent/null OR only {status, started_at, completed_at}
     - scores null, deliverable null
  3. Admin GET /api/admin/sessions/{id} still exposes all those fields
  4. Regression D1/D2: archive toggle clears and restores expires_at
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import requests

BASE = "https://farm-readiness.preview.emergentagent.com/api"
ADA_SID = "2253141a-830f-4810-a683-890f098b5664"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASSWORD = "test1234"

PUBLIC_FORBIDDEN_TOP = (
    "admin_notes",
    "last_admin_viewed_at",
    "deleted_at",
    "hard_delete_at",
    "redacted",
)
PUBLIC_ALLOWED_SYNTHESIS_KEYS = {"status", "started_at", "completed_at"}
PUBLIC_FORBIDDEN_SYNTHESIS_KEYS = ("provider", "model", "fallbacks_tried", "error")


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


failures: list[str] = []


def check(cond: bool, desc: str) -> None:
    if cond:
        _ok(desc)
    else:
        _fail(desc)
        failures.append(desc)


def admin_login() -> dict:
    r = requests.post(
        f"{BASE}/admin/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    cookie = r.cookies.get("tra_admin_token")
    assert cookie, f"no tra_admin_token in Set-Cookie, got {r.cookies!r}"
    return {"tra_admin_token": cookie}


def main() -> int:
    print(f"\n=== D3 re-verification on {BASE} ===\n")
    admin_cookies = admin_login()
    print(f"Admin login OK; cookie len={len(admin_cookies['tra_admin_token'])}\n")

    # ------------------------------------------------------------------ #
    # 1. PATCH admin_notes (Phase-8 private field)
    # ------------------------------------------------------------------ #
    note = "private admin note (D3 re-verify)"
    r = requests.patch(
        f"{BASE}/admin/sessions/{ADA_SID}",
        json={"notes": note},
        cookies=admin_cookies,
        timeout=30,
    )
    check(r.status_code == 200, f"PATCH /admin/sessions/{{id}} notes -> 200 (got {r.status_code})")
    if r.status_code == 200:
        body = r.json()
        check(body.get("admin_notes") == note,
              f"admin PATCH response carries admin_notes == '{note}'")

    # ------------------------------------------------------------------ #
    # 2. PUBLIC GET must not leak any Phase-8 admin fields
    # ------------------------------------------------------------------ #
    r = requests.get(f"{BASE}/sessions/{ADA_SID}", timeout=30)
    check(r.status_code == 200, f"public GET /sessions/{{id}} -> 200 (got {r.status_code})")
    pub = r.json() if r.status_code == 200 else {}

    for key in PUBLIC_FORBIDDEN_TOP:
        check(key not in pub,
              f"public body omits top-level '{key}' (actual: {pub.get(key, '<absent>')!r})")

    check(pub.get("scores") is None, "public scores is null")
    check(pub.get("deliverable") is None, "public deliverable is null")

    synth = pub.get("synthesis", None)
    if synth is None:
        _ok("public synthesis is absent/null -> allowed")
    elif isinstance(synth, dict):
        extra = set(synth.keys()) - PUBLIC_ALLOWED_SYNTHESIS_KEYS
        check(not extra,
              f"public synthesis contains only {PUBLIC_ALLOWED_SYNTHESIS_KEYS} "
              f"(extra keys leaked: {sorted(extra)})")
        for k in PUBLIC_FORBIDDEN_SYNTHESIS_KEYS:
            check(k not in synth,
                  f"public synthesis omits '{k}' (actual: {synth.get(k, '<absent>')!r})")
    else:
        _fail(f"public synthesis is unexpected type: {type(synth).__name__}")
        failures.append("public synthesis wrong type")

    # Dump the full keys for operator visibility
    print(f"\n  public top-level keys: {sorted(pub.keys())}")
    if isinstance(synth, dict):
        print(f"  public synthesis keys: {sorted(synth.keys())}")

    # ------------------------------------------------------------------ #
    # 3. ADMIN GET still exposes every Phase-8 admin field
    # ------------------------------------------------------------------ #
    r = requests.get(f"{BASE}/admin/sessions/{ADA_SID}", cookies=admin_cookies, timeout=30)
    check(r.status_code == 200, f"admin GET /admin/sessions/{{id}} -> 200 (got {r.status_code})")
    adoc = r.json() if r.status_code == 200 else {}

    check(adoc.get("admin_notes") == note,
          f"admin body carries admin_notes == '{note}' (actual: {adoc.get('admin_notes')!r})")
    check("last_admin_viewed_at" in adoc and adoc["last_admin_viewed_at"],
          f"admin body carries last_admin_viewed_at (actual: {adoc.get('last_admin_viewed_at')!r})")
    # deleted_at / hard_delete_at / redacted are allowed to be None for an
    # active session — we only require the field to be PRESENT on the admin view.
    for key in ("deleted_at", "hard_delete_at", "redacted"):
        check(key in adoc, f"admin body carries '{key}' key (value: {adoc.get(key)!r})")

    asynth = adoc.get("synthesis")
    if isinstance(asynth, dict):
        exposed = [k for k in PUBLIC_FORBIDDEN_SYNTHESIS_KEYS if k in asynth]
        print(f"  admin synthesis exposes: {sorted(asynth.keys())}")
        # At least provider / model are required on a completed synthesis.
        check("provider" in asynth and "model" in asynth,
              f"admin synthesis still exposes provider+model (got: {exposed})")
    else:
        print(f"  admin synthesis value: {asynth!r}")

    # ------------------------------------------------------------------ #
    # 4. Regression — D1/D2 archive toggle clears and restores expires_at
    # ------------------------------------------------------------------ #
    # Capture baseline
    base_completed_at = adoc.get("completed_at")
    base_expires_at = adoc.get("expires_at")
    base_hard_delete_at = adoc.get("hard_delete_at")
    print(f"\n  baseline completed_at={base_completed_at} expires_at={base_expires_at}")
    check(bool(base_completed_at), "Ada session has completed_at (needed for D2)")

    # D1: archive=true -> expires_at null
    r = requests.patch(
        f"{BASE}/admin/sessions/{ADA_SID}",
        json={"archived": True},
        cookies=admin_cookies,
        timeout=30,
    )
    check(r.status_code == 200, f"PATCH archived=true -> 200 (got {r.status_code})")
    if r.status_code == 200:
        b1 = r.json()
        check(b1.get("archived") is True, f"archived now True (got {b1.get('archived')!r})")
        check(b1.get("expires_at") is None, f"expires_at cleared (got {b1.get('expires_at')!r})")
        check(b1.get("hard_delete_at") is None,
              f"hard_delete_at cleared (got {b1.get('hard_delete_at')!r})")

    # D2: archive=false -> expires_at == completed_at + 60d exactly
    r = requests.patch(
        f"{BASE}/admin/sessions/{ADA_SID}",
        json={"archived": False},
        cookies=admin_cookies,
        timeout=30,
    )
    check(r.status_code == 200, f"PATCH archived=false -> 200 (got {r.status_code})")
    if r.status_code == 200:
        b2 = r.json()
        check(b2.get("archived") is False, f"archived now False (got {b2.get('archived')!r})")
        exp = b2.get("expires_at")
        check(exp is not None, f"expires_at restored (got {exp!r})")
        if exp and base_completed_at:
            try:
                d_exp = datetime.fromisoformat(exp)
                d_cmp = datetime.fromisoformat(base_completed_at)
                delta_days = (d_exp - d_cmp).total_seconds() / 86400.0
                check(abs(delta_days - 60.0) < (1.0 / 86400.0),
                      f"expires_at == completed_at + 60 days exactly (delta={delta_days}d)")
            except Exception as e:
                _fail(f"could not parse expires_at/completed_at: {e}")
                failures.append("expires_at parse failure")

    # Cleanup: strip the test note so we don't persist it
    requests.patch(
        f"{BASE}/admin/sessions/{ADA_SID}",
        json={"notes": ""},
        cookies=admin_cookies,
        timeout=30,
    )
    print("\n  cleanup: cleared admin_notes back to empty string.")

    # ------------------------------------------------------------------ #
    print("\n=== SUMMARY ===")
    if failures:
        print(f"{len(failures)} FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All D3 + D1/D2 assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
