"""Profile insight Agent port."""

from __future__ import annotations

from typing import Protocol

from nanobot.career.domain.profile import ProfileInsightResult


class ProfileInsightAnalyzer(Protocol):
    name: str
    schema_version: str
    prompt_version: str

    def analyze(self, *, context: dict) -> ProfileInsightResult: ...
