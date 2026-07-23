"""Job pool and explainable matching domain."""

from .entities import (
    CandidateEvidence,
    EvidenceDecision,
    JobRequirement,
    MatchResult,
    RequirementCategory,
    RequirementLevel,
    evaluate_match,
)

__all__ = [
    "CandidateEvidence",
    "EvidenceDecision",
    "JobRequirement",
    "MatchResult",
    "RequirementCategory",
    "RequirementLevel",
    "evaluate_match",
]
