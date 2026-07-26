"""Pure, deterministic job requirement and matching rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RequirementLevel(StrEnum):
    MUST = "must"
    PREFERRED = "preferred"


class RequirementCategory(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    LANGUAGE = "language"
    LOCATION = "location"
    WORK_MODE = "work_mode"
    OTHER = "other"


class EvidenceDecision(StrEnum):
    MATCHED = "matched"
    GAP = "gap"


@dataclass(frozen=True, slots=True)
class JobRequirement:
    id: str
    category: RequirementCategory
    level: RequirementLevel
    description: str
    evidence_text: str
    weight: int = 1


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    requirement_id: str
    decision: EvidenceDecision
    fact_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class MatchResult:
    hard_gate_passed: bool
    score: int
    matched_count: int
    gap_count: int
    must_gap_count: int
    recommendation: str


def evaluate_match(
    requirements: list[JobRequirement], evidence: list[CandidateEvidence]
) -> MatchResult:
    """Compute a stable score; an unmet MUST requirement always vetoes suitability."""
    decisions = {item.requirement_id: item for item in evidence}
    matched_weight = total_weight = matched_count = gaps = must_gaps = 0
    for requirement in requirements:
        weighted = max(1, requirement.weight) * (
            3 if requirement.level is RequirementLevel.MUST else 1
        )
        total_weight += weighted
        item = decisions.get(requirement.id)
        if item is not None and item.decision is EvidenceDecision.MATCHED and item.fact_ids:
            matched_weight += weighted
            matched_count += 1
        else:
            gaps += 1
            if requirement.level is RequirementLevel.MUST:
                must_gaps += 1
    score = round(matched_weight * 100 / total_weight) if total_weight else 0
    gate = must_gaps == 0
    recommendation = (
        "blocked"
        if not gate
        else "high_priority"
        if score >= 75
        else "consider"
        if score >= 50
        else "low_priority"
    )
    return MatchResult(gate, score, matched_count, gaps, must_gaps, recommendation)
