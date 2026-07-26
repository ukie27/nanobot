"""Ports for the independent material Drafter and Reviewer Agents."""

from __future__ import annotations

from typing import Protocol

from nanobot.career.domain.materials import MaterialReviewResult, ResumeDraftResult


class ResumeDrafter(Protocol):
    name: str
    schema_version: str
    prompt_version: str

    def draft(self, *, context: dict) -> ResumeDraftResult: ...


class MaterialReviewer(Protocol):
    name: str
    schema_version: str
    prompt_version: str

    def review(self, *, context: dict) -> MaterialReviewResult: ...
