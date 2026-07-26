"""Validated output contract for semantic job-fit proposals."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobRequirementAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    requirement_id: str = Field(min_length=1, max_length=36, alias="requirementId")
    interpretation: str = Field(min_length=1, max_length=1_000)
    decision: Literal["matched", "gap"]
    evidence_fact_ids: list[str] = Field(default_factory=list, max_length=30, alias="evidenceFactIds")
    transferable_fact_ids: list[str] = Field(default_factory=list, max_length=30, alias="transferableFactIds")
    rationale: str = Field(min_length=1, max_length=2_000)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def consistent_decision(self) -> "JobRequirementAssessment":
        direct = set(self.evidence_fact_ids)
        transferable = set(self.transferable_fact_ids)
        if len(direct) != len(self.evidence_fact_ids) or len(transferable) != len(self.transferable_fact_ids):
            raise ValueError("Fact references contain duplicates")
        if direct & transferable:
            raise ValueError("A Fact ID cannot be direct and transferable evidence")
        if self.decision == "matched" and not (direct or transferable):
            raise ValueError("A matched requirement requires confirmed Fact evidence")
        if self.decision == "gap" and direct:
            raise ValueError("A gap cannot contain direct evidence")
        return self


class JobFitAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["job_fit_analysis.v2"] = Field(alias="schemaVersion")
    summary: str = Field(min_length=1, max_length=2_000)
    assessments: list[JobRequirementAssessment] = Field(min_length=1, max_length=100)
    strengths: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    material_effort: Literal["low", "medium", "high"] = Field(alias="materialEffort")
    preparation_hours: int = Field(ge=0, le=200, alias="preparationHours")
    recommendation_context: str = Field(min_length=1, max_length=2_000, alias="recommendationContext")

    @model_validator(mode="after")
    def requirement_references_are_unique(self) -> "JobFitAnalysisResult":
        ids = [item.requirement_id for item in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("Each requirement may be assessed only once")
        return self
