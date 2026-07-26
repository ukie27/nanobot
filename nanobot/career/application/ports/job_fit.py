"""Semantic job-fit Agent port."""

from __future__ import annotations

from typing import Protocol

from nanobot.career.domain.jobs import JobFitAnalysisResult


class JobFitAnalyzer(Protocol):
    name: str
    schema_version: str
    prompt_version: str

    def analyze(self, *, context: dict) -> JobFitAnalysisResult: ...
