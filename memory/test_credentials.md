# SOE TRA — Test / Seed Credentials

## Admin seed (configured for Phase 3 seeding; NOT wired up yet in Phase 2)
- Email:    steve@org-logic.io
- Password: test1234
- Role:     admin
- Notes:    The admin area, login, and password hashing come online in Phase 3.
            These values are captured here now so the seed script / first login
            flow can use them without asking the human again.

## Phase 2 test participants (created during verification; safe to leave in Mongo)
- Participant flows do not use passwords — they use resume codes from
  POST /api/sessions. Disposable Mongo state only; cleared when you
  drop the `sessions` collection.

## Fallback / seed code behaviour
- Resume codes are issued by the server on every POST /api/sessions
  (format: XXXX-XXXX, 8 chars, uppercase alphanumeric, stored unique in Mongo).

## Phase 7 handoff — completed session (deliverable generated, stage=results)
- session_id: 2253141a-830f-4810-a683-890f098b5664
- resume_code: 7M7A-X5F5
- Participant: Ada Lovelace / Analytical Engine Co / Chief Mathematician
- deliverable populated (category "High Potential"); synthesis via Emergent / claude-opus-4-6 (fallbacks_tried=0).
  Use this session for any additional Phase 7 verification or for Phase 8 work when authorised.

## Phase 6 handoff — completed session (scenario scored, stage=processing)
- session_id: 4d2be235-ec1f-431e-a8a6-193c493bac26
- resume_code: 7JSN-K45S
- Participant: Handoff Curl / curl.handoff@example.co.uk
- scores.scenario populated (CF=5, ST=5), via Emergent / claude-opus-4-6.
  Use this session for Phase 7 (Synthesis + Results) work when authorised.
