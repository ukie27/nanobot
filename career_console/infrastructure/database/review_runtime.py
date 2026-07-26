"""Shared persistence helpers for review tasks and AgentRun audits."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from career_console.infrastructure.database.models import AgentRunModel, ReviewTaskModel


def ensure_review_task(
    session: Session,
    *,
    task_type: str,
    entity_type: str,
    entity_id: str,
    now: datetime,
    title: str,
    summary: str,
    source_type: str,
    priority: int = 0,
    agent_run_id: str | None = None,
) -> ReviewTaskModel:
    """Create one durable review projection per business entity."""
    task = session.scalar(
        select(ReviewTaskModel).where(
            ReviewTaskModel.task_type == task_type,
            ReviewTaskModel.entity_type == entity_type,
            ReviewTaskModel.entity_id == entity_id,
        )
    )
    if task is None:
        task = ReviewTaskModel(
            id=str(uuid4()),
            task_type=task_type,
            entity_type=entity_type,
            entity_id=entity_id,
            status="open",
            version=1,
            title=title[:300],
            summary=summary[:5_000],
            source_type=source_type[:80],
            priority=priority,
            agent_run_id=agent_run_id,
            created_at=now,
            updated_at=now,
            resolved_at=None,
            resolution=None,
            resolution_reason=None,
            resolved_by=None,
        )
        session.add(task)
        return task
    if task.status == "open":
        task.title = title[:300]
        task.summary = summary[:5_000]
        task.source_type = source_type[:80]
        task.priority = priority
        task.agent_run_id = agent_run_id or task.agent_run_id
        task.updated_at = now
    return task


def set_review_resolution(
    task: ReviewTaskModel,
    *,
    now: datetime,
    resolution: str | None,
    reason: str,
    resolved_by: str = "user",
    reopen: bool = False,
) -> None:
    task.status = "open" if reopen else "resolved"
    task.resolved_at = None if reopen else now
    task.resolution = None if reopen else resolution
    task.resolution_reason = None if reopen else reason[:500]
    task.resolved_by = None if reopen else resolved_by[:80]
    task.updated_at = now
    task.version += 1


def create_agent_run(
    session: Session,
    *,
    task_type: str,
    implementation: str,
    schema_version: str,
    status: str,
    output_count: int,
    error_code: str | None,
    created_at: datetime,
    finished_at: datetime | None,
    document_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    input_entity_type: str | None = None,
    input_entity_id: str | None = None,
    input_revision: str | None = None,
    input_hash: str | None = None,
    output_hash: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duration_ms: int | None = None,
    retry_count: int = 0,
    sensitivity: str = "private",
) -> AgentRunModel:
    run = AgentRunModel(
        id=str(uuid4()),
        task_type=task_type,
        execution_mode="task",
        correlation_id=None,
        implementation=implementation[:100],
        provider=provider[:100] if provider else None,
        model=model[:200] if model else None,
        prompt_version=prompt_version[:100] if prompt_version else None,
        skill_version=None,
        schema_version=schema_version[:32],
        document_id=document_id,
        input_entity_type=input_entity_type,
        input_entity_id=input_entity_id,
        input_revision=input_revision,
        input_hash=input_hash,
        output_hash=output_hash,
        tool_calls_json=json.dumps([], separators=(",", ":")),
        status=status,
        output_count=output_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        retry_count=retry_count,
        sensitivity=sensitivity,
        retention_until=None,
        error_code=error_code,
        created_at=created_at.astimezone(UTC),
        finished_at=finished_at.astimezone(UTC) if finished_at else None,
    )
    session.add(run)
    session.flush()
    return run
