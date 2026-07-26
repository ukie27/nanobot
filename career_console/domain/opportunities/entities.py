"""Recruitment opportunity state and validation rules."""

from __future__ import annotations

from enum import StrEnum


class OpportunityTriageStatus(StrEnum):
    NEW = "new"
    FOLLOWING = "following"
    IGNORED = "ignored"


def normalize_opportunity_text(value: object, *, max_length: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:max_length]
