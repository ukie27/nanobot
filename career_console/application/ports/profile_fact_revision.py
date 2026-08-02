"""Constrained profile fact revision contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProfileFactRevision:
    value: str
    rationale: str


class ProfileFactReviser(Protocol):
    name: str
    schema_version: str

    def revise(
        self,
        *,
        fact_id: str,
        category: str,
        field_key: str,
        current_value: str,
        instruction: str,
        evidence_texts: tuple[str, ...],
    ) -> ProfileFactRevision: ...
