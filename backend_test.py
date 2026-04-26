"""
Phase 11A backend test sweep.

Targets:
  (A) GET /api/admin/sessions extended filters & sort:
      dimension_min[<dim>], dimension_max[<dim>], overall_category,
      response_flag (csv + any/none), sort by 6 dimension keys (asc/desc),
      filters_applied echo, error 422s, regression of existing params.
  (B) GET /api/admin/sessions/compare?ids=A,B
      happy paths, 422 / 404 / 401 errors, route-ordering.

Uses internal http://localhost:8001/api per brief; replays admin JWT
via explicit Cookie header (Secure cookie cannot replay over plain http
via requests.Session).
"""

import json
import sys
from typing import Dict, Any, List, Optional

import requests

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "steve@org-logic.io"
ADMIN_PASSWORD = "test1234"

# Canonical sessions per brief
ADA_A = "f9959971-5ee8-4f9f-83e6-f59ea747d9e0"
ADA_B = "2253141a-830f-4810-a683-890f098b5664"
TESTER = "5953a3d3-9539-45dd-9835-34a8c719be19"
PHASE2_TESTER_INCOMPLETE = "1178ba0a-4c66-4dd0-a62a-2de014ee5acb"

# ───────────────────────── helpers ─────────────────────────
PASS: List[str] = []
FAIL: List[str] = []


def record(label: str, ok: bool, info: str = ""):
    if ok:
        PASS.append(label)
        print(f"  PASS {label}" + (f" — {info}" if info else ""))
    else:
        FAIL.append(f"{label}: {info}")
        print(f"  FAIL {label} — {info}")


