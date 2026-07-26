"""Validated contracts for fact-bound Agent material drafting and review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResumeDraftBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    block_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$", alias="blockId")
    section: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=10_000)
    fact_ids: list[str] = Field(min_length=1, max_length=20, alias="factIds")
    requirement_ids: list[str] = Field(default_factory=list, max_length=30, alias="requirementIds")

    @model_validator(mode="after")
    def references_are_unique(self) -> "ResumeDraftBlock":
        if len(self.fact_ids) != len(set(self.fact_ids)):
            raise ValueError("factIds contains duplicates")
        if len(self.requirement_ids) != len(set(self.requirement_ids)):
            raise ValueError("requirementIds contains duplicates")
        return self


class ResumeDraftResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["resume_draft.v2"] = Field(alias="schemaVersion")
    title: str = Field(min_length=1, max_length=300)
    blocks: list[ResumeDraftBlock] = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def block_ids_are_unique(self) -> "ResumeDraftResult":
        ids = [item.block_id for item in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("blockId must be unique")
        return self


class AgentMaterialFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    severity: Literal["error", "warning", "info"]
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    message: str = Field(min_length=1, max_length=1_000)
    block_id: str | None = Field(default=None, alias="blockId", max_length=80)


class MaterialReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["material_review.v2"] = Field(alias="schemaVersion")
    verdict: Literal["pass", "needs_revision"]
    findings: list[AgentMaterialFinding] = Field(default_factory=list, max_length=200)
    summary: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def verdict_matches_findings(self) -> "MaterialReviewResult":
        has_error = any(item.severity == "error" for item in self.findings)
        if (self.verdict == "pass") == has_error:
            raise ValueError("verdict must reflect error findings")
        return self
