"""Validated output and lifecycle contracts for daily job recommendations."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecommendationStatus(StrEnum):
    ACTIVE = "active"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    STALE = "stale"


class RecommendationDecision(StrEnum):
    RECOMMEND = "recommend"
    REJECT = "reject"


class RecommendationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendationAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    requirement_id: str = Field(min_length=1, max_length=36, alias="requirementId")
    decision: Literal["matched", "gap"]
    evidence_fact_ids: list[str] = Field(default_factory=list, max_length=30, alias="evidenceFactIds")
    transferable_fact_ids: list[str] = Field(
        default_factory=list, max_length=30, alias="transferableFactIds"
    )
    rationale: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_evidence(self) -> "RecommendationAssessment":
        direct = set(self.evidence_fact_ids)
        transferable = set(self.transferable_fact_ids)
        if len(direct) != len(self.evidence_fact_ids) or len(transferable) != len(
            self.transferable_fact_ids
        ):
            raise ValueError("Fact references contain duplicates")
        if direct & transferable:
            raise ValueError("A Fact ID cannot be direct and transferable evidence")
        if self.decision == "matched" and not (direct or transferable):
            raise ValueError("A matched requirement requires confirmed evidence")
        if self.decision == "gap" and direct:
            raise ValueError("A gap cannot contain direct evidence")
        return self


class JobRecommendationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["daily_job_recommendation.v1"] = Field(alias="schemaVersion")
    decision: Literal["recommend", "reject"]
    score: int = Field(ge=0, le=100)
    priority: Literal["high", "medium", "low"]
    summary: str = Field(min_length=1, max_length=2_000)
    matched_directions: list[str] = Field(
        default_factory=list, max_length=20, alias="matchedDirections"
    )
    strengths: list[str] = Field(default_factory=list, max_length=20)
    gaps: list[str] = Field(default_factory=list, max_length=20)
    hard_gate_failures: list[str] = Field(
        default_factory=list, max_length=20, alias="hardGateFailures"
    )
    preference_reasons: list[str] = Field(
        default_factory=list, max_length=20, alias="preferenceReasons"
    )
    action_suggestion: str = Field(min_length=1, max_length=2_000, alias="actionSuggestion")
    assessments: list[RecommendationAssessment] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_decision(self) -> "JobRecommendationResult":
        ids = [item.requirement_id for item in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("Each requirement may be assessed only once")
        if self.decision == "recommend" and self.hard_gate_failures:
            raise ValueError("A recommended job cannot have unresolved hard gate failures")
        return self
