"""Ports for deterministic JD discovery and tool-free recommendation analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from career_console.domain.recommendations import JobRecommendationResult


@dataclass(frozen=True, slots=True)
class DiscoveredJobDescription:
    name: str
    url: str
    text: str


@dataclass(frozen=True, slots=True)
class JobDiscoveryResult:
    status: str
    jobs: tuple[DiscoveredJobDescription, ...] = ()
    error_code: str | None = None


class JobDescriptionDiscovery(Protocol):
    def discover(self, *, opportunity: dict[str, Any]) -> JobDiscoveryResult: ...


class JobRecommendationAnalyzer(Protocol):
    name: str
    schema_version: str
    prompt_version: str

    def analyze(self, *, context: dict[str, Any]) -> JobRecommendationResult: ...
