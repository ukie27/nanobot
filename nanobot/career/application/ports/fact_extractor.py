"""Constrained fact extraction contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nanobot.career.domain.profile.entities import FactCategory


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    category: FactCategory
    field_key: str
    value: str
    evidence_text: str
    confidence: float


class FactExtractor(Protocol):
    """Extract candidates from exactly one supplied document text."""

    name: str
    schema_version: str

    def extract(self, *, document_id: str, text: str) -> list[ExtractedFact]: ...
