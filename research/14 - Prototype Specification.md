# Prototype Specification

## From Framework to Instrument

This document specifies what a working prototype assessment looks like—the candidate experience, assessor protocols, AI integration points, scoring logic, and output format. This is what Jonathan and Betty would actually see.

---

## Prototype Scope

### What the Prototype Demonstrates

1. **End-to-end assessment flow** for one leader
2. **AI integration** at key points
3. **Core methodology** (psychometrics, simulation, interview, 360)
4. **Output format** showing actionable insights
5. **Scalability path** for 1,000 leaders

### What the Prototype Does Not Include

1. Full psychometric instrument development
2. Complete simulation library
3. Production-ready AI models
4. Full assessor training programme
5. Enterprise system integration

---

## Candidate Journey

### Overview

```
DAY 0: INVITATION
├── Candidate receives assessment invitation
├── Briefing materials provided
└── Scheduling confirmed

DAY 1-7: PREPARATION
├── 360 raters invited
├── Documents collected
└── Pre-reading completed

DAY 8: PSYCHOMETRICS (Remote, ~2 hours)
├── Cognitive assessment
├── Personality inventory
├── Learning agility scale
└── Ambiguity tolerance scale

DAY 9-14: 360 COLLECTION
├── Raters complete surveys
├── AI analysis ongoing
└── Gaps flagged for follow-up

DAY 15: ASSESSMENT DAY (Hybrid, ~5 hours)
├── AI Fluency Discussion (45 min)
├── Strategic Scenario Simulation (90 min)
├── Crisis Decision Simulation (60 min)
├── Structured Behavioural Interview (90 min)
└── Reflection and Close (15 min)

DAY 16-21: INTEGRATION
├── AI analysis of all data
├── Human scoring and calibration
└── Report generation

DAY 22: FEEDBACK SESSION
├── Results presentation
├── Development discussion
└── Next steps
```

---

## Component Specifications

### 1. Psychometric Battery

**Cognitive Assessment (45 min)**
- Fluid intelligence: Pattern recognition, abstract reasoning
- Working memory: Information manipulation
- Processing speed: Rapid accurate decisions

*AI Role: Scoring, norming, anomaly detection*

**Personality Inventory (30 min)**
- Big Five dimensions
- Focus on: Openness, Conscientiousness, Emotional Stability
- Facet-level analysis

*AI Role: Scoring, profile comparison, risk flagging*

**Learning Agility Scale (25 min)**
- Mental agility items
- People agility items
- Change agility items
- Results agility items
- Self-awareness items

*AI Role: Scoring, dimensional profile*

**Ambiguity Tolerance Scale (15 min)**
- Discomfort with uncertainty items
- Need for closure items
- Comfort with complexity items

*AI Role: Scoring, benchmark comparison*

### 2. 360-Degree Feedback

**Rater Selection:**
- 3+ direct reports
- 3+ peers
- 2+ superiors/board
- Self-rating

**Survey Design:**
- 16 dimensions, 3 items each (48 items)
- Behavioural frequency scale (1-5)
- 3 open-ended questions per rater group

**AI Integration:**
- Aggregation and gap analysis
- Sentiment analysis of comments
- Pattern detection across raters
- Self-awareness accuracy calculation

### 3. AI Fluency Discussion (45 min)

**Format:** Semi-structured discussion via video

**Topics:**
1. Current AI usage (personal and organisational)
2. Understanding of AI capabilities/limitations
3. View on AI paradigms (Anthropic vs. OpenAI awareness)
4. Thinking about AI governance
5. Vision for AI in their organisation

**Scoring Rubric:**

| **Level** | **Description** |
|-----------|-----------------|
| 5 | Deep understanding; articulates nuances; sophisticated governance thinking |
| 4 | Solid understanding; aware of key distinctions; proactive about governance |
| 3 | Basic understanding; uses AI personally; limited strategic thinking |
| 2 | Surface awareness; delegates AI thinking; reactive to AI |
| 1 | Minimal awareness; dismissive or uninformed; no governance perspective |

**AI Integration:**
- Transcription
- Claim verification
- Comparison to demonstrated usage
- Sophistication scoring

### 4. Strategic Scenario Simulation (90 min)

