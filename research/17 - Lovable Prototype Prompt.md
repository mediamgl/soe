# Lovable Prototype Prompt

## Instructions for Building the Assessment Demo

Copy the prompt below into Lovable to generate the prototype. You may need to iterate with follow-up prompts to refine specific sections.

---

## Primary Prompt

```
Build a professional web application for an executive leadership assessment platform called "Transformation Readiness Assessment" designed for Indonesian state-owned enterprise (SOE) leaders.

The app should demonstrate the following:

## 1. LANDING PAGE
- Clean, executive-appropriate design (think McKinsey/Bain aesthetic)
- Headline: "Transformation Readiness Assessment"
- Subhead: "Assessing leadership capability for Indonesia's 2030+ ambitions"
- Brief description of the assessment purpose
- "Begin Demo" button

## 2. ASSESSMENT OVERVIEW PAGE
Show the assessment structure:

Four capability clusters displayed as cards:
- Adaptive Capacity (30%) - Learning Agility, Cognitive Flexibility, Tolerance for Ambiguity, Self-Awareness Accuracy
- Future Leadership (25%) - AI Fluency, Hybrid Workforce Capability, Systems Thinking, Generational Intelligence
- Contextual Navigation (25%) - Political Acumen, Stakeholder Orchestration, Cultural Adaptability, Long-Term Orientation  
- Transformation Execution (20%) - Change Leadership, Institutional Building, Governance Capability, Results Under Ambiguity

Show the assessment methods:
- Psychometric Assessment (2 hours)
- 360-Degree Feedback (1 week collection)
- Strategic Simulation (90 min)
- Crisis Decision Simulation (60 min)
- Structured Behavioural Interview (90 min)

Timeline: ~3 weeks end-to-end

"View Sample Results" button

## 3. CANDIDATE JOURNEY PAGE
Interactive timeline/stepper showing:
- Day 0: Invitation & Briefing
- Days 1-7: 360 Rater Collection
- Day 8: Psychometric Assessment (remote)
- Day 15: Assessment Day (simulations + interview)
- Days 16-21: Integration & Analysis
- Day 22: Feedback Session

Each step expandable to show details

## 4. SAMPLE RESULTS DASHBOARD
Show a fictional completed assessment for "Sample Candidate" with:

Executive Summary Card:
- Overall Readiness Score: 3.7/5.0 (displayed as gauge or progress)
- Category: "High Potential"
- Visual indicator (green/amber)

Cluster Scores (spider/radar chart):
- Adaptive Capacity: 4.0
- Future Leadership: 3.2
- Contextual Navigation: 3.9
- Transformation Execution: 3.6

Key Strengths (bulleted):
- Exceptional learning agility (4.3)
- Strong systems thinking (4.1)
- Solid political acumen (3.9)

Development Priorities (bulleted):
- AI fluency requires significant development (2.4)
- Self-awareness accuracy shows moderate gap (2.9)

Role Implications text box:
"Well-suited for transformation leadership with AI-fluency development support and executive coaching for self-awareness development."

## 5. DETAILED DIMENSION VIEW
Clicking on a cluster shows all dimensions within it:
- Dimension name
- Score (1-5 scale, visual bar)
- Confidence level (High/Medium/Low)
- Brief evidence summary (1-2 sentences)
- "View Full Analysis" button (can be non-functional)

## 6. SELF-AWARENESS ANALYSIS PAGE
Show comparison between Self-Rating and 360 Others' Rating:
- Bar chart comparing self vs others across dimensions
- Highlight gaps > 0.5 points
- "Blind Spots Identified" section
- "Development Implications" section

## DESIGN REQUIREMENTS
- Professional, executive-appropriate aesthetic
- Colour scheme: Navy blue primary, white background, gold/amber accents
- Clean typography (Inter or similar)
- Responsive design
- Subtle animations for polish
- Charts should use a professional charting library look

## NAVIGATION
- Persistent top nav: Overview | Journey | Sample Results | About
- Logo placeholder top left: "TRA" (Transformation Readiness Assessment)

Generate this as a complete, shareable web application.
```

---

## Follow-Up Prompts (if needed)

### To improve the charts:
```
Make the radar/spider chart larger and more prominent on the results page. Use smooth lines and filled area with transparency. Add hover states showing exact values.
```

### To add more detail to dimensions:
```
Add a modal or expandable section for each of the 16 dimensions showing:
- Full definition
- What HIGH looks like (3 bullet points)
- What LOW looks like (3 bullet points)
- Assessment methods used for this dimension
```

### To add the prototype specification detail:
```
Add a "Methodology" page accessible from the nav that explains:
- The hybrid AI-human assessment approach
- How psychometrics, simulation, interview, and 360 combine
- Quality assurance processes
- A brief section on validity commitment
```

### To add comparison view:
```
Add a "Cohort View" page showing how a candidate compares to:
- Overall benchmark (all assessed leaders)
- Sector benchmark (leaders in same industry)
- Top quartile performers
Use distribution curves or box plots.
```

### To polish the look:
```
Make the design more premium:
- Add subtle gradient backgrounds
- Use card shadows consistently
- Add micro-interactions on buttons
- Ensure consistent spacing (8px grid)
- Add a professional footer with copyright
```

---

## After Building

Once Lovable generates the prototype:

1. **Review** - Check all pages render correctly
2. **Adjust** - Use follow-up prompts to refine
3. **Add content** - You may want to manually edit text to match exact wording
4. **Test sharing** - Get the shareable link
5. **Preview on mobile** - Ensure it looks good for executives viewing on phones

---

## Sharing with Jonathan and Betty

When sharing, include context:

> "This is a working prototype of the assessment framework we discussed. It shows the candidate journey, capability architecture, and sample output format. The underlying methodology is detailed in the research documents—this demonstrates what participants and reviewers would experience."

---

*Last updated: April 2026*
*Research conducted by: Steven Bianchi*
*For: Indonesia SOE leadership assessment*

**Confidential and restricted.** This research material is provided solely for authorised use and is not licensed for any other use. No part of this material may be used, reproduced, distributed, disclosed, or adapted outside the agreed scope without the prior written consent of the author. All rights reserved.
