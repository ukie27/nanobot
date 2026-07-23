"""Worker lifecycle skeleton; business handlers arrive in later Parts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

JobHandler = Callable[[dict[str, Any]], None]


class JobHandlerRegistry:
    """Explicit allowlist of background job types."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        if not job_type or job_type in self._handlers:
            raise ValueError(f"Invalid or duplicate job type: {job_type}")
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> JobHandler:
        try:
            return self._handlers[job_type]
        except KeyError as exc:
            raise LookupError(f"No handler registered for job type: {job_type}") from exc

    @property
    def job_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
