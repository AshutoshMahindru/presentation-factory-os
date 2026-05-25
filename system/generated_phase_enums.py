"""
Generated from docs/08_StateMachine_Spec.yaml by scripts/generate_phase_enums.py. Do not edit by hand.
"""

from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    CREATED = "created"
    INTAKE = "intake"
    STRATEGY = "strategy"
    RESEARCH = "research"
    FINANCIAL_MODEL = "financial_model"
    NARRATIVE = "narrative"
    VISUAL_DESIGN = "visual_design"
    REVIEW = "review"
    APPROVED = "approved"
    EXPORTED = "exported"
    REJECTED = "rejected"


PHASES: tuple[Phase, ...] = (
    Phase.CREATED,
    Phase.INTAKE,
    Phase.STRATEGY,
    Phase.RESEARCH,
    Phase.FINANCIAL_MODEL,
    Phase.NARRATIVE,
    Phase.VISUAL_DESIGN,
    Phase.REVIEW,
    Phase.APPROVED,
    Phase.EXPORTED,
    Phase.REJECTED
)


PHASE_VALUES: tuple[str, ...] = tuple(phase.value for phase in PHASES)