**Scenario:** Indonesian SOE facing transformation decision

**Setup:**
> "You are the CEO of a major Indonesian SOE in [sector]. The government has announced Indonesia's ambition to become a regional hub. Your board wants a transformation strategy. You have the following information..."

**Information Provided:**
- Industry analysis (with contradictions)
- Stakeholder mapping (competing interests)
- Resource constraints
- Political dynamics

**Candidate Tasks:**
1. Analyse situation (20 min)
2. Present initial recommendation (15 min)
3. Receive new information that complicates analysis (5 min)
4. Revise recommendation (15 min)
5. Answer probing questions (20 min)
6. Stakeholder role-play (15 min)

**What We're Observing:**
- Cognitive flexibility (response to new information)
- Systems thinking (connections identified)
- Stakeholder orchestration (navigation of interests)
- Tolerance for ambiguity (comfort with incomplete data)
- Long-term orientation (time horizon of thinking)

**AI Integration:**
- Real-time behaviour coding
- Response pattern analysis
- Comparison to benchmark performances
- Cognitive load indicators

### 5. Crisis Decision Simulation (60 min)

**Scenario:** Urgent decision required with incomplete information

**Setup:**
> "An incident has occurred at one of your facilities. You have 45 minutes before you must make a public statement. Information is incomplete and evolving. Multiple stakeholders are demanding different responses..."

**Information Drip:**
- Initial situation brief (conflicting accounts)
- Updates every 10 minutes (some contradict earlier information)
- Stakeholder pressure (calls from ministry, media, employees)

**Candidate Tasks:**
1. Assess situation and prioritise
2. Make preliminary decisions
3. Update as information changes
4. Prepare and deliver statement
5. Respond to challenges

**What We're Observing:**
- Decision-making under uncertainty
- Information processing under pressure
- Communication under ambiguity
- Results orientation despite chaos

**AI Integration:**
- Time-stamped decision tracking
- Information usage analysis
- Communication analysis
- Stress indicators

### 6. Structured Behavioural Interview (90 min)

**Format:** Face-to-face or video, two interviewers

**Structure:**

| **Section** | **Time** | **Focus** |
|-------------|----------|-----------|
| Opening | 10 min | Rapport, context |
| Learning experiences | 20 min | Learning agility, cognitive flexibility |
| Change leadership | 20 min | Change leadership, resistance navigation |
| Stakeholder challenges | 15 min | Political acumen, stakeholder orchestration |
| Building and developing | 15 min | Institutional building, generational intelligence |
| Closing | 10 min | Candidate questions, next steps |

**Question Examples:**

*Learning Agility:*
> "Tell me about a time when you had to learn something completely new to succeed. How did you approach it? What was most difficult? What did you learn about how you learn?"

*Cognitive Flexibility:*
> "Describe a situation where you had to significantly change your thinking about something important. What triggered the change? How did you handle the discomfort of being wrong?"

*Change Leadership:*
> "Tell me about leading a change where you faced significant resistance. How did you understand the resistance? What did you do about it? What would you do differently?"

**AI Integration:**
- Transcription
- Behavioural coding against rubric
- Pattern matching to other data
- Follow-up question suggestions (real-time)

---

## Assessor Protocols

### Assessor Roles

| **Role** | **Responsibility** |
|----------|-------------------|
| Lead Assessor | Overall quality, integration, final scoring |
| Simulation Facilitator | Runs simulations, observes behaviour |
| Interviewer (Primary) | Conducts structured interview |
| Interviewer (Secondary) | Note-taking, follow-up probes |
| AI Analyst | Monitors AI outputs, flags issues |

### Calibration Process

Before assessment:
1. Review candidate background
2. Review prior data (360, psychometrics)
3. Align on areas to probe

After assessment:
1. Independent scoring by each assessor
2. Calibration discussion
3. AI analysis review
4. Consensus scoring
5. Report drafting

---

## Scoring Integration

### Data Flow

```
PSYCHOMETRICS ──────────┐
                        │
360 FEEDBACK ───────────┼──► AI ANALYSIS ──► HUMAN REVIEW ──► FINAL SCORES
                        │
SIMULATIONS ────────────┤
                        │
INTERVIEW ──────────────┘
```