def admin_token() -> str:
    r = requests.post(
        f"{BASE}/admin/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"FATAL: admin login failed -> {r.status_code} {r.text[:200]}")
        sys.exit(2)
    set_cookie = r.headers.get("set-cookie", "")
    tok = None
    for piece in set_cookie.split(";"):
        piece = piece.strip()
        if piece.startswith("tra_admin_token="):
            tok = piece.split("=", 1)[1]
            break
    if not tok:
        try:
            tok = r.json().get("token")
        except Exception:
            pass
    if not tok:
        print(f"FATAL: could not extract tra_admin_token from set-cookie={set_cookie!r}")
        sys.exit(2)
    return tok


def H(token: str) -> Dict[str, str]:
    return {"Cookie": f"tra_admin_token={token}"}


def G_raw(path_with_qs: str, token: Optional[str] = None) -> requests.Response:
    headers = H(token) if token else {}
    return requests.get(f"{BASE}{path_with_qs}", headers=headers, timeout=30)


# ───────────────────────── tests ─────────────────────────
def test_auth_prep() -> str:
    print("\n[1] AUTH PREP")
    tok = admin_token()
    record("admin login -> token retrieved", bool(tok), info=f"len={len(tok)}")
    r = G_raw("/admin/auth/me", tok)
    record("GET /admin/auth/me with replayed Cookie -> 200",
           r.status_code == 200, info=f"status={r.status_code}")
    return tok


def test_list_filters(tok: str):
    print("\n[2] LIST FILTERS")

    # 2a
    r = G_raw("/admin/sessions?dimension_min%5Blearning_agility%5D=3.5&page_size=200", tok)
    ok = r.status_code == 200
    record("2a status 200", ok, info=f"status={r.status_code}")
    if ok:
        body = r.json()
        items = body.get("items", [])
        bad = [it for it in items
               if (it.get("dimensions") or {}).get("learning_agility") is None
               or it["dimensions"]["learning_agility"] < 3.5]
        record("2a all items LA>=3.5 (nulls excluded)", not bad,
               info=f"items={len(items)} bad={len(bad)}")
        record("2a filters_applied.dimension_min == {learning_agility:3.5}",
               body.get("filters_applied", {}).get("dimension_min") == {"learning_agility": 3.5},
               info=str(body.get("filters_applied", {}).get("dimension_min")))
        if items:
            sample = items[0]
            dims = sample.get("dimensions") or {}
            expected = {"learning_agility", "tolerance_for_ambiguity", "cognitive_flexibility",
                        "self_awareness_accuracy", "ai_fluency", "systems_thinking"}
            record("2a item.dimensions has all 6 keys",
                   set(dims.keys()) == expected, info=f"keys={sorted(dims.keys())}")
            record("2a item has response_pattern_flag key",
                   "response_pattern_flag" in sample)

    # 2b
    r = G_raw("/admin/sessions?dimension_min%5Blearning_agility%5D=3.5&dimension_max%5Blearning_agility%5D=4.5&page_size=200", tok)
    if r.status_code == 200:
        items = r.json().get("items", [])
        bad = [it for it in items
               if not (3.5 <= ((it.get("dimensions") or {}).get("learning_agility") or -1) <= 4.5)]
        record("2b 3.5<=LA<=4.5", not bad, info=f"items={len(items)} bad={len(bad)}")
    else:
        record("2b status 200", False, info=f"status={r.status_code} body={r.text[:160]}")

    # 2c
    r = G_raw("/admin/sessions?dimension_min%5Bai_fluency%5D=3.0&dimension_min%5Bcognitive_flexibility%5D=3.0&page_size=200", tok)
    if r.status_code == 200:
        items = r.json().get("items", [])
        bad = []
        for it in items:
            d = it.get("dimensions") or {}
            af, cf = d.get("ai_fluency"), d.get("cognitive_flexibility")
            if af is None or cf is None or af < 3.0 or cf < 3.0:
                bad.append(it.get("session_id"))
        record("2c both dim constraints applied (AND)", not bad,
               info=f"items={len(items)} bad={len(bad)}")
    else:
        record("2c status 200", False, info=f"status={r.status_code}")

    # 2d
    r = G_raw("/admin/sessions?overall_category=High%20Potential&page_size=200", tok)
    if r.status_code == 200:
        body = r.json()
        items = body.get("items", [])
        bad = [it for it in items if it.get("overall_category") != "High Potential"]
        record("2d all items overall_category=='High Potential'", not bad,
               info=f"items={len(items)} bad={len(bad)}")
        record("2d filters_applied.overall_category echoed",
               body.get("filters_applied", {}).get("overall_category") == "High Potential")
    else:
        record("2d status 200", False, info=f"status={r.status_code}")

    # 2e
    r = G_raw("/admin/sessions?overall_category=High%20Potential,Transformation%20Ready&page_size=200", tok)
    if r.status_code == 200:
        items = r.json().get("items", [])
        cats = {it.get("overall_category") for it in items}
        bad = cats - {"High Potential", "Transformation Ready"}
        record("2e CSV expansion: only HP+TR returned", not bad, info=f"cats={cats}")
    else:
        record("2e status 200", False, info=f"status={r.status_code}")

    # 2f
    r = G_raw("/admin/sessions?response_flag=any&page_size=200", tok)
    if r.status_code == 200:
        items = r.json().get("items", [])
        bad = [it for it in items if it.get("response_pattern_flag") is None]
        record("2f response_flag=any -> only non-null flags", not bad,
               info=f"items={len(items)} bad={len(bad)}")
    else:
        record("2f status 200", False, info=f"status={r.status_code}")

    # 2g
    r = G_raw("/admin/sessions?response_flag=none&page_size=200", tok)
    if r.status_code == 200:
        items = r.json().get("items", [])
        bad = [it for it in items if it.get("response_pattern_flag") is not None]
        record("2g response_flag=none -> only null flags", not bad,
               info=f"items={len(items)} bad={len(bad)}")
    else:
        record("2g status 200", False, info=f"status={r.status_code}")

    # 2h
    r = G_raw("/admin/sessions?response_flag=high_acquiescence&page_size=200", tok)
    if r.status_code == 200:
        items = r.json().get("items", [])
        bad = [it for it in items if it.get("response_pattern_flag") != "high_acquiescence"]
        record("2h response_flag=high_acquiescence only matching", not bad,
               info=f"items={len(items)} bad={len(bad)}")
    else:
        record("2h status 200", False, info=f"status={r.status_code}")

    # 2i SORT
    for dim in ("learning_agility", "ai_fluency", "cognitive_flexibility"):
        r = G_raw(f"/admin/sessions?sort=-{dim}&page_size=200", tok)
        if r.status_code == 200:
            items = r.json().get("items", [])
            vals = [(it.get("dimensions") or {}).get(dim) for it in items]
            non_null = [v for v in vals if v is not None]
            ordered = all(non_null[i] >= non_null[i + 1] for i in range(len(non_null) - 1))
            record(f"2i sort=-{dim} desc among non-nulls", ordered, info=f"n_nn={len(non_null)}")
        else:
            record(f"2i sort=-{dim} status 200", False, info=f"status={r.status_code}")
        r = G_raw(f"/admin/sessions?sort={dim}&page_size=200", tok)
        if r.status_code == 200:
            items = r.json().get("items", [])
            vals = [(it.get("dimensions") or {}).get(dim) for it in items]
            non_null = [v for v in vals if v is not None]
            ordered = all(non_null[i] <= non_null[i + 1] for i in range(len(non_null) - 1))
            record(f"2i sort={dim} asc among non-nulls", ordered, info=f"n_nn={len(non_null)}")
        else:
            record(f"2i sort={dim} status 200", False, info=f"status={r.status_code}")

    # 2j ERROR PATHS
    cases = [
        ("/admin/sessions?dimension_min%5Blearning_agility%5D=6.0", 422, "between 1.0 and 5.0"),
        ("/admin/sessions?dimension_min%5Blearning_agility%5D=foo", 422, "must be a number"),
        ("/admin/sessions?dimension_min%5Bbad_dim%5D=3", 422, "Unknown dimension"),
        ("/admin/sessions?overall_category=Bogus%20Category", 422, "Unknown overall_category"),
        ("/admin/sessions?response_flag=any,none", 422, "any"),
        ("/admin/sessions?response_flag=bogus_flag", 422, "Unknown response_flag"),
    ]
    for path, exp_status, exp_substr in cases:
        r = G_raw(path, tok)
        ok_status = r.status_code == exp_status
        try:
            detail = r.json().get("detail")
            detail_s = json.dumps(detail) if not isinstance(detail, str) else detail
        except Exception:
            detail_s = r.text
        ok_msg = exp_substr.lower() in (detail_s or "").lower()
        record(f"2j {path[-55:]} -> {exp_status} & '{exp_substr}'",
               ok_status and ok_msg,
               info=f"got={r.status_code} detail={detail_s[:140]}")

    # 2k REGRESSION
    r = G_raw("/admin/sessions?page=1&page_size=10", tok)
    if r.status_code == 200:
        body = r.json()
        keys = set(body.keys())
        record("2k regression top-level keys",
               keys >= {"items", "total", "page", "page_size", "filters_applied"},
               info=f"keys={keys}")
        fa = body.get("filters_applied", {})
        record("2k filters_applied has new keys (dimension_min/max/overall_category/response_flag)",
               all(k in fa for k in ("dimension_min", "dimension_max",
                                     "overall_category", "response_flag")),
               info=f"fa_keys={sorted(fa.keys())}")
        rq = G_raw("/admin/sessions?q=Ada&page_size=10", tok)
        if rq.status_code == 200:
            items = rq.json().get("items", [])
            record("2k q=Ada regression returns items", len(items) >= 1, info=f"n={len(items)}")
        else:
            record("2k q=Ada status 200", False, info=f"status={rq.status_code}")
        rs = G_raw("/admin/sessions?status=completed&page_size=200", tok)
        if rs.status_code == 200:
            items = rs.json().get("items", [])
            bad = [it for it in items if it.get("status") != "completed"]
            record("2k status=completed regression", not bad,
                   info=f"items={len(items)} bad={len(bad)}")
        else:
            record("2k status=completed status 200", False, info=f"status={rs.status_code}")
    else:
        record("2k regression status 200", False, info=f"status={r.status_code}")


def test_compare(tok: str):
    print("\n[3] COMPARE")

    # 3a — Ada vs Ada
    r = G_raw(f"/admin/sessions/compare?ids={ADA_A},{ADA_B}", tok)
    ok = r.status_code == 200
    record("3a Ada x Ada -> 200", ok, info=f"status={r.status_code} body={r.text[:200] if not ok else ''}")
    if ok:
        b = r.json()
        expected_top = {"participants", "radar_data", "dimension_table",
                        "executive_summaries", "key_quotes", "scenario_quotes",
                        "flags", "axis_order", "generated_at"}
        record("3a top-level keys", set(b.keys()) >= expected_top,
               info=f"missing={expected_top - set(b.keys())}")
        ps = b.get("participants", [])
        record("3a participants len==2", len(ps) == 2)
        for i, p in enumerate(ps):
            need = {"name", "organisation", "role", "completion_date",
                    "overall_category", "overall_colour", "response_pattern_flag",
                    "scoring_error"}
            record(f"3a participants[{i}] required keys", need <= set(p.keys()),
                   info=f"missing={need - set(p.keys())}")
        rd = b.get("radar_data", [])
        record("3a radar_data len==2", len(rd) == 2)
        for i, ri in enumerate(rd):
            dims = ri.get("dimensions", {})
            need = {"learning_agility", "tolerance_for_ambiguity", "cognitive_flexibility",
                    "self_awareness_accuracy", "ai_fluency", "systems_thinking"}
            record(f"3a radar_data[{i}].dimensions has 6 keys",
                   set(dims.keys()) == need, info=f"keys={sorted(dims.keys())}")
        dt = b.get("dimension_table", [])
        record("3a dimension_table len==6", len(dt) == 6, info=f"n={len(dt)}")
        for i, row in enumerate(dt):
            need = {"dimension", "dimension_id", "a_score", "a_band",
                    "b_score", "b_band", "delta", "delta_band", "divergent"}
            record(f"3a dimension_table[{i}] required keys",
                   need <= set(row.keys()),
                   info=f"missing={need - set(row.keys())}")
        deltas = [abs(row["delta"]) if row.get("delta") is not None else -1 for row in dt]
        sorted_ok = all(deltas[i] >= deltas[i + 1] for i in range(len(deltas) - 1))
        record("3a dimension_table sorted by abs(delta) desc", sorted_ok, info=f"deltas={deltas}")
        es = b.get("executive_summaries", [])
        record("3a executive_summaries len==2", len(es) == 2)
        for i, e in enumerate(es):
            need = {"overall_category", "category_statement", "prose",
                    "key_strengths", "development_priorities", "bottom_line"}
            record(f"3a executive_summaries[{i}] required keys", need <= set(e.keys()),
                   info=f"missing={need - set(e.keys())}")
        kq = b.get("key_quotes", [])
        record("3a key_quotes len==2", len(kq) == 2)
        for i, k in enumerate(kq):
            qs = k.get("quotes", [])
            cap_ok = isinstance(qs, list) and len(qs) <= 3 and all(isinstance(s, str) for s in qs)
            record(f"3a key_quotes[{i}] capped <=3 strings", cap_ok, info=f"len={len(qs)}")
        sq = b.get("scenario_quotes", [])
        record("3a scenario_quotes len==2", len(sq) == 2)
        for i, s in enumerate(sq):
            cf = s.get("cognitive_flexibility") or {}
            st = s.get("systems_thinking") or {}
            ok_cf = {"score", "band", "key_quote"} <= set(cf.keys())
            ok_st = {"score", "band", "key_quote"} <= set(st.keys())
            record(f"3a scenario_quotes[{i}] cf+st score/band/key_quote",
                   ok_cf and ok_st)
        fl = b.get("flags", [])
        record("3a flags len==2", len(fl) == 2)
        for i, f in enumerate(fl):
            record(f"3a flags[{i}] response_pattern_flag+scoring_error",
                   {"response_pattern_flag", "scoring_error"} <= set(f.keys()))
        ax = b.get("axis_order")
        expected_axis = ["learning_agility", "tolerance_for_ambiguity",
                         "cognitive_flexibility", "self_awareness_accuracy",
                         "ai_fluency", "systems_thinking"]
        record("3a axis_order matches fixed order", ax == expected_axis,
               info=f"got={ax}")

    # 3b — Ada vs Tester
    r = G_raw(f"/admin/sessions/compare?ids={ADA_A},{TESTER}", tok)
    ok = r.status_code == 200
    record("3b Ada x Tester -> 200", ok, info=f"status={r.status_code}")
    if ok:
        b = r.json()
        dt = b.get("dimension_table", [])
        deltas = [abs(row["delta"]) if row.get("delta") is not None else -1 for row in dt]
        sorted_ok = all(deltas[i] >= deltas[i + 1] for i in range(len(deltas) - 1))
        record("3b dimension_table sorted by |delta| desc", sorted_ok, info=f"deltas={deltas}")
        if len(dt) >= 2:
            top_two_ids = {dt[0]["dimension_id"], dt[1]["dimension_id"]}
            record("3b top two rows are CF and ST",
                   top_two_ids == {"cognitive_flexibility", "systems_thinking"},
                   info=f"top_two={top_two_ids} top_deltas={[dt[0]['delta'], dt[1]['delta']]}")
            for row in dt[:2]:
                record(f"3b top row {row['dimension_id']} divergent=true",
                       bool(row.get("divergent")),
                       info=f"delta={row.get('delta')}")
        non_zero = [d for d in deltas if d > 0]
        record("3b at least one non-zero delta", bool(non_zero), info=f"non_zero={non_zero}")

    # 3c ERRORS
    r = G_raw("/admin/sessions/compare?ids=onlyone", tok)
    record("3c only-one-id -> 422 + 'exactly two'",
           r.status_code == 422 and "exactly two" in r.text.lower(),
           info=f"status={r.status_code} body={r.text[:140]}")

    r = G_raw("/admin/sessions/compare?ids=", tok)
    record("3c empty ids -> 422", r.status_code == 422,
           info=f"status={r.status_code} body={r.text[:140]}")

    r = G_raw(f"/admin/sessions/compare?ids={ADA_A},{ADA_A}", tok)
    record("3c identical ids -> 422 + 'two different'",
           r.status_code == 422 and "different" in r.text.lower(),
           info=f"status={r.status_code} body={r.text[:140]}")

    bogus = "does-not-exist-99999999"
    r = G_raw(f"/admin/sessions/compare?ids={ADA_A},{bogus}", tok)
    ok_status = r.status_code == 404
    detail_ok = False
    try:
        d = r.json().get("detail")
        if isinstance(d, dict) and bogus in (d.get("missing") or []):
            detail_ok = True
    except Exception:
        pass
    record("3c missing id -> 404 + detail.missing array",
           ok_status and detail_ok,
           info=f"status={r.status_code} body={r.text[:200]}")

    r = G_raw(f"/admin/sessions/compare?ids={PHASE2_TESTER_INCOMPLETE},{ADA_A}", tok)
    ok_status = r.status_code == 422
    detail_ok = False
    try:
        d = r.json().get("detail")
        if isinstance(d, dict):
            inc = d.get("incomplete") or []
            if inc and all("reasons" in i for i in inc):
                any_ms = any(any("missing_scores" in r0 for r0 in (i.get("reasons") or [])) for i in inc)
                detail_ok = any_ms
    except Exception:
        pass
    record("3c incomplete session -> 422 + detail.incomplete[].reasons (missing_scores)",
           ok_status and detail_ok,
           info=f"status={r.status_code} body={r.text[:300]}")

    r = requests.get(f"{BASE}/admin/sessions/compare?ids={ADA_A},{ADA_B}", timeout=15)
    record("3c no auth cookie -> 401",
           r.status_code == 401,
           info=f"status={r.status_code} body={r.text[:120]}")


def test_route_ordering(tok: str):
    print("\n[4] ROUTE ORDERING")

    r = G_raw(f"/admin/sessions/compare?ids={ADA_A},{ADA_B}", tok)
    if r.status_code == 200:
        body = r.json()
        is_compare = ("axis_order" in body and "dimension_table" in body
                      and "radar_data" in body)
        record("4 /sessions/compare returns COMPARE payload (not session detail)",
               is_compare, info=f"keys={sorted(body.keys())[:8]}")
    else:
        record("4 /sessions/compare returns 200", False, info=f"status={r.status_code}")

    r = G_raw(f"/admin/sessions/{ADA_B}", tok)
    if r.status_code == 200:
        body = r.json()
        is_session = ("session_id" in body and "participant" in body
                      and "axis_order" not in body)
        record("4 /sessions/<real-id> returns SESSION payload (not compare)",
               is_session, info=f"session_id={body.get('session_id')}")
    else:
        record("4 /sessions/<real-id> returns 200", False, info=f"status={r.status_code}")


def main():
    print(f"BASE = {BASE}")
    tok = test_auth_prep()
    test_list_filters(tok)
    test_compare(tok)
    test_route_ordering(tok)
    print("\n" + "=" * 60)
    print(f"PASS: {len(PASS)}    FAIL: {len(FAIL)}")
    if FAIL:
        print("\nFailures:")
        for f in FAIL:
            print(f"  FAIL {f}")
    print("=" * 60)
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
