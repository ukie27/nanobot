"""Validated output contract for tool-free profile intelligence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProfileInsightItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    category: Literal[
        "interview", "application", "resume", "learning", "career_direction"
    ]
    analysis: str = Field(min_length=1, max_length=2_000)
    recommendation: str = Field(min_length=1, max_length=2_000)
    evidence_fact_ids: list[str] = Field(default_factory=list, max_length=50, alias="evidenceFactIds")
    evidence_improvement_ids: list[str] = Field(
        default_factory=list, max_length=50, alias="evidenceImprovementIds"
    )
    counter_evidence_fact_ids: list[str] = Field(
        default_factory=list, max_length=50, alias="counterEvidenceFactIds"
    )
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def references_are_distinct(self) -> "ProfileInsightItem":
        if not self.evidence_fact_ids and not self.evidence_improvement_ids:
            raise ValueError("At least one confirmed evidence reference is required")
        if len(set(self.evidence_fact_ids)) != len(self.evidence_fact_ids):
            raise ValueError("evidenceFactIds contains duplicates")
        if len(set(self.evidence_improvement_ids)) != len(self.evidence_improvement_ids):
            raise ValueError("evidenceImprovementIds contains duplicates")
        if len(set(self.counter_evidence_fact_ids)) != len(self.counter_evidence_fact_ids):
            raise ValueError("counterEvidenceFactIds contains duplicates")
        if set(self.evidence_fact_ids) & set(self.counter_evidence_fact_ids):
            raise ValueError("A fact cannot be both evidence and counter-evidence")
        return self


class ProfileInsightResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["profile_insight.v3"] = Field(alias="schemaVersion")
    insights: list[ProfileInsightItem] = Field(min_length=1, max_length=20)
