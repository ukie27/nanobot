"""Recruitment opportunity use cases."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from career_console.application.ports.opportunity_gateway import OpportunityGateway
from career_console.domain.opportunities import OpportunityTriageStatus


class OpportunityApplicationService:
    def __init__(self, gateway: OpportunityGateway) -> None:
        self.gateway = gateway

    def list(
        self,
        *,
        triage_status: OpportunityTriageStatus | None = None,
        today: bool = False,
    ) -> dict[str, Any]:
        collected_since = None
        if today:
            china = ZoneInfo("Asia/Shanghai")
            local_today = datetime.now(china).date()
            collected_since = datetime.combine(local_today, time.min, china).astimezone(UTC)
        items = self.gateway.list(
            triage_status=triage_status,
            collected_since=collected_since,
        )
        return {"items": items, "total": len(items)}

    def get(self, opportunity_id: str) -> dict[str, Any]:
        return self.gateway.get(opportunity_id)

    def triage(
        self,
        opportunity_id: str,
        *,
        triage_status: OpportunityTriageStatus,
        expected_version: int,
    ) -> dict[str, Any]:
        return self.gateway.triage(
            opportunity_id,
            triage_status=triage_status,
            expected_version=expected_version,
        )
