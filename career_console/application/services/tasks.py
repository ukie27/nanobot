"""Task and reminder use-case orchestration."""

from __future__ import annotations

from typing import Any

from career_console.application.ports.task_gateway import TaskGateway


class TaskApplicationService:
    def __init__(self, gateway: TaskGateway) -> None:
        self.gateway = gateway

    def create(self, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.create_task(**kwargs)

    def update(self, task_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.update_task(task_id, **kwargs)

    def add_reminder(self, task_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.create_reminder(task_id, **kwargs)

    def run_due(self, **kwargs: Any) -> dict[str, int]:
        return self.gateway.run_due(**kwargs)
