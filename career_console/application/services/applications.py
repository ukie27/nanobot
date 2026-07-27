"""Application lifecycle use-case orchestration."""

from __future__ import annotations

from typing import Any

from career_console.application.ports.application_gateway import ApplicationGateway


class CareerApplicationService:
    def __init__(self, gateway: ApplicationGateway) -> None:
        self.gateway = gateway

    def create(self, *, job_post_id: str) -> dict[str, Any]:
        return self.gateway.create_application(job_post_id=job_post_id)

    def mark_job_ready(self, *, job_post_id: str) -> int:
        return self.gateway.mark_job_ready(job_post_id)

    def submit(self, application_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.submit_application(application_id, **kwargs)

    def add_event(self, application_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.add_event(application_id, **kwargs)

    def correct_event(self, application_id: str, event_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.correct_event(application_id, event_id, **kwargs)

    def archive(self, application_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.archive_application(application_id, **kwargs)

    def propose_event(self, application_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.propose_event(application_id, **kwargs)

    def resolve_proposal(self, proposal_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.resolve_proposal(proposal_id, **kwargs)
