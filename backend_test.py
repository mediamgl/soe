"""
Phase 8 backend test — Admin dashboard + lifecycle + exports.
Runs end-to-end against the public REACT_APP_BACKEND_URL/api surface.
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

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
load_dotenv(Path("/app/frontend/.env"))
load_dotenv(Path("/app/backend/.env"))

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/") + "/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "soe_tra")

ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PW = "test1234"

ADA_SESSION = "2253141a-830f-4810-a683-890f098b5664"

RESULTS: list[tuple[str, bool, str]] = []


def record(letter: str, ok: bool, msg: str = "") -> None:
    mark = "OK" if ok else "FAIL"
    RESULTS.append((letter, ok, msg))
    print(f"  [{mark}] {letter}: {msg}")


def admin_login() -> str:
    r = requests.post(f"{BASE}/admin/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=15)
    r.raise_for_status()
    token = None
    for c in r.cookies:
        if c.name == "tra_admin_token":
            token = c.value
    if not token:
        for sc in r.headers.get("set-cookie", "").split(","):
            m = re.search(r"tra_admin_token=([^;]+)", sc)
            if m:
                token = m.group(1)
                break
    assert token, "No admin token received"
    return token


def H(token: str, extra: dict | None = None) -> dict:
    h = {"Cookie": f"tra_admin_token={token}"}
    if extra:
        h.update(extra)
    return h


def seed_fresh_session() -> tuple[str, str]:
    r = subprocess.run(
        [sys.executable, "/app/backend/seed_phase7_test_session.py"],
        check=True, capture_output=True, text=True,
    )
    lines = [ln.strip() for ln in r.stdout.strip().splitlines() if ln.strip()]
    sid, code = lines[-2], lines[-1]
    assert re.match(r"^[0-9a-f-]{36}$", sid), f"bad sid: {sid!r} stdout={r.stdout}"
    return sid, code


def db():
    cli = AsyncIOMotorClient(MONGO_URL)
    return cli[DB_NAME]


async def mongo_set(session_id: str, update: dict):
    d = db()
    await d.sessions.update_one({"session_id": session_id}, {"$set": update})


async def mongo_get(session_id: str):
    d = db()
    return await d.sessions.find_one({"session_id": session_id})


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def block_A_auth_gating():
    print("\n== A: Auth gating (401 on all new endpoints) ==")
    endpoints = [
        ("GET", "/admin/sessions"),
        ("GET", f"/admin/sessions/{ADA_SESSION}"),
        ("PATCH", f"/admin/sessions/{ADA_SESSION}"),
        ("DELETE", f"/admin/sessions/{ADA_SESSION}"),
        ("POST", f"/admin/sessions/{ADA_SESSION}/restore"),
        ("GET", f"/admin/sessions/{ADA_SESSION}/conversation/download"),
        ("GET", f"/admin/sessions/{ADA_SESSION}/deliverable/download"),
        ("GET", "/admin/dashboard/summary"),
        ("POST", "/admin/lifecycle/run"),
    ]
    fails = []
    for method, path in endpoints:
        kw = {"timeout": 10}
        if method in ("PATCH", "POST"):
            kw["json"] = {}
        r = requests.request(method, f"{BASE}{path}", **kw)
        if r.status_code != 401:
            fails.append(f"{method} {path} -> {r.status_code}")
    record("A", not fails, f"9 endpoints 401-gated" + (f" FAILS: {fails}" if fails else ""))


def block_B_list_search_filter(token):
    print("\n== B: /admin/sessions list + search + filter + pagination + sort ==")
    r = requests.get(f"{BASE}/admin/sessions", headers=H(token), timeout=15)
    j = r.json()
    ok = r.status_code == 200 and all(k in j for k in ("items", "total", "page", "page_size", "filters_applied"))
    record("B1", ok, f"baseline list shape; total={j.get('total')}, items={len(j.get('items', []))}")

    r = requests.get(f"{BASE}/admin/sessions", headers=H(token), params={"q": "Ada"}, timeout=15)
    j = r.json()
    found = any(ADA_SESSION == it["session_id"] for it in j["items"])
    record("B2", found and j["filters_applied"]["q"] == "Ada",
           f"q=Ada -> {len(j['items'])} items, Ada found={found}")

    r1 = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                      params={"page_size": 1, "page": 1, "sort": "-created_at"}, timeout=15).json()
    r2 = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                      params={"page_size": 1, "page": 2, "sort": "-created_at"}, timeout=15).json()
    p_adv = r1["page"] == 1 and r2["page"] == 2 and r1["page_size"] == 1 and r2["page_size"] == 1
    diff_items = (len(r1["items"]) == 1 and len(r2["items"]) == 1 and
                  r1["items"][0]["session_id"] != r2["items"][0]["session_id"]) if r1["total"] >= 2 else True
    record("B3", p_adv and diff_items, f"pagination page=1->2 advances (total={r1['total']})")

    r = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                     params={"status": "completed"}, timeout=15).json()
    all_done = all(it["status"] == "completed" for it in r["items"])
    record("B4", all_done, f"status=completed -> {len(r['items'])} items, all completed={all_done}")

    r_only = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                          params={"archived": "only"}, timeout=15).json()
    r_exc = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                         params={"archived": "exclude"}, timeout=15).json()
    all_arc = all(it["archived"] for it in r_only["items"]) if r_only["items"] else True
    all_unarc = all(not it["archived"] for it in r_exc["items"]) if r_exc["items"] else True
    record("B5", all_arc and all_unarc,
           f"archived=only({len(r_only['items'])} items, all archived={all_arc}); exclude({len(r_exc['items'])} items, all unarchived={all_unarc})")

    ra = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                      params={"sort": "created_at", "page_size": 5}, timeout=15).json()
    rd = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                      params={"sort": "-created_at", "page_size": 5}, timeout=15).json()
    asc_ok = all(ra["items"][i]["created_at"] <= ra["items"][i+1]["created_at"]
                 for i in range(len(ra["items"])-1)) if len(ra["items"]) > 1 else True
    desc_ok = all(rd["items"][i]["created_at"] >= rd["items"][i+1]["created_at"]
                  for i in range(len(rd["items"])-1)) if len(rd["items"]) > 1 else True
    record("B6", asc_ok and desc_ok, f"sort asc={asc_ok}, desc={desc_ok}")

    r = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                     params={"q": "ada", "status": "completed", "archived": "exclude",
                             "sort": "-completed_at", "page": 1, "page_size": 10},
                     timeout=15).json()
    fa = r["filters_applied"]
    ok = (fa["q"] == "ada" and fa["status"] == "completed" and
          fa["archived"] == "exclude" and fa["sort"] == "-completed_at")
    record("B7", ok, f"filters_applied reflects all params: {fa}")

    r = requests.get(f"{BASE}/admin/sessions", headers=H(token),
                     params={"include_deleted": "false"}, timeout=15).json()
    no_deleted = all(it.get("deleted_at") is None for it in r["items"])
    record("B8", no_deleted, f"include_deleted=false -> only non-deleted ({len(r['items'])} items)")


def block_C_get_session_stamp(token):
    print("\n== C: GET /admin/sessions/{id} stamps last_admin_viewed_at ==")
    r1 = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token), timeout=15).json()
    t1 = r1.get("last_admin_viewed_at")
    time.sleep(1.2)
    r2 = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token), timeout=15).json()
    t2 = r2.get("last_admin_viewed_at")
    record("C1", bool(t1) and bool(t2) and t2 > t1,
           f"last_admin_viewed_at stamps/bumps: t1={t1} < t2={t2}")
    r = requests.get(f"{BASE}/admin/sessions/{uuid.uuid4()}", headers=H(token), timeout=10)
    record("C2", r.status_code == 404, f"unknown session -> {r.status_code}")


def block_D_patch_archive_notes(token):
    print("\n== D: PATCH archive + notes semantics ==")
    before = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token)).json()
    assert before.get("completed_at"), "Ada session must have completed_at"

    r = requests.patch(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token),
                       json={"archived": True}, timeout=15).json()
    ok = r.get("archived") is True and r.get("expires_at") is None and r.get("hard_delete_at") is None
    record("D1", ok, f"archived=true -> expires_at={r.get('expires_at')}, hard_delete_at={r.get('hard_delete_at')}, archived={r.get('archived')}")

    r = requests.patch(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token),
                       json={"archived": False}, timeout=15).json()
    cat = datetime.fromisoformat(r["completed_at"])
    exp = datetime.fromisoformat(r["expires_at"]) if r.get("expires_at") else None
    delta_days = (exp - cat).days if exp else None
    record("D2", r["archived"] is False and delta_days == 60,
           f"archived=false -> expires_at = completed_at+{delta_days}d")

    r = requests.patch(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token),
                       json={"notes": "Phase 8 testing admin note"}, timeout=15).json()
    pub = requests.get(f"{BASE}/sessions/{ADA_SESSION}", timeout=10).json()
    ok = (r.get("admin_notes") == "Phase 8 testing admin note"
          and "admin_notes" not in pub and "notes" not in pub)
    record("D3", ok, f"notes persists as admin_notes; absent from public GET={'admin_notes' not in pub}")

    r = requests.patch(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token),
                       json={"notes": "x" * 2001}, timeout=10)
    record("D4", r.status_code == 422, f"notes len=2001 -> {r.status_code}")


def block_E_soft_delete(token):
    print("\n== E: Admin DELETE soft-delete semantics ==")
    sid, _ = seed_fresh_session()
    asyncio.run(mongo_set(sid, {
        "status": "completed",
        "completed_at": iso(datetime.now(timezone.utc)),
        "expires_at": iso(datetime.now(timezone.utc) + timedelta(days=60)),
    }))
    pre = asyncio.run(mongo_get(sid))
    orig_scores = pre.get("scores")
    orig_deliv = pre.get("deliverable")
    orig_conv = pre.get("conversation")
    orig_scen = pre.get("scenario")

    r = requests.delete(f"{BASE}/admin/sessions/{sid}", headers=H(token), timeout=15)
    record("E1", r.status_code == 200 and r.json().get("ok") is True, f"DELETE -> {r.status_code} {r.json()}")

    got = requests.get(f"{BASE}/admin/sessions/{sid}", headers=H(token)).json()
    p = got.get("participant") or {}
    pii_ok = (p.get("name") == "(redacted)" and p.get("email") is None
              and p.get("organisation") is None and p.get("role") is None)
    record("E2", pii_ok, f"PII scrubbed: name={p.get('name')!r}, email={p.get('email')}")

    flags_ok = got.get("redacted") is True and bool(got.get("deleted_at")) and bool(got.get("hard_delete_at"))
    record("E3", flags_ok, f"redacted=True, deleted_at/hard_delete_at set")

    da = datetime.fromisoformat(got["deleted_at"])
    ha = datetime.fromisoformat(got["hard_delete_at"])
    diff_days = (ha - da).days
    record("E4", 29 <= diff_days <= 30, f"hard_delete_at - deleted_at = {diff_days}d (~30)")

    post = asyncio.run(mongo_get(sid))
    preserved = (post.get("scores") == orig_scores and
                 post.get("deliverable") == orig_deliv and
                 post.get("conversation") == orig_conv)
    scen = post.get("scenario") or {}
    scen_ok = (scen.get("part1_response") == (orig_scen or {}).get("part1_response") and
               scen.get("part2_response") == (orig_scen or {}).get("part2_response"))
    record("E5", preserved and scen_ok,
           f"scores/deliverable/conversation preserved; part1+part2 responses intact")
    return sid


def block_F_restore_in_grace(token, sid):
    print("\n== F: Restore within grace window ==")
    r = requests.post(f"{BASE}/admin/sessions/{sid}/restore", headers=H(token), timeout=15)
    j = r.json()
    ok = (r.status_code == 200 and j.get("ok") is True
          and j.get("restored") is True and j.get("pii_recoverable") is False)
    record("F1", ok, f"restore -> {r.status_code} {j}")

    got = requests.get(f"{BASE}/admin/sessions/{sid}", headers=H(token)).json()
    flags = (got.get("deleted_at") is None and got.get("hard_delete_at") is None
             and (got.get("participant") or {}).get("name") == "(redacted)")
    record("F2", flags, f"deleted_at/hard_delete_at cleared; name still '(redacted)'")


def block_G_restore_past_grace(token):
    print("\n== G: Restore past grace window -> 409 ==")
    sid, _ = seed_fresh_session()
    r = requests.delete(f"{BASE}/admin/sessions/{sid}", headers=H(token), timeout=15)
    assert r.status_code == 200
    asyncio.run(mongo_set(sid, {"hard_delete_at": iso(datetime.now(timezone.utc) - timedelta(days=1))}))
    r = requests.post(f"{BASE}/admin/sessions/{sid}/restore", headers=H(token), timeout=10)
    record("G1", r.status_code == 409, f"restore past hard_delete_at -> {r.status_code} (detail={r.json().get('detail')!r})")


def block_H_lifecycle_cron(token):
    print("\n== H: Lifecycle cron full cycle ==")
    sid, _ = seed_fresh_session()
    asyncio.run(mongo_set(sid, {
        "status": "completed",
        "completed_at": iso(datetime.now(timezone.utc) - timedelta(days=61)),
        "expires_at": iso(datetime.now(timezone.utc) - timedelta(minutes=1)),
        "archived": False,
    }))
    r = requests.post(f"{BASE}/admin/lifecycle/run", headers=H(token), timeout=30)
    j = r.json()
    record("H1", r.status_code == 200 and j.get("soft_deleted", 0) >= 1, f"lifecycle soft-pass: {j}")

    got = requests.get(f"{BASE}/admin/sessions/{sid}", headers=H(token)).json()
    record("H2", got.get("redacted") is True and bool(got.get("deleted_at")),
           f"seeded session now redacted={got.get('redacted')}")

    asyncio.run(mongo_set(sid, {"hard_delete_at": iso(datetime.now(timezone.utc) - timedelta(minutes=1))}))
    r = requests.post(f"{BASE}/admin/lifecycle/run", headers=H(token), timeout=30)
    j = r.json()
    record("H3", r.status_code == 200 and j.get("hard_deleted", 0) >= 1, f"lifecycle hard-pass: {j}")

    r = requests.get(f"{BASE}/admin/sessions/{sid}", headers=H(token), timeout=10)
    record("H4", r.status_code == 404, f"post-hard-delete GET -> {r.status_code}")

    r1 = requests.post(f"{BASE}/admin/lifecycle/run", headers=H(token), timeout=15).json()
    r2 = requests.post(f"{BASE}/admin/lifecycle/run", headers=H(token), timeout=15).json()
    record("H5", r1.get("skipped") is False and r2.get("skipped") is False,
           f"back-to-back manual runs force=True (skipped={r1.get('skipped')}, {r2.get('skipped')}) — documented")


def block_I_conversation_downloads(token):
    print("\n== I: Conversation downloads ==")
    r = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}/conversation/download",
                     headers=H(token), params={"format": "markdown"}, timeout=15)
    ct = r.headers.get("content-type", "")
    cd = r.headers.get("content-disposition", "")
    body = r.text
    ok_md = (r.status_code == 200 and "text/markdown" in ct and
             'filename="TRA-conversation-' in cd and cd.endswith('.md"') and
             "Interviewer" in body and "Participant" in body and ADA_SESSION in body)
    record("I1", ok_md, f"MD ct={ct!r}, cd={cd!r}, roles+sid present")

    r = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}/conversation/download",
                     headers=H(token), params={"format": "json"}, timeout=15)
    ct = r.headers.get("content-type", "")
    cd = r.headers.get("content-disposition", "")
    j = r.json()
    ok_json = (r.status_code == 200 and "application/json" in ct and
               'filename="TRA-conversation-' in cd and cd.endswith('.json"') and
               isinstance(j.get("conversation"), list) and j.get("session_id") == ADA_SESSION)
    record("I2", ok_json, f"JSON ct={ct!r}, cd={cd!r}, conv_len={len(j.get('conversation', []))}")

    sid, _ = seed_fresh_session()
    requests.delete(f"{BASE}/admin/sessions/{sid}", headers=H(token), timeout=15)
    r_md = requests.get(f"{BASE}/admin/sessions/{sid}/conversation/download",
                        headers=H(token), params={"format": "markdown"}, timeout=15)
    body = r_md.text
    cd = r_md.headers.get("content-disposition", "")
    short = sid[:8]
    fn_ok = f"session-{short}" in cd
    pii_ok = ("ada.test@example.co.uk" not in body and "Analytical Engine Co" not in body)
    record("I3", r_md.status_code == 200 and fn_ok and pii_ok,
           f"redacted MD: fn session-{short}={fn_ok}, no PII={pii_ok}")

    r_json = requests.get(f"{BASE}/admin/sessions/{sid}/conversation/download",
                          headers=H(token), params={"format": "json"}, timeout=15)
    pii_ok_j = ("ada.test@example.co.uk" not in r_json.text and
                "Analytical Engine Co" not in r_json.text)
    label_ok = "(redacted)" in (r_json.json().get("participant_label") or "")
    record("I4", r_json.status_code == 200 and pii_ok_j and label_ok,
           f"redacted JSON: no PII={pii_ok_j}, label has '(redacted)'={label_ok}")


def block_J_deliverable_downloads(token):
    print("\n== J: Deliverable admin downloads ==")
    r = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}/deliverable/download",
                     headers=H(token), params={"format": "pdf"}, timeout=30)
    ok = (r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf")
          and r.content.startswith(b"%PDF"))
    record("J1", ok, f"PDF: {r.status_code}, ct={r.headers.get('content-type')}, magic={r.content[:5]!r}")

    r = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}/deliverable/download",
                     headers=H(token), params={"format": "markdown"}, timeout=30)
    ok = (r.status_code == 200 and "text/markdown" in r.headers.get("content-type", "")
          and r.text.startswith("# Transformation Readiness Assessment"))
    record("J2", ok, f"MD: {r.status_code}, starts with H1")

    requests.patch(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token),
                   json={"archived": True}, timeout=10)
    r = requests.get(f"{BASE}/admin/sessions/{ADA_SESSION}/deliverable/download",
                     headers=H(token), params={"format": "pdf"}, timeout=30)
    ok_arc = r.status_code == 200 and r.content.startswith(b"%PDF")
    requests.patch(f"{BASE}/admin/sessions/{ADA_SESSION}", headers=H(token),
                   json={"archived": False}, timeout=10)
    record("J3", ok_arc, f"archived session PDF download works: {ok_arc}")


def block_K_dashboard_summary(token):
    print("\n== K: Dashboard summary shape + caching ==")
    r1 = requests.get(f"{BASE}/admin/dashboard/summary", headers=H(token), timeout=20)
    j1 = r1.json()
    needed = ("totals", "completed_this_week", "completed_last_week",
              "avg_completion_duration_seconds", "score_distribution",
              "dimension_averages", "activity_14d", "generated_at")
    missing = [k for k in needed if k not in j1]
    record("K1", r1.status_code == 200 and not missing, f"top-level keys present (missing={missing})")

    tkeys = ("total_sessions", "in_progress", "completed", "failed",
             "archived", "soft_deleted", "expiring_soon")
    tm = [k for k in tkeys if k not in j1.get("totals", {})]
    record("K2", not tm, f"totals={j1.get('totals')}")

    record("K3", len(j1.get("dimension_averages", [])) == 6,
           f"dimension_averages len={len(j1.get('dimension_averages', []))}")
    record("K4", len(j1.get("activity_14d", [])) == 14,
           f"activity_14d len={len(j1.get('activity_14d', []))}")

    sd = j1.get("score_distribution", {})
    sd_ok = all(k in sd for k in ("navy", "gold", "terracotta"))
    record("K5", sd_ok, f"score_distribution keys: {sd}")

    time.sleep(1)
    r2 = requests.get(f"{BASE}/admin/dashboard/summary", headers=H(token), timeout=20).json()
    record("K6", j1["generated_at"] == r2["generated_at"],
           f"cache: generated_at same across back-to-back calls within 60s")


def block_L_regression(token):
    print("\n== L: Regression spot-checks ==")
    fwd = {"X-Forwarded-For": f"10.{os.getpid() % 255}.{int(time.time()) % 255}.{(int(time.time())//256) % 255}"}
    r = requests.post(f"{BASE}/sessions", headers=fwd, json={
        "name": "Reg Tester", "email": f"reg.{uuid.uuid4().hex[:8]}@example.com",
        "organisation": "Test Co", "role": "QA", "consent": True,
    }, timeout=10)
    ok = r.status_code == 201 and "session_id" in r.json() and "resume_code" in r.json()
    record("L1", ok, f"POST /sessions -> {r.status_code}")
    sid = r.json().get("session_id") if ok else None

    if sid:
        requests.patch(f"{BASE}/sessions/{sid}/stage", json={"stage": "context"}, timeout=10)
        requests.patch(f"{BASE}/sessions/{sid}/stage", json={"stage": "psychometric"}, timeout=10)
        r = requests.get(f"{BASE}/assessment/psychometric/next",
                         params={"session_id": sid}, timeout=10)
        record("L2", r.status_code == 200 and "item" in r.json(), f"/psychometric/next -> {r.status_code}")
        item = r.json().get("item") or {}
        if item.get("id"):
            r = requests.post(f"{BASE}/assessment/psychometric/answer", json={
                "session_id": sid, "item_id": item["id"], "value": 4, "response_time_ms": 2000,
            }, timeout=10)
            record("L3", r.status_code == 200, f"/psychometric/answer -> {r.status_code}")

        r = requests.post(f"{BASE}/assessment/ai-discussion/start",
                          json={"session_id": sid}, timeout=15)
        record("L4", r.status_code == 409, f"/ai-discussion/start (wrong stage) -> {r.status_code}")

    r = requests.get(f"{BASE}/assessment/scenario/state",
                     params={"session_id": ADA_SESSION}, timeout=10)
    record("L5", r.status_code == 200, f"/scenario/state(Ada) -> {r.status_code}")

    r = requests.get(f"{BASE}/assessment/processing/state",
                     params={"session_id": ADA_SESSION}, timeout=10)
    record("L6", r.status_code == 200 and r.json().get("status") == "completed",
           f"/processing/state(Ada) -> {r.status_code}, status={r.json().get('status')}")

    r = requests.get(f"{BASE}/assessment/results",
                     params={"session_id": ADA_SESSION}, timeout=10)
    record("L7", r.status_code == 200 and r.json().get("status") == "ok",
           f"/assessment/results(Ada) -> {r.status_code}")


def block_M_openapi():
    print("\n== M: OpenAPI path count ==")
    r = requests.get(f"{BASE}/openapi.json", timeout=10)
    paths = list(r.json().get("paths", {}).keys())
    api_paths = [p for p in paths if p.startswith("/api/")]
    record("M", len(api_paths) == 35, f"/api/* path count = {len(api_paths)} (expected 35)")


def block_N_log_hygiene():
    print("\n== N: Log hygiene ==")
    proc = subprocess.run(
        ["grep", "-E", "ada.test@example.co.uk|Analytical Engine Co|Chief Mathematician",
         "/var/log/supervisor/backend.out.log", "/var/log/supervisor/backend.err.log"],
        capture_output=True, text=True,
    )
    hits = []
    for line in (proc.stdout or "").splitlines():
        if " INFO " in line or " INFO:" in line or ":INFO:" in line:
            hits.append(line)
    record("N1", not hits, f"no INFO-level PII (ada.test email / Analytical Engine Co / Chief Mathematician) — found {len(hits)}")
    for h in hits[:3]:
        print(f"      sample: {h[:200]}")


def main():
    print(f"Base URL: {BASE}")
    token = admin_login()
    print(f"admin token: {token[:20]}...")

    block_A_auth_gating()
    block_B_list_search_filter(token)
    block_C_get_session_stamp(token)
    block_D_patch_archive_notes(token)
    sid = block_E_soft_delete(token)
    block_F_restore_in_grace(token, sid)
    block_G_restore_past_grace(token)
    block_H_lifecycle_cron(token)
    block_I_conversation_downloads(token)
    block_J_deliverable_downloads(token)
    block_K_dashboard_summary(token)
    block_L_regression(token)
    block_M_openapi()
    block_N_log_hygiene()

    print("\n================ SUMMARY ================")
    fails = [x for x in RESULTS if not x[1]]
    for lt, ok, msg in RESULTS:
        print(f" {'OK  ' if ok else 'FAIL'} {lt}: {msg}")
    print(f"\nTotal: {len(RESULTS)} | Passed: {len(RESULTS)-len(fails)} | Failed: {len(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
