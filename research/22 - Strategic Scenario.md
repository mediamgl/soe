# Strategic Scenario

## Overview

This document specifies the strategic scenario component of the mini-assessment demo. The scenario assesses **Cognitive Flexibility** (belief revision, adaptive response) and **Systems Thinking** (interdependency recognition, effect anticipation).

The design follows a Read → Respond → Curveball → Revise structure that reveals how participants handle new information that challenges their initial analysis.

---

## Scenario Design Principles

1. **No "right answer"** — Multiple viable approaches exist; we assess reasoning quality, not conclusion
2. **Genuine ambiguity** — Information is incomplete and partly contradictory
3. **Stakeholder complexity** — Multiple interests that can't all be satisfied
4. **Curveball matters** — The revision reveals more than the initial response
5. **Time-boxed** — Forces prioritisation under constraint

---

## The Scenario

### Context Setting (shown before scenario)

> You're about to read a strategic scenario. Take 3-4 minutes to read and analyse, then you'll have 4-5 minutes to write your initial recommendation. After that, you'll receive new information and have 3-4 minutes to revise.
>
> This isn't about industry knowledge—it's about how you analyse complex situations and adapt your thinking. There's no single right answer.

---

### Part 1: Initial Scenario

**Scenario: Meridian Energy Holdings**

Meridian Energy Holdings is a state-owned enterprise (SOE) with 12,000 employees, operating power generation and distribution across a developing economy. The government has announced an ambitious national goal: achieve 50% renewable energy by 2032 (currently at 18%) while simultaneously reducing electricity costs by 15% to support industrial growth.

You are the CEO of Meridian. Your board meets in two weeks to approve your strategic direction.

**The situation:**

**Financial Position**
- Current debt-to-equity ratio: 2.1x (high for the sector)
- Operating margin: 8% (sector average: 12%)
- Government has signalled no additional capital injection; must self-fund transformation
- Credit rating at risk of downgrade if margins decline further

**Workforce**
- 60% of workforce in thermal generation (coal/gas plants)
- Average age: 47; average tenure: 18 years
- Strong union presence; previous restructuring attempt in 2019 triggered strikes
- Limited internal capability in renewable technologies

**Market Dynamics**
- Two private competitors have announced major renewable investments
- Industrial customers beginning to explore "green supply" contracts with competitors
- Distributed solar growing rapidly; threatens traditional distribution revenue
- Government considering unbundling generation from distribution (regulatory uncertainty)

**Stakeholder Landscape**
- Ministry of Energy: Focused on renewable targets; will judge your performance on 2032 goal
- Ministry of Finance: Focused on fiscal impact; wants reduced government exposure
- Ministry of Labour: Concerned about job losses; election in 18 months
- Local communities: Depend on existing plants for employment and economic activity
- Board: Three ministry appointees, two independent directors, one employee representative

**Recent Data Points**
- Internal analysis suggests renewable transition requires $2.3B investment over 8 years
- Workforce reskilling estimated at $180M; timeline 4-5 years for meaningful capability shift
- Competitor announced partnership with international renewable developer
- Employee survey shows 67% "concerned" about job security; 43% would consider early retirement if offered

---

**Your Task (Part 1)**

Write your strategic recommendation for the board. Address:
1. What is your core strategic direction?
2. What are the key trade-offs you're making?
3. How will you manage the stakeholder tensions?

*You have 4-5 minutes. Write in whatever format works for you—bullet points, prose, however you think best.*

---

### Part 2: The Curveball

After they submit Part 1, present this new information:

**New Development**

Two days before your board meeting, you receive the following:

1. **Ministry of Finance** has privately indicated they would support a partial privatisation (up to 40% stake sale) to fund the transition, but only if announced in the next fiscal year. The Minister of Labour was not consulted and will likely oppose.

2. **Your CFO** informs you that three months of customer payment data was exposed in a cybersecurity incident last week. It's not yet public, but will need to be disclosed within 30 days. The incident originated from an outdated system in your distribution network.

3. **A major industrial customer** (15% of revenue) has informed you they're in "advanced discussions" with a competitor for a 10-year green supply agreement. They'd consider staying if you can match terms, but need a commitment within 6 weeks.

---

**Your Task (Part 2)**

Revise your strategic recommendation in light of this new information. Specifically:
1. What changes in your strategic direction, if anything?
2. How do you sequence or prioritise now?
3. What's your biggest concern that wasn't on your radar before?

*You have 3-4 minutes.*

---

## Scoring Criteria

We assess two dimensions through this scenario:

### Cognitive Flexibility (8% of framework)

**What we're looking for:**
- Does their Part 2 response genuinely integrate the new information?
- Do they revise their position where evidence warrants, or defend their original view?
- Can they hold complexity without collapsing to simple answers?

