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
  version: "0.4.0-phase4"
  test_sequence: 3
  run_ui: false

test_plan:
  current_focus:
    - "Psychometric: next/answer/progress endpoints, scoring, admin read"
    - "Regression: Phase 2 + Phase 3 endpoints still pass"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

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

