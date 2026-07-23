"""Structured job extraction contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from nanobot.career.domain.jobs import RequirementCategory, RequirementLevel


@dataclass(frozen=True, slots=True)
class ExtractedRequirement:
    category: RequirementCategory
    level: RequirementLevel
    description: str
    evidence_text: str
    keywords: tuple[str, ...]
    weight: int = 1


@dataclass(frozen=True, slots=True)
class ExtractedJob:
    title: str
    company: str
    location: str | None
    employment_type: str | None
    work_mode: str | None
    target_audience: str | None
    deadline_at: datetime | None
    requirements: tuple[ExtractedRequirement, ...]


class JobExtractor(Protocol):
    name: str
    schema_version: str

    def extract(self, text: str) -> ExtractedJob: ...
