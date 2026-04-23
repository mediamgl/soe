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
