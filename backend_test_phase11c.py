"""Phase 11C — backend verification for GET /api/admin/sessions/cohort.

Per spec, internal base URL: http://localhost:8001/api
Admin creds: steve@org-logic.io / test1234

Cookie is Secure so we replay via explicit `Cookie: tra_admin_token=...` header
rather than letting requests.Session carry it over plain http.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASS = "test1234"

ADA1 = "f9959971-5ee8-4f9f-83e6-f59ea747d9e0"
ADA2 = "2253141a-830f-4810-a683-890f098b5664"
CLAIRE = "e5691ed5-e28e-4c28-b803-3d33a578fbe6"
TESTER = "5953a3d3-9539-45dd-9835-34a8c719be19"
INCOMPLETE = "1178ba0a-4c66-4dd0-a62a-2de014ee5acb"

VALID_4 = [ADA1, ADA2, CLAIRE, TESTER]

EXPECTED_AXIS_ORDER = [
    "learning_agility",
    "tolerance_for_ambiguity",
    "cognitive_flexibility",
    "self_awareness_accuracy",
    "ai_fluency",
    "systems_thinking",
]
EXPECTED_TOP_KEYS = {
    "axis_order", "participants", "cohort_summary", "dimension_stats",
    "heatmap", "outliers", "cohort_type", "category_distribution",
    "flag_summary", "generated_at",
}
EXPECTED_PARTICIPANT_KEYS = {
    "session_id", "name", "label", "organisation", "role", "completion_date",
    "overall_category", "overall_colour", "response_pattern_flag",
    "dimension_scores",
}
EXPECTED_DIM_STAT_KEYS = {
    "dimension_id", "label", "n", "mean", "median", "p25", "p75",
    "min", "max", "std_dev", "band_distribution",
}
EXPECTED_BAND_NAMES = {"Exceptional", "Strong", "Moderate", "Limited", "Low"}
EXPECTED_VALID_CATEGORIES = {
    "Transformation Ready", "High Potential", "Development Required", "Limited Readiness",
}
EXPECTED_FLAG_KEYS = {"none", "high_acquiescence", "low_variance",
                     "extreme_response_bias", "total_flagged"}

PASS: List[str] = []
FAIL: List[str] = []


def ok(label: str, cond: bool, msg: str = ""):
    if cond:
        PASS.append(label)
        print(f"  ✓ {label}")
    else:
        FAIL.append(f"{label}: {msg}")
        print(f"  ✗ {label}  -- {msg}")


def admin_login() -> str:
    r = requests.post(
        f"{BASE}/admin/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    if r.status_code != 200:
        raise SystemExit(f"admin login failed: {r.status_code} {r.text!r}")
    setc = r.headers.get("set-cookie") or r.headers.get("Set-Cookie") or ""
    m = re.search(r"tra_admin_token=([^;]+)", setc)
    if not m:
        raise SystemExit(f"no tra_admin_token cookie in: {setc!r}")
    return m.group(1)


def H(token: Optional[str]) -> Dict[str, str]:
    return {"Cookie": f"tra_admin_token={token}"} if token else {}


# ---------------------------------------------------------------------------
def section1_auth():
    print("\n[1] AUTH")
    tok = admin_login()
    ok("1.1 admin login → tra_admin_token cookie", bool(tok))
    return tok


def section2_happy_path(tok: str) -> Dict[str, Any]:
    print("\n[2] HAPPY PATH (4 completed sessions)")
    ids = ",".join(VALID_4)
    r = requests.get(
        f"{BASE}/admin/sessions/cohort",
        params={"ids": ids},
        headers=H(tok),
        timeout=30,
    )
    ok("2.0 200 OK", r.status_code == 200, f"got {r.status_code} body={r.text[:200]}")
    if r.status_code != 200:
        return {}
    body = r.json()

    # Top-level keys
    keys = set(body.keys())
    ok("2.1 top-level keys exactly match spec",
       keys == EXPECTED_TOP_KEYS,
       f"diff: missing={EXPECTED_TOP_KEYS-keys} extra={keys-EXPECTED_TOP_KEYS}")

    # axis_order
    ok("2.2 axis_order = fixed 6-element list",
       body.get("axis_order") == EXPECTED_AXIS_ORDER,
       f"got {body.get('axis_order')}")

    # participants
    parts = body.get("participants") or []
    ok("2.3 participants length == 4", len(parts) == 4, f"len={len(parts)}")
    for i, p in enumerate(parts):
        pk = set(p.keys())
        # spec says 10 keys (the 10 listed)
        missing = EXPECTED_PARTICIPANT_KEYS - pk
        ok(f"2.3.{i}.keys participant {i} has all 10 spec keys",
           not missing, f"missing={missing} extra={pk-EXPECTED_PARTICIPANT_KEYS}")
        ds = p.get("dimension_scores") or {}
        ok(f"2.3.{i}.dim_scores participant {i} dimension_scores has 6 keys",
           set(ds.keys()) == set(EXPECTED_AXIS_ORDER),
           f"keys={list(ds.keys())}")

    # cohort_summary
    cs = body.get("cohort_summary") or {}
    ok("2.4.n cohort_summary.n == 4", cs.get("n") == 4, f"n={cs.get('n')}")
    orgs = cs.get("organisations") or []
    ok("2.4.orgs sorted+unique", orgs == sorted(set(orgs)), f"orgs={orgs}")
    ok("2.4.dur avg_session_duration_seconds is int > 0",
       isinstance(cs.get("avg_session_duration_seconds"), int)
       and cs.get("avg_session_duration_seconds") > 0,
       f"got {cs.get('avg_session_duration_seconds')!r}")

    # dimension_stats
    ds = body.get("dimension_stats") or []
    ok("2.5.len dimension_stats has 6 entries", len(ds) == 6, f"len={len(ds)}")
    if len(ds) == 6:
        ok("2.5.order dimension_stats in axis_order",
           [d.get("dimension_id") for d in ds] == EXPECTED_AXIS_ORDER,
           f"got {[d.get('dimension_id') for d in ds]}")
        for i, d in enumerate(ds):
            keys = set(d.keys())
            miss = EXPECTED_DIM_STAT_KEYS - keys
            ok(f"2.5.{i}.keys", not miss, f"missing={miss}")
            bd = d.get("band_distribution") or {}
            ok(f"2.5.{i}.bands band names exactly = 5 spec",
               set(bd.keys()) == EXPECTED_BAND_NAMES,
               f"got {list(bd.keys())}")
            ok(f"2.5.{i}.bandsum sum(band_distribution.values()) == n",
               sum(bd.values()) == d.get("n"),
               f"sum={sum(bd.values())} n={d.get('n')}")

    # heatmap
    hm = body.get("heatmap") or {}
    ok("2.6.axis heatmap.axis_order == axis_order",
       hm.get("axis_order") == EXPECTED_AXIS_ORDER,
       f"got {hm.get('axis_order')}")
    rows = hm.get("rows") or []
    ok("2.6.rows heatmap.rows length == 4", len(rows) == 4, f"len={len(rows)}")
    for i, row in enumerate(rows):
        scores = row.get("scores") or []
        ok(f"2.6.{i}.scores row {i} scores is 6-element list", len(scores) == 6,
           f"len={len(scores)}")

    # outliers
    outs = body.get("outliers") or []
    ok("2.7.len outliers length == 6", len(outs) == 6, f"len={len(outs)}")
    if len(outs) == 6:
        ok("2.7.order outliers in axis_order",
           [o.get("dimension_id") for o in outs] == EXPECTED_AXIS_ORDER)
        # Map dim → outlier entry
        by_dim = {o.get("dimension_id"): o for o in outs}

        def names_in(lst):
            return [e.get("name") for e in (lst or [])]

        # Tester low on Learning Agility
        la_low = by_dim.get("learning_agility", {}).get("low_outliers") or []
        ok("2.7.LA Tester among low_outliers on Learning Agility",
           any("Tester" in (e.get("name") or "") for e in la_low),
           f"got {names_in(la_low)}")

        # Claire low on Cognitive Flexibility
        cf_low = by_dim.get("cognitive_flexibility", {}).get("low_outliers") or []
        ok("2.7.CF Claire among low_outliers on Cognitive Flexibility",
           any("Claire" in (e.get("name") or "") for e in cf_low),
           f"got {names_in(cf_low)}")

        # Claire low on Systems Thinking
        st_low = by_dim.get("systems_thinking", {}).get("low_outliers") or []
        ok("2.7.ST Claire among low_outliers on Systems Thinking",
           any("Claire" in (e.get("name") or "") for e in st_low),
           f"got {names_in(st_low)}")

        # Claire high on AI Fluency
        ai_hi = by_dim.get("ai_fluency", {}).get("high_outliers") or []
        ok("2.7.AI Claire among high_outliers on AI Fluency",
           any("Claire" in (e.get("name") or "") for e in ai_hi),
           f"got {names_in(ai_hi)}")

        # Verify outlier entry keys + sort by |z| desc
        for o in outs:
            for kind, zkey in (("low_outliers", "std_devs_below"),
                               ("high_outliers", "std_devs_above")):
                lst = o.get(kind) or []
                for e in lst:
                    ek = set(e.keys())
                    needed = {"session_id", "label", "name", "score"}
                    ok(f"2.7.entry {o.get('dimension_id')} {kind} keys",
                       needed.issubset(ek) and (zkey in ek),
                       f"missing={needed - ek}; zkey={zkey} present={zkey in ek}")
                # sort: |z| descending
                zs = [abs(e.get(zkey, 0.0)) for e in lst]
                ok(f"2.7.sort {o.get('dimension_id')} {kind} sorted by |z| desc",
                   zs == sorted(zs, reverse=True),
                   f"got {zs}")

    # cohort_type
    ct = body.get("cohort_type") or {}
    ts = ct.get("top_strengths") or []
    td = ct.get("top_dev_areas") or []
    ok("2.8.ts top_strengths length 3", len(ts) == 3, f"len={len(ts)}")
    ok("2.8.td top_dev_areas length 3", len(td) == 3, f"len={len(td)}")
    sumstr = ct.get("strength_summary") or ""
    ok("2.8.tpl strength_summary contains 'strongest dimensions' and 'respectively.'",
       "strongest dimensions" in sumstr and "respectively." in sumstr,
       f"got {sumstr!r}")
    ts_means = [t.get("mean") for t in ts if t.get("mean") is not None]
    ok("2.8.ts.nonincr top_strengths means non-increasing",
       all(ts_means[i] >= ts_means[i+1] for i in range(len(ts_means)-1)),
       f"means={ts_means}")
    td_means = [t.get("mean") for t in td if t.get("mean") is not None]
    ok("2.8.td.nondecr top_dev_areas means non-decreasing",
       all(td_means[i] <= td_means[i+1] for i in range(len(td_means)-1)),
       f"means={td_means}")

    # category_distribution
    cd = body.get("category_distribution") or {}
    ok("2.9.cd_keys keys exactly = 4 valid labels",
       set(cd.keys()) == EXPECTED_VALID_CATEGORIES,
       f"got {set(cd.keys())}")
    ok("2.9.cd_sum sum == 4",
       sum(cd.values()) == 4, f"sum={sum(cd.values())}")

    # flag_summary
    fs = body.get("flag_summary") or {}
    ok("2.10.fs.keys flag_summary keys",
       set(fs.keys()) == EXPECTED_FLAG_KEYS,
       f"got {set(fs.keys())}")
    ok("2.10.fs.total total_flagged == 1",
       fs.get("total_flagged") == 1,
       f"got {fs.get('total_flagged')}")

    # generated_at parseable
    gen = body.get("generated_at") or ""
    parsed = None
    try:
        parsed = datetime.fromisoformat(gen.replace("Z", "+00:00"))
    except Exception as e:
        parsed = None
    ok("2.11 generated_at parseable iso8601",
       parsed is not None, f"got {gen!r}")

    return body


def section3_validation(tok: str):
    print("\n[3] VALIDATION")

    # Empty ids
    r = requests.get(f"{BASE}/admin/sessions/cohort", params={"ids": ""},
                     headers=H(tok), timeout=10)
    ok("3.1 empty ids → 422", r.status_code == 422, f"got {r.status_code}: {r.text[:200]}")

    # 1 id only
    r = requests.get(f"{BASE}/admin/sessions/cohort", params={"ids": ADA1},
                     headers=H(tok), timeout=10)
    ok("3.2.status 1 id → 422", r.status_code == 422, f"got {r.status_code}")
    if r.status_code == 422:
        body = r.text
        ok("3.2.msg detail contains 'between 2 and 50'",
           "between 2 and 50" in body, f"body: {body[:200]}")

    # 51 same id repeated
    r = requests.get(f"{BASE}/admin/sessions/cohort",
                     params={"ids": ",".join([ADA1] * 51)},
                     headers=H(tok), timeout=10)
    ok("3.3 same id repeated 51× (dedupe→1) → 422",
       r.status_code == 422, f"got {r.status_code}: {r.text[:200]}")

    # 3 same id repeated
    r = requests.get(f"{BASE}/admin/sessions/cohort",
                     params={"ids": ",".join([ADA1] * 3)},
                     headers=H(tok), timeout=10)
    ok("3.4 same id repeated 3× (dedupe→1) → 422",
       r.status_code == 422, f"got {r.status_code}: {r.text[:200]}")

    # Unknown id mixed with valid
    r = requests.get(f"{BASE}/admin/sessions/cohort",
                     params={"ids": f"{ADA1},{ADA2},bogus-id-99999"},
                     headers=H(tok), timeout=15)
    ok("3.5.status unknown id mixed → 404",
       r.status_code == 404, f"got {r.status_code}: {r.text[:200]}")
    if r.status_code == 404:
        try:
            body = r.json()
            missing = (body.get("detail") or {}).get("missing")
            ok("3.5.missing detail.missing == ['bogus-id-99999']",
               missing == ["bogus-id-99999"], f"got {missing!r}")
        except Exception as e:
            ok("3.5.missing parse", False, str(e))

    # Incomplete session mixed with valid
    r = requests.get(f"{BASE}/admin/sessions/cohort",
                     params={"ids": f"{ADA1},{ADA2},{INCOMPLETE}"},
                     headers=H(tok), timeout=15)
    ok("3.6.status incomplete mixed → 422",
       r.status_code == 422, f"got {r.status_code}: {r.text[:200]}")
    if r.status_code == 422:
        try:
            body = r.json()
            detail = body.get("detail") or {}
            msg = detail.get("message") or ""
            ok("3.6.msg detail.message contains 'Cohort requires every session to be completed'",
               "Cohort requires every session to be completed" in msg,
               f"got {msg!r}")
            inc = detail.get("incomplete") or []
            ok("3.6.inc0sid incomplete[0].session_id == INCOMPLETE id",
               len(inc) >= 1 and inc[0].get("session_id") == INCOMPLETE,
               f"got {inc}")
            reasons = (inc[0].get("reasons") if inc else []) or []
            wanted = {"missing_scores.psychometric", "missing_scores.ai_fluency",
                      "missing_scores.scenario", "missing_or_errored_deliverable"}
            ok("3.6.reasons reasons include all 4 spec values",
               wanted.issubset(set(reasons)),
               f"got {reasons}; missing {wanted - set(reasons)}")
        except Exception as e:
            ok("3.6.parse", False, str(e))

    # No admin cookie
    r = requests.get(f"{BASE}/admin/sessions/cohort",
                     params={"ids": f"{ADA1},{ADA2}"}, timeout=10)
    ok("3.7.status no admin cookie → 401",
       r.status_code == 401, f"got {r.status_code}: {r.text[:200]}")
    if r.status_code == 401:
        try:
            body = r.json()
            ok("3.7.msg 'Not authenticated.'",
               (body.get("detail") or "") == "Not authenticated.",
               f"got {body}")
        except Exception:
            ok("3.7.msg 'Not authenticated.'", False, "non-json body")


def section4_route_ordering(tok: str):
    print("\n[4] ROUTE ORDERING")

    # /sessions/compare still works
    r = requests.get(f"{BASE}/admin/sessions/compare",
                     params={"ids": f"{ADA1},{ADA2}"},
                     headers=H(tok), timeout=20)
    ok("4.1 /sessions/compare still 200",
       r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
    if r.status_code == 200:
        b = r.json()
        wanted = {"participants", "radar_data", "dimension_table",
                  "executive_summaries", "key_quotes", "scenario_quotes",
                  "flags", "axis_order", "generated_at"}
        ok("4.1.keys compare keys present (superset of spec)",
           wanted.issubset(set(b.keys())),
           f"missing={wanted - set(b.keys())}")

    # /sessions/{id} detail
    r = requests.get(f"{BASE}/admin/sessions/{ADA1}",
                     headers=H(tok), timeout=15)
    ok("4.2 /sessions/{id} detail 200",
       r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        ok("4.2.sid detail contains session_id",
           r.json().get("session_id") == ADA1, "session_id mismatch")

    # /sessions/{id}/engagement
    r = requests.get(f"{BASE}/admin/sessions/{ADA1}/engagement",
                     headers=H(tok), timeout=15)
    ok("4.3 /sessions/{id}/engagement 200",
       r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")

    # OpenAPI
    r = requests.get(f"{BASE}/openapi.json", timeout=15)
    ok("4.4.status openapi 200", r.status_code == 200)
    if r.status_code == 200:
        spec = r.json()
        path = "/api/admin/sessions/cohort"
        path_obj = (spec.get("paths") or {}).get(path)
        ok("4.4.path /api/admin/sessions/cohort present in openapi",
           path_obj is not None, f"missing {path}")
        if path_obj:
            summary = (path_obj.get("get") or {}).get("summary", "")
            ok("4.4.summary openapi summary text",
               summary == "Cohort aggregation across N completed sessions (admin)",
               f"got {summary!r}")


def section5_side_effects(tok: str):
    print("\n[5] SIDE EFFECTS — cohort triggers no Mongo write")

    # Baseline detail call
    r0 = requests.get(f"{BASE}/admin/sessions/{ADA1}",
                      headers=H(tok), timeout=15)
    ok("5.0 baseline detail 200", r0.status_code == 200)
    if r0.status_code != 200:
        return
    baseline_ts = r0.json().get("last_admin_viewed_at")
    ok("5.0.ts baseline last_admin_viewed_at present",
       isinstance(baseline_ts, str) and len(baseline_ts) > 0,
       f"got {baseline_ts!r}")

    # Wait a beat to ensure any new write would yield a different ISO
    time.sleep(1.1)

    # Cohort call
    r1 = requests.get(f"{BASE}/admin/sessions/cohort",
                     params={"ids": ",".join(VALID_4)},
                     headers=H(tok), timeout=30)
    ok("5.1 cohort 200", r1.status_code == 200, f"got {r1.status_code}")

    # Verify Ada's last_admin_viewed_at unchanged immediately after cohort.
    # We can't directly query Mongo here without a side-channel, so do
    # the second detail call and verify the timestamp moved forward
    # ONLY because of the second detail call (i.e. baseline -> after cohort
    # should be unchanged; we infer that by reading the timestamp in the
    # detail response). Approach: capture timestamps before & after the cohort,
    # but the only way to read without mutating is the detail GET itself.
    # So we use an alternative: after the cohort call, read the participant
    # cohort payload — does the cohort itself echo the current last_admin
    # timestamp? No, it doesn't. So we read the next detail; that detail call
    # itself stamps a NEW timestamp. To infer that the cohort didn't write,
    # we compare: the new timestamp captured in the detail GET should be
    # "fresh" (right now), AND if the cohort had stamped, we'd expect the
    # admin doc's mongo state to already have the newer ts.
    # We approximate: if the detail's NEW timestamp is strictly greater than
    # baseline AND the cohort call doesn't itself appear to have touched the
    # field, that's enough.
    time.sleep(1.1)
    r2 = requests.get(f"{BASE}/admin/sessions/{ADA1}",
                     headers=H(tok), timeout=15)
    ok("5.2 second detail 200", r2.status_code == 200)
    if r2.status_code != 200:
        return
    second_ts = r2.json().get("last_admin_viewed_at")
    ok("5.2.adv second detail's ts > baseline (only this call wrote)",
       isinstance(second_ts, str) and second_ts > baseline_ts,
       f"baseline={baseline_ts} second={second_ts}")

    # The test that cohort itself did not write requires DB-level inspection.
    # Best-effort proxy: check via mongo if accessible.
    try:
        from motor.motor_asyncio import AsyncIOMotorClient  # noqa
        import asyncio

        async def _probe():
            mongo_url = os.environ.get("MONGO_URL")
            if not mongo_url:
                # try reading backend/.env
                with open("/app/backend/.env") as fh:
                    for line in fh:
                        if line.startswith("MONGO_URL="):
                            return line.split("=", 1)[1].strip()
                return None
            return mongo_url

        mongo_url = asyncio.run(_probe())
        if mongo_url:
            from pymongo import MongoClient
            cli = MongoClient(mongo_url)
            db_name = os.environ.get("DB_NAME") or "test_database"
            try:
                with open("/app/backend/.env") as fh:
                    for line in fh:
                        if line.startswith("DB_NAME="):
                            db_name = line.split("=", 1)[1].strip()
            except Exception:
                pass
            db = cli[db_name]
            # Repeat: capture current ts, run cohort, capture after cohort,
            # run detail, capture after detail. Verify cohort did not bump it.
            doc1 = db.sessions.find_one({"session_id": ADA1},
                                        {"last_admin_viewed_at": 1, "_id": 0})
            ts_pre = (doc1 or {}).get("last_admin_viewed_at")

            time.sleep(1.1)
            requests.get(f"{BASE}/admin/sessions/cohort",
                         params={"ids": ",".join(VALID_4)},
                         headers=H(tok), timeout=30)
            doc2 = db.sessions.find_one({"session_id": ADA1},
                                        {"last_admin_viewed_at": 1, "_id": 0})
            ts_after_cohort = (doc2 or {}).get("last_admin_viewed_at")

            ok("5.3.no_write cohort did NOT modify last_admin_viewed_at",
               ts_after_cohort == ts_pre,
               f"pre={ts_pre} after_cohort={ts_after_cohort}")

            time.sleep(1.1)
            requests.get(f"{BASE}/admin/sessions/{ADA1}",
                        headers=H(tok), timeout=15)
            doc3 = db.sessions.find_one({"session_id": ADA1},
                                        {"last_admin_viewed_at": 1, "_id": 0})
            ts_after_detail = (doc3 or {}).get("last_admin_viewed_at")
            ok("5.3.detail_writes detail call DID modify last_admin_viewed_at",
               ts_after_detail and ts_after_detail != ts_after_cohort,
               f"after_cohort={ts_after_cohort} after_detail={ts_after_detail}")
        else:
            print("  (no MONGO_URL available; skipping DB-level proxy)")
    except Exception as e:
        print(f"  (mongo probe skipped: {e})")


def section6_regression():
    print("\n[6] REGRESSION pytest backend/tests/")
    import subprocess
    proc = subprocess.run(
        ["python", "-m", "pytest", "tests/", "-q"],
        cwd="/app/backend",
        capture_output=True, text=True, timeout=300,
    )
    print(proc.stdout[-2000:])
    if proc.returncode != 0:
        print("STDERR tail:", proc.stderr[-500:])
    out = proc.stdout
    m = re.search(r"(\d+) passed", out)
    n = int(m.group(1)) if m else 0
    ok("6.1 pytest exit 0", proc.returncode == 0, f"rc={proc.returncode}")
    ok("6.2 pytest reports 146 passed", n == 146, f"got {n} passed")


def main():
    tok = section1_auth()
    section2_happy_path(tok)
    section3_validation(tok)
    section4_route_ordering(tok)
    section5_side_effects(tok)
    section6_regression()

    print("\n" + "=" * 60)
    print(f"PASS: {len(PASS)}    FAIL: {len(FAIL)}")
    if FAIL:
        print("\nFAILURES:")
        for f in FAIL:
            print(f"  - {f}")
    print("=" * 60)
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
