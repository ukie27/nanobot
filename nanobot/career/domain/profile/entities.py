"""Deterministic candidate fact state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from nanobot.career.domain.common.errors import CareerDomainError


class FactStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class FactCategory(StrEnum):
    BASIC = "basic"
    EDUCATION = "education"
    INTERNSHIP = "internship"
    WORK = "work"
    PROJECT = "project"
    SKILL = "skill"
    AWARD = "award"
    CERTIFICATE = "certificate"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"


@dataclass(frozen=True, slots=True)
class CandidateFact:
    id: str
    profile_id: str
    category: FactCategory
    field_key: str
    value: str
    status: FactStatus
    version: int
    confidence: float | None
    created_at: datetime
    updated_at: datetime

    def confirm(self, *, now: datetime) -> "CandidateFact":
        if self.status is FactStatus.REJECTED:
            raise CareerDomainError(
                "Rejected facts must be edited before they can be confirmed.",
                code="invalid_fact_transition",
            )
        if self.status is FactStatus.CONFIRMED:
            return self
        return replace(self, status=FactStatus.CONFIRMED, version=self.version + 1, updated_at=now)

    def reject(self, *, now: datetime) -> "CandidateFact":
        if self.status is FactStatus.CONFIRMED:
            raise CareerDomainError(
                "Confirmed facts must be explicitly edited rather than silently rejected.",
                code="invalid_fact_transition",
            )
        if self.status is FactStatus.REJECTED:
            return self
        return replace(self, status=FactStatus.REJECTED, version=self.version + 1, updated_at=now)

    def edit(self, value: str, *, now: datetime) -> "CandidateFact":
        normalized = value.strip()
        if not normalized:
            raise CareerDomainError("Fact value cannot be empty.", code="empty_fact_value")
        if normalized == self.value:
            return self
        next_status = FactStatus.PROPOSED if self.status is FactStatus.REJECTED else self.status
        return replace(
            self,
            value=normalized,
            status=next_status,
            version=self.version + 1,
            updated_at=now,
        )
