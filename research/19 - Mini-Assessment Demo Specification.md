# Mini-Assessment Demo Specification

## Purpose

A working demonstration of the Transformation Readiness Assessment methodology that allows Jonathan, Betty, or any prospective client to *experience* the assessment first-hand. This is not a simulation of results—it's an actual assessment that produces a real, personalised profile.

---

## Design Principles

### 1. Experience Over Explanation
The demo should demonstrate through doing, not describing. Participants complete actual assessment components and receive genuine analysis of their responses.

### 2. Quality Over Comprehensiveness
Better to assess 4-6 dimensions brilliantly than all 16 superficially. Focus on the Adaptive Capacity cluster (30% weighting) plus AI Fluency (the differentiator).

### 3. Integration Is The Point
The compelling moment is when multiple inputs synthesise into coherent insight. Each component must feed the final output meaningfully.

### 4. Human-In-The-Loop Narrative
The output should explicitly reference that production assessments include expert assessor review. This is honest (matches actual methodology) and provides cover for AI limitations.

### 5. Respect Their Time
35-45 minutes maximum. Executives won't tolerate longer for a demo. Every minute must earn its place.

---

## Assessment Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    MINI-ASSESSMENT DEMO                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐                                                │
│  │  WELCOME    │  Context setting, consent, instructions        │
│  │  (2 min)    │  What they'll experience and why               │
│  └──────┬──────┘                                                │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────┐                                                │
│  │ PSYCHOMETRIC│  20 items: Learning Agility (12)               │
│  │  (8-10 min) │  + Tolerance for Ambiguity (8)                 │
│  └──────┬──────┘                                                │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────┐                                                │
│  │ AI FLUENCY  │  Structured conversation with AI interviewer   │
│  │ DISCUSSION  │  5 topic areas, ~10-12 exchanges               │
│  │ (12-15 min) │                                                │
│  └──────┬──────┘                                                │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────┐                                                │
│  │  SCENARIO   │  Strategic scenario: read, respond, curveball  │
│  │  RESPONSE   │  Tests cognitive flexibility + systems thinking│
│  │ (10-12 min) │                                                │
│  └──────┬──────┘                                                │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────┐                                                │
│  │  SYNTHESIS  │  AI integration of all inputs                  │
│  │  (30 sec)   │  "Analysing your responses..."                 │
│  └──────┬──────┘                                                │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────┐                                                │
│  │   OUTPUT    │  Personalised profile with scores, evidence,   │
│  │   REPORT    │  development recommendations                   │
│  └─────────────┘                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Dimensions Assessed

This demo focuses on 6 of the 16 dimensions:

| Dimension | Cluster | Weight | Assessment Method |
|-----------|---------|--------|-------------------|
| Learning Agility | Adaptive Capacity | 8% | Psychometric |
| Tolerance for Ambiguity | Adaptive Capacity | 7% | Psychometric |
| Cognitive Flexibility | Adaptive Capacity | 8% | Scenario (belief revision) |
| Self-Awareness Accuracy | Adaptive Capacity | 7% | Psychometric self-insight items + AI discussion |
| AI Fluency | Future Leadership | 7% | AI Discussion |
| Systems Thinking | Future Leadership | 6% | Scenario (interdependency recognition) |

**Total coverage:** 43% of framework weighting — enough to produce meaningful profile.

---

## Component Specifications

Detailed specifications for each component are in separate documents:

- [[20 - Psychometric Items]] — Learning Agility and Ambiguity Tolerance scales
- [[21 - AI Fluency Interviewer]] — System prompt, topic areas, scoring rubric
- [[22 - Strategic Scenario]] — Scenario content, curveball, scoring criteria
- [[23 - Synthesis Prompt]] — Integration logic for final output

---

## Output Specification

### Report Structure

The final output should include:

**1. Executive Summary**
- Overall Transformation Readiness indication (not full score—acknowledge demo scope)
- 2-3 key strengths identified
- 1-2 development areas

**2. Dimension Profiles**
For each of the 6 assessed dimensions:
- Score (1-5 scale)
- Confidence level (High/Medium/Low based on evidence strength)
- Evidence summary (specific quotes or response patterns)
- What this means for transformation readiness

**3. Self-Awareness Insight**
- Where self-perception aligned with observed behaviour
- Potential blind spots identified

**4. AI Fluency Deep Dive**
- Detailed breakdown of the 5 AI Fluency components
- Specific quotes demonstrating understanding or gaps
- Comparison to "what good looks like"

**5. Development Recommendations**
- Priority development areas based on gaps
- Suggested interventions (coaching, experience, training)
- What would move scores

**6. Methodology Note**
Brief explanation that:
- This is 6 of 16 dimensions
- Full assessment includes 360 feedback, additional simulations, structured interview
- Production reports undergo expert assessor review

---

## Visual Design Guidance

### Aesthetic
- Clean, executive-appropriate (McKinsey/Bain reference)
- Navy blue primary, white background, gold/amber accents
- Professional typography
- Generous whitespace

### Data Visualisation
- Radar/spider chart for dimension scores
- Progress bars or gauges for individual dimensions
- Colour coding: Green (4-5), Amber (3-3.9), Red (<3)

### Tone
- Direct but not harsh
- Evidence-based, not vague
- Developmental, not judgmental
- Sophisticated, not simplistic

---

## Candidate Experience Considerations

### Before Starting
- Clear time estimate (35-45 minutes)
- What to expect from each component
- Privacy/data handling statement (demo context)
- "This is a real assessment" framing

### During Assessment
- Progress indicator throughout
- Ability to pause/resume (if technically feasible)
- No "wrong answers" reassurance for psychometrics
- Natural conversation feel for AI discussion

### After Completion
- Immediate results (no waiting)
- Option to download/save report
- "Want to learn more about full assessment" CTA

---

## Testing Checklist

Before showing to Jonathan and Betty:

- [ ] Complete full assessment as participant
- [ ] Check synthesis coherence (does output reference all components?)
- [ ] Test edge cases (very short responses, unusual answers)
- [ ] Verify scoring logic produces sensible results
- [ ] Read output aloud—does it sound intelligent?
- [ ] Time the full experience (target: 35-45 min)
- [ ] Test on mobile (will they access on phone?)
- [ ] Have Claire complete it and review output

---

## Fallback Handling

If something breaks during demo:

| Issue | Fallback |
|-------|----------|
| AI discussion goes off-track | Built-in redirect prompts in interviewer |
| Synthesis produces weak output | Template sections that always appear |
| Scoring seems wrong | "Preliminary indication" language, human review caveat |
| Technical failure | Static sample report available |

---

## Success Criteria

The demo succeeds if Jonathan and Betty:

1. **Experience the methodology** — not just see outputs
2. **Recognise themselves** in the profile produced
3. **See AI adding value** — not just automation
4. **Believe it can scale** to 1,000 leaders
5. **Want the full assessment** for themselves or others

---

## Related Documents

- [[14 - Prototype Specification]] — Full prototype design (reference)
- [[12 - The Capability Architecture]] — Complete framework
- [[13 - Assessment Methodology]] — Full methodology
- [[20 - Psychometric Items]] — Scale items
- [[21 - AI Fluency Interviewer]] — Discussion prompt
- [[22 - Strategic Scenario]] — Scenario content
- [[23 - Synthesis Prompt]] — Integration logic

---

*Last updated: June 2025*
*For: Mini-Assessment Demo Build*
