"""Persistence, audit, and lifecycle actions for the daily recommendation pool."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.applications import ApplicationStatus
from career_console.domain.recommendations import JobRecommendationResult
from career_console.infrastructure.database.models import (
    ApplicationEventModel,
    ApplicationModel,
    CandidateFactModel,
    CareerPreferenceModel,
    CompanyModel,
    JobPostModel,
    JobPostSourceModel,
    JobPostVersionModel,
    JobRecommendationModel,
    JobRequirementModel,
    ProfileInsightProposalModel,
)
from career_console.infrastructure.database.profile_gateway import (
    PROFILE_ID,
    EntityNotFoundError,
    VersionConflictError,
    ensure_profile_model,
)
from career_console.infrastructure.database.review_runtime import create_agent_run


class SqlAlchemyRecommendationGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def context(
        self, job_id: str, *, manual_directions: list[str] | None = None
    ) -> dict[str, Any]:
        directions = sorted(
            {item.strip() for item in (manual_directions or []) if item.strip()}
        )
        with self._session_factory() as session:
            post = session.get(JobPostModel, job_id)
            if post is None:
                raise EntityNotFoundError("岗位不存在。")
            company = session.get(CompanyModel, post.company_id)
            version = session.scalar(
                select(JobPostVersionModel)
                .where(JobPostVersionModel.job_post_id == job_id)
                .order_by(JobPostVersionModel.version_number.desc())
            )
            requirements = list(
                session.scalars(
                    select(JobRequirementModel)
                    .where(JobRequirementModel.job_post_version_id == version.id)
                    .order_by(JobRequirementModel.ordinal)
                ).all()
            )
            if not requirements:
                raise ValueError("岗位没有可分析的结构化要求。")
            profile = ensure_profile_model(session, datetime.now(UTC))
            facts = list(
                session.scalars(
                    select(CandidateFactModel)
                    .where(
                        CandidateFactModel.profile_id == profile.id,
                        CandidateFactModel.status == "confirmed",
                    )
                    .order_by(CandidateFactModel.id)
                ).all()
            )
            if not facts:
                raise ValueError("至少需要一条已确认事实才能生成岗位推荐。")
            preferences = list(
                session.scalars(
                    select(CareerPreferenceModel)
                    .where(
                        CareerPreferenceModel.profile_id == profile.id,
                        CareerPreferenceModel.status == "confirmed",
                    )
                    .order_by(CareerPreferenceModel.preference_key)
                ).all()
            )
            insights = list(
                session.scalars(
                    select(ProfileInsightProposalModel)
                    .where(
                        ProfileInsightProposalModel.profile_id == profile.id,
                        ProfileInsightProposalModel.status == "confirmed",
                    )
                    .order_by(ProfileInsightProposalModel.created_at.desc())
                    .limit(50)
                ).all()
            )
            fact_hash = hashlib.sha256(
                "\n".join(
                    f"{item.id}:{item.version}:{item.value}" for item in facts
                ).encode("utf-8")
            ).hexdigest()
            preference_hash = hashlib.sha256(
                (
                    "\n".join(
                        f"{item.id}:{item.version}:{item.preference_key}:{item.value_json}"
                        for item in preferences
                    )
                    + "\nmanual:"
                    + json.dumps(directions, ensure_ascii=False, separators=(",", ":"))
                ).encode("utf-8")
            ).hexdigest()
            return {
                "schemaVersion": "daily_job_recommendation_context.v1",
                "businessTimezone": "Asia/Shanghai",
                "inputRevision": (
                    f"job:{version.id}:facts:{fact_hash}:preferences:{preference_hash}"
                ),
                "job": {
                    "id": post.id,
                    "versionId": version.id,
                    "versionNumber": version.version_number,
                    "company": company.canonical_name if company else "",
                    "title": post.title,
                    "location": post.location,
                    "workMode": post.work_mode,
                    "employmentType": post.employment_type,
                    "targetAudience": post.target_audience,
                    "deadlineAt": post.deadline_at.isoformat() if post.deadline_at else None,
                },
                "requirements": [
                    {
                        "id": item.id,
                        "category": item.category,
                        "level": item.level,
                        "description": item.description,
                        "evidenceText": item.evidence_text,
                        "weight": item.weight,
                    }
                    for item in requirements
                ],
                "confirmedFacts": [
                    {
                        "id": item.id,
                        "category": item.category,
                        "fieldKey": item.field_key,
                        "value": item.value,
                        "version": item.version,
                    }
                    for item in facts
                ],
                "confirmedPreferences": [
                    {
                        "key": item.preference_key,
                        "value": json.loads(item.value_json),
                        "version": item.version,
                    }
                    for item in preferences
                ],
                "confirmedInsights": [
                    {
                        "id": item.id,
                        "type": item.insight_type,
                        "conclusion": item.conclusion,
                        "confidence": item.confidence,
                        "evidenceRefs": json.loads(item.evidence_refs_json),
                    }
                    for item in insights
                ],
                "manualDirections": directions,
                "factSetHash": fact_hash,
                "preferenceSetHash": preference_hash,
            }

    def existing(self, *, job_id: str, input_hash: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(JobRecommendationModel)
                .where(
                    JobRecommendationModel.job_post_id == job_id,
                    JobRecommendationModel.input_hash == input_hash,
                )
                .order_by(JobRecommendationModel.recommended_at.desc())
            )
            return self._view(session, row) if row else None

    def save(
        self,
        *,
        job_id: str,
        opportunity_id: str | None,
        result: JobRecommendationResult,
        input_hash: str,
        output_hash: str,
        context: dict[str, Any],
        audit: dict[str, Any],
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            run = create_agent_run(
                session,
                task_type="daily_job_recommendation",
                implementation=audit["implementation"],
                schema_version=result.schema_version,
                status="succeeded",
                output_count=len(result.assessments),
                error_code=None,
                created_at=audit["created_at"],
                finished_at=now,
                provider=audit.get("provider"),
                model=audit.get("model"),
                prompt_version=audit.get("prompt_version"),
                skill_version=audit.get("skill_version"),
                input_entity_type="job_post",
                input_entity_id=job_id,
                input_revision=context["inputRevision"],
                input_hash=input_hash,
                output_hash=output_hash,
                input_tokens=audit.get("input_tokens"),
                output_tokens=audit.get("output_tokens"),
                duration_ms=audit.get("duration_ms"),
                retry_count=audit.get("retry_count", 0),
                sensitivity="sensitive",
            )
            row = JobRecommendationModel(
                id=str(uuid4()),
                job_post_id=job_id,
                job_post_version_id=context["job"]["versionId"],
                source_opportunity_id=opportunity_id,
                agent_run_id=run.id,
                profile_id=PROFILE_ID,
                fact_set_hash=context["factSetHash"],
                preference_set_hash=context["preferenceSetHash"],
                input_hash=input_hash,
                output_hash=output_hash,
                schema_version=result.schema_version,
                decision=result.decision,
                score=result.score,
                priority=result.priority,
                content_json=result.model_dump_json(by_alias=True),
                status="active" if result.decision == "recommend" else "stale",
                version=1,
                application_id=None,
                recommended_at=now,
                resolved_at=None if result.decision == "recommend" else now,
                resolution_reason=None if result.decision == "recommend" else "agent_rejected",
            )
            session.add(row)
            session.commit()
            return self._view(session, row) if row.status == "active" else None

    def save_failure(
        self,
        *,
        job_id: str,
        input_hash: str,
        input_revision: str,
        error_code: str,
        audit: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            create_agent_run(
                session,
                task_type="daily_job_recommendation",
                implementation=audit["implementation"],
                schema_version="daily_job_recommendation.v1",
                status="failed",
                output_count=0,
                error_code=error_code,
                created_at=audit["created_at"],
                finished_at=now,
                provider=audit.get("provider"),
                model=audit.get("model"),
                prompt_version=audit.get("prompt_version"),
                skill_version=audit.get("skill_version"),
                input_entity_type="job_post",
                input_entity_id=job_id,
                input_revision=input_revision,
                input_hash=input_hash,
                input_tokens=audit.get("input_tokens"),
                output_tokens=audit.get("output_tokens"),
                duration_ms=audit.get("duration_ms"),
                retry_count=audit.get("retry_count", 0),
                sensitivity="sensitive",
            )
            session.commit()

    def list(self, *, status: str = "active") -> dict[str, Any]:
        if status not in {"active", "accepted", "dismissed", "stale"}:
            raise ValueError("不支持的推荐状态。")
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(JobRecommendationModel)
                    .where(JobRecommendationModel.status == status)
                    .order_by(
                        JobRecommendationModel.score.desc(),
                        JobRecommendationModel.recommended_at.desc(),
                    )
                ).all()
            )
            return {"items": [self._view(session, row) for row in rows], "total": len(rows)}

    def get(self, recommendation_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(JobRecommendationModel, recommendation_id)
            if row is None:
                raise EntityNotFoundError("岗位推荐不存在。")
            return self._view(session, row)

    def dismiss(
        self, recommendation_id: str, *, expected_version: int, reason: str
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = self._recommendation(session, recommendation_id)
            if row.status != "active":
                return self._view(session, row)
            if row.version != expected_version:
                raise VersionConflictError("岗位推荐已变化，请刷新后重试。")
            row.status = "dismissed"
            row.version += 1
            row.resolved_at = now
            row.resolution_reason = (reason.strip() or "user_dismissed")[:500]
            session.commit()
            return self._view(session, row)

    def accept(
        self,
        recommendation_id: str,
        *,
        expected_version: int,
        command_id: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = self._recommendation(session, recommendation_id)
            if row.status == "accepted":
                return self._view(session, row)
            if row.status != "active":
                raise ValueError("只有推荐池中的岗位可以加入投递计划。")
            if row.version != expected_version:
                raise VersionConflictError("岗位推荐已变化，请刷新后重试。")
            application = (
                session.get(ApplicationModel, row.application_id)
                if row.application_id
                else None
            )
            if application is None:
                application = session.scalar(
                    select(ApplicationModel)
                    .where(
                        ApplicationModel.job_post_id == row.job_post_id,
                        ApplicationModel.archived_at.is_(None),
                    )
                    .order_by(ApplicationModel.created_at.desc())
                )
            post = session.get(JobPostModel, row.job_post_id)
            version = session.get(JobPostVersionModel, row.job_post_version_id)
            company = session.get(CompanyModel, post.company_id)
            if application is None:
                application = ApplicationModel(
                    id=str(uuid4()),
                    job_post_id=post.id,
                    job_post_version_id=version.id,
                    job_title_snapshot=post.title,
                    company_name_snapshot=company.canonical_name if company else "",
                    job_content_hash=version.content_hash,
                    current_status=ApplicationStatus.DISCOVERED.value,
                    version=1,
                    created_at=now,
                    updated_at=now,
                    archived_at=None,
                )
                session.add(application)
                session.flush()
                self._append_event(
                    session,
                    application,
                    event_type="application_created",
                    from_status=None,
                    to_status=ApplicationStatus.DISCOVERED.value,
                    occurred_at=now,
                    note="Application tracking created from a daily recommendation.",
                    source="user",
                    command_id=f"create:{command_id}",
                )
                session.flush()
                self._append_event(
                    session,
                    application,
                    event_type="application_status_changed",
                    from_status=ApplicationStatus.DISCOVERED.value,
                    to_status=ApplicationStatus.PREPARING_MATERIALS.value,
                    occurred_at=now,
                    note="Application materials must be bound before submission.",
                    source="system",
                    command_id=command_id,
                )
                application.current_status = ApplicationStatus.PREPARING_MATERIALS.value
                application.version += 1
                application.updated_at = now
            elif application.current_status == ApplicationStatus.DISCOVERED.value:
                self._append_event(
                    session,
                    application,
                    event_type="application_status_changed",
                    from_status=ApplicationStatus.DISCOVERED.value,
                    to_status=ApplicationStatus.PREPARING_MATERIALS.value,
                    occurred_at=now,
                    note="Application materials must be bound before submission.",
                    source="system",
                    command_id=command_id,
                )
                application.current_status = ApplicationStatus.PREPARING_MATERIALS.value
                application.version += 1
                application.updated_at = now
            row.status = "accepted"
            row.version += 1
            row.application_id = application.id
            row.resolved_at = now
            row.resolution_reason = "user_added_to_application_plan"
            session.commit()
            return self._view(session, row)

    @staticmethod
    def _append_event(
        session: Session,
        application: ApplicationModel,
        *,
        event_type: str,
        from_status: str | None,
        to_status: str,
        occurred_at: datetime,
        note: str,
        source: str,
        command_id: str,
    ) -> None:
        sequence = (
            session.scalar(
                select(ApplicationEventModel.sequence_number)
                .where(ApplicationEventModel.application_id == application.id)
                .order_by(ApplicationEventModel.sequence_number.desc())
                .limit(1)
            )
            or 0
        ) + 1
        session.add(
            ApplicationEventModel(
                id=str(uuid4()),
                application_id=application.id,
                sequence_number=sequence,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                occurred_at=occurred_at,
                note=note,
                source=source,
                proposal_id=None,
                supersedes_event_id=None,
                idempotency_key=command_id,
                created_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def _recommendation(
        session: Session, recommendation_id: str
    ) -> JobRecommendationModel:
        row = session.get(JobRecommendationModel, recommendation_id)
        if row is None:
            raise EntityNotFoundError("岗位推荐不存在。")
        return row

    def _view(self, session: Session, row: JobRecommendationModel) -> dict[str, Any]:
        post = session.get(JobPostModel, row.job_post_id)
        company = session.get(CompanyModel, post.company_id)
        source = session.scalar(
            select(JobPostSourceModel)
            .where(JobPostSourceModel.job_post_id == post.id)
            .order_by(JobPostSourceModel.last_seen_at.desc())
        )
        return {
            "id": row.id,
            "job_post_id": row.job_post_id,
            "job_post_version_id": row.job_post_version_id,
            "source_opportunity_id": row.source_opportunity_id,
            "agent_run_id": row.agent_run_id,
            "application_id": row.application_id,
            "company": company.canonical_name if company else "",
            "title": post.title,
            "location": post.location,
            "deadline_at": self._utc(post.deadline_at),
            "application_url": source.source_url if source else None,
            "schema_version": row.schema_version,
            "decision": row.decision,
            "score": row.score,
            "priority": row.priority,
            "content": json.loads(row.content_json),
            "status": row.status,
            "version": row.version,
            "recommended_at": self._utc(row.recommended_at),
            "resolved_at": self._utc(row.resolved_at),
            "resolution_reason": row.resolution_reason,
        }

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
