"""
Transformation Readiness Assessment — dimension catalogue.

Hard-coded from `/app/research/12 - The Capability Architecture.md` (the IP
core, by Steven Bianchi). 16 dimensions across 4 clusters; weights sum to 100%.
Six dimensions are assessed in the mini-demo (43% of total weighting); ten are
intentionally not assessed and must be surfaced in the participant report as
"not assessed in this preview" — see Doc 19 Mini-Assessment Demo Specification.

Invariants asserted at import time — fail loud if any of these ever drifts:
  - exactly 16 dimensions
  - exactly 6 marked assessed=True
  - exactly 10 marked assessed=False
  - weights sum to 100 ± 0.5
  - all six assessed dimensions are the ones Doc 19 names

Public API:
  - CATALOGUE: list[Dimension]
  - assessed(): list[Dimension]
  - not_assessed(): list[Dimension]
  - by_id(id): Dimension
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict


@dataclass(frozen=True)
class Dimension:
    id: str                    # stable machine id, e.g. "learning_agility"
    name: str                  # human label, e.g. "Learning Agility"
    cluster: str               # "Adaptive Capacity" | "Future Leadership" | "Contextual Navigation" | "Transformation Execution"
    weight_percent: float      # 0..100, per Doc 12
    definition: str            # one-line definition from Doc 12
    assessed: bool             # True for the 6 demo dimensions


# Verbatim definitions sourced from Doc 12 "Definition:" lines. Kept short
# (one clause) so they render cleanly in the report's two-column list.
CATALOGUE: List[Dimension] = [
    # Adaptive Capacity (30%)
    Dimension(
        id="learning_agility",
        name="Learning Agility",
        cluster="Adaptive Capacity",
        weight_percent=8.0,
        definition="The ability to learn from experience and apply that learning effectively to new, first-time situations.",
        assessed=True,
    ),
    Dimension(
        id="cognitive_flexibility",
        name="Cognitive Flexibility",
        cluster="Adaptive Capacity",
        weight_percent=8.0,
        definition="The ability to update mental models when evidence contradicts them, adapt thinking to new information, and shift between different conceptual frameworks.",
        assessed=True,
    ),
    Dimension(
        id="tolerance_for_ambiguity",
        name="Tolerance for Ambiguity",
        cluster="Adaptive Capacity",
        weight_percent=7.0,
        definition="The ability to function effectively without clear information, defined outcomes, or established procedures — and to make decisions when certainty is unavailable.",
        assessed=True,
    ),
    Dimension(
        id="self_awareness_accuracy",
        name="Self-Awareness Accuracy",
        cluster="Adaptive Capacity",
        weight_percent=7.0,
        definition="The correlation between how leaders perceive themselves and how others perceive them — the accuracy of self-assessment.",
        assessed=True,
    ),
    # Future Leadership (25%)
    Dimension(
        id="ai_fluency",
        name="AI Fluency",
        cluster="Future Leadership",
        weight_percent=7.0,
        definition="Understanding of AI capabilities, limitations, paradigms, and governance requirements sufficient to lead AI-integrated organisations.",
        assessed=True,
    ),
    Dimension(
        id="hybrid_workforce_capability",
        name="Hybrid Workforce Capability",
        cluster="Future Leadership",
        weight_percent=6.0,
        definition="Ability to lead organisations where significant work is performed by AI agents and automation alongside human workers.",
        assessed=False,
    ),
    Dimension(
        id="systems_thinking",
        name="Systems Thinking",
        cluster="Future Leadership",
        weight_percent=6.0,
        definition="Ability to understand complex interdependencies, anticipate second- and third-order effects, and see how components interact within larger systems.",
        assessed=True,
    ),
    Dimension(
        id="generational_intelligence",
        name="Generational Intelligence",
        cluster="Future Leadership",
        weight_percent=6.0,
        definition="Understanding of different generational values, expectations, and motivations — and ability to lead effectively across generations.",
        assessed=False,
    ),
    # Contextual Navigation (25%)
    Dimension(
        id="political_acumen",
        name="Political Acumen",
        cluster="Contextual Navigation",
        weight_percent=7.0,
        definition="Ability to navigate complex political environments, maintain relationships across factions, and create operational space within political constraints.",
        assessed=False,
    ),
    Dimension(
        id="stakeholder_orchestration",
        name="Stakeholder Orchestration",
        cluster="Contextual Navigation",
        weight_percent=6.0,
        definition="Ability to manage complex, competing stakeholder demands — balancing ministry, board, employees, customers, regulators, and public expectations.",
        assessed=False,
    ),
    Dimension(
        id="cultural_adaptability",
        name="Cultural Adaptability",
        cluster="Contextual Navigation",
        weight_percent=6.0,
        definition="Ability to operate effectively across cultural contexts while adapting to international standards and expectations.",
        assessed=False,
    ),
    Dimension(
        id="long_term_orientation",
        name="Long-Term Orientation",
        cluster="Contextual Navigation",
        weight_percent=6.0,
        definition="Capacity for decade-long thinking, building beyond personal tenure, and maintaining strategic patience despite political cycle pressures.",
        assessed=False,
    ),
    # Transformation Execution (20%)
    Dimension(
        id="change_leadership",
        name="Change Leadership",
        cluster="Transformation Execution",
        weight_percent=5.0,
        definition="Ability to lead others through transformational change — creating vision, building commitment, managing resistance, and sustaining momentum.",
        assessed=False,
    ),
    Dimension(
        id="institutional_building",
        name="Institutional Building",
        cluster="Transformation Execution",
        weight_percent=5.0,
        definition="Ability to create and strengthen organisational capabilities that persist beyond individual leaders — structures, processes, culture, and talent.",
        assessed=False,
    ),
    Dimension(
        id="governance_capability",
        name="Governance Capability",
        cluster="Transformation Execution",
        weight_percent=5.0,
        definition="Ability to design and operate effective governance structures — accountability, oversight, reporting, and board engagement — appropriate for transformed organisations.",
        assessed=False,
    ),
    Dimension(
        id="results_under_ambiguity",
        name="Results Under Ambiguity",
        cluster="Transformation Execution",
        weight_percent=5.0,
        definition="Ability to deliver outcomes in conditions of uncertainty, incomplete information, and changing requirements — where the playbook doesn't exist.",
        assessed=False,
    ),
]


# -------- Invariant assertions (run at import time) --------
def _validate() -> None:
    assert len(CATALOGUE) == 16, f"expected 16 dimensions, got {len(CATALOGUE)}"
    assessed_count = sum(1 for d in CATALOGUE if d.assessed)
    assert assessed_count == 6, f"expected 6 assessed dimensions, got {assessed_count}"
    assert len(CATALOGUE) - assessed_count == 10, "not-assessed count mismatch"

    total_weight = sum(d.weight_percent for d in CATALOGUE)
    assert 99.5 <= total_weight <= 100.5, f"weights sum to {total_weight}, expected ~100"

    # Spot-check Doc 19's six assessed dimensions by id
    expected_assessed = {
        "learning_agility", "tolerance_for_ambiguity", "cognitive_flexibility",
        "self_awareness_accuracy", "ai_fluency", "systems_thinking",
    }
    actual_assessed = {d.id for d in CATALOGUE if d.assessed}
    assert actual_assessed == expected_assessed, f"assessed set drift: {actual_assessed ^ expected_assessed}"

    # Doc 12 sanity — confirm its file is on disk (handoff requires it be reachable,
    # so we fail loud if someone accidentally deletes research material).
    doc12 = Path(__file__).resolve().parent.parent.parent / "research" / "12 - The Capability Architecture.md"
    assert doc12.exists(), f"Doc 12 missing at {doc12}"


_validate()


# -------- Public helpers --------
def assessed() -> List[Dimension]:
    return [d for d in CATALOGUE if d.assessed]


def not_assessed() -> List[Dimension]:
    return [d for d in CATALOGUE if not d.assessed]


def by_id(dim_id: str) -> Dimension:
    for d in CATALOGUE:
        if d.id == dim_id:
            return d
    raise KeyError(f"Unknown dimension id: {dim_id!r}")


def as_public_dicts() -> Dict[str, List[Dict]]:
    """Serialise both halves of the catalogue for API payloads."""
    return {
        "assessed": [asdict(d) for d in assessed()],
        "not_assessed": [asdict(d) for d in not_assessed()],
        "total_weight_percent": round(sum(d.weight_percent for d in CATALOGUE), 2),
    }
