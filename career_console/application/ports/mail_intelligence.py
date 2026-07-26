"""Agent-facing contract for structured recruiting-mail analysis."""

from typing import Protocol

from career_console.domain.mail.intelligence import MailIntelligenceResult


class MailIntelligenceAnalyzer(Protocol):
    name: str
    schema_version: str
    model: str | None
    last_usage: dict[str, int]
    last_retry_count: int

    def analyze(self, *, message: dict, applications: list[dict]) -> MailIntelligenceResult: ...
