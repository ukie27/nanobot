"""Unified review queue and AgentRun audit queries."""

from __future__ import annotations

from typing import Any

from nanobot.career.application.ports.runtime_gateway import RuntimeGateway


class RuntimeApplicationService:
    def __init__(self, gateway: RuntimeGateway) -> None:
        self.gateway = gateway

    def reviews(self, *, status: str | None = "open") -> dict[str, Any]:
        items = self.gateway.list_reviews(status=status)
        return {"items": items, "total": len(items)}

    def review(self, review_id: str) -> dict[str, Any]:
        return self.gateway.get_review(review_id)

    def agent_runs(self, *, limit: int = 100) -> dict[str, Any]:
        items = self.gateway.list_agent_runs(limit=limit)
        return {"items": items, "total": len(items)}

    def agent_run(self, run_id: str) -> dict[str, Any]:
        return self.gateway.get_agent_run(run_id)
