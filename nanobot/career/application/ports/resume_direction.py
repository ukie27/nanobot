"""Resume Direction Planner Agent port."""

from __future__ import annotations

from typing import Protocol

from nanobot.career.domain.materials import ResumeDirectionResult


class ResumeDirectionAnalyzer(Protocol):
    name: str
    schema_version: str
    prompt_version: str

    def analyze(self, *, context: dict) -> ResumeDirectionResult: ...
