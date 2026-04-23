# Psychometric Items

## Overview

This document contains the psychometric items for the mini-assessment demo, measuring two dimensions from the Adaptive Capacity cluster:

1. **Learning Agility** (12 items)
2. **Tolerance for Ambiguity** (8 items)

Total: 20 items, approximately 8-10 minutes to complete.

---

## Response Scale

All items use a 6-point Likert scale (no neutral midpoint to force discrimination):

| Value | Label |
|-------|-------|
| 1 | Strongly Disagree |
| 2 | Disagree |
| 3 | Slightly Disagree |
| 4 | Slightly Agree |
| 5 | Agree |
| 6 | Strongly Agree |

---

## Learning Agility Scale (12 Items)

Based on research from Korn Ferry, CCL, and academic learning agility literature. Items assess the five components of learning agility.

### Mental Agility (Items 1-3)

**LA01** — I enjoy tackling problems that don't have obvious solutions.

**LA02** — When facing a complex issue, I naturally look for connections to other domains or experiences.

**LA03** — I'm comfortable holding multiple contradictory ideas while working toward a resolution.

### People Agility (Items 4-5)

**LA04** — I can quickly adjust my communication style when I notice it's not landing with someone.

**LA05** — I actively seek perspectives from people who see the world differently than I do.

### Change Agility (Items 6-8)

**LA06** — I volunteer for assignments where I'll need to learn something new.

**LA07** — I find the uncertainty of new situations more energising than stressful.

**LA08** — When an approach isn't working, I'm quick to try something different rather than persisting.

### Results Agility (Items 9-10)

**LA09** — I've delivered strong results in situations where I had no established playbook to follow.

**LA10** — When facing obstacles, I find ways to make progress even without ideal resources or support.

### Self-Awareness (Items 11-12)

**LA11** — I have a clear picture of which situations bring out my best and worst performance.

**LA12** — Feedback that challenges my self-image makes me curious rather than defensive.

---

## Tolerance for Ambiguity Scale (8 Items)

Based on academic ambiguity tolerance research (Budner, McLain, and subsequent work). Items assess comfort with uncertainty, complexity, and incomplete information.

### Uncertainty Comfort (Items 13-15)

**TA01** — I can make decisions confidently even when I don't have all the information I'd like.

**TA02** — When plans are unclear, I maintain my effectiveness rather than becoming anxious.

**TA03** — I'm comfortable committing to a direction while knowing I might need to change course.

### Complexity Comfort (Items 16-17)

**TA04** — I'm drawn to problems with many interacting factors rather than simple cause-and-effect situations.

**TA05** — When facing a messy, ill-defined situation, I can identify where to start without needing to see the whole path.

### Closure Resistance (Items 18-20)

**TA06** — I can tolerate unresolved issues without forcing premature conclusions.

**TA07** — When others push for quick answers, I'm comfortable saying "we don't know yet."

**TA08** — I'd rather sit with uncertainty than accept a false certainty just to feel settled.

---

## Scoring Logic

### Item-Level Scoring

All items are positively worded. No reverse scoring required.

Raw score = sum of item responses (1-6)

### Dimension-Level Scoring

**Learning Agility:**
- Raw score range: 12-72
- Calculate mean: raw score ÷ 12
- Convert to 1-5 scale: (mean - 1) × (4/5) + 1

**Tolerance for Ambiguity:**
- Raw score range: 8-48
- Calculate mean: raw score ÷ 8
- Convert to 1-5 scale: (mean - 1) × (4/5) + 1

### Score Interpretation

| Score | Category | Interpretation |
|-------|----------|----------------|
| 4.5-5.0 | Exceptional | Top quartile; clear strength |
| 3.5-4.4 | Strong | Above average; solid capability |
| 2.5-3.4 | Moderate | Average; development opportunity |
| 1.5-2.4 | Limited | Below average; significant development needed |
| 1.0-1.4 | Low | Significant gap; may be difficult to develop |

---

## Sub-Score Analysis (Learning Agility)

For richer output, calculate sub-scores for Learning Agility components:

| Component | Items | Score Range | Interpretation Focus |
|-----------|-------|-------------|---------------------|
| Mental Agility | LA01-LA03 | 1-5 | Cognitive complexity comfort |
| People Agility | LA04-LA05 | 1-5 | Interpersonal adaptability |
| Change Agility | LA06-LA08 | 1-5 | Openness to new experiences |
| Results Agility | LA09-LA10 | 1-5 | First-time situation performance |
| Self-Awareness | LA11-LA12 | 1-5 | Accuracy of self-perception |

---

## Self-Awareness Accuracy Indicator

Items LA11 and LA12 specifically address self-awareness. Additionally, we can derive a "self-awareness accuracy" indicator by comparing:

1. **Stated self-awareness** (LA11-LA12 scores)
2. **Demonstrated self-awareness** (from AI Fluency discussion—does their self-assessment align with their demonstrated capability?)

If someone scores high on "I have a clear picture of my strengths/weaknesses" but demonstrates blind spots in the AI discussion, this indicates a self-awareness gap.

---

## Presentation Guidance

### Instructions to Participant

> The following statements describe how people approach different situations. For each statement, indicate how much you agree or disagree based on how you actually are—not how you think you should be.
>
> There are no right or wrong answers. The value of this assessment depends on honest self-reflection.
>
> Work quickly—your first instinct is usually most accurate.

### Item Presentation

- One item per screen (mobile-friendly)
- Progress indicator showing completion
- No "back" button (to prevent overthinking)
- Randomise item order within each scale

### Timing

- Target: 20-30 seconds per item
- If participant spends >60 seconds on item, subtle prompt to move on
- Total section: 8-10 minutes

---

## Validation Notes

These items are adapted from validated scales but have been reworded for this context. For production use, consider:

1. Licensing existing validated instruments
2. Running validation study on adapted items
3. Establishing norms against relevant population

For demo purposes, the items are sufficiently robust to produce meaningful differentiation and face-valid results.

---

## Data Captured

For each participant, store:

- Individual item responses (1-6)
- Response times per item (for analysis)
- Dimension scores (calculated)
- Sub-scores (for Learning Agility)
- Timestamp of completion

This data feeds into the Synthesis Prompt alongside AI Discussion and Scenario data.

---

## Related Documents

- [[19 - Mini-Assessment Demo Specification]] — Overall demo spec
- [[12 - The Capability Architecture]] — Dimension definitions
- [[23 - Synthesis Prompt]] — How these scores integrate into output

---

*Last updated: June 2025*
*For: Mini-Assessment Demo Build*
