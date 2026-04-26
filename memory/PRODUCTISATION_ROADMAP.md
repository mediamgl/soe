# Productisation Roadmap — Transformation Readiness Assessment

This document captures the path from "demo that works for invited beta testers" to "fully developed product you can sell". Maintained for Steven's reference; updated as items move between tiers.

## Tier 1 — Foundation (required before any paying client)

| Item | Why | Effort |
|------|-----|--------|
| Multi-tenancy / organisations | Real customers need their own admin accounts, session lists, branding, billing — without seeing each other's data | 1–2 weeks |
| Email infrastructure (Resend) | Already stubbed. Resume codes by email + "your report is ready" + invitation emails | 1 day |
| Audit log | Every admin action — who/what/when. Required for SOC 2 + insurance + trust | 2–3 days |
| Sentry / observability | Currently bugs surface only when a user complains | 0.5 day |
| DB backups + restore drill | Mongo currently has no backup. One pod restart = data loss | 2–3 days |
| Privacy policy + ToS + cookie banner | Legal requirement, especially with PII + LLM transcripts | 0.5 day + lawyer review |
| Per-org LLM cost cap with admin alerts | Production needs explicit daily/monthly LLM spend caps | 1–2 days |

**Tier 1 total: ~3–4 weeks of dev work + email/legal/infra setup.**

---

## Tier 2 — Product (turns it from "tool" to "product")

| Item | Why | Effort |
|------|-----|--------|
| Cohort/batch management | Invite N executives at once, track completion, send reminders, aggregate cohort results | 1–2 weeks |
| Norming / benchmarking | Percentile-based reporting against a reference pool | 1 week + ongoing data collection |
| Branded / white-label reports | Each client wants their own logo, palette, terminology on the deliverable | 3–4 days |
| Manager/stakeholder views | Different report tiers for participant vs. coach vs. executive sponsor | 1 week |
| Coach/HR dashboard | Trends over time, intervention recommendations, comparison views | 2–3 weeks |
| Email-delivered reports with expiring links | Tokenised links to participants and stakeholders | 2–3 days |
| Pricing / Stripe integration | Per-seat or per-cohort billing | 3–5 days |

**Tier 2 total: ~6–8 weeks.**

---

## Tier 3 — Methodology (the moat)

| Item | Why |
|------|-----|
| Validation study | Run 200+ pilot sessions, factor analysis, Cronbach's alpha, convergent/divergent validity. Required for credibility |
| Test–retest reliability | Same participants 3–6 months apart |
| Full 16-dimension instrument | Currently shipping the 6-dimension mini-demo (Doc 19); the full version is the upsell (Doc 14) |
| Bias / fairness assessment | Gender, culture, industry — required for any employment-adjacent use |
| White paper / peer-reviewed publication | Authority signal — HBR, MIT Sloan, or major consulting insights piece |

**Tier 3 effort: months, not weeks. Mostly Steven's time + a research collaborator.**

---

## Tier 4 — Scale (only when you need it)

- Multi-replica backend + Redis-shared rate limit/cache
- Queue-based synthesis (Celery/RQ) — fixes the LiteLLM event-loop blocking
- CDN for static assets
- Multi-region for international latency
- Auto-scaling
- Read replicas on Mongo
- 2FA for admins
- SSO / SAML for enterprise

**Tier 4 total: 4–6 weeks when needed. Don't build pre-emptively.**

---

## Recommended sequencing

**Track A — Engineering (6–8 weeks of focused dev)**

1. Tier 1 foundation (~3–4 weeks)
2. Highest-value Tier 2 items: cohorts + branded reports + email delivery (~3–4 weeks)
3. Park the rest of Tier 2 until customer-funded signal on priorities

**Track B — Methodology (Steven's time, ongoing in parallel)**

1. Pilot study design with 200+ participants
2. Validate v2 instrument and write up
3. Author synthesis prompt for the full 16-dim version

---

## What NOT to do

- No pre-emptive Tier 4 scale infrastructure
- No voice/multi-modal until customer demand
- No internationalisation until a beachhead market is identified
- No HIPAA/SOC 2 certification until a real customer is asking

---

## Quick wins available right now

- Wire Resend (~30 min) — eliminates manual resume-code loop
- Set up Sentry (~30 min, free tier) — catches future bugs proactively
