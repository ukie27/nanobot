"""Unified read model for review tasks and audited Agent runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, sessionmaker

from career_console.infrastructure.database.models import (
    AgentRunModel,
    ApplicationEventProposalModel,
    MailIntelligenceAnalysisModel,
    MailIntelligenceItemModel,
    ReviewBundleItemModel,
    ReviewBundleModel,
    ReviewTaskModel,
)

_REVIEW_TARGETS = {
    "candidate_fact": "/review",
    "mail_intelligence_item": "/message-center",
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
            bundle_statement = select(ReviewBundleModel)
            if status is not None:
                bundle_statement = bundle_statement.where(ReviewBundleModel.status == status)
            bundles = session.scalars(
                bundle_statement.order_by(
                    ReviewBundleModel.priority.desc(), ReviewBundleModel.created_at
                )
            ).all()
            legacy_statement = select(ReviewTaskModel).where(
                ~exists().where(ReviewBundleItemModel.review_task_id == ReviewTaskModel.id)
            )
            if status is not None:
                legacy_statement = legacy_statement.where(ReviewTaskModel.status == status)
            legacy = session.scalars(
                legacy_statement.order_by(
                    ReviewTaskModel.priority.desc(), ReviewTaskModel.created_at
                )
            ).all()
            return [
                *[self._bundle_view(session, item) for item in bundles],
                *[self._review_view(session, item) for item in legacy],
            ]

    def get_review(self, review_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            bundle = session.get(ReviewBundleModel, review_id)
            if bundle is not None:
                return self._bundle_view(session, bundle)
            row = session.get(ReviewTaskModel, review_id)
            if row is None:
                raise LookupError("审查任务不存在。")
            return self._review_view(session, row)

    @classmethod
    def _bundle_view(cls, session: Session, row: ReviewBundleModel) -> dict[str, Any]:
        links = session.scalars(
            select(ReviewBundleItemModel)
            .where(ReviewBundleItemModel.bundle_id == row.id)
            .order_by(ReviewBundleItemModel.display_order, ReviewBundleItemModel.created_at)
        ).all()
        items = []
        for link in links:
            task = session.get(ReviewTaskModel, link.review_task_id)
            if task is not None:
                item = cls._review_view(session, task)
                item["required"] = bool(link.required)
                items.append(item)
        first = items[0] if items else None
        return {
            "id": row.id,
            "task_type": f"{row.bundle_type}_review",
            "entity_type": "review_bundle",
            "entity_id": row.id,
            "title": row.title,
            "summary": row.summary,
            "source_type": row.source_type,
            "priority": row.priority,
            "status": row.status,
            "version": row.version,
            "agent_run_id": row.agent_run_id,
            "target_url": cls._bundle_target(row, first),
            "entity_subtype": row.bundle_type,
            "can_resolve_inline": False,
            "bundle_type": row.bundle_type,
            "section_type": row.section_type,
            "aggregate_key": row.aggregate_key,
            "item_count": len(items),
            "items": items,
            "created_at": cls._utc(row.created_at),
            "updated_at": cls._utc(row.updated_at),
            "resolved_at": cls._utc(row.resolved_at),
            "resolution": row.resolution,
            "resolution_reason": row.resolution_reason,
            "resolved_by": row.resolved_by,
        }

    @staticmethod
    def _bundle_target(row: ReviewBundleModel, first: dict[str, Any] | None) -> str:
        if row.bundle_type == "profile_section":
            return f"/reviews/{row.id}"
        if row.bundle_type == "mail_analysis":
            return first["target_url"] if first else "/message-center"
        return f"/reviews/{row.id}"

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
    def _review_view(cls, session: Session, row: ReviewTaskModel) -> dict[str, Any]:
        entity_subtype = None
        can_resolve_inline = False
        if row.entity_type == "mail_intelligence_item":
            item = session.get(MailIntelligenceItemModel, row.entity_id)
            if item is not None:
                entity_subtype = item.item_type
                can_resolve_inline = item.item_type != "create_application"
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
            "target_url": cls._review_target(session, row),
            "entity_subtype": entity_subtype,
            "can_resolve_inline": can_resolve_inline,
            "bundle_type": None,
            "section_type": None,
            "aggregate_key": None,
            "item_count": 1,
            "items": [],
            "created_at": cls._utc(row.created_at),
            "updated_at": cls._utc(row.updated_at or row.created_at),
            "resolved_at": cls._utc(row.resolved_at),
            "resolution": row.resolution,
            "resolution_reason": row.resolution_reason,
            "resolved_by": row.resolved_by,
        }

    @staticmethod
    def _review_target(session: Session, row: ReviewTaskModel) -> str:
        if row.entity_type == "application_event_proposal":
            proposal = session.get(ApplicationEventProposalModel, row.entity_id)
            if proposal is not None:
                return (
                    f"/applications/{proposal.application_id}"
                    f"?review={proposal.id}"
                )
            return "/applications"
        if row.entity_type == "mail_intelligence_item":
            item = session.get(MailIntelligenceItemModel, row.entity_id)
            analysis = (
                session.get(MailIntelligenceAnalysisModel, item.analysis_id)
                if item is not None
                else None
            )
            if analysis is not None:
                return f"/message-center?messageId={analysis.mail_message_id}"
        return _REVIEW_TARGETS.get(row.entity_type, "/workspace")

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
