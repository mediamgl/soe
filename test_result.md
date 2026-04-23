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
  version: "0.2.0-phase2"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Phase 2 complete. Acceptance criteria 1-10 all met. Backend has 4 new session endpoints
        all under /api with pydantic validation and are visible in /api/docs. Frontend has a new
        /start page, a Resume modal on /, a Save & exit button on /assessment/*, and a Zustand
        store that hydrates from localStorage (sessionId+resumeCode only, no PII). Mongo
        `sessions` collection has the exact schema per spec with unique index on resume_code and
        compound index on status+expires_at. No PII appears in INFO logs (verified via grep).
        Methodology content inventory delivered separately in the main chat; documents 19, 20,
        21, 22 are all present and usable verbatim in Phase 4/5/6. Document 23 (Synthesis Prompt)
        is referenced but MISSING from the repo — this is the one real gap and will need to be
        authored before Phase 7.
        For Phase 5 AI Fluency Discussion: Claude Opus 4.6 IS available via emergentintegrations
        as `claude-opus-4-6`. Documented for later.
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

