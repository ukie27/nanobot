"""Interview preparation and review orchestration."""

from __future__ import annotations

from typing import Any


class InterviewApplicationService:
    def __init__(self, gateway) -> None:
        self.gateway = gateway

    def list(self) -> list[dict[str, Any]]:
        return self.gateway.list_interviews()

    def get(self, interview_id: str) -> dict[str, Any]:
        return self.gateway.get_interview(interview_id)

    def create(self, **values: Any) -> dict[str, Any]:
        return self.gateway.create_interview(**values)

    def reschedule(self, interview_id: str, **values: Any) -> dict[str, Any]:
        return self.gateway.reschedule_interview(interview_id, **values)

    def cancel(self, interview_id: str, **values: Any) -> dict[str, Any]:
        return self.gateway.cancel_interview(interview_id, **values)

    def prepare(self, interview_id: str) -> dict[str, Any]:
        return self.gateway.generate_preparation(interview_id)

    def record(self, interview_id: str, **values: Any) -> dict[str, Any]:
        return self.gateway.save_record(interview_id, **values)

    def list_feedback(self) -> list[dict[str, Any]]:
        return self.gateway.list_feedback()

    def resolve_feedback(self, feedback_id: str, **values: Any) -> dict[str, Any]:
        return self.gateway.resolve_feedback(feedback_id, **values)

    def list_improvements(self) -> list[dict[str, Any]]:
        return self.gateway.list_improvements()

    def update_improvement(self, improvement_id: str, **values: Any) -> dict[str, Any]:
        return self.gateway.update_improvement(improvement_id, **values)
