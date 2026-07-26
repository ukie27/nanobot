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
from .intelligence import JobFitAnalysisResult, JobRequirementAssessment

__all__ = [
    "CandidateEvidence",
    "EvidenceDecision",
    "JobRequirement",
    "JobFitAnalysisResult",
    "JobRequirementAssessment",
    "MatchResult",
    "RequirementCategory",
    "RequirementLevel",
    "evaluate_match",
]