### Dimension Scoring

For each dimension:
1. Gather evidence from all applicable methods
2. AI generates preliminary score with confidence
3. Assessors review and adjust
4. Discrepancies discussed and resolved
5. Final score with rationale

### Confidence Levels

| **Level** | **Meaning** |
|-----------|-------------|
| High | Strong convergent evidence across methods |
| Medium | Most evidence aligns; some gaps |
| Low | Limited or conflicting evidence |

---

## Output Format

### Executive Summary (1 page)

```
┌─────────────────────────────────────────────────────────┐
│              TRANSFORMATION READINESS ASSESSMENT        │
│                     [Candidate Name]                    │
│                      [Date]                             │
├─────────────────────────────────────────────────────────┤
│  OVERALL READINESS:  HIGH POTENTIAL (3.7/5.0)           │
├─────────────────────────────────────────────────────────┤
│  KEY STRENGTHS:                                         │
│  • Exceptional learning agility (4.3)                   │
│  • Strong systems thinking (4.1)                        │
│  • Solid political acumen (3.9)                         │
├─────────────────────────────────────────────────────────┤
│  DEVELOPMENT PRIORITIES:                                │
│  • AI fluency requires significant development (2.4)    │
│  • Self-awareness accuracy moderate gap (2.9)           │
├─────────────────────────────────────────────────────────┤
│  ROLE IMPLICATIONS:                                     │
│  Well-suited for transformation leadership with         │
│  AI-fluency development support and executive coach     │
│  for self-awareness development.                        │
└─────────────────────────────────────────────────────────┘
```

### Visual Profile (1 page)

Spider chart showing all 16 dimensions, with benchmark comparison.

### Cluster Details (4 pages)

One page per cluster:
- Cluster score and interpretation
- Each dimension within cluster
- Evidence highlights
- Development recommendations

### Self-Awareness Analysis (1 page)

- Self vs. 360 comparison
- Blind spots identified
- Implications

### Development Plan (2 pages)

- Priority areas
- Recommended interventions
- Timeline
- Success indicators

---

## Scalability Considerations

### For 1,000 Leaders

| **Component** | **Scaling Approach** |
|---------------|---------------------|
| Psychometrics | Fully automated; cloud platform |
| 360 | Automated; aggregated AI analysis |
| Simulations | Video-based with AI observation; human review of subset |
| Interviews | Trained assessor pool; AI-assisted coding |
| Integration | AI first pass; human calibration |
| Reporting | Automated generation; human quality check |

### Timeline for Full Population

- Wave 1 (100 leaders): Months 1-3
- Wave 2 (200 leaders): Months 4-6
- Wave 3 (300 leaders): Months 7-9
- Wave 4 (400 leaders): Months 10-12

### Resource Requirements

| **Resource** | **Quantity** |
|--------------|--------------|
| Lead Assessors | 10 |
| Simulation Facilitators | 20 |
| Interviewers | 30 |
| AI Analysts | 5 |
| Programme Management | 5 |

---

## Prototype Demonstration

### What Jonathan and Betty Would See

1. **Live demonstration** of AI fluency discussion with sample candidate
2. **Simulation walkthrough** showing behaviour observation and coding
3. **360 analysis example** showing AI pattern detection
4. **Report review** of complete assessment for demonstration candidate
5. **Platform preview** showing scalable technology

### Questions We'd Address

- How does this differ from standard competency assessment?
- What gives us confidence in predictive validity?
- How does AI integration work in practice?
- What does the candidate experience feel like?
- How would this scale to 1,000 leaders?
- What does implementation look like?

---

## Related Documents

- [[11 - Assessment Premise]] — Why we assess this way
- [[12 - The Capability Architecture]] — What we measure
- [[13 - Assessment Methodology]] — How we measure
- [[15 - Key Statistics and Data Points]] — Numbers that support the approach

---

*Last updated: April 2026*
*Research conducted by: Steven Bianchi*
*For: Indonesia SOE leadership assessment*

**Confidential and restricted.** This research material is provided solely for authorised use and is not licensed for any other use. No part of this material may be used, reproduced, distributed, disclosed, or adapted outside the agreed scope without the prior written consent of the author. All rights reserved.
