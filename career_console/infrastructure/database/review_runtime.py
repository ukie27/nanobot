"""Shared persistence helpers for review tasks and AgentRun audits."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from career_console.infrastructure.database.models import (
    AgentRunModel,
    ReviewBundleItemModel,
    ReviewBundleModel,
    ReviewTaskModel,
)


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
        # ReviewBundleItem has a real foreign key to review_tasks.  The models
        # deliberately do not define ORM relationships, so make the principal
        # durable before a bundle link is inserted.
        session.flush()
        return task
    if task.status == "open":
        task.title = title[:300]
        task.summary = summary[:5_000]
        task.source_type = source_type[:80]
        task.priority = priority
        task.agent_run_id = agent_run_id or task.agent_run_id
        task.updated_at = now
    return task


def ensure_review_bundle(
    session: Session,
    *,
    bundle_type: str,
    source_type: str,
    source_entity_id: str,
    title: str,
    summary: str,
    now: datetime,
    section_type: str | None = None,
    aggregate_key: str | None = None,
    priority: int = 0,
    agent_run_id: str | None = None,
) -> ReviewBundleModel:
    bundle = session.scalar(
        select(ReviewBundleModel).where(
            ReviewBundleModel.bundle_type == bundle_type,
            ReviewBundleModel.source_type == source_type,
            ReviewBundleModel.source_entity_id == source_entity_id,
            ReviewBundleModel.section_type == section_type,
            ReviewBundleModel.aggregate_key == aggregate_key,
        )
    )
    if bundle is None:
        bundle = ReviewBundleModel(
            id=str(uuid4()),
            bundle_type=bundle_type[:80],
            source_type=source_type[:80],
            source_entity_id=source_entity_id[:100],
            title=title[:300],
            summary=summary[:5_000],
            section_type=section_type[:80] if section_type else None,
            aggregate_key=aggregate_key[:160] if aggregate_key else None,
            status="open",
            version=1,
            priority=priority,
            agent_run_id=agent_run_id,
            created_at=now,
            updated_at=now,
            resolved_at=None,
            resolution=None,
            resolution_reason=None,
            resolved_by=None,
        )
        session.add(bundle)
        session.flush()
    elif bundle.status == "open":
        bundle.title = title[:300]
        bundle.summary = summary[:5_000]
        bundle.priority = priority
        bundle.agent_run_id = agent_run_id or bundle.agent_run_id
        bundle.updated_at = now
    return bundle


def link_review_task(
    session: Session,
    *,
    bundle: ReviewBundleModel,
    task: ReviewTaskModel,
    entity_type: str,
    entity_id: str,
    now: datetime,
    display_order: int = 0,
    required: bool = True,
) -> ReviewBundleItemModel:
    # Callers may pass newly-created principals.  Explicit flushing keeps
    # SQLite foreign-key ordering deterministic without adding persistence
    # relationships to the domain-facing models.
    session.flush()
    link = session.scalar(
        select(ReviewBundleItemModel).where(
            ReviewBundleItemModel.bundle_id == bundle.id,
            ReviewBundleItemModel.review_task_id == task.id,
        )
    )
    if link is None:
        link = ReviewBundleItemModel(
            id=str(uuid4()),
            bundle_id=bundle.id,
            review_task_id=task.id,
            entity_type=entity_type[:80],
            entity_id=entity_id[:100],
            display_order=display_order,
            required=int(required),
            created_at=now,
        )
        session.add(link)
    return link


def refresh_bundle_resolution(session: Session, bundle_id: str, *, now: datetime) -> None:
    bundle = session.get(ReviewBundleModel, bundle_id)
    if bundle is None:
        return
    tasks = session.scalars(
        select(ReviewTaskModel)
        .join(ReviewBundleItemModel, ReviewBundleItemModel.review_task_id == ReviewTaskModel.id)
        .where(ReviewBundleItemModel.bundle_id == bundle_id)
    ).all()
    if not tasks or any(task.status == "open" for task in tasks):
        bundle.status = "open"
        bundle.resolved_at = None
        bundle.resolution = None
        bundle.resolution_reason = None
        bundle.resolved_by = None
    else:
        resolutions = {task.resolution for task in tasks}
        bundle.status = "resolved"
        bundle.resolved_at = now
        bundle.resolution = resolutions.pop() if len(resolutions) == 1 else "mixed"
        bundle.resolution_reason = "组内事项已全部处理。"
        bundle.resolved_by = "user"
    bundle.version += 1
    bundle.updated_at = now


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
    skill_version: str | None = None,
    tool_calls: list[dict] | None = None,
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
        skill_version=skill_version[:100] if skill_version else None,
        schema_version=schema_version[:32],
        document_id=document_id,
        input_entity_type=input_entity_type,
        input_entity_id=input_entity_id,
        input_revision=input_revision,
        input_hash=input_hash,
        output_hash=output_hash,
        tool_calls_json=json.dumps(tool_calls or [], ensure_ascii=False, separators=(",", ":")),
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
