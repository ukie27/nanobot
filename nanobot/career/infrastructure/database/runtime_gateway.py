"""Unified read model for review tasks and audited Agent runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from nanobot.career.infrastructure.database.models import AgentRunModel, ReviewTaskModel

_REVIEW_TARGETS = {
    "candidate_fact": "/review",
    "application_event_proposal": "/application-review",
    "mail_intelligence_item": "/mail",
    "profile_insight": "/profile",
    "strategy_snapshot": "/profile",
    "job_fit_proposal": "/job-posts",
    "resume_direction_proposal": "/job-posts",
    "interview_feedback": "/interviews",
}


class SqlAlchemyRuntimeGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_reviews(self, *, status: str | None = "open") -> list[dict[str, Any]]:
        with self._session_factory() as session:
            statement = select(ReviewTaskModel)
            if status is not None:
                statement = statement.where(ReviewTaskModel.status == status)
            rows = session.scalars(
                statement.order_by(
                    ReviewTaskModel.priority.desc(), ReviewTaskModel.created_at
                )
            ).all()
            return [self._review_view(item) for item in rows]

    def get_review(self, review_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(ReviewTaskModel, review_id)
            if row is None:
                raise LookupError("审查任务不存在。")
            return self._review_view(row)

    def list_agent_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AgentRunModel)
                .order_by(AgentRunModel.created_at.desc())
                .limit(max(1, min(limit, 500)))
            ).all()
            return [self._agent_run_view(item) for item in rows]

    def get_agent_run(self, run_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(AgentRunModel, run_id)
            if row is None:
                raise LookupError("Agent 运行记录不存在。")
            return self._agent_run_view(row)

    @classmethod
    def _review_view(cls, row: ReviewTaskModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "task_type": row.task_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "title": row.title or cls._fallback_title(row.entity_type),
            "summary": row.summary or "等待用户核对业务对象。",
            "source_type": row.source_type or "legacy",
            "priority": row.priority,
            "status": row.status,
            "version": row.version,
            "agent_run_id": row.agent_run_id,
            "target_url": _REVIEW_TARGETS.get(row.entity_type, "/workspace"),
            "created_at": cls._utc(row.created_at),
            "updated_at": cls._utc(row.updated_at or row.created_at),
            "resolved_at": cls._utc(row.resolved_at),
            "resolution": row.resolution,
            "resolution_reason": row.resolution_reason,
            "resolved_by": row.resolved_by,
        }

    @classmethod
    def _agent_run_view(cls, row: AgentRunModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "task_type": row.task_type,
            "execution_mode": row.execution_mode,
            "implementation": row.implementation,
            "provider": row.provider,
            "model": row.model,
            "prompt_version": row.prompt_version,
            "skill_version": row.skill_version,
            "schema_version": row.schema_version,
            "input_entity_type": row.input_entity_type,
            "input_entity_id": row.input_entity_id,
            "input_revision": row.input_revision,
            "input_hash": row.input_hash,
            "output_hash": row.output_hash,
            "tool_calls": json.loads(row.tool_calls_json),
            "status": row.status,
            "output_count": row.output_count,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "duration_ms": row.duration_ms,
            "retry_count": row.retry_count,
            "sensitivity": row.sensitivity,
            "error_code": row.error_code,
            "created_at": cls._utc(row.created_at),
            "finished_at": cls._utc(row.finished_at),
            "retention_until": cls._utc(row.retention_until),
        }

    @staticmethod
    def _fallback_title(entity_type: str) -> str:
        return {
            "candidate_fact": "职业事实待确认",
            "application_event_proposal": "申请进度事件待确认",
            "interview_feedback": "面试改进建议待确认",
        }.get(entity_type, "业务对象待确认")

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
