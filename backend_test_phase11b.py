"""Phase 11B backend test — admin engagement analytics endpoint.

Run sequentially against http://localhost:8001/api per spec.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASS  = "test1234"

CLAIRE_ID = "e5691ed5-e28e-4c28-b803-3d33a578fbe6"
ADA_ID    = "f9959971-5ee8-4f9f-83e6-f59ea747d9e0"
P2T_ID    = "1178ba0a-4c66-4dd0-a62a-2de014ee5acb"
UNKNOWN   = "no-such-session-99999"

PASS = []
FAIL = []

def ok(label, cond, info=""):
    if cond:
        PASS.append(label)
        print(f"  PASS  {label}")
    else:
        FAIL.append(f"{label} :: {info}")
        print(f"  FAIL  {label}  -- {info}")

def section(title):
    print(f"\n=== {title} ===")


# -------- 1. AUTH --------
section("1. Auth — admin login")
r = requests.post(f"{BASE}/admin/auth/login",
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
                  timeout=15)
ok("1.0 admin login 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
sc = r.headers.get("set-cookie") or ""
admin_token = None
for part in sc.split(","):
    for kv in part.split(";"):
        kv = kv.strip()
        if kv.lower().startswith("tra_admin_token="):
            admin_token = kv.split("=", 1)[1]
            break
    if admin_token:
        break
ok("1.1 tra_admin_token cookie issued", bool(admin_token), f"set-cookie={sc[:200]}")
COOKIE = f"tra_admin_token={admin_token}"
H_ADMIN = {"Cookie": COOKIE}


# -------- 2. HAPPY PATH — Claire --------
section("2. Happy path — Claire engagement")
r = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}/engagement",
                 headers=H_ADMIN, timeout=20)
ok("2.0 GET claire/engagement 200", r.status_code == 200, f"status={r.status_code}")
claire = r.json() if r.status_code == 200 else {}
ok("2.1 top-level keys exactly {psychometric, ai_discussion, scenario}",
   set(claire.keys()) == {"psychometric", "ai_discussion", "scenario"},
   f"keys={set(claire.keys())}")

# Psychometric
psych = claire.get("psychometric", {})
ok("2.2 psychometric is dict with items+summary",
   isinstance(psych, dict) and "items" in psych and "summary" in psych,
   f"psych keys={list(psych.keys())[:5]}")
items = psych.get("items") or []
summ = psych.get("summary") or {}

# Pull session doc to verify count match
r2 = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}", headers=H_ADMIN, timeout=20)
claire_doc = r2.json() if r2.status_code == 200 else {}
expected_answers = (claire_doc.get("psychometric") or {}).get("answers") or []
ok("2.3 psychometric.items length == count of psychometric.answers",
   len(items) == len(expected_answers),
   f"items={len(items)} answers={len(expected_answers)}")

required_item_keys = {"item_id","scale","subscale","is_reverse_keyed","text","value","response_time_ms","response_time_band"}
all_keys_ok = all(set(it.keys()) >= required_item_keys for it in items)
ok("2.4 each item has required keys", all_keys_ok,
   f"first_item_keys={sorted(items[0].keys()) if items else []}")

scales_ok = all(it["scale"] in ("LA", "TA") for it in items)
ok("2.5 each item.scale in {LA,TA}", scales_ok)
rev_bool_ok = all(isinstance(it["is_reverse_keyed"], bool) for it in items)
ok("2.6 is_reverse_keyed is bool", rev_bool_ok)
rt_int_ok = all(isinstance(it["response_time_ms"], int) for it in items)
ok("2.7 response_time_ms is int", rt_int_ok)
band_set = set(it["response_time_band"] for it in items)
ok("2.8 bands subset of {fast,normal,slow,deliberated}",
   band_set.issubset({"fast","normal","slow","deliberated"}),
   f"bands={band_set}")
ok("2.9 all four bands appear in Claire's items",
   band_set == {"fast","normal","slow","deliberated"},
   f"bands={band_set}")

required_summary_keys = {"median_ms","p25_ms","p75_ms","iqr_ms","deliberation_threshold_ms",
                         "fastest_3","slowest_3","deliberated_count"}
ok("2.10 summary has required keys",
   set(summ.keys()) >= required_summary_keys,
   f"summary_keys={sorted(summ.keys())}")
ok("2.11 fastest_3 length 3", len(summ.get("fastest_3", [])) == 3, f"fastest_3={summ.get('fastest_3')}")
ok("2.12 slowest_3 length 3", len(summ.get("slowest_3", [])) == 3, f"slowest_3={summ.get('slowest_3')}")
ok("2.13 deliberated_count is int", isinstance(summ.get("deliberated_count"), int))

# Verify ascending / descending
items_by_id = {it["item_id"]: it for it in items}
fast_rts = [items_by_id[i]["response_time_ms"] for i in summ.get("fastest_3", []) if i in items_by_id]
ok("2.14 fastest_3[0] has lowest RT amongst fastest_3 (ascending)",
   len(fast_rts) == 3 and fast_rts == sorted(fast_rts),
   f"fast_rts={fast_rts}")
slow_rts = [items_by_id[i]["response_time_ms"] for i in summ.get("slowest_3", []) if i in items_by_id]
ok("2.15 slowest_3[0] has highest RT amongst slowest_3 (descending)",
   len(slow_rts) == 3 and slow_rts == sorted(slow_rts, reverse=True),
   f"slow_rts={slow_rts}")
# Cross-check against full list
all_rts_sorted_asc = sorted(it["response_time_ms"] for it in items)
ok("2.16 fastest_3 RTs match the 3 lowest RTs overall",
   sorted(fast_rts) == sorted(all_rts_sorted_asc[:3]),
   f"fast_rts={sorted(fast_rts)} vs lowest3={all_rts_sorted_asc[:3]}")
ok("2.17 slowest_3 RTs match the 3 highest RTs overall",
   sorted(slow_rts) == sorted(all_rts_sorted_asc[-3:]),
   f"slow_rts={sorted(slow_rts)} vs highest3={all_rts_sorted_asc[-3:]}")

# AI Discussion
aid = claire.get("ai_discussion", {})
turns = aid.get("turns") or []
us = aid.get("user_summary") or {}
asum = aid.get("assistant_summary") or {}
ok("2.20 turns is list non-empty for Claire", isinstance(turns, list) and len(turns) > 0, f"len={len(turns)}")

# Verify dev-kind turns excluded — check vs raw conversation in admin doc
raw_conv = claire_doc.get("conversation") or []
non_dev_count = sum(1 for t in raw_conv if t.get("kind") != "dev")
ok("2.21 turns count == non-dev turns in conversation",
   len(turns) == non_dev_count,
   f"turns={len(turns)} non_dev={non_dev_count}")

user_required = {"turn_index","role","content_length_chars","content_length_words","time_to_respond_ms","timestamp"}
asst_required = {"turn_index","role","content_length_chars","content_length_words","model_latency_ms","provider","model","fallbacks_tried","timestamp"}
user_turns = [t for t in turns if t["role"] == "user"]
asst_turns = [t for t in turns if t["role"] == "assistant"]

uk_ok = all(set(t.keys()) >= user_required for t in user_turns)
ok("2.22 user turns have required keys", uk_ok, f"sample={list(user_turns[0].keys()) if user_turns else []}")
ak_ok = all(set(t.keys()) >= asst_required for t in asst_turns)
ok("2.23 assistant turns have required keys", ak_ok, f"sample={list(asst_turns[0].keys()) if asst_turns else []}")

# First user turn ttr — None allowed only if no preceding assistant turn
# Check ttr non-negative ints when present
ttr_nonneg = all(
    (t.get("time_to_respond_ms") is None) or
    (isinstance(t.get("time_to_respond_ms"), int) and t["time_to_respond_ms"] >= 0)
    for t in user_turns
)
ok("2.24 user.time_to_respond_ms None or non-negative int", ttr_nonneg)

# user_summary keys
us_required = {"total_turns","avg_words_per_turn","max_words","min_words","longest_turn_index","shortest_turn_index","avg_time_to_respond_ms","slowest_response_turn_index"}
ok("2.25 user_summary has required keys", set(us.keys()) >= us_required, f"keys={sorted(us.keys())}")
ok("2.26 user_summary.total_turns == user-role turn count",
   us.get("total_turns") == len(user_turns), f"sum={us.get('total_turns')} len={len(user_turns)}")
ok("2.27 user_summary.avg_words_per_turn is float", isinstance(us.get("avg_words_per_turn"), float))

as_required = {"total_turns","avg_latency_ms","max_latency_ms","fallbacks_total"}
ok("2.28 assistant_summary has required keys", set(asum.keys()) >= as_required, f"keys={sorted(asum.keys())}")
ok("2.29 assistant_summary.fallbacks_total >= 0",
   isinstance(asum.get("fallbacks_total"), int) and asum["fallbacks_total"] >= 0)
providers_seen = set(t.get("provider") for t in asst_turns)
ok("2.30 at least one assistant turn has known provider",
   bool(providers_seen & {"anthropic","openai","emergent"}),
   f"providers={providers_seen}")
ok("2.31 at least one assistant turn has non-null model_latency_ms",
   any(t.get("model_latency_ms") is not None for t in asst_turns))

# Scenario
sc_obj = claire.get("scenario", {})
phases = sc_obj.get("phases") or []
sc_summ = sc_obj.get("summary") or {}
ok("2.40 scenario.phases length 4", len(phases) == 4, f"len={len(phases)}")
ok("2.41 phase ordering exact",
   [p.get("phase") for p in phases] == ["read","part1","curveball","part2"],
   f"order={[p.get('phase') for p in phases]}")
phase_required = {"phase","target_minutes","target_ms","actual_ms","ratio","overran"}
ok("2.42 each phase has required keys",
   all(set(p.keys()) >= phase_required for p in phases))
expected_targets = {"read":4, "part1":5, "curveball":4, "part2":4}
tgt_ok = all(p["target_minutes"] == expected_targets[p["phase"]] for p in phases)
ok("2.43 target_minutes match scenario_service constants", tgt_ok,
   f"got={[(p['phase'], p['target_minutes']) for p in phases]}")
overran_bools = all(isinstance(p["overran"], bool) for p in phases)
ok("2.44 overran is bool on each phase", overran_bools)
ratios_floats = all(isinstance(p["ratio"], float) for p in phases)
ok("2.45 ratio is float on each phase", ratios_floats,
   f"types={[type(p['ratio']).__name__ for p in phases]}")
sum_target = sum(p["target_ms"] for p in phases)
ok("2.46 sum(target_ms) == 1020000 == summary.total_target_ms",
   sum_target == 1020000 == sc_summ.get("total_target_ms"),
   f"sum={sum_target} summary.total_target_ms={sc_summ.get('total_target_ms')}")

# Claire's part1 actual is extreme — verify ratio is float and it overran
p1 = next(p for p in phases if p["phase"] == "part1")
ok("2.47 Claire part1 actual_ms is int", isinstance(p1["actual_ms"], int))
ok("2.48 Claire part1 ratio is float", isinstance(p1["ratio"], float))


# -------- 3. INCOMPLETE — Phase Two Tester --------
section("3. Incomplete session (Phase Two Tester)")
r = requests.get(f"{BASE}/admin/sessions/{P2T_ID}/engagement",
                 headers=H_ADMIN, timeout=20)
ok("3.0 GET p2t/engagement 200", r.status_code == 200, f"status={r.status_code}")
p2t = r.json() if r.status_code == 200 else {}
ok("3.1 p2t.psychometric.items == []", p2t.get("psychometric", {}).get("items") == [],
   f"items={p2t.get('psychometric', {}).get('items')}")
ok("3.2 p2t.psychometric.summary is None",
   p2t.get("psychometric", {}).get("summary") is None,
   f"summary={p2t.get('psychometric', {}).get('summary')}")
ok("3.3 p2t.ai_discussion.user_summary is None",
   p2t.get("ai_discussion", {}).get("user_summary") is None)
ok("3.4 p2t.ai_discussion.assistant_summary is None",
   p2t.get("ai_discussion", {}).get("assistant_summary") is None)
ok("3.5 p2t.scenario.phases == []",
   p2t.get("scenario", {}).get("phases") == [],
   f"phases={p2t.get('scenario', {}).get('phases')}")
ok("3.6 p2t.scenario.summary is None",
   p2t.get("scenario", {}).get("summary") is None)


# -------- 4. ADA fixture --------
section("4. ADA fixture — graceful partial handling")
r = requests.get(f"{BASE}/admin/sessions/{ADA_ID}/engagement",
                 headers=H_ADMIN, timeout=20)
ok("4.0 GET ada/engagement 200", r.status_code == 200, f"status={r.status_code}")
ada = r.json() if r.status_code == 200 else {}
ok("4.1 ada has 3 top-level keys",
   set(ada.keys()) == {"psychometric","ai_discussion","scenario"})

# Get raw doc to check whether ada.psychometric.answers populated
r4 = requests.get(f"{BASE}/admin/sessions/{ADA_ID}", headers=H_ADMIN, timeout=20)
ada_doc = r4.json() if r4.status_code == 200 else {}
ada_answers = (ada_doc.get("psychometric") or {}).get("answers") or []
print(f"  INFO  ada.psychometric.answers count = {len(ada_answers)}")
if not ada_answers:
    ok("4.2 ada.psychometric == {items:[], summary:null} (older fixture)",
       ada.get("psychometric") == {"items": [], "summary": None},
       f"got={ada.get('psychometric')}")
else:
    ok("4.2 ada.psychometric.items length == answers count",
       len(ada.get("psychometric", {}).get("items") or []) == len(ada_answers))
# ai_discussion populated
ada_turns = ada.get("ai_discussion", {}).get("turns") or []
ok("4.3 ada.ai_discussion populated (older fixture has conversation)",
   len(ada_turns) > 0, f"turns={len(ada_turns)}")
# scenario phases length 4 if scenario data exists
ada_phases = ada.get("scenario", {}).get("phases") or []
ada_topm = (ada_doc.get("scenario") or {}).get("time_on_phase_ms")
if ada_topm:
    ok("4.4 ada.scenario.phases length 4 (has time_on_phase_ms)",
       len(ada_phases) == 4, f"len={len(ada_phases)}")
else:
    ok("4.4 ada.scenario.phases empty (no time_on_phase_ms)",
       ada_phases == [], f"phases={ada_phases}")


# -------- 5. ERROR PATHS --------
section("5. Error paths")
r = requests.get(f"{BASE}/admin/sessions/{UNKNOWN}/engagement",
                 headers=H_ADMIN, timeout=15)
ok("5.0 unknown session → 404", r.status_code == 404, f"status={r.status_code} body={r.text[:200]}")
try:
    body = r.json()
    ok("5.1 unknown session detail == 'Session not found.'",
       body.get("detail") == "Session not found.", f"detail={body.get('detail')}")
except Exception:
    ok("5.1 unknown session detail JSON", False, f"body={r.text[:200]}")

r = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}/engagement", timeout=15)
ok("5.2 no cookie → 401", r.status_code == 401, f"status={r.status_code} body={r.text[:200]}")
try:
    body = r.json()
    ok("5.3 no cookie detail == 'Not authenticated.'",
       body.get("detail") == "Not authenticated.", f"detail={body.get('detail')}")
except Exception:
    ok("5.3 no cookie detail JSON", False, f"body={r.text[:200]}")


# -------- 6. NO SIDE EFFECTS --------
section("6. Engagement endpoint must not stamp last_admin_viewed_at")
# Baseline: GET /sessions/{id} stamps last_admin_viewed_at
r1 = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}", headers=H_ADMIN, timeout=15)
t1 = r1.json().get("last_admin_viewed_at") if r1.status_code == 200 else None
ok("6.0 first /sessions/{id} returns last_admin_viewed_at", t1 is not None, f"t1={t1}")

time.sleep(1.2)

# Call engagement — should NOT stamp
re = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}/engagement", headers=H_ADMIN, timeout=15)
ok("6.1 engagement call ok", re.status_code == 200)

# Re-fetch /sessions/{id} — last_admin_viewed_at should be unchanged from t1
# BUT this call itself stamps it. So fetch first WITHOUT calling /sessions to look at side effect ...
# Spec says: confirm last_admin_viewed_at moved forward only between the two /sessions/{id} calls
# i.e. unchanged after the engagement call alone.
# Approach: read the doc via admin sessions list filter? Not easy.
# Better: just check engagement does no Mongo write side effect to last_admin_viewed_at:
# We compare t1 (first /sessions call) → engagement → t2 (second /sessions call).
# t2 will move forward because /sessions/{id} stamps. The way to confirm engagement didn't
# stamp is to check that the time delta between t1 and t2 is "fresh" (close to now), not
# stamped by the engagement call in the middle. Tricky. Simpler proof:
# do call A: /sessions  -> t1
# do call B: /engagement (sleep 0)
# do call C: /engagement again (sleep 0)
# do call D: /sessions  -> t2
# If engagement stamps, t2 would reflect call C's time, not D's. But hard to prove negative.

# Pragmatic approach: directly check via mongo if we can.
import importlib.util
mongo_check_ok = False
try:
    spec = importlib.util.spec_from_file_location("server_env", "/app/backend/.env")
    # Use motor / pymongo
    from pymongo import MongoClient
    with open("/app/backend/.env") as f:
        env = dict(line.strip().split("=", 1) for line in f if "=" in line and not line.strip().startswith("#"))
    mongo_url = env.get("MONGO_URL", "").strip().strip('"')
    db_name = env.get("DB_NAME", "test_database").strip().strip('"')
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    db = client[db_name]
    before_doc = db.sessions.find_one({"session_id": CLAIRE_ID}, {"last_admin_viewed_at": 1})
    before = before_doc.get("last_admin_viewed_at") if before_doc else None

    # Call engagement only (no /sessions in between)
    rx = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}/engagement", headers=H_ADMIN, timeout=15)
    after_doc = db.sessions.find_one({"session_id": CLAIRE_ID}, {"last_admin_viewed_at": 1})
    after = after_doc.get("last_admin_viewed_at") if after_doc else None

    ok("6.2 engagement call did NOT change last_admin_viewed_at in Mongo",
       before == after, f"before={before} after={after}")
    mongo_check_ok = True
except Exception as e:
    ok("6.2 mongo direct check setup", False, f"err={e}")

# Round-trip: do /sessions again after — should advance vs t1
r3 = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}", headers=H_ADMIN, timeout=15)
t3 = r3.json().get("last_admin_viewed_at") if r3.status_code == 200 else None
ok("6.3 /sessions/{id} call AFTER engagement still advances last_admin_viewed_at",
   t3 is not None and t3 > (t1 or ""), f"t1={t1} t3={t3}")


# -------- 7. ROUTE MATCHING --------
section("7. Route matching")
# 7a. compare endpoint must still work
r = requests.get(f"{BASE}/admin/sessions/compare?ids={CLAIRE_ID},{ADA_ID}",
                 headers=H_ADMIN, timeout=20)
ok("7.0 GET /admin/sessions/compare 200 (not shadowed)",
   r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")

# 7b. engagement then detail both work
re = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}/engagement", headers=H_ADMIN, timeout=15)
ok("7.1 engagement after compare works", re.status_code == 200)
rd = requests.get(f"{BASE}/admin/sessions/{CLAIRE_ID}", headers=H_ADMIN, timeout=15)
ok("7.2 detail endpoint after engagement works", rd.status_code == 200)
detail_doc = rd.json() if rd.status_code == 200 else {}
ok("7.3 detail returns full doc with admin_notes/last_admin_viewed_at",
   "last_admin_viewed_at" in detail_doc,
   f"keys_sample={list(detail_doc.keys())[:8]}")

# 7c. OpenAPI listing
r = requests.get(f"{BASE}/openapi.json", timeout=15)
ok("7.4 GET /openapi.json 200", r.status_code == 200)
spec = r.json() if r.status_code == 200 else {}
paths = spec.get("paths", {})
eng_path = "/api/admin/sessions/{session_id}/engagement"
ok("7.5 engagement path present in openapi.json", eng_path in paths,
   f"sample_paths={list(paths.keys())[:5]}")
if eng_path in paths:
    op_summary = paths[eng_path].get("get", {}).get("summary", "")
    ok("7.6 engagement openapi summary mentions 'Engagement analytics for a session'",
       "Engagement analytics for a session" in op_summary,
       f"summary={op_summary!r}")


# -------- 8. REGRESSION pytest --------
section("8. Regression pytest")
import subprocess
res = subprocess.run(
    ["python", "-m", "pytest", "tests/", "-q", "--tb=short"],
    cwd="/app/backend", capture_output=True, text=True, timeout=240
)
out = (res.stdout or "") + (res.stderr or "")
print(out[-3000:])
# Look for "134 passed" line
import re as _re
m = _re.search(r"(\d+)\s+passed", out)
passed_count = int(m.group(1)) if m else -1
ok("8.0 pytest exit code 0", res.returncode == 0, f"rc={res.returncode}")
ok("8.1 pytest reports 134 passed",
   passed_count == 134,
   f"passed={passed_count}")


# -------- SUMMARY --------
print("\n\n" + "=" * 60)
print(f"PASS: {len(PASS)}")
print(f"FAIL: {len(FAIL)}")
if FAIL:
    print("\nFAILURES:")
    for f in FAIL:
        print(f"  - {f}")
sys.exit(0 if not FAIL else 1)
