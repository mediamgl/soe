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
  Phase 1 of the Transformation Readiness Assessment web app (FARM stack).
  Goal: build the navigable shell — landing + context pages fully styled, plus five
  placeholder assessment stages with a 5-step progress indicator. McKinsey/Bain aesthetic
  (navy #1e3a5f, gold #d4a84b, Playfair Display + Inter, generous whitespace). No methodology
  logic yet — that is Phase 2+.

backend:
  - task: "Scaffold FastAPI backend with /api/health and /api/docs"
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
            Created /app/backend/server.py with FastAPI app, MongoDB motor client, CORS, and an /api router.
            Added GET /api/health returning {status: "ok"}. Exposed FastAPI docs at /api/docs, redoc at
            /api/redoc, openapi at /api/openapi.json (all under /api/* to match Kubernetes ingress).
            Verified via curl: /api/health=200, /api/docs=200, /api/openapi.json=200.

frontend:
  - task: "Phase 1 shell — landing, context, 5 placeholder assessment stages, progress stepper"
    implemented: true
    working: true
    file: "frontend/src/App.js, frontend/src/pages/*, frontend/src/components/*"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Scaffolded CRA+craco+Tailwind frontend from scratch. Design system: navy #1e3a5f, gold #d4a84b,
            Playfair Display (serif headings) + Inter (sans-serif body) via Google Fonts.
            Routes: /, /context, /assessment/{psychometric,ai-discussion,scenario,processing,results}.
            Progress stepper (5 steps) appears only on /assessment/* routes; hidden on / and /context.
            Hit one PostCSS issue where Tailwind directives were not being processed — fixed by using
            craco.config.js with an explicit webpack.configure that injects tailwindcss + autoprefixer
            into every postcss-loader instance. Verified end-to-end via Playwright screenshots:
              - Full forward path: / -> /context -> psych -> ai -> scenario -> processing -> results (all links work).
              - Full back path: results -> processing -> scenario -> ai -> psych -> /context (all links work).
              - Footer "Demonstration Version • Methodology by Steven Bianchi" present on every page.
              - Stepper shows correct current/complete/upcoming states.
              - Mobile 375px: no horizontal scroll (verified via scrollWidth vs clientWidth).
              - Desktop 1440px: layout matches McKinsey/Bain brief (whitespace, thin gold accents, subtle card borders).

metadata:
  created_by: "main_agent"
  version: "0.1.0-phase1"
  test_sequence: 0
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Phase 1 build complete. Scaffolded full FARM stack from scratch inside /app (the repo itself
        is the SOE Transformation Readiness Assessment repo — reference docs live in /app/research/).
        Backend: FastAPI with /api/health + /api/docs. Frontend: CRA+craco+Tailwind with 7 routes,
        5-stage progress stepper, full navigable flow. No real assessment logic yet (reserved for Phase 2).
        Verified acceptance criteria manually via Playwright screenshots at 1440px and 375px.
        Not running deep_testing_backend_v2 for Phase 1 because the only backend changes are the
        trivial /api/health endpoint and exposing FastAPI docs under /api/* — both verified via curl.
