"""Validated contract for resume-direction planning."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResumeDirectionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    direction_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$", alias="directionId")
    name: str = Field(min_length=1, max_length=120)
    narrative: str = Field(min_length=1, max_length=1_500)
    focus_requirement_ids: list[str] = Field(min_length=1, max_length=30, alias="focusRequirementIds")
    emphasize_fact_ids: list[str] = Field(min_length=1, max_length=50, alias="emphasizeFactIds")
    de_emphasize_fact_ids: list[str] = Field(default_factory=list, max_length=50, alias="deEmphasizeFactIds")
    estimated_change_percent: int = Field(ge=0, le=100, alias="estimatedChangePercent")
    expected_pages: float = Field(ge=0.5, le=5, alias="expectedPages")
    gaps: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    rationale: str = Field(min_length=1, max_length=1_500)

    @model_validator(mode="after")
    def references_are_consistent(self) -> "ResumeDirectionItem":
        for values in (
            self.focus_requirement_ids, self.emphasize_fact_ids, self.de_emphasize_fact_ids
        ):
            if len(values) != len(set(values)):
                raise ValueError("Direction references contain duplicates")
        if set(self.emphasize_fact_ids) & set(self.de_emphasize_fact_ids):
            raise ValueError("A Fact cannot be emphasized and de-emphasized")
        return self


class ResumeDirectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["resume_direction.v1"] = Field(alias="schemaVersion")
    directions: list[ResumeDirectionItem] = Field(min_length=2, max_length=4)
    comparison_note: str = Field(min_length=1, max_length=2_000, alias="comparisonNote")

    @model_validator(mode="after")
    def direction_ids_are_unique(self) -> "ResumeDirectionResult":
        ids = [item.direction_id for item in self.directions]
        if len(ids) != len(set(ids)):
            raise ValueError("directionId must be unique")
        return self