| Score | Description | Evidence |
|-------|-------------|----------|
| 5 | Sophisticated adaptation | Materially revises approach based on new info; explains what changed in their thinking; comfortable with "I was focused on wrong thing" |
| 4 | Clear adaptation | Incorporates new info meaningfully; adjusts priorities; some revision to original view |
| 3 | Moderate adaptation | Acknowledges new info; makes some adjustments; partly defensive of original |
| 2 | Limited adaptation | Mentions new info but doesn't substantively change approach; "this doesn't change my view" |
| 1 | No adaptation | Ignores or dismisses new info; rigid adherence to original position |

**Key signals:**
- Positively: "This changes my sequencing because..." / "I hadn't weighted [X] correctly"
- Concerning: "My original plan handles this" / "This is noise, I'm staying course"

### Systems Thinking (6% of framework)

**What we're looking for:**
- Do they identify connections between elements?
- Do they anticipate second/third-order effects?
- Do they map stakeholder interdependencies?

| Score | Description | Evidence |
|-------|-------------|----------|
| 5 | Sophisticated systems view | Identifies non-obvious connections; anticipates how action A affects B/C; maps feedback loops; sees stakeholder interdependencies |
| 4 | Good systems view | Sees key connections; considers downstream effects; understands stakeholder dynamics |
| 3 | Moderate systems view | Some connection-making; may miss important interdependencies; linear thinking in places |
| 2 | Limited systems view | Treats issues in isolation; surprised by obvious connections; stakeholder blind spots |
| 1 | No systems view | Completely siloed thinking; no interdependency recognition |

**Key signals:**
- Positively: "If we do X, the union will interpret it as Y, which affects our position with Z..."
- Concerning: "Let's handle the customer issue, then separately deal with the workforce..."

---

## Response Analysis Guidance

The AI should analyse responses for:

**Part 1 Analysis:**
- What trade-offs did they explicitly identify?
- Which stakeholders did they prioritise? Ignore?
- Did they acknowledge uncertainty and constraints?
- Was their reasoning coherent and evidence-based?
- Did they spot non-obvious connections?

**Part 2 Analysis:**
- What specifically changed between Part 1 and Part 2?
- Did they integrate all three new elements or cherry-pick?
- Did they acknowledge where their Part 1 was incomplete?
- How did they handle the ethical dimension (cybersecurity disclosure)?
- Did new info reveal blind spots from Part 1?

**Cross-Part Analysis:**
- Cognitive flexibility signal: degree of genuine revision
- Systems thinking signal: connections made across scenario elements
- Self-awareness signal: acknowledgment of what they missed

---

## Output Data Structure

```json
{
  "scenario_analysis": {
    "cognitive_flexibility": {
      "score": 4,
      "confidence": "high",
      "evidence": {
        "part1_position": "Phased renewable transition with workforce managed through attrition",
        "part2_revision": "Accelerated timeline, privatisation considered, customer retention prioritised",
        "revision_quality": "Substantively changed sequencing; acknowledged customer urgency wasn't weighted appropriately; defensive on workforce approach",
        "key_quote": "The customer situation forces my hand on timeline—I was probably too gradualist before."
      }
    },
    "systems_thinking": {
      "score": 4,
      "confidence": "medium",
      "evidence": {
        "connections_identified": [
          "Linked cybersecurity incident to broader modernisation narrative",
          "Connected privatisation to workforce messaging challenge"
        ],
        "connections_missed": [
          "Didn't connect customer departure risk to union negotiating leverage",
          "Didn't anticipate how disclosure timing affects privatisation valuation"
        ],
        "key_quote": "The cyber disclosure gives us a burning platform for the modernisation spend."
      }
    },
    "additional_observations": {
      "stakeholder_awareness": "Strong on Ministry tensions; weaker on community impact",
      "ethical_reasoning": "Addressed disclosure appropriately; didn't explore minimisation",
      "analytical_quality": "Structured thinking; some assertions without evidence"
    }
  },
  "part1_response": "[full text]",
  "part2_response": "[full text]"
}
```

---

## Presentation Guidance

### Part 1 Presentation
- Display scenario as scrollable text
- Timer visible (suggested 4-5 min for response)
- Large text input area
- "Submit and Continue" button

### Curveball Presentation
- Clear visual break ("New Information")
- Three new items clearly numbered
- Emphasise this builds on previous scenario
- Timer visible (suggested 3-4 min)
- Show their Part 1 response for reference (collapsed/expandable)

### Transition
- After Part 2 submitted: "Thank you. Your responses will be analysed as part of your assessment."
- Move to synthesis/processing screen

---

## Alternative Scenarios (Future)

For variety or sector-specific demos, alternative scenarios can be developed:

1. **Technology Transformation** — Legacy tech company facing AI disruption
2. **Healthcare System** — Hospital network managing cost pressure + quality mandate
3. **Financial Services** — Bank facing fintech competition + regulatory change
4. **Manufacturing** — Industrial company facing supply chain restructuring + ESG pressure

Each would follow the same Read → Respond → Curveball → Revise structure.

---

## Related Documents

- [[19 - Mini-Assessment Demo Specification]] — Overall demo spec
- [[12 - The Capability Architecture]] — Dimension definitions
- [[23 - Synthesis Prompt]] — How this integrates into output

---

*Last updated: June 2025*
*For: Mini-Assessment Demo Build*
