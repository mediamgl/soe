#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================


#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Phase 2 of the Transformation Readiness Assessment web app. Builds on Phase 1.
  Goal: (1) ingest methodology content (scan only, don't wire copy yet), (2) capture participant
  identity at Begin, (3) persist session state in Mongo, (4) implement resume-by-code with
  a Save & exit affordance and localStorage hydrate. Placeholder stages remain placeholders.

backend:
  - task: "Phase 9 hotfix — synthesis timeouts, terminal-status guarantee, admin re-synthesize"
    implemented: true
    working: false
    file: "backend/server.py, backend/services/synthesis_service.py, backend/services/llm_router.py"
    stuck_count: 1
    priority: "high"
    needs_retesting: true
    status_history:
        - working: false
          agent: "testing"
          comment: |
            Phase 9 backend sweep complete. Ran /app/backend_test_phase9.py
            against http://localhost:8001/api. 62/63 assertions PASS. ONE
            FAILURE — small but real audit-trail bug in the new admin
            re-synthesize endpoint. Details below.

            ============  FAILURE  ============
            C4.9 — POST /api/admin/sessions/{ada}/resynthesize succeeds
                  (returns 202 with the right body, kicks off the worker,
                  clears deliverable, sets stage=processing, sets
                  synthesis.status=in_progress + synthesis.restarted_at).
                  HOWEVER, synthesis.restarted_by is persisted as `None`
                  instead of the admin email "steve@org-logic.io". The
                  spec explicitly requires restarted_by==<admin_email>.

                  Root cause: server.py:2134 reads the admin email from
                  the JWT payload as `current.get("email")`, but
                  create_access_token (auth_utils.py:35-45) stores the
                  email in the `sub` claim, not `email`. Existing admin
                  endpoints correctly use `current["sub"]` (e.g.
                  /admin/auth/me at server.py:1602). The new endpoint at
                  server.py:2114 mismatches this contract.

                  Same bug also corrupts the audit log line — the call
                  emits `INFO: Admin re-synthesis triggered
                  session=… by=unknown_admin` because admin_email
                  resolves to None and the logger falls back to
                  "unknown_admin" (server.py:2153-2154). This means
                  re-synthesis events are NOT attributable to a specific
                  admin in the operator audit trail. (Verified directly
                  in /var/log/supervisor/backend.err.log — both runs in
                  this sweep wrote `by=unknown_admin`.)

                  REMEDIATION: change line 2134 from
                    admin_email = (current or {}).get("email") if isinstance(current, dict) else None
                  to
                    admin_email = (current or {}).get("sub") if isinstance(current, dict) else None
                  One-line fix. No other callers of the JWT payload need
                  to change (the rest of the codebase already reads
                  `sub`).

            (Side-observation: the F2 log-hygiene assertion in my
            harness *accidentally* passed because the log file contains
            stale "Admin settings updated by=steve@org-logic.io" lines
            from previous Phase-3 sweeps that match my substring search.
            The actual resynth log lines from this sweep all read
            `by=unknown_admin`, confirmed via grep.)

            ============  PASSED  ============
            A. /api/openapi.json
              A0. 200 OK ✓
              A1. Exactly 36 /api/* paths (35 prior + 1 new) ✓
              A2. /api/admin/sessions/{session_id}/resynthesize present ✓

            B. POST /api/assessment/processing/start 409 detail.reason:
              B0. Fresh session created (Grace Hopper, 203.0.113.50) ✓
              B1. session at stage=identity → 409 ✓
              B1.1. detail.reason == "stage_mismatch" ✓
              B1.2. detail.current_stage == "identity" ✓
              B2. After mutating scores.scenario off a fresh
                  stage=processing seed → 409 ✓
              B2.1. detail.reason == "missing_inputs" ✓
              B2.2. detail.missing == ["scenario"] (list) ✓
              (Restored doc post-test.)

            C. POST /api/admin/sessions/{id}/resynthesize:
              C1. No cookie → 401 ✓
              C2. Unknown UUID → 404 ✓
              C3. Session 12d0dd11-… (organic seed missing all 3 score
                  blocks) → 409 with detail.reason="missing_inputs",
                  detail.missing == ["psychometric","ai_fluency",
                  "scenario"] ✓
              C4 (Ada session 2253141a-…):
                C4.1. 202 status ✓
                C4.2. body.status == "in_progress" ✓
                C4.3. body.started_at present (ISO8601) ✓
                C4.4. body.poll_url == "/api/admin/sessions/{ada}" ✓
                C4.5. Endpoint returned in <0.01s — no blocking on the
                      worker spawn ✓
                C4.6. DB: deliverable cleared to None ✓
                C4.7. DB: synthesis.status == "in_progress" ✓
                C4.8. DB: synthesis.started_at present ✓
                C4.9. DB: synthesis.restarted_by == admin_email — FAIL,
                      see above ✗
                C4.10. DB: synthesis.restarted_at present ✓
                C4.11. DB: stage == "processing" ✓
                Also verified out-of-band via direct Mongo: synthesis
                completed cleanly ~137s later (claude-opus-4-6, fallbacks
                _tried=0); deliverable was rewritten with all 6 sections
                + 6 dimension_profiles. Self-healing path is intact.

            D. Regression spot-checks Phases 2-8:
              D1.   POST /api/sessions → 201 with valid resume_code
                    (5RFC-PK2E matches XXXX-XXXX) ✓
              D2.   PATCH /sessions/{id}/stage identity→context → 200 ✓
              D2.1. PATCH /sessions/{id}/stage context→psychometric
                    → 200 ✓
              D3.   GET /assessment/psychometric/next → 200 with item ✓
              D3.1. POST /assessment/psychometric/answer → 200 ✓
              D4.   GET /assessment/ai-discussion/state(Ada) → 200 ✓
              D5.   GET /assessment/scenario/state(Ada) → 200 ✓
              D6.   admin GET /admin/sessions/{Ada} → 200 with full
                    scores doc visible ✓
              D7.   PATCH {archived:true} → 200 ✓
              D7.1. PATCH {archived:false} → 200 ✓
              D8.   GET /admin/dashboard/summary → 200 ✓
              D9.   POST /admin/lifecycle/run → 200 ✓

            E. Privacy regression — public GET /api/sessions/{Ada}:
              E0. 200 ✓
              E1. admin_notes ABSENT ✓
              E1. last_admin_viewed_at ABSENT ✓
              E1. deleted_at ABSENT ✓
              E1. hard_delete_at ABSENT ✓
              E1. redacted ABSENT ✓
              E2. synthesis is dict ✓
              E2.1. synthesis keys == exactly {status, started_at,
                    completed_at} ✓
              E2.2. synthesis.provider, .model, .fallbacks_tried,
                    .error, .restarted_by, .restarted_at all ABSENT
                    from public surface ✓
              The Phase-8 D3 fix at server.py:371-396 still holds
              cleanly under the new Phase-9 fields (restarted_by /
              restarted_at). Public surface is locked down.

            F. Log hygiene during the resynth call window:
              F1. INFO marker "Admin re-synthesis triggered session=
                  2253141a-…" present ✓
              F2. Admin email substring present in log blob ✓
                  CAVEAT: the substring matched stale Phase-3 log lines
                  ("Admin settings updated by=steve@org-logic.io"). The
                  actual resynth log lines from THIS sweep read
                  "by=unknown_admin" — see C4.9 above.
              F3. Ada participant email "ada.test@example.co.uk" — ZERO
                  INFO/WARN/ERROR hits ✓
              F3. Ada participant organisation "Analytical Engine Co"
                  — ZERO INFO/WARN/ERROR hits ✓
              F4. No "sk-emergent-" fragments in logs ✓
              F4. No "sk-ant-" fragments in logs ✓
              F4. No "sk-proj-" fragments in logs ✓
              No full LLM prompts logged at INFO. PII surface clean
              apart from the audit-attribution gap in C4.9.

            HARNESS NOTES (test-side, not server-side):
              - Internal base http://localhost:8001/api per the brief.
              - Admin JWT cookie extracted from Set-Cookie and replayed
                via explicit Cookie header (Secure cookie can't replay
                over http://localhost via requests.Session).
              - Three fresh sessions consumed: one for B1
                stage_mismatch, one fresh phase-7 seed (mutated to
                strip scores.scenario for B2), one for D1 regression.
                None require cleanup — they remain in Mongo for any
                follow-up sweeps.
              - Ada session was left re-running synthesis at the end
                of the C4 sweep; it completed in ~137s out-of-band and
                Ada now has a fresh deliverable.

            STUCK-TASK ASSESSMENT: not stuck. This is the first review
            cycle for Phase 9; the bug is a one-line typo in the new
            endpoint and remediation is clear. stuck_count=1 reflects
            that one unresolved issue exists; recommend bumping back
            down to 0 once main agent applies the `email` → `sub` fix
            and the next sweep confirms restarted_by == admin email.

            Main agent: please apply the one-line fix at server.py:2134
            ((`current.get("email")` → `current.get("sub")`). Everything
            else in Phase 9 is green and the synthesis worker pipeline
            is solid.
        - working: "NA"
          agent: "main"
          comment: |
            Production incident root-caused: a real participant (Claire,
            resume Y87Y-U7DC) saw the Processing screen stuck because she
            had not finished the scenario — `/processing/start` returns 409
            in that case, but the FE was swallowing the error and spinning
            the loading animation forever. Synthesis itself was healthy.

            Hotfix bundle (5 patches, all applied as a single deploy):

            G1 — Frontend Processing.js escape panel (240s).
              Already applied to the frontend; backend changes here include
              the supporting 409 responses that the frontend keys off:
              POST /api/assessment/processing/start now returns
              detail.reason ∈ {"stage_mismatch", "missing_inputs"} so the
              FE can show the right copy.

            G2 — Frontend Scenario.js autosave reliability.
              Frontend-only change. Server-side /autosave is unchanged.

            G3 — Hard timeouts on every LLM call:
              - llm_router.PER_CALL_TIMEOUT_SEC = 90s. Every tier (1, 2, 3,
                AND the Emergent fallback) is now wrapped in
                asyncio.wait_for. asyncio.TimeoutError is categorised as
                "timeout" so the cascade can fall through cleanly.
              - synthesis_service.TOTAL_SYNTHESIS_BUDGET_SEC = 240s.
                run_synthesis() now wraps its two-call sequence in
                asyncio.wait_for; on TimeoutError it returns
                {ok:false, scoring_error:true, error:"timeout: ..."}
                so the worker writes synthesis.status="failed" cleanly.

            G4 — _run_synthesis_task `finally` guarantee.
              Re-reads synthesis.status from Mongo; if still "in_progress"
              (i.e. neither the happy nor the except branch wrote a
              terminal status — e.g. their own update_one raised) it
              forces status="failed" with error="internal_unhandled".
              The finally itself is wrapped in try/except so the cleanup
              can never propagate.

            G5 — Module-level _SYNTHESIS_TASKS registry.
              `_register_synthesis_task(coro)` adds the task to a module
              `set` and registers a done_callback that auto-discards it.
              Both /processing/start and /admin/sessions/{id}/resynthesize
              now use this helper. Verified by a unit test that the task is
              held while running and removed once done.

            G6 — Admin re-synthesize endpoint.
              POST /api/admin/sessions/{session_id}/resynthesize (admin
              JWT only). Pre-condition: scores.{psychometric, ai_fluency,
              scenario} all populated; otherwise 409 with
              detail.reason="missing_inputs" and detail.missing list.
              On success: clears deliverable, sets synthesis to {status:
              "in_progress", started_at, restarted_by:<admin_email>,
              restarted_at}, sets stage="processing", spawns the worker
              via _register_synthesis_task. Returns 202 with poll_url.

            G7 — SYNTHESIS_STUCK_AFTER_SEC bumped from 120s to 240s
              (matches the new total budget; aligns with the FE
              escape-panel timer).

            Unit tests added (5 new in tests/test_phase9_hotfix.py):
              - run_synthesis returns scoring_error=true when the LLM call
                exceeds the outer budget (tested with a 50ms budget +
                2s sleep)
              - llm_router.chat times out a single tier and falls through
                to the next
              - llm_router.chat raises LLMRouterError when every tier
                times out (categories all "timeout")
              - _run_synthesis_task `finally` forces "failed" when the
                main body and except branch both fail to write
              - _SYNTHESIS_TASKS holds a task during execution and
                discards it on completion via done_callback

            Total backend tests now: 114/114 green (109 prior + 5 new).
            OpenAPI: 36 /api/* paths (35 prior + 1 new resynthesize).
            /api/health 200 OK, both services running clean.

            Awaiting deep_testing_backend_v2 sweep covering:
              - The new admin /resynthesize endpoint (success, missing_inputs
                409, non-admin 401, 404 unknown session)
              - /processing/start now carries detail.reason on 409 errors
              - Regression: every Phases 2–8 endpoint still responds
              - /api/openapi.json count = 36

  - task: "Admin dashboard + lifecycle + exports (Phase 8)"
    implemented: true
    working: true
    file: "backend/server.py, backend/services/lifecycle_service.py, backend/services/dashboard_summary.py, backend/services/conversation_export.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: |
            D3 re-verification PASS (2026-04-23, post-fix). Ran /app/d3_retest.py
            against https://farm-readiness.preview.emergentagent.com/api. The
            surgical fix in get_session (server.py:371-396) correctly pops
            admin_notes, last_admin_viewed_at, deleted_at, hard_delete_at,
            redacted, and reduces synthesis to exactly {status, started_at,
            completed_at}.

            Evidence on Ada session 2253141a-830f-4810-a683-890f098b5664:

              1. PATCH /api/admin/sessions/{id} {notes:"private admin note
                 (D3 re-verify)"} -> 200; admin response body carries
                 admin_notes == that exact string. ✓

              2. Public GET /api/sessions/{id} (no cookie) -> 200.
                 - admin_notes              : ABSENT ✓
                 - last_admin_viewed_at     : ABSENT ✓
                 - deleted_at               : ABSENT ✓
                 - hard_delete_at           : ABSENT ✓
                 - redacted                 : ABSENT ✓
                 - scores                   : null  ✓
                 - deliverable              : null  ✓
                 - synthesis keys           : exactly
                   {'completed_at','started_at','status'} ✓
                 - synthesis.provider       : ABSENT ✓
                 - synthesis.model          : ABSENT ✓
                 - synthesis.fallbacks_tried: ABSENT ✓
                 - synthesis.error          : ABSENT ✓
                 Public top-level keys now = [ai_discussion, answers, archived,
                 completed_at, consent, conversation, created_at, deliverable,
                 expires_at, participant, psychometric, resume_code, scenario,
                 scenario_responses, scores, session_id, stage, status,
                 synthesis, updated_at]. No admin-only surface leaks.

              3. Admin GET /api/admin/sessions/{id} (with tra_admin_token
                 cookie) -> 200. Still exposes:
                 - admin_notes              : "private admin note (D3 re-verify)" ✓
                 - last_admin_viewed_at     : "2026-04-23T19:13:18.015680+00:00" ✓
                 - hard_delete_at           : null (Ada never soft-deleted; key
                                              present) ✓
                 - synthesis.provider       : present ✓
                 - synthesis.model          : present ✓
                 - synthesis.fallbacks_tried: present ✓
                 - synthesis.error          : present (null) ✓
                 NOTE: `deleted_at` and `redacted` are absent from the raw
                 Mongo doc because Ada was never soft-deleted — admin_get_session
                 (server.py:1903-1915) is a pass-through of whatever is in
                 Mongo, so those optional fields only appear post-delete. This
                 is expected Phase-8 behaviour and was already documented in
                 the prior Phase-8 sweep (E2/E3). Admin surface is unchanged
                 by the fix — the fix touched ONLY the public handler.

              4. D1/D2 archive-toggle regression — GREEN.
                 - PATCH {archived:true}  -> archived=True, expires_at=None,
                   hard_delete_at=None. ✓
                 - PATCH {archived:false} -> archived=False, expires_at
                   restored to "2026-06-22T18:02:27.176397+00:00" =
                   completed_at + 60d exactly (delta=60.0 days). ✓

            Test cleanup: admin_notes was cleared back to empty string after
            the sweep. No code changes made during testing.

            All other Phase-8 behaviour (A, B1-B8, C1-C2, D1-D2, D4, E1-E5,
            F1-F2, G1, H1-H5, I1-I4, J1-J3, K1-K6, L1-L7, M, N) remains as
            verified in the prior sweep. Marking Phase 8 as working=true,
            needs_retesting=false.
        - working: false
          agent: "testing"
          comment: |
            Phase 8 backend sweep complete. Ran /app/backend_test.py against
            https://farm-readiness.preview.emergentagent.com/api (REACT_APP_BACKEND_URL).
            48/49 assertions PASS. ONE failure (D3) — a privacy regression on
            the PUBLIC participant-safe GET /api/sessions/{id} endpoint that
            now leaks admin-only fields added in Phase 8. Details below.

            ============  FAILURE  ============
            D3. PATCH {notes:"Phase 8 testing admin note"} persists as
                admin_notes (confirmed in admin GET response). HOWEVER the
                PUBLIC endpoint GET /api/sessions/{id} ALSO returns the
                admin_notes field verbatim. The public SessionOut model is
                declared with `model_config = ConfigDict(extra="allow")` at
                server.py:214 and the handler at server.py:371-379 only
                nulls `scores`, `deliverable`, and strips assistant-turn
                internals from `conversation` — it does NOT pop the Phase-8
                admin-only fields. Confirmed via curl:
                  GET /api/sessions/2253141a-…
                    → {"admin_notes":"Phase 8 testing admin note",
                        "last_admin_viewed_at":"2026-04-23T…",
                        "synthesis":{"provider":"emergent","model":
                          "claude-opus-4-6","fallbacks_tried":0,…},
                        "hard_delete_at":null, "deleted_at":null,
                        "redacted":null, …}
                Critical leak is `admin_notes` — the spec explicitly says
                "notes field must never appear on public GET /api/sessions/
                {id}". Also leaking `last_admin_viewed_at` and the
                `synthesis` sub-doc (provider/model/fallbacks_tried). These
                are Phase 8 additions that slipped past the public filter.
                Phase-5 J fix on _public_conversation still holds for the
                conversation[] array, but the top-level synthesis doc is a
                separate pass-through.
                REMEDIATION: in the public get_session handler, pop
                admin_notes, last_admin_viewed_at, synthesis, deleted_at,
                hard_delete_at, redacted before returning. (Keeping redacted
                false-ish is fine but admin_notes / last_admin_viewed_at /
                synthesis internals must go.)

            ============  PASSED  ============
            A. Auth gating. All 9 new admin endpoints return 401 without a
               tra_admin_token cookie (GET/POST/PATCH/DELETE variants
               covered). ✓
            B. /admin/sessions list + search + filter + pagination + sort:
               B1. Baseline returns {items, total, page, page_size,
                   filters_applied}. ✓
               B2. q=Ada → 5 items, Ada session found, filters_applied.q
                   reflects the param. ✓
               B3. page_size=1 pagination advances: page=1 and page=2 each
                   return a single different row (total=152). ✓
               B4. status=completed → 4/4 items all have status==completed. ✓
               B5. archived=only (0 items, all archived-true) and
                   archived=exclude (25 items, all archived-false) both
                   honoured. ✓
               B6. sort=created_at ascending order verified; sort=-created_at
                   descending order verified. ✓
               B7. filters_applied shape correctly reflects ALL params
                   (q, status, archived, include_deleted, date_from,
                   date_to, sort). ✓
               B8. include_deleted=false → every row has deleted_at==null. ✓
            C. GET /admin/sessions/{id} stamps last_admin_viewed_at:
               C1. Two back-to-back calls produce distinct, increasing
                   timestamps (t1 < t2, 1.2s apart). ✓
               C2. Unknown session → 404. ✓
            D. PATCH archive + notes semantics:
               D1. {archived:true} on Ada → archived:true, expires_at:null,
                   hard_delete_at:null. ✓
               D2. {archived:false} → expires_at restored to
                   completed_at + exactly 60 days. ✓
               D3. **FAILED — see above.** PATCH {notes:"…"} correctly
                   writes admin_notes on the server, but the field LEAKS to
                   the public GET /api/sessions/{id}. ✗
               D4. PATCH {notes:"x"*2001} → 422 (Pydantic validator
                   enforces ≤2000 chars). ✓
            E. Admin DELETE → soft delete on a fresh seeded session (given
               completed_at + expires_at via Mongo so it looked like a
               completed doc):
               E1. DELETE → 200 {"ok":true, "soft_deleted":true,
                   "deleted_at":…, "hard_delete_at":…}. ✓
               E2. participant.name == "(redacted)", email/org/role all
                   null. ✓
               E3. redacted=true, deleted_at + hard_delete_at both set. ✓
               E4. hard_delete_at - deleted_at == exactly 30 days. ✓
               E5. scores, deliverable, conversation all preserved
                   byte-for-byte; scenario.part1_response and
                   scenario.part2_response also preserved. ✓
            F. Restore inside the 30-day grace window:
               F1. POST /restore → 200 {ok:true, restored:true,
                   pii_recoverable:false}. ✓
               F2. deleted_at and hard_delete_at cleared; participant.name
                   stays "(redacted)". ✓
            G. Restore past grace:
               G1. Second seeded session: admin-delete then mutate
                   hard_delete_at to -1 day in Mongo. POST /restore → 409
                   "Restore window has passed." ✓
            H. Full lifecycle cron cycle:
               H1. Third seeded session: mutate expires_at = now-1min,
                   completed_at = now-61d. POST /admin/lifecycle/run →
                   {skipped:false, soft_deleted:1, hard_deleted:1,
                   errors:0}. Incidentally caught the stale leftover from
                   block G (hard-delete count:1). ✓
               H2. After that run the fresh session is redacted and has
                   deleted_at set. ✓
               H3. Mutate hard_delete_at into the past → POST again →
                   {hard_deleted:1}. ✓
               H4. Follow-up admin GET → 404. ✓
               H5. Back-to-back POSTs to /admin/lifecycle/run both return
                   skipped:false. Documented behaviour — the manual
                   endpoint passes force=True to bypass the 5-minute
                   guard. This is the intended operator experience (a
                   manual click should always run). The 5-minute guard is
                   still exercised by the APScheduler _lifecycle_cron_tick.
                   ✓
            I. Conversation downloads:
               I1. format=markdown on Ada → Content-Type
                   "text/markdown; charset=utf-8", Content-Disposition
                   filename="TRA-conversation-Ada-Lovelace-2026-04-23.md",
                   body contains "Interviewer", "Participant", and the
                   session_id. ✓
               I2. format=json on Ada → Content-Type "application/json",
                   filename TRA-conversation-Ada-Lovelace-2026-04-23.json,
                   body parses to {session_id, conversation:[15 turns],
                   scoring, …}. ✓
               I3. Fresh seeded session, admin-delete, then download
                   markdown: filename uses "session-{first_8_of_sid}"
                   label, body contains ZERO hits of the seed email
                   (ada.test@example.co.uk) or organisation (Analytical
                   Engine Co). ✓
               I4. Same redacted session via format=json: participant_label
                   starts with "(redacted)", body contains zero hits of
                   email/org. ✓
            J. Deliverable admin downloads:
               J1. format=pdf on Ada → 200, Content-Type "application/pdf",
                   body begins b"%PDF-". ✓
               J2. format=markdown → 200, Content-Type text/markdown,
                   body starts "# Transformation Readiness Assessment". ✓
               J3. After PATCHing Ada to archived=true → PDF download
                   STILL works (starts %PDF-). Archive=false restored. ✓
            K. Dashboard summary:
               K1. Top-level keys present: totals, completed_this_week,
                   completed_last_week, avg_completion_duration_seconds,
                   score_distribution, dimension_averages, activity_14d,
                   generated_at. ✓
               K2. totals has total_sessions=154, in_progress=3,
                   completed=5, failed=2, archived=0, soft_deleted=1,
                   expiring_soon=0 — all seven keys present. ✓
               K3. dimension_averages length == 6. ✓
               K4. activity_14d length == 14. ✓
               K5. score_distribution carries navy/gold/terracotta
                   (plus unknown bucket). {navy:0, gold:2, terracotta:0,
                   unknown:0}. ✓
               K6. Two calls 1s apart return identical generated_at →
                   60s cache hit confirmed. ✓
            L. Regression — Phases 2-7:
               L1. POST /api/sessions (fresh X-Forwarded-For) → 201 with
                   session_id + resume_code. ✓
               L2. GET /assessment/psychometric/next → 200 with item. ✓
               L3. POST /assessment/psychometric/answer → 200. ✓
               L4. POST /assessment/ai-discussion/start on an
                   identity-stage session → 409. ✓
               L5. GET /assessment/scenario/state(Ada) → 200. ✓
               L6. GET /assessment/processing/state(Ada) → 200 with
                   status:"completed". ✓
               L7. GET /assessment/results(Ada) → 200 with status:"ok". ✓
            M. /api/openapi.json enumerates exactly 35 /api/* paths
               (29 prior + 6 Phase 8 new). ✓
            N. Log hygiene: grep over /var/log/supervisor/backend.{out,err}.log
               for "ada.test@example.co.uk", "Analytical Engine Co",
               "Chief Mathematician" — ZERO INFO-level hits, even after
               executing soft-delete and hard-delete events. Soft-delete
               logs only the session_id (lifecycle_service.py:80 confirms:
               `"Soft-deleted session %s (hard_delete_at=%s)"`). ✓

            NOTES / OBSERVATIONS (non-blocking):
              (i)  The public GET /api/sessions/{id} SessionOut model uses
                   ConfigDict(extra="allow"). That pattern was fine in
                   Phases 2-7 because the only admin-internal fields then
                   were `scores` and `deliverable`, which the handler
                   explicitly nulls. Phase 8 added admin_notes,
                   last_admin_viewed_at, and the synthesis sub-doc as new
                   fields without adding them to the participant-safe
                   filter. The fix is a ~6-line handler update, not a
                   model redesign.
              (ii) Public GET also exposes `synthesis.provider` /
                   `synthesis.model` / `synthesis.fallbacks_tried` for
                   completed sessions. Phase 5 J fix only strips those from
                   conversation[] assistant turns — the top-level
                   synthesis doc is a separate object. Consider whether
                   this is acceptable (probably not for a participant).
              (iii) hard_delete_at / deleted_at / redacted also pass through
                    to the public endpoint. Not personal data, but telegraphs
                    lifecycle state to participants. Worth tightening.

            Test-side cleanup: removed test admin_notes +
            last_admin_viewed_at from the Ada session after the sweep.
            Fresh seeded sessions used for E/F/G/H are now hard-deleted or
            marked redacted (as designed). No code changes were made during
            testing. Main agent should address D3/remediation only; all
            other Phase 8 behaviour is green.
        - working: "NA"
          agent: "main"
          comment: |
            Phase 8 implementation complete, live smoke-tested end-to-end incl.
            a forced full lifecycle cycle (soft-delete -> restore -> hard-delete).
            Ready for deep_testing_backend_v2 sweep.

            New services:
              - services/lifecycle_service.py — two-stage retention. run_cleanup_cycle
                finds non-archived, non-deleted sessions with expires_at <= now and
                soft-deletes them (scrubs participant PII, sets deleted_at + redacted
                + hard_delete_at=+30d; preserves scores, conversation, scenario
                responses, deliverable). Then finds any doc with hard_delete_at <=
                now and removes it. Per-session try/except so one bad doc cannot
                halt the sweep. 5-minute min-run-interval guard avoids back-to-back
                runs from cron + manual trigger. Archive=true clears expires_at ->
                protected from both stages. restore_session() unwinds deleted_at +
                hard_delete_at within the 30-day grace, flags pii_recoverable=false.
              - services/conversation_export.py — Markdown and JSON exporters.
                Markdown has H1 title + Participant/Interviewer H2 per turn +
                timestamp + admin-only provider/model/latency trailer on assistant
                turns + scoring summary footer. Redacted sessions render as
                "(redacted) session {first_8}" with no email or organisation leaked.
                Filename sanitiser: TRA-conversation-{label}-{YYYY-MM-DD}.{md|json}.
              - services/dashboard_summary.py — aggregate metrics producer with a
                60-second in-memory cache (double-checked locking). Totals:
                {total_sessions, in_progress, completed, failed, archived,
                soft_deleted, expiring_soon (within 7d & not archived)}. Weekly
                deltas completed_this_week / completed_last_week. Avg completion
                duration (last 30d). Score distribution by band colour from each
                deliverable.executive_summary.overall_colour. Dimension averages
                per assessed dim over last 30d. 14-day activity (new_sessions +
                completions per UTC day). Cache invalidated on any admin write
                (patch, delete, restore, lifecycle run).

            New endpoints (all admin JWT-gated):
              GET  /api/admin/sessions?q=&status=&include_deleted=&archived=&date_from=&date_to=&page=&page_size=&sort=
                   Returns {items, total, page, page_size, filters_applied}.
                   Each row: session_id, participant, stage, status, dates,
                   archived, deleted_at, hard_delete_at, redacted,
                   overall_category, overall_colour, synthesis_status,
                   has_scoring_error, duration_seconds. Case-insensitive regex
                   search over name/email/organisation/session_id. Status is
                   comma-separated whitelist. Sort whitelist enforced.
              GET  /api/admin/sessions/{id}
                   Full doc + stamps last_admin_viewed_at on each call.
              PATCH /api/admin/sessions/{id}
                   Body {archived?: bool, notes?: string (<=2000)}. Archive=true
                   clears expires_at + hard_delete_at; archive=false restores
                   expires_at to completed_at+60d when completed_at present.
                   admin_notes is the private field.
              DELETE /api/admin/sessions/{id}
                   Admin-initiated immediate soft-delete (PII scrub, 30d grace).
              POST /api/admin/sessions/{id}/restore
                   409 if not soft-deleted or past hard_delete_at; 200 with
                   pii_recoverable:false flag on success.
              GET  /api/admin/sessions/{id}/conversation/download?format=markdown|json
                   Streams text/markdown or application/json body with sanitised
                   Content-Disposition filename. Works on redacted sessions
                   (admin exports are allowed post-redaction) with
                   "(redacted)" label instead of the participant's real name.
              GET  /api/admin/sessions/{id}/deliverable/download?format=pdf|markdown
                   Thin wrapper around the Phase 7 renderer; works even if the
                   session is archived.
              GET  /api/admin/dashboard/summary
                   Single-call aggregate for the Overview dashboard.
              POST /api/admin/lifecycle/run
                   On-demand trigger for the cleanup cycle (force=True bypasses
                   the 5-minute guard). Returns {soft_deleted, hard_deleted,
                   errors, scanned_at}.

            Mongo changes:
              - New fields on `sessions`: deleted_at, hard_delete_at, redacted,
                last_admin_viewed_at, admin_notes.
              - New indexes (created at startup):
                  {archived, expires_at}        archived_expires
                  {hard_delete_at}              hard_delete_at
                  {status, created_at}          status_created
                  {participant.email} (sparse)  participant_email

            APScheduler:
              - AsyncIOScheduler started on app startup, tz=UTC, runs
                _lifecycle_cron_tick every 6 hours; first tick 5 minutes after
                startup. Shuts down cleanly on app shutdown. Tick wraps the
                cycle in try/except; per-cycle errors logged and swallowed so
                the scheduler stays alive.

            Live smoke evidence (one forced full cycle):
              - Seeded fresh session, mutated expires_at into the past.
              - POST /admin/lifecycle/run -> {soft_deleted:1, hard_deleted:0}.
              - Admin GET shows redacted=true, deleted_at + hard_delete_at set,
                participant.name=="(redacted)", participant.email==null,
                scores still intact.
              - POST /admin/sessions/{id}/restore -> {ok:true, restored:true,
                pii_recoverable:false}. deleted_at/hard_delete_at cleared;
                participant.name stays "(redacted)".
              - Mutated hard_delete_at into the past, re-ran lifecycle ->
                {hard_deleted:1}. Follow-up GET -> 404.

            Unit tests: 12 new in tests/test_phase8_services.py covering:
              - soft-delete of expired non-archived doc
              - archive protection
              - hard-delete after window
              - admin soft-delete + restore within grace; PII not recoverable
              - restore 409 past hard_delete_at
              - 5-minute run guard
              - per-session error isolation
              - Markdown export contains both roles + meta trailer + scoring
                summary; redacted version hides PII
              - JSON export round-trip
              - filename sanitisation for both named and redacted sessions
              - dashboard_summary tiles on a canned 9-session dataset (totals,
                score_distribution, dim_averages length=6, activity_14d length=14)
            All 109 tests green (60 prior + 37 Phase 7 + 12 Phase 8).

            Frontend (polished executive grade):
              - /admin layout: navy header bar with gold accent, left nav
                (Overview / Sessions / Settings) with active gold left bar,
                responsive collapse to hamburger on mobile.
              - /admin (Overview): 4 stat tiles (Total sessions w/ 14-day
                sparkline, Completed this week w/ weekly delta arrow, Avg
                completion time, Expiring within 7 days), score distribution
                donut, dimension averages bars, 14-day activity chart, recent
                sessions table. All charts are hand-rolled inline SVG (no CDN).
              - /admin/sessions: search (debounced 300ms), status multi-select,
                archived toggle, include-deleted toggle, sort dropdown,
                pagination (25/page default). Row actions menu (View, Archive,
                Soft delete, Restore) with confirmation.
              - /admin/sessions/{id}: navy ribbon with participant / session_id
                (copy) / status pills / action rail (PDF, MD, Convo MD, Convo
                JSON, Archive toggle, Soft delete/Restore) + lifecycle strip
                (Created/Started/Completed/Expires). Seven tabs:
                  Overview: exec summary prose + dimension RADAR chart +
                    self-awareness calibration bar.
                  Psychometric: LA + TA score cards with subscale bars; full
                    20-item response table with position or response-time sort.
                  AI Discussion: rendered conversation with admin-only
                    provider/model/latency/fallbacks trailer; expandable raw
                    scores.ai_fluency JSON.
                  Scenario: Part 1 / Part 2 q1/q2/q3 side-by-side; CF + ST
                    score cards with evidence objects (connections identified
                    vs missed as two columns, key_quote in italic).
                  Deliverable: full 6-section inline render of
                    session.deliverable with navy/gold/terracotta chips.
                  Timeline: merged event timeline (session events + psychometric
                    answers + conversation turns + scenario transitions +
                    synthesis start/complete + soft-delete event + last admin
                    view) sorted chronologically.
                  Notes: auto-save (1s debounce) with character counter (0/2000).
              - /admin/settings: existing LLM key UI preserved; new Lifecycle
                panel below with the 60/90 day policy copy + "Run cleanup now"
                button that posts to /admin/lifecycle/run and shows a result
                pill.

  - task: "Processing + Results + Synthesis (Phase 7)"
    implemented: true
    working: true
    file: "backend/server.py, backend/services/synthesis_service.py, backend/services/dimensions_catalogue.py, backend/services/results_render.py, backend/templates/results.{html,md}.j2"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: |
            Phase 7 backend sweep complete. Ran /app/backend_test_phase7.py against
            http://localhost:8001/api. 24/24 scripted assertions passed (letters
            A, B1-B2, C1, D1, F1, G1-G2, H1-H5, I1-I2, J1-J2, K1-K6, L); PLUS a
            full live synthesis run was verified end-to-end against a fresh seeded
            session f9959971-5ee8-4f9f-83e6-f59ea747d9e0 (letters E1-E8 below).
            No 500s. No secret leaks. No regressions.

              A. OpenAPI /api/openapi.json enumerates exactly 29 /api/* paths. All
                 four new paths present: /api/assessment/processing/{start,state},
                 /api/assessment/results, /api/assessment/results/download.
              B. POST /assessment/processing/start:
                 B1. Unknown session_id -> 404 {"detail":"Session not found."} ✓
                 B2. Already-completed Ada session -> 200 with
                     {status:"completed", started_at, completed_at, poll_url} and
                     NO re-run of synthesis. ✓
              C. Stage gate:
                 C1. session at stage=identity -> 409 with detail
                     {message:"Synthesis cannot start yet. Complete the scenario
                     first.", current_stage:"identity"}. ✓
              D. Missing score blocks gate:
                 D1. Seeded fresh session, then mutated scores.psychometric=null
                     directly in Mongo while keeping stage='processing'. POST /start
                     -> 409 with detail {message:"Synthesis cannot run: missing score
                     blocks.", missing:["psychometric"]}. ✓
              E. LIVE end-to-end synthesis on fresh seed (ONE fresh session
                 consumed, as budgeted):
                 Fresh session: f9959971-5ee8-4f9f-83e6-f59ea747d9e0
                 E1. POST /start -> 202 {status:"in_progress", started_at, poll_url}. ✓
                 E2. Idempotency check partial — second /start within the in-progress
                     window was held up client-side due to LiteLLM blocking the event
                     loop during the active synthesis call (ReadTimeout at 60s).
                     Server-side behaviour verified via code review (server.py:1356-1365
                     — status=="in_progress" + not stuck returns the persisted
                     started_at without spawning a new task). Not counted as a
                     failure; real browsers will not hit this because /start calls
                     don't happen while polling. [Minor — infra note below.]
                 E3. Polled /state — synthesis completed in ~136 s total. Two Emergent
                     calls via Claude Opus 4.6. NOTE: the FIRST synthesis attempt
                     failed with part_a:"no JSON block" after both internal
                     _one_call retries exhausted (both raw outputs unparseable),
                     worker correctly wrote synthesis.status="failed" +
                     deliverable.scoring_error=true. A subsequent /start (triggered
                     by the retry branch at server.py:1367) re-ran synthesis and it
                     succeeded cleanly. This is the documented self-healing behaviour
                     — the outer restart path works as designed. [Worth flagging to
                     main agent as an operational sensitivity — see note at bottom.]
                 E4. After completion, subsequent /start -> 200 with
                     {status:"completed", completed_at, poll_url}, no re-run. ✓
                 E5. /state shape is {status, started_at, completed_at, error} only.
                     NO deliverable body. ✓
                 E6. /results schema conformance on fresh session:
                      - status="ok", participant.first_name="Ada"
                      - executive_summary has all expected keys (overall_category,
                        overall_colour, prose, key_strengths, development_priorities,
                        bottom_line) + extras category_statement/overall_language.
                        overall_colour="gold" ∈ {navy,gold,terracotta}. ✓
                      - dimension_profiles has exactly 6 entries covering all six
                        expected ids: learning_agility, tolerance_for_ambiguity,
                        cognitive_flexibility, self_awareness_accuracy, ai_fluency,
                        systems_thinking. Every profile carries band.colour ∈
                        {navy,gold,terracotta} (all "gold" on this run). ✓
                      - integration_analysis present ✓
                      - ai_fluency_deep_dive.components_table has exactly 5 rows ✓
                      - development_recommendations has exactly 2 entries ✓
                      - methodology_note present ✓
                      - dimensions.assessed len=6, dimensions.not_assessed len=10 ✓
                 E7. Admin synthesis meta: {provider:"emergent",
                     model:"claude-opus-4-6", fallbacks_tried:0, status:"completed"}.
                     Matches admin_settings.fallback_model. ✓
                 E8. Session terminal state: stage="results", status="completed",
                     completed_at and expires_at populated. expires_at - completed_at
                     = exactly 60 days (Phase 8 cleanup input ready). ✓
              F. /results on the pre-seeded Ada Lovelace session
                 (2253141a-830f-4810-a683-890f098b5664):
                 F1. All schema conformance checks pass (same as E6) — dp_ids
                     covers all 6 expected, cmp_rows=5, es.overall_colour="gold",
                     self_awareness.band="Well-calibrated" / delta=0.2 /
                     direction="over_claiming" (observed=4.0, claimed=4.2,
                     blind_spots_count=2), devrecs=2. ✓
              G. /results gating:
                 G1. Unknown session -> 404. ✓
                 G2. Fresh identity-stage session (no synthesis) -> 409 with detail
                     {message:"Synthesis not yet complete.", synthesis_status:null}. ✓
              H. /results/download:
                 H1. PDF: HTTP 200, Content-Type "application/pdf", Content-Disposition
                     'attachment; filename="TRA-Ada-2026-04-23.pdf"', body begins
                     with b"%PDF-" (exact %PDF-1.7 confirmed, 58 KB). ✓
                 H2. Markdown: HTTP 200, Content-Type "text/markdown; charset=utf-8",
                     Content-Disposition 'attachment; filename="TRA-Ada-2026-04-23.md"',
                     body begins with "# Transformation Readiness Assessment". ✓
                 H3. Markdown body contains all 10 not-assessed dimension names
                     (Hybrid Workforce Capability, Generational Intelligence,
                     Political Acumen, Stakeholder Orchestration, Cultural
                     Adaptability, Long-Term Orientation, Change Leadership,
                     Institutional Building, Governance Capability, Results Under
                     Ambiguity) and the heading "Not assessed in this preview". ✓
                 H4. Invalid format value (format=html) -> 422. ✓
                 H5. Unknown session -> 404. ✓
              I. Graceful scoring_error path (Doc 22 + Doc 23 failure behaviour):
                 Mutated a fresh session's deliverable to
                 {scoring_error:true, _error:"test injected error", _raw:"oops"}
                 and synthesis.status="completed", stage="results".
                 I1. GET /results -> 200 with {status:"error", scoring_error:true,
                     participant.first_name:"Ada", message:"The synthesis could not
                     be produced..."} — NOT 500. ✓
                 I2. GET /results/download?format=pdf -> 409, NOT 500. ✓
              J. Privacy / Doc 22 + Doc 12 compliance:
                 J1. Public GET /api/sessions/{Ada session} — scores:null,
                     deliverable:null, conversation[] assistant turns contain zero
                     hits of provider / model / latency_ms / fallbacks_tried keys
                     (Phase 5 J fix still in effect: _public_conversation strips
                     those fields). ✓
                 J2. Admin GET /api/admin/sessions/{Ada session} with JWT cookie
                     exposes the full scores + deliverable payload. ✓
              K. Regression — Phases 2-6:
                 K1. POST /api/sessions -> 201 ✓
                 K2. Admin login + GET /admin/settings -> 200, fallback_model
                     "claude-opus-4-6" ✓
                 K3. GET /assessment/psychometric/next -> 200, POST /answer -> 200 ✓
                 K4. POST /assessment/ai-discussion/start while
                     stage=psychometric -> 409 (gate still enforced) ✓
                 K5. GET /assessment/scenario/state on pre-unlock session ->
                     200 {status:null, phase:null} ✓
                 K6. POST /assessment/scenario/advance on a completed Ada
                     session -> 409 (phase mismatch / already-done gate) ✓
              L. Log hygiene: scanned /var/log/supervisor/backend*.log for
                 INFO-level hits of admin password "test1234", API key prefixes
                 (sk-ant-, sk-emergent-, sk-proj-), participant email
                 (ada.test@example.co.uk), conversation content needles
                 ("smart intern", "over-indexed on financial stability"), and
                 deliverable internals ("executive_summary"). Zero hits at
                 INFO level. ✓

            OPERATIONAL NOTES for main agent (not blockers, but worth knowing):

              (i) LiteLLM blocks event loop during synthesis. While the fire-
                  and-forget worker is calling Claude Opus 4.6 via Emergent,
                  the entire uvicorn event loop is blocked — including simple
                  /api/health reads. This caused the test-harness idempotency
                  check on /start to ReadTimeout at the client side (60 s),
                  though the server did serve that request correctly once the
                  active LLM call returned. Production UX: the browser poll on
                  /state will similarly stall for up to ~60 s per LLM call.
                  Not a Phase 7 bug — it's an emergentintegrations/LiteLLM
                  transport characteristic. Consider documenting or running the
                  worker in a dedicated executor if user-facing polling latency
                  matters.

              (ii) First-attempt synthesis flake observed on one fresh run:
                   part_a failed with "no JSON block" after both internal
                   _one_call retries (2 attempts exhausted), worker correctly
                   wrote synthesis.status="failed" +
                   deliverable.scoring_error=true. The outer re-entry via a
                   subsequent /start call (server.py:1367) restarted synthesis
                   and it succeeded on the next run. The self-healing path is
                   robust, BUT in production a participant whose first
                   synthesis fails will see a "failed" state until their
                   browser re-hits /start. Worth surfacing a retry affordance
                   on /processing or auto-retrying once server-side after a
                   short backoff.

            Harness notes (test-side, not server-side):
              - Fresh X-Forwarded-For per session creation to sidestep 10/hr
                POST /sessions per-IP rate limit across the sweep.
              - Admin JWT cookie extracted from Set-Cookie (cookie name
                "tra_admin_token") and replayed via explicit Cookie header —
                Secure cookie can't replay over http://localhost via
                requests.Session.
              - One fresh seed consumed (f9959971); Ada session re-used for
                everything else per main-agent guidance.

            No code changes were made during testing. Phase 7 backend passes.
            Main agent can summarise and close Phase 7.

        - working: "NA"
          agent: "main"
          comment: |
            Phase 7 implementation complete, live smoke-tested once end-to-end.
            Ready for deep_testing_backend_v2 sweep.

            New services:
              - services/dimensions_catalogue.py — 16-dimension catalogue hardcoded
                from Doc 12 (8+8+7+7 / 7+6+6+6 / 7+6+6+6 / 5+5+5+5 = 100%).
                Asserts at import: 16 items, 6 assessed, 10 not assessed, weights
                ≈ 100, and the six assessed ids match Doc 19. Doc 12 presence on
                disk is also asserted.
              - services/synthesis_service.py — loads `/app/research/23 - Synthesis
                Prompt.md` at import. Extracts the verbatim SYSTEM_PROMPT from the
                first fenced block under "## System Prompt" (1328 chars). Exposes
                Doc 23 CATEGORY_THRESHOLDS (4 tiers — Transformation Ready ≥4.2
                / High Potential 3.5-4.19 / Development Required 2.8-3.49 /
                Limited Readiness <2.8) mapped to 3 palette colours (navy / gold /
                terracotta / terracotta). compute_self_awareness_accuracy() uses
                observed = 0.5·capability_understanding + 0.5·clip(5 - 0.5·blind_spots,
                1, 5); bands Well/Slightly/Significantly miscalibrated at |Δ|<0.5,
                ≤1.0, >1.0; direction = over_claiming / aligned / under_claiming.
              - services/results_render.py — Jinja2 renderer for both PDF (WeasyPrint
                from results.html.j2) and Markdown (results.md.j2). Sanitised
                filename TRA-{first_name}-{YYYY-MM-DD}.{ext}. Templates are shared-
                context so both formats render identical content.
              - templates/results.html.j2 + templates/results.md.j2 — 9 report
                sections (cover, exec summary, dimension profile, self-awareness,
                AI fluency deep dive, strategic decision profile, development recs,
                integration analysis, methodology + not-assessed). A4 print CSS on
                the HTML template; page-break rules on section boundaries. Chips
                carry text label alongside colour (a11y). The 10 not-assessed
                dimensions render as a two-column list from Doc 12.

            Architectural decision (fixes observed Emergent-proxy constraint):
              - The Emergent/Claude Opus 4.6 path reliably generates up to ~2500
                output tokens before truncating/timing out (confirmed via probes).
                A one-shot synthesis of the full 6-section deliverable needs
                ~3500+ tokens → fails. So run_synthesis() now makes TWO focused
                LLM calls through the same 3-tier router cascade:
                  Call A (max_tokens=2000): executive_summary, integration_analysis,
                    ai_fluency_deep_dive (narrative only), development_recommendations,
                    methodology_note.
                  Call B (max_tokens=2500): dimension_profiles (6 items) +
                    ai_fluency_deep_dive.components_table (5 rows).
                Both halves parsed with the strict JSON extractor + validator
                (one retry each on malformed output). Merged in Python, validated
                against the full schema, annotated with band colours, persisted to
                session.deliverable. On any unrecoverable failure the scoring_error
                path writes {scoring_error:true,_error,_raw} and the /results
                endpoint returns a graceful error JSON (no 500).

            New endpoints (/api/assessment/**, no admin auth):
              - POST /processing/start   — gates on stage in {processing, results};
                                           gates on scores.{psychometric, ai_fluency,
                                           scenario} all present; idempotent when
                                           in_progress + fresh (≤120s); otherwise
                                           restarts. Returns 202 + poll_url. Kicks
                                           off a fire-and-forget asyncio.create_task.
              - GET  /processing/state   — {status, started_at, completed_at, error}.
                                           No deliverable body.
              - GET  /assessment/results — gated by synthesis.status=="completed".
                                           Returns participant-safe deliverable,
                                           self_awareness, strategic_scenario_scores,
                                           dimensions.{assessed,not_assessed}, and
                                           participant first_name/organisation/role.
                                           scoring_error path returns 200 with a
                                           graceful apology shape.
              - GET  /assessment/results/download?format=pdf|markdown — streams
                                           FAResponse with correct Content-Type and
                                           Content-Disposition filename.

            Session lifecycle on synthesis success:
              - deliverable = annotated payload
              - synthesis = {status:"completed", started_at, completed_at, provider,
                             model, fallbacks_tried}
              - stage = "results"
              - status = "completed"
              - completed_at = now()
              - expires_at = completed_at + 60 days (Phase 8 cleanup input)

            Live smoke evidence (one full run, Emergent/claude-opus-4-6):
              - Seeded canned session 2253141a-830f-4810-a683-890f098b5664 / resume 7M7A-X5F5.
              - POST /processing/start → 202 in_progress.
              - Synthesis completed in ~135s total (two LLM calls).
              - GET /results: category "High Potential", 6 dimension_profiles (all 6
                expected ids), 5 components_table rows (Capability Understanding,
                Paradigm Awareness, Orchestration Concepts, Governance Thinking,
                Personal Usage), self_awareness.delta=0.2 ("Well-calibrated"),
                10 not-assessed dimensions.
              - GET /results/download?format=pdf → 200, application/pdf,
                filename TRA-Ada-2026-04-23.pdf, 59236 bytes, starts with %PDF-1.7.
              - GET /results/download?format=markdown → 200, text/markdown,
                filename TRA-Ada-2026-04-23.md, 22384 bytes, starts with
                "# Transformation Readiness Assessment".
              - Public GET /api/sessions/{id}: scores=null, deliverable=null
                (privacy intact). Admin GET exposes both.
              - session.stage="results", expires_at - completed_at = 60 days.

            Unit tests: tests/test_synthesis_service.py — 37 tests, all passing.
            (Catalogue invariants, Doc 23 parsing, band mapping, self-awareness
            computation edges, bundle builder, JSON extractor, validator positive +
            8 negative paths, annotate_deliverable, two-call run_synthesis happy
            path + retry + double-fail paths via monkeypatched router_chat.)

  - task: "Strategic Scenario endpoints + scoring (Phase 6)"
    implemented: true
    working: true
    file: "backend/server.py, backend/services/scenario_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: |
            Phase 6 backend sweep complete. Ran /app/backend_test_phase6.py against
            http://localhost:8001/api. 46/46 assertions passed across letters A–I.
            ONE live Emergent scoring call consumed (14358ms, claude-opus-4-6, score CF=5
            conf=high, ST=4 conf=high, no scoring_error, fallbacks_tried=0).

              A. OpenAPI /api/openapi.json enumerates exactly 25 /api/* paths; all four
                 new scenario routes present:
                 /api/assessment/scenario/{state,start,advance,autosave}.
              B. Doc 22 content fidelity (spot-check via state.content payload):
                 B1. read.title == "Meridian Energy Holdings" ✓
                 B2. body_sections length == 6 ✓
                 B3. body_sections heading order == [None, "Financial Position",
                     "Workforce", "Market Dynamics", "Stakeholder Landscape",
                     "Recent Data Points"] ✓
                 B4. part1.questions length == 3 ✓
                 B5. curveball.items length == 3 ✓
                 B6. curveball items all have integer `number` + non-empty heading + body ✓
                 B7. part2.questions length == 3 ✓
              C. GET /state + POST /start edge cases:
                 C1. unknown session_id -> 404 ✓
                 C2. pre-start (stage=identity) state returns {status:null, phase:null,
                     phase_entered_at:{}, time_on_phase_ms:{}, part1_response:{},
                     part2_response:{}, content:{}} — exact match ✓
                 C3. POST /start while stage != 'scenario' -> 409 with detail.message
                     "Scenario not yet unlocked. Complete the AI Fluency discussion first."
                     and current_stage present ✓
                 C4. POST /start unknown session -> 404 ✓
                 C5. Idempotency: calling /start twice on an in-progress session returns
                     identical {status:in_progress, phase:read} and phase_entered_at.read
                     is preserved byte-for-byte on the second call (no re-init) ✓
              D. POST /advance transitions + validation:
                 D1. from_phase mismatch (claim part1 while actually at read) -> 409
                     {message:"Out-of-order advance.", expected_from_phase:"read",
                     received_from_phase:"part1"} ✓
                 D2. Non-adjacent forward skip (read -> curveball) -> 409 ✓
                 D3. Trio missing q3 -> 422 ✓
                 D4. Trio with whitespace-only q2 -> 422 ✓
                 D5. Non-string q1 (integer) -> 422 ✓
                 D6. q1 with 4001 chars -> 422 ✓
                 D7. advance with unknown session_id -> 404 ✓
              E. POST /autosave:
                 E1. phase mismatch (claim part2 while at part1) -> 409 ✓
                 E2. Unknown partial key (q99) -> 422 ✓
                 E3. Non-string value (int) -> 422 ✓
                 E4. 4001-char string -> 422 ✓
                 E5. Save q1 only -> 200 with saved_at timestamp ✓
                 E6. Subsequent save of q2 -> merge preserves q1; final part1_response
                     == {q1:"first draft value", q2:"second answer"} ✓
                 E7. autosave unknown session -> 404 ✓
              F. LIVE end-to-end happy path (one session, one scoring call):
                 Drove fresh session through identity -> context -> psychometric (20×
                 value=4) -> ai-discussion (3 live turns + /complete) -> scenario
                 start -> part1 (rich trio ~650 chars/answer) -> curveball -> part2
                 (rich trio ~750 chars/answer) -> advance(part2->done). The final
                 advance took 14358ms via Emergent (Claude Opus 4.6):
                 F1. response.status=="completed", response.phase=="done" ✓
                 F2. time_on_phase_ms.part2 populated (integer ≥0) ✓
                 F3. session.stage == "processing" (verified via public GET
                     /sessions/{id}) ✓
                 F4. Public GET /sessions/{id} still returns scores=null,
                     deliverable=null ✓
                 F5. scores.scenario has no scoring_error flag ✓
                 F6. cognitive_flexibility.{score:5 (int, 1-5), confidence:"high" ∈
                     {high,medium,low}, evidence} with evidence object carrying
                     non-empty part1_position/part2_revision/revision_quality/
                     key_quote all as strings ✓
                 F7. systems_thinking.{score:4, confidence:"high", evidence} with
                     connections_identified:list[str], connections_missed:list[str],
                     key_quote:str ✓
                 F8. additional_observations has stakeholder_awareness, ethical_reasoning,
                     analytical_quality — all non-empty strings ✓
                 F9. _meta == {provider:"emergent", model:"claude-opus-4-6",
                     fallbacks_tried:0} ✓
                 F10. scoring model ("claude-opus-4-6") matches admin_settings.
                      fallback_model ("claude-opus-4-6") ✓
                 F11. scenario.status=="completed", scenario.completed_at populated
                      (e.g. "2026-04-23T15:59:43.862658+00:00") ✓
              G. Regression spot-check Phases 2-5:
                 G1. POST /sessions 201 + GET /sessions/resume/{code} 200 ✓
                 G2. Admin login + GET /admin/settings 200 with fallback_model key ✓
                 G3. GET /assessment/psychometric/next 200 with item ✓
                 G4. POST /assessment/psychometric/answer 200 ✓
                 G5. POST /assessment/ai-discussion/start while stage=='identity'
                     -> 409 (gate still correct) ✓
              H. Phase-5 J fix still in effect: after the live ai-discussion run in F,
                 public GET /sessions/{id} conversation[] contains 4 assistant turns
                 (opener + 3 replies) and ZERO of them expose provider / model /
                 latency_ms / fallbacks_tried. `_public_conversation` at server.py:370
                 is correctly applied. ✓
              I. Log hygiene: /var/log/supervisor/backend.*.log scanned for INFO-level
                 occurrences of admin password "test1234", API-key prefixes "sk-ant-"
                 and "sk-emergent-", the test email domain "@meridian-test.example.co.uk",
                 participant name "Priya Ashworth-Wainwright", and answer-content needle
                 "debt covenant". Zero INFO-level hits across all needles. Participant
                 names/emails/contents only surface at DEBUG or in structured internals
                 that don't get logged. ✓

            Robustness (scoring_error path): verified by code review of
            server.py:1146-1164 + scenario_service.run_scoring lines 534-607. If the
            router cascade raises LLMRouterError or the validator keeps failing after
            2 attempts, the handler writes scores.scenario = {scoring_error:true,
            _raw, _error} and still advances the stage; scenario.status="completed"
            is still set. Not exercised live (conserving Emergent budget) but the
            code path is sound.

            Rate-limit on autosave: verified the bucket _scn_autosave_hits is
            registered on every call (successful E5-E7 requests populated the bucket
            observably; 30/min/IP cap from RATE_LIMIT_SCN_AUTOSAVE_MAX). Not
            exhausted to avoid contaminating subsequent tests.

            Test-harness notes: fresh X-Forwarded-For per session creation to avoid
            the 10/hr POST /sessions per-IP limit across 4 sessions; admin JWT
            extracted from Set-Cookie and replayed via explicit Cookie header
            (Secure cookie can't replay over http://localhost via requests.Session
            — not a server bug).

            No code changes were made during testing. No 500s observed. No secret
            leaks. All Phase 6 backend tasks are green. Main agent can summarise
            and close Phase 6.

        - working: "NA"
          agent: "main"
          comment: |
            Phase 6 implementation complete. Added:
              - services/scenario_service.py — parses /app/research/22 - Strategic Scenario.md
                at import time. Validates doc shape (5 named body sections in order, exactly
                3 Part-1 questions, 3 curveball items, 3 Part-2 questions). Exposes
                get_read_content / get_part1 / get_curveball / get_part2 with
                duration_target_minutes (4/5/4/4, picked from the upper end of Doc 22 ranges;
                timers count UP past target, NO auto-submit). Doc 22 content counts:
                title=\"Meridian Energy Holdings\", body_sections=6 (1 unnamed intro + 5
                named), part1_qs=3, curveball_items=3, part2_qs=3.
              - Scoring prompt assembled verbatim from Doc 22 Scoring Criteria + Response
                Analysis Guidance + explicit JSON-only output schema. Validator covers both
                dimensions (cognitive_flexibility: evidence as object with
                part1_position/part2_revision/revision_quality/key_quote; systems_thinking:
                evidence as object with connections_identified[]/connections_missed[]/
                key_quote; plus additional_observations object).
              - 4 new participant endpoints under /api/assessment/scenario:
                  GET  /state     — returns status, phase, phase_entered_at, time_on_phase_ms,
                                    part1_response, part2_response, plus phase-appropriate
                                    content (read|part1|curveball|part2).
                  POST /start     — gate: session.stage must == 'scenario'. Initialises
                                    scenario.{started_at,status=in_progress,phase=read,
                                    phase_entered_at{read},empty trios}. Idempotent if
                                    already in_progress or completed.
                  POST /advance   — strict single-step forward transitions only
                                    (read->part1->curveball->part2->done). Validates trio
                                    on part1/part2 submit (q1/q2/q3 strings, trimmed,
                                    non-empty, ≤4000 chars). On from=part2 -> to=done:
                                    runs scn_svc.run_scoring via llm_router 3-tier cascade
                                    (up to 2 LLM attempts if JSON/schema malformed), writes
                                    scores.scenario with _meta{provider,model,fallbacks_tried}
                                    on success or {scoring_error:true,_raw,_error} on failure;
                                    sets scenario.status=completed, scenario.completed_at,
                                    and advances session.stage to 'processing'.
                  POST /autosave  — merges partial{q1?,q2?,q3?} into the current phase's
                                    response trio. Rate-limited per IP. Rejects unknown
                                    keys (422) and phase mismatches (409).
              - 17 unit tests in tests/test_scenario_service.py all pass (doc parse invariants,
                JSON block extractor, schema validator positive+negative, dimension rubric
                shape, scoring-prompt composition sanity).
              - Playwright E2E already green: walks start -> read -> part1 -> curveball
                -> part2 -> submit -> lands on /assessment/processing.
              - Not yet verified: deep_testing_backend_v2 sweep of the four scenario
                endpoints, end-to-end live scoring via the router, scoring_error path,
                and full regression of Phases 2-5 under the new code.

  - task: "Sessions API: POST, GET, PATCH stage, resume"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Full sessions API landed.
              - POST /api/sessions — EmailStr validation, blank-name rejection, consent=true required,
                sliding-window rate limit (10/hr/IP), returns {session_id, resume_code, stage:'identity'}.
              - GET /api/sessions/resume/{code} — normalises to uppercase + inserts dash if missing,
                returns {session_id, stage, participant} or 404.
              - PATCH /api/sessions/{id}/stage — Literal-validated stage; rejects out-of-order
                transitions (only -1/0/+1 allowed) with 400; returns 200 on valid. Sets
                status='completed', completed_at, and expires_at = completed_at + 60d when stage='results'.
              - GET /api/sessions/{id} — returns full (non-sensitive) state for rehydration.
              - Validation errors returned as 422 via custom handler that uses jsonable_encoder
                so Pydantic ValueErrors serialise correctly.
              - Mongo indexes created at startup: uniq_resume_code (unique), status_expires (compound).
              - Logging: session_id is logged at INFO; participant (name/email) only at DEBUG.
            Verified via 15-point curl smoke test (all pass), plus end-to-end browser flow
            (create -> advance -> save-exit -> resume -> land at last stage).

  - task: "Mongo sessions schema & indexes"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            sessions collection. Docs use str(uuid.uuid4()) as both _id and session_id
            (no ObjectIds anywhere). Fields per spec: participant{name,email,organisation,role},
            consent{accepted,accepted_at}, status, stage, answers[], conversation[],
            scenario_responses{}, deliverable, scores, archived, created_at, updated_at,
            completed_at, expires_at. Verified in mongosh: indexes present and correctly typed.

frontend:
  - task: "Participant capture /start + resume code issuance"
    implemented: true
    working: true
    file: "frontend/src/pages/Start.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            /start form: full name (required, blank trimmed), email (required, validated), organisation
            (optional), role (optional), consent checkbox (required, verbatim per spec).
            Client-side errors shown inline; server 422 surfaced via store.error. On successful POST
            the page flips to a "Save your resume code" card with the XXXX-XXXX code, a Copy button
            with clipboard + textarea fallback, and a Continue CTA that PATCHes stage='context'
            before navigating to /context. Email delivery explicitly noted as STUBBED (Resend coming
            in a later phase).

  - task: "Landing page — Begin + Resume-a-session"
    implemented: true
    working: true
    file: "frontend/src/pages/Landing.js, frontend/src/components/ResumeModal.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Landing now routes Begin Assessment -> /start. Secondary affordance "Resume a session"
            opens a modal with a code field (auto-uppercase, strips non-alphanumeric chars, max 9
            incl. dash). On submit the store hydrates via GET /api/sessions/resume/{code} and
            navigates to STAGE_PATH[stage]. 404 shows "Resume code not found." inline.

  - task: "Save & exit + localStorage hydration"
    implemented: true
    working: true
    file: "frontend/src/components/AssessmentLayout.js, SaveExitButton.js, SaveExitModal.js, store/sessionStore.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Save & exit button rendered top-right inside AssessmentLayout on every /assessment/*.
            Modal shows the current resumeCode with copy button + "Exit to home" CTA that clears
            only the in-memory store (leaves Mongo session + localStorage intact) and routes to /.
            AssessmentLayout hydrates from localStorage on hard reload when store is empty; if no
            localStorage entry OR GET /api/sessions/{id} 404s, clears storage and redirects to /.
            localStorage key 'tra_session_v1' stores ONLY sessionId + resumeCode. Verified:
              - close browser (clear in-memory) + reopen at /assessment/scenario -> stays on
                scenario, stepper shows SCENARIO as current.
              - Clear localStorage + reload /assessment/scenario -> bounced to /.

  - task: "Placeholder pages wired to PATCH + zustand session store"
    implemented: true
    working: true
    file: "frontend/src/pages/stages/*, store/sessionStore.js"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            StagePlaceholder now calls advanceStage(next) / advanceStage(prev) via the store
            before navigating. Each stage page declares its prevStage/prevPath/nextStage/nextPath.
            Back on psychometric PATCHes to 'context'; forward flow submits each next stage.
            Old React Context replaced by Zustand store (`useSession`). Store shape per spec:
            { sessionId, resumeCode, participant, stage, loading, error,
              startSession, hydrateFromResumeCode, hydrateFromLocalStorage,
              advanceStage, goBack, saveAndExit, clearLastCreated, fullReset }.

  - task: "Privacy copy updated on /context"
    implemented: true
    working: true
    file: "frontend/src/pages/Context.js"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Privacy note replaced verbatim: "Your responses are stored securely and used only for
            your assessment and authorised review. Sessions are deleted 60 days after completion
            unless flagged for archive." Styling unchanged (mist background, gold left border).

metadata:
  created_by: "main_agent"
  version: "0.5.0-phase5"
  test_sequence: 4
  run_ui: false

test_plan:
  current_focus:
    - "Phase 9 hotfix — synthesis timeouts (router per-call + total budget)"
    - "_run_synthesis_task finally-clause guarantees terminal status"
    - "asyncio.create_task held in _SYNTHESIS_TASKS module set"
    - "POST /api/admin/sessions/{id}/resynthesize (admin force re-run)"
    - "/processing/start returns reason='stage_mismatch' / 'missing_inputs' on 409"
    - "Regression: Phases 2–8 endpoints still respond correctly"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Phase 9 hotfix bundle is code-complete and unit-test green
        (114/114). Requesting a deep_testing_backend_v2 sweep covering the
        new admin endpoint, the 409 response shape changes, and a
        regression of Phases 2–8.

        Quick orientation:

        Internal base URL: http://localhost:8001/api
        Admin creds: steve@org-logic.io / test1234
        OpenAPI: 36 /api/* paths now (one new: POST /api/admin/sessions/{id}/resynthesize)

        Targets:

          1. POST /api/admin/sessions/{session_id}/resynthesize
             - 401 on unauthenticated request
             - 404 on unknown session_id
             - 409 with detail.reason == "missing_inputs" + detail.missing
               (a list) when scores.psychometric / .ai_fluency / .scenario
               are not all populated. Use a fresh seeded session and remove
               one score block to exercise this.
             - 202 happy path: response carries
               {status:"in_progress", started_at, poll_url}.
             - DB side-effects: deliverable cleared, synthesis = {status:
               "in_progress", started_at, restarted_by:<admin_email>,
               restarted_at}, stage="processing".
             - You can short-circuit the actual LLM call cost: trigger
               /resynthesize on the pre-existing Ada session
               (2253141a-…) which already has all scores. The worker WILL
               kick off; if you don't want to wait ~135s for it to land,
               poll until synthesis.status moves out of "in_progress" OR
               cancel after a minute and check the registry length.
               (You don't need to verify it completes — just that the
               endpoint correctly clears state, spawns the task, and
               returns 202.)

          2. POST /api/assessment/processing/start now returns 409 with
             detail.reason ∈ {"stage_mismatch", "missing_inputs"} on the
             gate failures (was previously a flat detail.message). Verify:
             - On a fresh session at stage="identity":
                 detail.reason == "stage_mismatch"
                 detail.current_stage == "identity"
             - On a session at stage="processing" but with one score block
               nulled out:
                 detail.reason == "missing_inputs"
                 detail.missing carries the list

          3. Regression of /api/openapi.json — exactly 36 /api/* paths;
             includes the new /resynthesize.

          4. Regression spot-checks on Phases 2–8:
             - POST /api/sessions still 201
             - admin login + GET /api/admin/settings still 200
             - psychometric /next + /answer still 200
             - ai-discussion /start + /state still 200
             - scenario /state + /advance still 200
             - processing /start (happy session) still 202
             - dashboard /summary still 200, has the existing shape
             - lifecycle /run still 200 (idempotent)
             - public GET /api/sessions/{id} STILL strips admin-only
               fields (admin_notes, last_admin_viewed_at, deleted_at,
               hard_delete_at, redacted, synthesis internals beyond
               status/started_at/completed_at)

          5. Log hygiene: no participant PII or LLM key material at
             INFO level, even when /resynthesize is invoked.

        Please update the Phase 9 task's status_history with letter-coded
        findings and mark working=true / needs_retesting=false if green.
        Do not change any other phase's task entries or the test_plan.

agent_communication:
    - agent: "main"
      message: |
        Phase 8 (Admin dashboard + lifecycle cron + exports) was code-complete
        and live smoke-tested end-to-end. The deep_testing_backend_v2 sweep
        passed (49/49) after a single privacy fix on public GET
        /api/sessions/{id}.

        target list is in the "Admin dashboard + lifecycle + exports (Phase 8)"
        task entry at the top of /app/test_result.md.

        Quick orientation:

        Internal base URL: http://localhost:8001/api
        Admin creds: steve@org-logic.io / test1234 (cookie is Secure — use
        explicit Cookie header).

        Seven+ new endpoints to exercise:
          GET    /api/admin/sessions              — list w/ search/filter/sort/page
          GET    /api/admin/sessions/{id}         — full doc (stamps last_admin_viewed_at)
          PATCH  /api/admin/sessions/{id}         — {archived?, notes?} incl. expires_at recalc
          DELETE /api/admin/sessions/{id}         — admin-initiated soft delete
          POST   /api/admin/sessions/{id}/restore — restore within 30d; PII not recoverable
          GET    /api/admin/sessions/{id}/conversation/download?format=markdown|json
          GET    /api/admin/sessions/{id}/deliverable/download?format=pdf|markdown (Phase 7 renderer via admin route)
          GET    /api/admin/dashboard/summary     — cached 60s aggregates
          POST   /api/admin/lifecycle/run         — manual cleanup trigger

        Verifications I would like covered (see status_history for the full
        list; highlights):

          1. Search + filter + pagination + sort on /admin/sessions with
             various combinations; assert total/page/page_size metadata.
          2. PATCH archive=true clears expires_at + hard_delete_at;
             archive=false restores expires_at = completed_at + 60d when the
             session is completed.
          3. DELETE then GET: participant.name == "(redacted)",
             participant.email is null, redacted=true, deleted_at +
             hard_delete_at set, but scores/conversation/scenario
             responses/deliverable preserved.
          4. Restore within 30d -> 200 {ok:true, restored:true,
             pii_recoverable:false}. PII stays "(redacted)".
          5. Restore after 30d (mutate hard_delete_at into the past) -> 409.
          6. Full cycle via POST /admin/lifecycle/run with time-frozen
             expires_at and hard_delete_at — soft_deleted/hard_deleted counts
             match expectations.
          7. Conversation downloads: correct Content-Type, non-empty body,
             sanitised Content-Disposition filename, correct content shape.
             Redacted sessions still work (exports allowed after redaction)
             and NEVER leak email/organisation.
          8. Deliverable admin downloads (pdf/markdown) work even for
             archived sessions.
          9. Dashboard summary: shape and caching (hit once, then again
             within 60s — should be identical without any mutation).
         10. Non-admin requests to all new endpoints -> 401.
         11. Regression: Phases 2-7 endpoints all still respond correctly.
         12. /api/openapi.json now enumerates 35 /api/* paths (29 prior + 6
             new Phase 8 paths, counting METHODS on the same path once).
         13. Log hygiene: no participant email/organisation/role/answer
             content/API keys/deliverable content at INFO level in
             /var/log/supervisor/backend.*.log even when a soft-delete event
             fires.

        A fresh fully-scored session is trivial to mint via
          `python /app/backend/seed_phase7_test_session.py`
        which prints a session_id + resume_code.

        Please update the Phase 8 task's status_history with letter-coded
        findings (consistent with prior phases). Do not change the test_plan
        block or any other phase's task entries.

agent_communication:
    - agent: "main"
      message: |
        Phase 7 (Processing + Results + Doc 23 synthesis) was code-complete and
        passed a full live smoke run end-to-end. Requesting a thorough
        deep_testing_backend_v2 sweep of the new surface before handing back.

        Please test against http://localhost:8001/api.

        Completed smoke-test session available for reuse (already has a full
        deliverable persisted) — only spend a fresh synthesis call if you
        genuinely need one:
          session_id: 2253141a-830f-4810-a683-890f098b5664
          resume_code: 7M7A-X5F5
        And a re-seeder script exists: `python /app/backend/seed_phase7_test_session.py`
        will mint a new pristine session with full psychometric + ai_fluency +
        scenario scores and stage="processing".

        Targets (full list in test_result.md status_history):

          1. POST /assessment/processing/start
             - 404 on unknown session
             - 409 when stage ∉ {processing, results} (with detail.current_stage)
             - 409 when any of scores.{psychometric, ai_fluency, scenario} missing
             - Happy path → 202 {status:"in_progress", started_at, poll_url}
             - Idempotency: second call within 2 min while in_progress → same 202
               payload, NO new asyncio task spawned (detectable by started_at
               staying the same).
             - After completion → subsequent /start returns 200 "completed" with
               completed_at — no re-run.

          2. GET /assessment/processing/state?session_id=...
             - Unknown session → 404
             - {status, started_at, completed_at, error} shape; NO deliverable body

          3. GET /assessment/results?session_id=...
             - 404 on unknown
             - 409 when synthesis.status != "completed"
             - Happy path: deliverable with ai_fluency_deep_dive.components_table
               (5 rows), dimension_profiles (6 with correct dimension_id set),
               executive_summary carrying overall_colour ∈ {navy,gold,terracotta},
               dimensions.assessed (6) + dimensions.not_assessed (10)
             - scoring_error path: 200 with {status:"error", scoring_error:true,
               participant.first_name}

          4. GET /assessment/results/download?format=pdf|markdown
             - PDF: Content-Type application/pdf, Content-Disposition filename
               matches TRA-{first_name}-{YYYY-MM-DD}.pdf, body starts with %PDF
             - Markdown: Content-Type text/markdown; charset=utf-8, body starts
               with "# Transformation Readiness Assessment", contains all 10
               not-assessed dimension names and "Not assessed in this preview"
             - Invalid format value → 422
             - scoring_error path → 409 (download not available)
             - When synthesis not complete → 409

          5. Privacy
             - Public GET /api/sessions/{id}: scores, deliverable still null
               even after synthesis completes
             - Conversation entries on public read still strip provider/model/
               latency_ms/fallbacks_tried (Phase 5 J fix still in effect)
             - Admin GET /api/admin/sessions/{id}: scores + deliverable visible

          6. Regression — Phases 2-6 endpoints still respond (sessions, admin,
             psychometric, ai-discussion, scenario).

          7. /api/openapi.json: 29 /api/* paths total (25 prior + 4 new).

          8. Log hygiene: no deliverable content, conversation content, API keys,
             or full prompts at INFO level in /var/log/supervisor/backend.*.log.

        Admin credentials (for admin reads):
          email: steve@org-logic.io
          password: test1234

        Live LLM budget: ONE additional real synthesis run will consume two
        Emergent/Claude Opus 4.6 calls. Prefer reusing the Ada Lovelace
        session above; only mint a fresh one if you're verifying a code path
        that actually requires an unsullied session (e.g. the idempotency
        window).

        Please update the Phase 7 task's status_history with letter-coded
        findings (A…N style, as in Phases 4/5/6) and set needs_retesting=false
        if green. Do NOT modify any other phase's task entries.
    - agent: "testing"
      message: |
        Phase 7 backend sweep: 24/24 scripted assertions PASS, plus live
        end-to-end synthesis verified on a fresh seeded session. See the
        Phase 7 task's status_history above for the full letter-coded
        detail (A, B1-B2, C1, D1, E1-E8 live, F1, G1-G2, H1-H5, I1-I2,
        J1-J2, K1-K6, L).

        Highlights:
          - OpenAPI enumerates exactly 29 /api/* paths; all four new Phase-7
            endpoints present.
          - /processing/start gates correctly (404 unknown, 409 stage,
            409 missing score blocks) and is idempotent for
            already-completed sessions (200).
          - /processing/state shape clean — no deliverable body leaks.
          - /results schema conformance verified on BOTH the Ada session
            and the fresh live session: executive_summary.overall_colour ∈
            {navy,gold,terracotta}, exactly 6 dimension_profiles covering
            all 6 expected ids, every profile carries band.colour in the
            palette, components_table has 5 rows, development_recommendations
            has 2, methodology_note + integration_analysis present,
            dimensions.assessed=6 / not_assessed=10.
          - Downloads: PDF body starts %PDF-, MD starts with
            "# Transformation Readiness Assessment", both carry correct
            Content-Type + filename TRA-Ada-2026-04-23.{pdf|md}; MD contains
            all 10 not-assessed dimension names + "Not assessed in this preview".
          - Graceful scoring_error path: /results returns 200 status:"error"
            (not 500), /download returns 409 (not 500).
          - Privacy: public GET hides scores + deliverable; conversation
            assistant turns strip provider/model/latency_ms/fallbacks_tried
            (Phase 5 J fix still in effect). Admin read exposes both.
          - Fresh synthesis run: provider=emergent, model=claude-opus-4-6,
            fallbacks_tried=0, ~136 s end-to-end, stage="results",
            expires_at - completed_at = exactly 60 days.
          - Regression Phases 2-6 green.
          - Log hygiene: zero INFO-level leaks of passwords, API keys,
            participant emails, conversation content, or deliverable
            internals.

        Two non-blocking operational notes for main agent (NOT failures):

          1. LiteLLM blocks the uvicorn event loop during synthesis.
             Concurrent requests (including /api/health) stall for up to
             ~60 s while an LLM call is in flight. Browser poll latency on
             /processing/state will be affected. Phase 7 code is correct;
             this is an emergentintegrations/LiteLLM transport
             characteristic — consider running the worker in a dedicated
             executor if poll UX latency is user-visible.

          2. On one of the two live synthesis runs performed this sweep, the
             first attempt failed with part_a:"no JSON block" after both
             internal _one_call retries (2 attempts) exhausted. Worker
             correctly wrote synthesis.status="failed" +
             deliverable.scoring_error=true. A subsequent /start triggered
             the server.py:1367 restart branch and synthesis succeeded on
             that second run. Self-healing works, but a participant whose
             first synthesis flakes will be stuck at "failed" until their
             client re-hits /start. Worth surfacing either a retry button
             on /processing or a one-off server-side auto-retry with
             backoff.

        No code changes were made during testing. Phase 7 backend passes;
        main agent can summarise and close Phase 7.


agent_communication:
    - agent: "main"
      message: |
        Phase 6 (Strategic Scenario) backend was code-complete and Playwright-verified
        end-to-end on the frontend; now requesting a thorough deep_testing_backend_v2
        sweep of the four new endpoints under /api/assessment/scenario before I hand
        Phase 6 back to the user.

        Please test against http://localhost:8001/api (internal; matches prior phases).

        Targets:
          1. GET /assessment/scenario/state
             - unknown session_id -> 404
             - pre-start (stage=identity/...) -> returns {status:null, phase:null,
               phase_entered_at:{}, time_on_phase_ms:{}, part1_response:{},
               part2_response:{}, content:{}}
             - mid-phase -> returns correct phase + phase-appropriate content block
               (body_sections for read; preamble+questions for part1/part2; items for
               curveball).

          2. POST /assessment/scenario/start
             - gate: session.stage != 'scenario' -> 409 with detail.message
               "Scenario not yet unlocked. Complete the AI Fluency discussion first."
               and current_stage.
             - happy path from stage='scenario' -> 200, scenario.status='in_progress',
               phase='read', phase_entered_at.read set.
             - idempotency: call twice -> same public state, no double-initialisation.

          3. POST /assessment/scenario/advance
             - invalid transitions: wrong from_phase, skip, backward -> 409/422.
             - trio validation on part1->curveball and part2->done:
                 missing/empty q1/q2/q3 -> 422, >4000 chars -> 422,
                 non-string values -> 422.
             - time_on_phase_ms for the exited phase is set to a sensible positive
               integer.
             - CRITICAL: from=part2 to=done runs scoring via llm_router cascade.
               Expect provider='emergent' (the only tier configured), model matches
               admin_settings.fallback_model, fallbacks_tried=0. scores.scenario
               populated with scenario_analysis.{cognitive_flexibility, systems_thinking,
               additional_observations} and _meta. session.stage advances to
               'processing'. session.scenario.status='completed', completed_at set.
             - Robustness: confirm that if scoring fails (we won't force this, but
               confirm the code path exists), session.scores.scenario carries
               {scoring_error:true, _raw, _error} and the stage still advances.
               (You can assert this by code review; don't try to break the live LLM.)

          4. POST /assessment/scenario/autosave
             - phase mismatch -> 409.
             - unknown partial keys -> 422.
             - non-string value -> 422, >4000 chars -> 422.
             - merges partial into current trio without overwriting absent keys.
             - rate limit is enforced (don't need to exhaust it; just confirm the
               handler registers hits).

          5. Public vs admin read:
             - GET /api/sessions/{id} must NOT expose scores or deliverable (still null),
               but scenario state (phase, part1_response, part2_response, time_on_phase_ms)
               is expected to be visible for hydration.
             - GET /api/admin/sessions/{id} (authed) exposes the full scores.scenario.

          6. Doc 22 content fidelity (spot-check via the content payload):
             - read.title == 'Meridian Energy Holdings' (from '**Scenario: Meridian
               Energy Holdings**' header).
             - read.body_sections has 6 entries (1 intro + 5 named: Financial Position,
               Workforce, Market Dynamics, Stakeholder Landscape, Recent Data Points).
             - part1.questions has length 3, postamble mentions "4-5 minutes".
             - curveball.items has length 3 with numbered heading+body.
             - part2.questions has length 3, postamble mentions "3-4 minutes".

          7. OpenAPI: /api/openapi.json should include all four scenario paths and
             list 25 /api/* paths total.

          8. Regression — confirm Phase 2-5 endpoints still respond correctly
             (/api/sessions CRUD, admin auth, psychometric /next+/answer, ai-discussion
             /start+/message+/complete+/state+/retry, admin /settings,
             /settings/test-fallback). Include the earlier Phase 5 J minor fix:
             GET /api/sessions/{id} conversation[] assistant turns must NOT carry
             provider/model/latency_ms/fallbacks_tried (that is the _public_conversation
             stripping).

          9. Log hygiene: no INFO-level emission of participant names, email, answer
             content, API keys, or full prompts in /var/log/supervisor/backend.*.log.

        Admin credentials (for /api/admin/sessions/{id}):
          email: steve@org-logic.io
          password: test1234

        The cookie is Secure, so drive admin calls via an explicit Cookie header on
        localhost (same pattern used in Phases 3-5).

        Live LLM budget: the scoring call on advance->done will burn one real
        Emergent/Claude Opus 4.6 call per session you run through. One end-to-end
        success is enough; don't replay unnecessarily.

        After the sweep, please update this task's status_history and set
        needs_retesting=false if green.

agent_communication:
    - agent: "main"
      message: |
        Phase 5 complete. Added:
          - `services/ai_discussion_service.py`: Doc 21 SYSTEM_PROMPT verbatim, 3 opening probes
            verbatim, deterministic session-hashed opener selection, prompt assembly with
            participant context (first-name only, bands not numbers), final-turn note, strict
            JSON scoring prompt + extractor + schema validator.
          - 5 new participant endpoints under /api/assessment/ai-discussion: start, message,
            complete, state, retry. All consume the Phase-3 llm_router cascade.
          - session.conversation[] append-only with provider/model/latency/fallbacks_tried on
            assistant turns. session.ai_discussion tracks status/started_at/completed_at/
            user_turn_count/exit_reason/opener.
          - Turn-numbering convention: opening assistant turn = 0, user turn N (1..12) = N,
            assistant reply to user-turn N also carries N. user_turn_count = count of user turns.
          - On the 12th user turn, assistant is instructed to emit ONLY the Doc 21 closing line;
            scoring runs in the same request, writes scores.ai_fluency with _meta (provider/
            model/fallbacks_tried). Early /complete runs scoring too (requires turn_count>=3).
          - Emergent fallback rebuilt to use LlmChat.with_params(max_tokens=...) and a clean
            [PRIOR CONVERSATION]/[Interviewer]/[Participant] bracketed format in system_message
            — no more "User:" prefix that would trigger the model to hallucinate participant turns.
          - 20 new unit tests in tests/test_ai_discussion_service.py (opener determinism, ctx
            builder, JSON extraction with fences/prose/nested, schema validator for all 5
            failure modes, scoring happy path + retry + double-fail graceful).
          - 43/43 unit tests pass. Live end-to-end verified: 3 real turns via Emergent fallback
            (Claude Opus 4.6), /complete runs, scores.ai_fluency populated with overall_score
            + 5 components + evidence + key_quotes + strengths + blind_spots + _meta.
        Doc 21 conflicts resolved:
          - Confidence field is "high"/"medium"/"low" per Doc 21 (brief had 0..1 or 1..5; Doc 21 wins).
        Please sweep Phase 5 backend thoroughly.

backend:
  - task: "AI Fluency Discussion endpoints + scoring (Phase 5)"
    implemented: true
    working: true
    file: "backend/server.py, backend/services/ai_discussion_service.py, backend/services/llm_router.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            End-to-end manually verified with real Emergent fallback (Claude Opus 4.6):
            /start produces opener; 3 user turns return contextual probing replies from Doc 21
            persona without hallucinated Participant turns; /complete finalises + scores. Resume
            via /state on refresh hydrates the transcript cleanly. Unit tests cover prompt
            assembly, JSON extraction (fenced/nested/trailing-prose), validator rejections, and
            scoring retry+fail paths (43/43 pass).
        - working: true
    - agent: "testing"
      message: |
        Phase 5 backend sweep: 45/46 passed. See letters A–M detail in the Phase-5
        task status_history above.

        Only failure: [J] MINOR — Public GET /api/sessions/{id} leaks assistant-turn
        internals (provider, model, latency_ms, fallbacks_tried) in the conversation[]
        array. Spec says these should be stripped via the _public_conversation helper.
        Suggested fix (one line): in get_session(), set
          doc["conversation"] = _public_conversation(doc.get("conversation") or [])
        before returning. Not a security-critical leak (no PII, no keys, no prompts),
        but a spec deviation.

        A–I, K–M all green. Live 3-turn loop via Emergent Claude Opus 4.6 works end to
        end, scoring returns a schema-valid overall_score=3.4 with all 5 components,
        and no Participant: hallucinations observed. /api/openapi.json lists all 5
        new endpoints. Log hygiene is clean at INFO level.

          agent: "testing"
          comment: |
            Phase 5 backend sweep complete. Ran /app/backend_test_phase5.py against
            http://localhost:8001/api. 45/46 assertions passed. Only failure is a minor
            spec deviation on public conversation shape (letter J below).

              A. Gate check: POST /start at stage=identity -> 409
                 {detail:{message:"AI discussion not yet unlocked. Complete the psychometric
                 first.", current_stage:"identity"}}. After driving context -> psychometric
                 (20x value=4 answers) -> ai-discussion and POST /start -> 200.
              B. /start response shape: {messages:[opener], user_turn_count:0, can_submit:true,
                 at_cap:false, status:"in_progress"}. Opener text was verbatim
                 OPENING_PROBES[1] ("To kick us off—what's the most useful thing AI has done
                 for you recently..."). Re-calling /start on the same in_progress session
                 returned a single-message payload (no duplicate opener persisted).
              C. 3-turn live loop via Emergent fallback all succeed:
                 turn 1 (2.9s), turn 2 (3.6s), turn 3 (4.7s). Conversation grows 1→3→5→7
                 entries. Assistant turn numbers = 1,2,3 matching user turn numbers. No
                 "[Participant]:" / "Participant:" prefix in any assistant content (regex
                 check). Claude Opus 4.6 via Emergent returns contextual probing follow-ups
                 that directly reference the participant's prior statements.
              D. Validation: empty content -> 422; 2001-char content -> 422; missing
                 session_id -> 422. No 500s.
              E. /complete after 3 turns -> 200 {status:"completed", user_turn_count:3}.
                 Second call is idempotent -> same body. Pre-3 test on a separate session
                 with only 1 user turn returned 409 with detail.message
                 "Please complete at least three exchanges before ending.".
              F. POST /message after /complete -> 409 {detail:{message:"AI discussion is not
                 in progress.", status:"completed"}}.
              G. /state — unknown session 404; pre-start session returns
                 {status:null, messages:[], user_turn_count:0}; completed session returns
                 {status:"completed", can_submit:false, at_cap:false, user_turn_count:3,
                 messages len=7}. All matches spec.
              H. Resume: fresh session, drove to ai-discussion, /start, /message once. Cold
                 GET /state returned 3 messages with turns=[0,1,1] and roles=
                 [assistant,user,assistant]. Turn numbering preserved across the cold read.
              I. Admin GET /api/admin/sessions/{id}: all 3 assistant turns carry
                 provider="emergent", model="claude-opus-4-6", latency_ms>0, fallbacks_tried=0.
                 scores.ai_fluency populated with overall_score=3.4 (float), all 5 components
                 (capability_understanding, paradigm_awareness, orchestration_concepts,
                 governance_thinking, personal_usage) each with integer score 1-5,
                 confidence ∈ {high,medium,low}, evidence:list[str]. key_quotes, blind_spots,
                 strengths all list[str]. _meta = {provider:"emergent",
                 model:"claude-opus-4-6", fallbacks_tried:0}. NO scoring_error.
              J. MINOR: Public GET /api/sessions/{id} — scores IS null (✅), conversation
                 IS exposed (✅, len=7). However, assistant turns in the PUBLIC response
                 still carry {provider, model, latency_ms, fallbacks_tried}, leaking
                 backend internals. The brief says this should be stripped via the
                 _public_conversation helper. Current get_session() in server.py does
                 NOT invoke _public_conversation — it returns the raw doc with only
                 scores/deliverable nulled. The helper exists at server.py:584 but is
                 only applied by the ai-discussion endpoints. Suggested fix: in
                 get_session, replace doc["conversation"] with
                 _public_conversation(doc.get("conversation") or []) before returning.
                 Not a security-critical leak (no PII, no keys), but a spec violation.
              K. Log hygiene: tail -n 4000 /var/log/supervisor/backend.*.log checked for
                 user message content needles ("writing assistant", "pattern-matches",
                 "Agentic AI") at " - INFO - " level — zero hits. INFO lines only show
                 session_id, turn number, provider/model/latency.
              L. OpenAPI /api/openapi.json lists all 5 new paths:
                 /api/assessment/ai-discussion/{start, message, complete, state, retry}.
                 Total 21 /api/* paths enumerated.
              M. Regression — Phase 2/3/4 endpoints all still respond correctly:
                 POST /api/sessions 201, GET /sessions/resume/{code} 200, PATCH
                 /sessions/{id}/stage 200, GET /sessions/{id} 200, admin /auth/me 200,
                 admin /settings 200, psychometric /next 200, /progress 200, admin
                 /sessions/{id} 200. (Live /admin/settings/test-fallback skipped to
                 conserve Emergent token budget — was verified in Phase 3 with ok:true,
                 latency_ms=3548ms.)

            No 500s observed. No secret/key leaks. Scoring payload is clean and
            schema-valid — overall_score=3.4 is a realistic value for a 3-turn
            conversation with a capable senior participant. The Emergent fallback is
            the only configured tier so fallbacks_tried=0 across the board, as expected.

            Harness notes (test-side): fresh X-Forwarded-For per session creation to
            avoid the 10/hr POST /sessions rate limit, and per psychometric answer
            sequence to avoid the 60/min /answer rate limit. Admin JWT extracted once
            from Set-Cookie and replayed via explicit Cookie header (cookie is Secure
            so requests.Session cannot replay over http://localhost). Real browsers
            on the HTTPS preview URL replay automatically — test-harness workaround,
            not a server bug.

agent_communication:
    - agent: "main"
      message: |
        Phase 4 complete. Added:
          - `psychometric_service.py` — parses Doc 20 at module import (20 items: 12 LA + 8 TA),
            validates counts/uniqueness, maps subscales, scores per Doc 20 formulas and bands.
            Fails loudly if the doc ever grows reverse-keyed items or count mismatches.
          - 3 new participant endpoints: GET /api/assessment/psychometric/next,
            POST /api/assessment/psychometric/answer, GET /api/assessment/psychometric/progress.
          - 1 new admin endpoint: GET /api/admin/sessions/{id} (requires admin JWT).
          - Public GET /api/sessions/{id} now strips `scores` and `deliverable`.
          - Per-session randomised item order persisted on first /next, never overwritten.
          - Append-only answers with strict ordering: out-of-order / already-answered => 409 with
            expected_item_id. Within-2s duplicate same-value = 200 idempotent. Unknown item_id = 422.
          - Answer rate limit: 60/min/IP.
          - On the 20th answer, server computes scores.psychometric (raw_sum, mean_6pt, mean_1_5,
            band, subscales, timing, self_awareness_claimed). Never exposed on participant endpoints.
          - 23/23 unit tests pass (11 psychometric + 12 existing LLM router).
        Frontend:
          - Real /assessment/psychometric page replaces placeholder. Intro panel (first-time only;
            resumers skip it), then per-item screen: progress bar, scale chip, serif item text,
            6-card Likert row with numerals + labels. Auto-advance ~450ms after selection.
            Keyboard 1-6 to select+advance, arrows ← → preview, Enter = submit selected.
            Response-time timer pauses when tab hidden >5s. Save & exit header button still present.
            Retry-on-409 reconciles by re-fetching /next.
          - Done panel with gold check + "Continue" to advance stage to ai-discussion.

        Please run a thorough backend sweep of the new endpoints plus regression of Phase 2+3 endpoints.
        Use http://localhost:8001 (same as Phase 3 test).

backend:
  - task: "Psychometric endpoints + scoring + admin session read (Phase 4)"
    implemented: true
    working: true
    file: "backend/server.py, backend/psychometric_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            End-to-end manually verified: 20-answer scripted loop (bash) completes with
            session.psychometric.order = 20 items (LA block then TA block, shuffled within each)
            and session.scores.psychometric populated. Admin GET /api/admin/sessions/{id} returns
            scores; public GET /api/sessions/{id} returns scores=null. Edge cases covered:
            bad value (0/7/decimal) -> 422; unknown item_id -> 422; out-of-order post -> 409;
            replay within 2s same value -> 200 idempotent; replay after 2s -> 409 already-answered.
            Playwright E2E: 20 answers via keyboard, intro panel shown first run, skipped on
            resume, completion panel advances stage, resume lands on next unanswered item.
        - working: true
          agent: "testing"
          comment: |
            Phase 4 backend verification complete. Ran /app/backend_test.py against
            http://localhost:8001/api. 39/39 assertions passed across letters A-Q.
              A. POST /sessions then GET /assessment/psychometric/next (first call):
                 200 with {done:false, item:{item_id,text,scale,subscale}, progress:{answered:0,
                 total:20, current_index_1based:1, done:false, scale_counts:{LA:{0,12}, TA:{0,8}}}}.
                 Admin read confirms: session.psychometric.order has 20 IDs with first 12 all
                 LA* (e.g. ['LA04','LA02','LA11',...]) and last 8 all TA* (e.g. [...,'TA04',
                 'TA08','TA06']); session.stage flipped to 'psychometric';
                 psychometric.started_at populated with UTC ISO timestamp.
              B. Two consecutive GET /next for the same session return the same item_id
                 (idempotent initialisation — no re-shuffle, same head of queue).
              C. 20 sequential POSTs: progress.answered increments exactly 0->1->...->20, the
                 next item served always differs from the previous, the 20th response has
                 {done:true, progress.answered:20}. Subsequent admin read shows
                 scores.psychometric with keys {learning_agility, tolerance_for_ambiguity,
                 self_awareness_claimed, timing, bands_reference}, plus all five LA subscales
                 (Change/Mental/People/Results/Self-Awareness) and all three TA subscales
                 (Uncertainty/Complexity/Closure).
              D. Score math sanity with all value=4: LA raw_sum=48, mean_6pt=4.0, mean_1_5=3.4,
                 band='Moderate'. TA raw_sum=32, mean_6pt=4.0, mean_1_5=3.4, band='Moderate'.
                 Matches Doc 20 formulas exactly.
              E. Validation rejections all 422 (no 500s): value=0 -> 422; value=7 -> 422;
                 value=3.5 -> 422; response_time_ms=-1 -> 422; missing session_id -> 422;
                 missing item_id -> 422; missing value -> 422.
              F. POST with item_id='ZZ99' -> 422 {"detail": "Unknown item_id 'ZZ99'."}. Exact.
              G. Out-of-order POST: expected LA05, sent LA09 -> 409 with detail
                 {message: 'Out-of-order answer.', expected_item_id: 'LA05',
                 received_item_id: 'LA09'}.
              H. Replay within 2s with same item_id+value -> 200 {idempotent:true} with
                 unchanged progress. After 2.6s, same payload -> 409 with detail.message
                 'Item already answered.'.
              I. Within 2s, same item_id but DIFFERENT value -> 409 (not idempotent).
              J. GET /progress works pre-init (answered:0, total:20, done:false,
                 scale_counts.LA.total:12, scale_counts.TA.total:8) and mid-flight after 5
                 LA answers (answered:5, LA.answered:5, TA.answered:0).
              K. Resume behaviour: after 5 answers, order is persisted and GET /next returns
                 order[5] (the 6th item). Calling GET /next again (simulated resume) returns
                 the same id and the persisted order array is byte-identical (no reshuffle).
                 scores.psychometric stays absent until the 20th POST, then appears once with
                 all expected keys.
              L. Admin GET /api/admin/sessions/{id}: unauth -> 401 "Not authenticated."; with
                 valid JWT cookie -> 200 returning the full session with scores.psychometric
                 AND psychometric.order both present.
              M. Public GET /api/sessions/{id}: scores=null, deliverable=null, but
                 participant{name,email,organisation,role}, psychometric.order (20 IDs) and
                 psychometric.answers (populated) are still present — frontend can track
                 progress without seeing scores.
              N. Rate limit: 60 POST /answer requests in a minute from the same X-Forwarded-For
                 IP all succeeded; the 61st returned 429 "Too many answers. Please slow down."
              O. OpenAPI /api/openapi.json lists all 4 new paths:
                 /api/assessment/psychometric/next, /api/assessment/psychometric/answer,
                 /api/assessment/psychometric/progress, /api/admin/sessions/{session_id}.
                 Total 16 /api/* paths enumerated.
              P. Regression — Phase 2+3 endpoints still return the expected codes:
                 POST /api/sessions 201, GET /api/sessions/resume/{code} 200, PATCH
                 /api/sessions/{id}/stage 200, GET /api/sessions/{id} 200, POST
                 /api/admin/auth/login 200, GET /api/admin/auth/me 200, GET /api/admin/settings
                 200, POST /api/admin/auth/logout 200.
              Q. Security log hygiene: tail of /var/log/supervisor/backend.out.log shows NO
                 INFO-level lines containing @example.co.uk (test email), no occurrences of
                 password 'test1234', and no API-key-shaped strings (sk-ant-*, sk-emergent-*,
                 sk-proj-*).

            Harness notes (test-side, not server-side): a fresh X-Forwarded-For IP is used per
            session creation to avoid the documented 10/hr POST /sessions per-IP rate limit
            across the 16-test sweep; the admin JWT is cached once to avoid the 10/15min login
            limit. Cookie is correctly marked Secure, so requests.Session cannot replay it
            over http://localhost — harness explicitly extracts the JWT and sends it via an
            explicit Cookie header. Real browsers on the HTTPS preview URL replay the cookie
            automatically — this is a test-harness workaround, not a server bug.

            No code changes were made during testing. No 500s observed. No secret leaks.
            All Phase 4 backend tasks are green. Main agent can summarise and close Phase 4.


agent_communication:
    - agent: "main"
      message: |
        Phase 3 complete. Doc 23 pulled from origin (361 lines). Added:
          - Admin users collection + auto-seed steve@org-logic.io / test1234 (idempotent).
          - JWT cookie auth (HS256, HttpOnly + Secure + SameSite=Lax, 8h expiry).
          - Login rate limit 10/15min/IP. Generic "Invalid credentials" on any auth failure.
          - admin_settings singleton with Fernet-encrypted api_keys.
          - GET /api/admin/settings (masked), PUT (upsert, empty key clears slot, missing api_key keeps existing),
            POST /api/admin/settings/test (real provider round-trip for primary/secondary/adhoc),
            POST /api/admin/settings/test-fallback (real emergentintegrations round-trip).
          - LLM router /app/backend/services/llm_router.py with 3-tier cascade + categoriser.
            12 unit tests passing. Not yet wired into user-facing flows.
          - Provider catalog /app/backend/llm_providers.py (anthropic / openai / openrouter / straico / grok)
            with curated models sourced from emergentintegrations playbook + OpenRouter + x.ai + straico docs.
          - Frontend: /admin/login, /admin (overview), /admin/settings — all protected, all styled to spec.
          - Secrets (JWT_SECRET, SETTINGS_ENCRYPTION_KEY, EMERGENT_LLM_KEY) live only in /app/backend/.env,
            which is now in .gitignore. No secret values in any git-tracked file or supervisor log.

        Please test the following against http://localhost:8001 (internal) — cross-origin from localhost
        returns *-CORS headers from the ingress which is a test-harness artifact, not a real-user issue:
          - POST /api/admin/auth/login happy path + bad password + unknown email
          - GET /api/admin/auth/me with cookie / without cookie (401 when missing)
          - GET /api/admin/settings round-trip (unauth 401, authed 200 with masked key)
          - PUT /api/admin/settings: set, clear with api_key="", partial updates
          - POST /api/admin/settings/test: invalid Anthropic key should return ok:false with error_category "auth"
          - POST /api/admin/settings/test-fallback: real Emergent key should return ok:true with latency_ms
          - /api/docs should list 4 session endpoints + 6 admin endpoints = 10 total

backend:
  - task: "Admin auth + settings (Phase 3)"
    implemented: true
    working: true
    file: "backend/server.py, auth_utils.py, crypto_utils.py, llm_providers.py, services/llm_router.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            All 6 admin endpoints reachable. Login + logout + me + settings + test + test-fallback verified
            manually via curl and via browser (Playwright against farm-readiness.preview.emergentagent.com).
            Fallback round-trip hit real Claude Opus 4.6 via Emergent LLM key, returned "OK" in 4203ms.
            Invalid Anthropic key categorised correctly as "auth". Raw plaintext keys never leave the
            server — frontend always sees `key_hint` masked (e.g. "sk-a\u2022\u2022\u2022\u20220001").
        - working: true
          agent: "testing"
          comment: |
            Phase 3 backend verification complete. Ran /app/backend_test_phase3.py against
            http://localhost:8001/api. 33/33 assertions passed.
              A. Login happy path: 200 {email:'steve@org-logic.io', role:'admin'}. Set-Cookie
                 tra_admin_token=<jwt>; HttpOnly; Max-Age=28800; Path=/; SameSite=lax; Secure.
                 All four attributes verified.
              B. Wrong password -> 401 {"detail":"Invalid credentials."}. Exact match.
              C. Unknown email -> 401 {"detail":"Invalid credentials."} — identical body,
                 no user-existence leak.
              D. GET /admin/auth/me without cookie -> 401 {"detail":"Not authenticated."}.
              E. GET /admin/auth/me with cookie -> 200 {email, role}.
              F. POST /admin/auth/logout -> 200 {"ok":true}. Response Set-Cookie clears
                 the token with Max-Age=0 + expires in the past.
              G. GET /admin/auth/me after logout -> 401.
              H. GET /admin/settings without cookie -> 401.
              I. GET /admin/settings authed -> 200 with all 6 required keys
                 (primary, secondary, fallback_model, updated_at, updated_by, catalog).
                 catalog.providers contains exactly {anthropic, openai, openrouter, straico, grok}.
              J. PUT /admin/settings primary={provider:'anthropic', model:'claude-opus-4-6',
                 api_key:'sk-ant-testkey-ABC123XYZ', label:'T1'} -> 200. Subsequent GET shows
                 primary.has_key=true, key_hint='sk-a••••3XYZ'. Raw key "sk-ant-testkey-ABC123XYZ"
                 NOT present anywhere in PUT or GET response bodies.
              K. PUT primary={api_key:""} -> 200; subsequent GET shows primary:null.
              L. PUT unknown provider 'bogusco' -> 400 "Unknown provider 'bogusco'.".
              M. PUT unknown model 'claude-not-real' for anthropic -> 400 "Unknown model ...".
              N. PUT unknown fallback_model 'claude-moon-42' -> 400 "Unknown fallback model ...".
              O. POST /admin/settings/test slot=adhoc with the invalid anthropic key -> HTTP 200
                 {ok:false, provider:'anthropic', model:'claude-opus-4-6', error_category:'auth'}.
                 Error body references Anthropic's 401 response. Acceptable per brief.
              P. POST /admin/settings/test slot=adhoc with unknown provider 'nobody' -> HTTP 200
                 {ok:false, error_category:'other', error:"Unknown provider 'nobod<redacted>'"}.
                 The api_key value was properly redacted from the error message.
              Q. POST /admin/settings/test-fallback -> 200 {ok:true, latency_ms:3548,
                 provider:'emergent', model:'claude-opus-4-6'} — real round-trip through
                 emergentintegrations + Claude Opus 4.6. Matches the configured fallback_model.
              R. Regression — POST /api/sessions still 201 with UUID session_id + XXXX-XXXX
                 resume_code; GET /api/sessions/resume/{code} still 200.
              S. Raw api_key 'sk-ant-testkey-ABC123XYZ' NEVER appears in any response body
                 (GET /admin/settings, PUT /admin/settings, /api/openapi.json).
              T. Password 'test1234' NOT present in /var/log/supervisor/backend.{out,err}.log.
                 Raw api_key NOT present in those logs either.
              U. /api/docs returns 200 (Swagger UI). /api/openapi.json lists all 11 endpoints:
                 POST /api/admin/auth/login, POST /api/admin/auth/logout, GET /api/admin/auth/me,
                 GET /api/admin/settings, PUT /api/admin/settings, POST /api/admin/settings/test,
                 POST /api/admin/settings/test-fallback, POST /api/sessions, GET
                 /api/sessions/resume/{resume_code}, PATCH /api/sessions/{session_id}/stage,
                 GET /api/sessions/{session_id}.

            Note on test harness: the login cookie is (correctly) marked Secure, so
            requests.Session cannot replay it over http://localhost. The harness extracts
            the JWT from Set-Cookie and sends it via an explicit Cookie header on every
            subsequent authed call. Real browsers on the HTTPS preview URL replay the cookie
            automatically — this is a test-harness workaround, not a server bug.

            No code changes were made during testing. No 500s observed. No secret leaks.
            All high-priority Phase 3 tasks are green.
    - agent: "testing"
      message: |
        Phase 2 backend verification complete. Ran /app/backend_test.py against the public
        ingress URL (https://farm-readiness.preview.emergentagent.com/api). 31/31 assertions
        passed.
          A. Happy path (4/4): POST /api/sessions -> 201; UUID session_id; resume_code matches
             ^[A-Z0-9]{4}-[A-Z0-9]{4}$ (e.g. 'P5VS-QRZT'); stage='identity'.
          B. Input validation (7/7): missing consent, consent=false, missing name, empty name,
             whitespace-only name, invalid email, and malformed JSON all return 422 with a
             `detail` key — no 500s.
          C. Resume (3/3): GET /sessions/resume/{code} with and without the dash both 200 and
             return {session_id, stage, participant}; unknown code returns 404 with exact body
             {"detail": "Resume code not found."}.
          D. Stage transitions (7/7): identity->context->psychometric->ai-discussion->scenario
             ->processing->results all 200 with {stage, updated_at}. On reaching 'results' the
             session record gets status='completed', completed_at set, and expires_at exactly
             completed_at + 60 days (verified by parsing ISO timestamps, delta = 60d ± <2s).
             Back by 1 (psychometric->context) 200. Stay (context->context) 200. Skip
             (context->scenario) -> 400 with "Invalid stage transition ... Only move one stage
             forward, stay, or go back one stage." Unknown stage 'bananas' -> 422 with
             literal_error. PATCH on bogus session id -> 404 "Session not found."
          E. GET /sessions/{id} (4/4): Returns all 15 expected fields; participant matches the
             submitted payload; defaults answers=[], conversation=[], scenario_responses={},
             deliverable=null, scores=null, archived=false. Bogus id -> 404.
          F. Rate limiting (2/2): 10 consecutive POSTs from X-Forwarded-For=198.51.100.77 all
             201, 11th returned 429 with detail "Too many sessions from this IP. Limit is 10
             per hour."
          G. Log hygiene (1/1): tail -n 2000 /var/log/supervisor/backend.out.log shows zero
             INFO-level lines containing our test email (@example.com) or the participant name
             "Alice Whittaker". DEBUG logging of participant is used in code but INFO is clean.
          H. Docs (2/2): /api/docs returns 200 with Swagger UI; /api/openapi.json lists all 4
             endpoints (POST /api/sessions, GET /api/sessions/resume/{resume_code},
             PATCH /api/sessions/{session_id}/stage, GET /api/sessions/{session_id}).
        No code changes were made. All priority-high backend tasks are working; nothing is
        stuck. Main agent can proceed with Phase 3.


    - agent: "testing"
      message: |
        Phase 8 backend sweep: 48/49 assertions PASS. See the
        "Admin dashboard + lifecycle + exports (Phase 8)" task's
        status_history for the full letter-coded detail (A, B1-B8, C1-C2,
        D1-D4, E1-E5, F1-F2, G1, H1-H5, I1-I4, J1-J3, K1-K6, L1-L7, M, N).

        ONE FAILURE — privacy regression on public GET /api/sessions/{id}:

        D3 FAIL. The public participant-safe session endpoint at
        server.py:369-379 now leaks three Phase-8-added admin fields:
          - admin_notes           (explicitly forbidden in the spec)
          - last_admin_viewed_at  (admin-only lifecycle metric)
          - synthesis.{provider,model,fallbacks_tried,…}
                                  (admin internals — the Phase 5 J fix
                                   stripped these from conversation[]
                                   turns only; the top-level synthesis
                                   sub-document is a separate object)

        Also exposed (borderline — probably wanted suppressed too):
        hard_delete_at, deleted_at, redacted.

        Root cause: SessionOut model uses
          model_config = ConfigDict(extra="allow")
        (server.py:214) and the handler only explicitly nulls scores,
        deliverable, and strips assistant-turn internals from the
        conversation array. New Phase-8 fields pass through untouched.

        REMEDIATION — small targeted patch in server.py:get_session:
          doc.pop("admin_notes", None)
          doc.pop("last_admin_viewed_at", None)
          doc.pop("synthesis", None)
          doc.pop("deleted_at", None)
          doc.pop("hard_delete_at", None)
          doc.pop("redacted", None)
        before constructing SessionOut. Admin endpoints already expose
        these fields separately so no admin functionality breaks.

        Everything else green:
          - All 9 new admin endpoints 401-gated (A).
          - List search/filter/pagination/sort all honoured; filters_applied
            shape correct; include_deleted toggle works (B1-B8).
          - last_admin_viewed_at stamps on every admin GET (C1).
          - Archive toggle correctly clears expires_at + hard_delete_at on
            archive-true and restores expires_at = completed_at + 60d on
            archive-false (D1-D2). Notes >2000 chars → 422 (D4).
          - Soft delete scrubs PII, preserves scores/deliverable/
            conversation/scenario responses, sets redacted=true and
            hard_delete_at = +30d (E1-E5).
          - Restore within grace → ok; participant stays "(redacted)"
            (F1-F2). Restore past grace → 409 (G1).
          - Lifecycle cron full cycle: forced soft-delete pass, redaction
            confirmed, forced hard-delete pass, follow-up GET → 404
            (H1-H4). Manual endpoint documented as force=True (H5).
          - Conversation MD/JSON downloads correct Content-Type,
            Content-Disposition, and body (Interviewer/Participant/
            session_id). Redacted sessions use "session-{first_8}"
            filename and strip all PII (I1-I4).
          - Deliverable admin downloads PDF (%PDF-…) and MD
            (# Transformation Readiness Assessment…), works for archived
            sessions (J1-J3).
          - Dashboard summary shape complete; dimension_averages=6,
            activity_14d=14, score_distribution{navy/gold/terracotta}
            present; cache hit confirmed (identical generated_at on
            back-to-back calls) (K1-K6).
          - Regression: sessions CRUD, psychometric/next+answer,
            ai-discussion gate, scenario/state, processing/state(Ada),
            results(Ada) all intact (L1-L7).
          - OpenAPI enumerates exactly 35 /api/* paths (M).
          - Log hygiene: zero INFO-level hits of ada.test email /
            Analytical Engine Co / Chief Mathematician across
            backend.{out,err}.log, even after soft/hard-delete events
            fired. Soft-delete log format confirmed as session_id-only
            (lifecycle_service.py:80) (N1).

        Test harness note: used the public REACT_APP_BACKEND_URL host
        since the admin cookie is Secure. Fresh X-Forwarded-For on
        regression POST /sessions to sidestep the per-IP rate limit.
        Three fresh seeded sessions consumed for soft-delete / restore /
        lifecycle cycles — all either restored or hard-deleted by end of
        run; Ada session left intact with admin_notes +
        last_admin_viewed_at cleaned up.

        Main agent: please address the D3 leak (small handler patch).
        Everything else is ready to ship.


    - agent: "testing"
      message: |
        D3 re-verification PASS after the surgical fix to get_session
        (server.py:371-396). 18/18 assertions green on
        https://farm-readiness.preview.emergentagent.com/api.

        Public GET /api/sessions/{Ada} now:
          - omits admin_notes, last_admin_viewed_at, deleted_at,
            hard_delete_at, redacted
          - scores=null, deliverable=null
          - synthesis = exactly {status, started_at, completed_at}
            (no provider / model / fallbacks_tried / error)

        Admin GET /api/admin/sessions/{Ada} still exposes the full set
        (admin_notes, last_admin_viewed_at, synthesis internals). The
        `deleted_at` and `redacted` keys are absent on Ada because she
        was never soft-deleted — admin_get_session is a pass-through,
        so those optional fields only materialise post-delete. Expected
        Phase-8 behaviour; admin surface untouched by the fix.

        D1/D2 archive-toggle regression also green:
          PATCH {archived:true}  -> expires_at=null, hard_delete_at=null
          PATCH {archived:false} -> expires_at restored to
                                     completed_at + exactly 60d

        Phase 8 task updated to working=true, needs_retesting=false,
        stuck_count=0. Test note was cleaned up post-run.


    - agent: "testing"
      message: |
        Phase 9 hotfix backend sweep: 62/63 assertions PASS. See the
        "Phase 9 hotfix — synthesis timeouts, terminal-status guarantee,
        admin re-synthesize" task's status_history for the full
        letter-coded detail (A, B, C1-C4, D1-D9, E0-E2.2, F1-F4).

        ONE FAILURE — audit-trail typo in the new admin re-synthesize
        endpoint:

        C4.9 FAIL. POST /api/admin/sessions/{ada}/resynthesize works
        end-to-end (202 + correct body, deliverable cleared, stage set
        to processing, synthesis flipped to in_progress + restarted_at
        stamped, worker task spawned, second-call DB read confirms all
        side-effects within ~10ms). BUT synthesis.restarted_by is
        persisted as `None` instead of "steve@org-logic.io".

        Root cause: server.py:2134 reads
          admin_email = (current or {}).get("email") if isinstance(current, dict) else None
        but the JWT payload built by create_access_token
        (auth_utils.py:35-45) stores the admin email in the `sub`
        claim, not `email`. Existing admin endpoints correctly read
        `current["sub"]` (e.g. /admin/auth/me at server.py:1602).

        Same bug also corrupts the audit log line — both runs in this
        sweep wrote
          INFO: Admin re-synthesis triggered session=2253141a-… by=unknown_admin
        to /var/log/supervisor/backend.err.log. So re-synthesis events
        are NOT attributable to a specific admin in operator audit logs.

        REMEDIATION (one-line fix):
          server.py:2134
          - admin_email = (current or {}).get("email") if isinstance(current, dict) else None
          + admin_email = (current or {}).get("sub") if isinstance(current, dict) else None

        Everything else green:
          - OpenAPI: exactly 36 /api/* paths; new resynthesize path
            present (A1-A2).
          - /processing/start 409 carries the new
            detail.reason ∈ {stage_mismatch, missing_inputs} shape with
            current_stage / missing[] respectively (B1-B2).
          - /admin/sessions/{id}/resynthesize 401-gated (C1), 404 on
            unknown id (C2), 409 + missing_inputs.detail.missing on a
            session with all 3 score blocks missing (C3).
          - 202 happy-path on Ada returns {status, started_at,
            poll_url}; deliverable cleared, stage=processing, synthesis
            in_progress with restarted_at stamped (C4.1-C4.11 except
            C4.9 above). Synthesis itself completed cleanly out-of-band
            in ~137s with claude-opus-4-6 fallbacks_tried=0; Ada now
            has a fresh deliverable.
          - Regression: POST /sessions, PATCH /stage, psychometric
            next/answer, ai-discussion/state, scenario/state, admin
            GET/PATCH on Ada, admin/dashboard/summary, admin/lifecycle/
            run all 200 (D1-D9).
          - Privacy regression on public GET /api/sessions/{Ada}:
            admin_notes / last_admin_viewed_at / deleted_at /
            hard_delete_at / redacted all absent; synthesis reduced to
            exactly {status, started_at, completed_at} with provider /
            model / fallbacks_tried / error / restarted_by /
            restarted_at all stripped. The Phase-8 D3 fix holds
            cleanly under the new Phase-9 fields (E0-E2.2).
          - Log hygiene: INFO trigger marker present (F1), zero hits of
            ada.test@example.co.uk / "Analytical Engine Co" at INFO/
            WARN/ERROR level, zero sk-emergent-/sk-ant-/sk-proj-
            fragments in logs (F3-F4). No full LLM prompts logged at
            INFO. (F2 substring match passed against stale Phase-3
            log lines — the actual Phase-9 audit lines read
            `by=unknown_admin` per the C4.9 bug.)

        Test harness notes:
          - Internal base http://localhost:8001/api per the brief.
          - Admin JWT extracted from Set-Cookie and replayed via
            explicit Cookie header (Secure cookie can't replay over
            http://localhost via requests.Session).
          - Three fresh sessions consumed (B1 / B2 / D1 regression).
            None require cleanup.
          - Ada session was left mid-resynth at end of C4; completed
            cleanly in ~137s out-of-band.

        Main agent: please apply the one-line `email` → `sub` fix at
        server.py:2134 and bounce the backend. The synthesis worker
        pipeline (timeouts, registry, finally-clause guarantee, /processing/
        start 409 reason shape, public-surface privacy filter) is
        otherwise solid.
