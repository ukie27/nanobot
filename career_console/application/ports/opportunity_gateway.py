"""Persistence contract for recruitment opportunities."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from career_console.domain.opportunities import OpportunityTriageStatus


class OpportunityGateway(Protocol):
    def ingest(
        self,
        *,
        connector_id: str,
        source_event_id: str,
        external_id: str,
        source_url: str,
        content_hash: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool, bool]: ...

    def list(
        self,
        *,
        triage_status: OpportunityTriageStatus | None = None,
        collected_since: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]: ...

    def get(self, opportunity_id: str) -> dict[str, Any]: ...

    def triage(
        self,
        opportunity_id: str,
        *,
        triage_status: OpportunityTriageStatus,
        expected_version: int,
    ) -> dict[str, Any]: ...
