"""Structured Career profile memory, digests, insights, and strategy snapshots."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from career_console.infrastructure.database.models import (
    AgentRunModel,
    ApplicationEventModel,
    ApplicationModel,
    CandidateFactModel,
    CareerPreferenceModel,
    CareerTaskModel,
    DailyDigestModel,
    ImprovementItemModel,
    ProfileChangeEventModel,
    ProfileImpactRunModel,
    ProfileInsightProposalModel,
    ReviewTaskModel,
    StrategySnapshotModel,
)
from career_console.infrastructure.database.profile_gateway import (
    PROFILE_ID,
    VersionConflictError,
    ensure_profile_model,
)
from career_console.infrastructure.database.review_runtime import create_agent_run


class SqlAlchemyProfileMemoryGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def overview(self) -> dict[str, Any]:
        with self._session_factory() as session:
            preferences = session.scalars(select(CareerPreferenceModel).where(
                CareerPreferenceModel.profile_id == PROFILE_ID
            ).order_by(CareerPreferenceModel.preference_key)).all()
            insights = session.scalars(select(ProfileInsightProposalModel).where(
                ProfileInsightProposalModel.profile_id == PROFILE_ID,
                ProfileInsightProposalModel.status == "active",
            ).order_by(ProfileInsightProposalModel.created_at.desc())).all()
            strategies = session.scalars(select(StrategySnapshotModel).where(
                StrategySnapshotModel.profile_id == PROFILE_ID
            ).order_by(StrategySnapshotModel.version_number.desc())).all()
            digests = session.scalars(select(DailyDigestModel).where(
                DailyDigestModel.profile_id == PROFILE_ID
            ).order_by(DailyDigestModel.digest_date.desc()).limit(14)).all()
            changes = session.scalars(select(ProfileChangeEventModel).where(
                ProfileChangeEventModel.profile_id == PROFILE_ID
            ).order_by(ProfileChangeEventModel.occurred_at.desc()).limit(100)).all()
            impacts = session.scalars(select(ProfileImpactRunModel).order_by(
                ProfileImpactRunModel.created_at.desc()
            ).limit(200)).all()
            return {
                "preferences": [self._preference_view(row) for row in preferences],
                "insights": [self._insight_view(session, row) for row in insights],
                "strategies": [self._strategy_view(session, row) for row in strategies],
                "digests": [self._digest_view(row) for row in digests],
                "changes": [self._change_view(row) for row in changes],
                "impact_runs": [self._impact_view(row) for row in impacts],
            }

    def run_due(self) -> dict[str, Any]:
        """Legacy gateway-only maintenance retained for adapter compatibility."""
        digest = self.generate_daily_digest()
        strategy = None
        if datetime.now(ZoneInfo("Asia/Shanghai")).weekday() == 0:
            strategy = self.generate_strategy_proposal()
        return {"digest_id": digest["id"], "strategy_id": strategy["id"] if strategy else None}

    def set_preference(
        self, *, preference_key: str, value: Any, expected_version: int | None
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        key = preference_key.strip().casefold()
        if not key or len(key) > 100:
            raise ValueError("偏好字段标识无效。")
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded) > 10_000:
            raise ValueError("偏好内容过长。")
        with self._session_factory() as session:
            self._ensure_profile(session, now)
            row = session.scalar(select(CareerPreferenceModel).where(
                CareerPreferenceModel.profile_id == PROFILE_ID,
                CareerPreferenceModel.preference_key == key,
            ))
            previous: Any = None
            if row is None:
                if expected_version is not None:
                    raise VersionConflictError("Preference no longer matches the loaded version.")
                row = CareerPreferenceModel(
                    id=str(uuid4()), profile_id=PROFILE_ID, preference_key=key,
                    value_json=encoded, status="confirmed", version=1,
                    created_at=now, updated_at=now,
                )
                session.add(row)
            else:
                if expected_version != row.version:
                    raise VersionConflictError("Preference changed after it was loaded.")
                previous = json.loads(row.value_json)
                if row.value_json == encoded:
                    return self._preference_view(row)
                row.value_json = encoded
                row.version += 1
                row.updated_at = now
            self._add_change(
                session, event_type="preference_confirmed", entity_type="career_preference",
                entity_id=row.id, entity_revision=row.version,
                changed_fields={"preference_key": key, "previous": previous, "value": value},
                impact_scopes=["opportunity_filter", "job_fit", "material_strategy", "career_strategy"],
                source="user", now=now,
            )
            session.commit()
            return self._preference_view(row)

    def generate_daily_digest(self, *, day: str | None = None) -> dict[str, Any]:
        china = ZoneInfo("Asia/Shanghai")
        local_day = datetime.fromisoformat(day).date() if day else datetime.now(china).date()
        start = datetime.combine(local_day, time.min, tzinfo=china).astimezone(UTC)
        end = start + timedelta(days=1)
        now = datetime.now(UTC)
        with self._session_factory() as session:
            self._ensure_profile(session, now)
            changes = session.scalars(select(ProfileChangeEventModel).where(
                ProfileChangeEventModel.profile_id == PROFILE_ID,
                ProfileChangeEventModel.occurred_at >= start,
                ProfileChangeEventModel.occurred_at < end,
            ).order_by(ProfileChangeEventModel.occurred_at)).all()
            application_events = session.scalars(select(ApplicationEventModel).where(
                ApplicationEventModel.created_at >= start,
                ApplicationEventModel.created_at < end,
            ).order_by(ApplicationEventModel.created_at)).all()
            pending_reviews = session.scalar(select(func.count()).select_from(ReviewTaskModel).where(
                ReviewTaskModel.status == "open"
            )) or 0
            tasks = session.scalars(select(CareerTaskModel).where(
                CareerTaskModel.status == "pending"
            ).order_by(CareerTaskModel.due_at).limit(20)).all()
            overdue = [task for task in tasks if self._aware(task.due_at) < now]
            content = {
                "schema_version": "daily_digest.v1",
                "date": local_day.isoformat(),
                "changes": [self._change_view(row) for row in changes],
                "application_changes": [
                    {"id": row.id, "application_id": row.application_id,
                     "event_type": row.event_type, "to_status": row.to_status,
                     "occurred_at": self._utc(row.occurred_at)}
                    for row in application_events
                ],
                "pending_review_count": pending_reviews,
                "risks": [f"{len(overdue)} 个任务已逾期"] if overdue else [],
                "tomorrow_actions": [
                    {"task_id": row.id, "title": row.title, "due_at": self._utc(row.due_at)}
                    for row in tasks[:5]
                ],
            }
            encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
            input_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            session.execute(sqlite_insert(DailyDigestModel).values(
                id=str(uuid4()), profile_id=PROFILE_ID,
                digest_date=local_day.isoformat(), schema_version="daily_digest.v1",
                content_json=encoded, input_hash=input_hash, generated_at=now,
            ).on_conflict_do_update(
                index_elements=["profile_id", "digest_date"],
                set_={"content_json": encoded, "input_hash": input_hash, "generated_at": now},
            ))
            session.commit()
            row = session.scalar(select(DailyDigestModel).where(
                DailyDigestModel.profile_id == PROFILE_ID,
                DailyDigestModel.digest_date == local_day.isoformat(),
            ))
            if row is None:
                raise RuntimeError("Daily digest upsert did not produce a row.")
            return self._digest_view(row)

    def generate_strategy_proposal(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        period_start = now - timedelta(days=7)
        with self._session_factory() as session:
            self._ensure_profile(session, now)
            latest = session.scalar(select(StrategySnapshotModel).where(
                StrategySnapshotModel.profile_id == PROFILE_ID
            ).order_by(StrategySnapshotModel.version_number.desc()))
            if latest is not None and self._aware(latest.created_at) >= period_start:
                return self._strategy_view(session, latest)
            preferences = session.scalars(select(CareerPreferenceModel).where(
                CareerPreferenceModel.profile_id == PROFILE_ID,
                CareerPreferenceModel.status == "confirmed",
            )).all()
            facts = session.scalars(select(CandidateFactModel).where(
                CandidateFactModel.profile_id == PROFILE_ID,
                CandidateFactModel.status == "confirmed",
            )).all()
            applications = session.scalars(select(ApplicationModel)).all()
            changes = session.scalars(select(ProfileChangeEventModel).where(
                ProfileChangeEventModel.profile_id == PROFILE_ID,
                ProfileChangeEventModel.occurred_at >= period_start,
            )).all()
            version_number = (session.scalar(select(func.max(StrategySnapshotModel.version_number)).where(
                StrategySnapshotModel.profile_id == PROFILE_ID
            )) or 0) + 1
            preference_map = {row.preference_key: json.loads(row.value_json) for row in preferences}
            content = {
                "schema_version": "career_strategy.v1",
                "target_directions": preference_map.get("target_roles", []),
                "priority_locations": preference_map.get("target_cities", []),
                "constraints": preference_map.get("constraints", []),
                "application_count": len(applications),
                "confirmed_fact_count": len(facts),
                "actions": [
                    "根据目标岗位复核当前最重要的能力缺口",
                    "优先完善高匹配岗位的真实 JD 和材料",
                    "复核即将到期的申请任务与面试准备",
                ],
                "evaluation_period_days": 7,
            }
            row = StrategySnapshotModel(
                id=str(uuid4()), profile_id=PROFILE_ID, version_number=version_number,
                schema_version="career_strategy.v1", period_start=period_start, period_end=now,
                content_json=json.dumps(content, ensure_ascii=False),
                evidence_refs_json=json.dumps([item.id for item in changes]),
                status="active", version=1, resolution_reason=None,
                created_at=now, resolved_at=None,
            )
            session.add(row)
            session.flush()
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                winner = session.scalar(select(StrategySnapshotModel).where(
                    StrategySnapshotModel.profile_id == PROFILE_ID
                ).order_by(StrategySnapshotModel.version_number.desc()))
                if winner is None:
                    raise
                return self._strategy_view(session, winner)
            return self._strategy_view(session, row)

    def profile_insight_context(self) -> dict[str, Any]:
        """Return only confirmed structured data and small recent aggregates."""
        now = datetime.now(UTC)
        period_start = now - timedelta(days=7)
        with self._session_factory() as session:
            self._ensure_profile(session, now)
            facts = session.scalars(select(CandidateFactModel).where(
                CandidateFactModel.profile_id == PROFILE_ID,
                CandidateFactModel.status == "confirmed",
            ).order_by(CandidateFactModel.id)).all()
            if not facts:
                raise ValueError("至少需要一条已确认事实才能生成洞察候选。")
            preferences = session.scalars(select(CareerPreferenceModel).where(
                CareerPreferenceModel.profile_id == PROFILE_ID,
                CareerPreferenceModel.status == "confirmed",
            ).order_by(CareerPreferenceModel.preference_key)).all()
            applications = session.scalars(select(ApplicationModel)).all()
            improvements = session.scalars(select(ImprovementItemModel).where(
                ImprovementItemModel.status == "active",
            ).order_by(
                ImprovementItemModel.updated_at.desc(),
                ImprovementItemModel.id,
            )).all()
            recent_changes = session.scalar(select(func.count()).select_from(
                ProfileChangeEventModel
            ).where(
                ProfileChangeEventModel.profile_id == PROFILE_ID,
                ProfileChangeEventModel.occurred_at >= period_start,
            )) or 0
            revision_source = [
                *(f"fact:{item.id}:{item.version}" for item in facts),
                *(f"preference:{item.id}:{item.version}" for item in preferences),
                *(
                    f"improvement:{item.id}:{self._utc(item.updated_at).isoformat()}:"
                    f"{item.occurrence_count}"
                    for item in improvements
                ),
            ]
            input_revision = hashlib.sha256("\n".join(revision_source).encode()).hexdigest()
            statuses: dict[str, int] = {}
            for application in applications:
                statuses[application.current_status] = statuses.get(application.current_status, 0) + 1
            return {
                "schemaVersion": "profile_insight_context.v3",
                "businessTimezone": "Asia/Shanghai",
                "inputRevision": input_revision,
                "confirmedFacts": [
                    {"id": item.id, "category": item.category, "fieldKey": item.field_key,
                     "value": item.value, "version": item.version}
                    for item in facts
                ],
                "confirmedPreferences": [
                    {"key": item.preference_key, "value": json.loads(item.value_json),
                     "version": item.version}
                    for item in preferences
                ],
                "confirmedInterviewImprovements": [
                    {
                        "id": item.id,
                        "category": item.category,
                        "title": item.title,
                        "description": item.description,
                        "occurrenceCount": item.occurrence_count,
                        "updatedAt": self._utc(item.updated_at),
                    }
                    for item in improvements
                ],
                "recentSevenDayAggregates": {
                    "profileChangeCount": recent_changes,
                    "applicationCount": len(applications),
                    "applicationStatusCounts": statuses,
                },
            }

    def existing_profile_insights(self, *, input_hash: str) -> list[dict[str, Any]] | None:
        """Return a completed result for the same trusted input, including an empty result."""
        with self._session_factory() as session:
            run = session.scalar(
                select(AgentRunModel)
                .where(
                    AgentRunModel.task_type == "profile_insight",
                    AgentRunModel.schema_version == "profile_insight.v3",
                    AgentRunModel.input_hash == input_hash,
                    AgentRunModel.status == "succeeded",
                )
                .order_by(AgentRunModel.created_at.desc())
            )
            if run is None:
                return None
            rows = session.scalars(
                select(ProfileInsightProposalModel)
                .where(
                    ProfileInsightProposalModel.agent_run_id == run.id,
                    ProfileInsightProposalModel.status == "active",
                )
                .order_by(ProfileInsightProposalModel.created_at)
            ).all()
            return [self._insight_view(session, row) for row in rows]

    def save_profile_insights(self, *, result: Any, input_hash: str, input_revision: str,
                              output_hash: str, audit: dict[str, Any]) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            run = create_agent_run(
                session, task_type="profile_insight", implementation=audit["implementation"],
                schema_version=result.schema_version, status="succeeded",
                output_count=len(result.insights), error_code=None,
                created_at=audit["created_at"], finished_at=now,
                provider=audit.get("provider"), model=audit.get("model"),
                prompt_version=audit.get("prompt_version"),
                skill_version=audit.get("skill_version"),
                input_entity_type="candidate_profile",
                input_entity_id=PROFILE_ID, input_revision=input_revision, input_hash=input_hash,
                output_hash=output_hash, input_tokens=audit.get("input_tokens"),
                output_tokens=audit.get("output_tokens"), duration_ms=audit.get("duration_ms"),
                retry_count=audit.get("retry_count", 0), sensitivity="sensitive",
            )
            previous_rows = session.scalars(
                select(ProfileInsightProposalModel).where(
                    ProfileInsightProposalModel.profile_id == PROFILE_ID,
                    ProfileInsightProposalModel.status == "active",
                )
            ).all()
            for previous in previous_rows:
                previous.status = "superseded"
                previous.version += 1
                previous.resolution_reason = "由最新一轮档案分析替代"
                previous.resolved_at = now
            rows = []
            for insight in result.insights:
                row = ProfileInsightProposalModel(
                    id=str(uuid4()), profile_id=PROFILE_ID, insight_type=insight.category,
                    conclusion=insight.analysis, recommended_action=insight.recommendation,
                    evidence_refs_json=json.dumps({
                        "fact_ids": insight.evidence_fact_ids,
                        "improvement_ids": insight.evidence_improvement_ids,
                    }),
                    counter_evidence_json=json.dumps(insight.counter_evidence_fact_ids),
                    confidence=insight.confidence, source="career_console_profile_insight",
                    status="active", version=1, agent_run_id=run.id,
                    resolution_reason=None, created_at=now, resolved_at=None,
                )
                session.add(row)
                session.flush()
                rows.append(row)
            session.commit()
            return [self._insight_view(session, row) for row in rows]

    def save_profile_insight_failure(self, *, input_hash: str, input_revision: str,
                                     error_code: str, audit: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            create_agent_run(
                session, task_type="profile_insight", implementation=audit["implementation"],
                schema_version="profile_insight.v3", status="failed", output_count=0,
                error_code=error_code, created_at=audit["created_at"], finished_at=now,
                provider=audit.get("provider"), model=audit.get("model"),
                prompt_version=audit.get("prompt_version"),
                skill_version=audit.get("skill_version"),
                input_entity_type="candidate_profile",
                input_entity_id=PROFILE_ID, input_revision=input_revision, input_hash=input_hash,
                input_tokens=audit.get("input_tokens"), output_tokens=audit.get("output_tokens"),
                duration_ms=audit.get("duration_ms"), retry_count=audit.get("retry_count", 0),
                sensitivity="sensitive",
            )
            session.commit()

    @staticmethod
    def _add_change(session: Session, *, event_type: str, entity_type: str, entity_id: str,
                    entity_revision: int, changed_fields: dict[str, Any], impact_scopes: list[str],
                    source: str, now: datetime) -> None:
        session.add(ProfileChangeEventModel(
            id=str(uuid4()), profile_id=PROFILE_ID, event_type=event_type,
            entity_type=entity_type, entity_id=entity_id, entity_revision=entity_revision,
            changed_fields_json=json.dumps(changed_fields, ensure_ascii=False),
            impact_scopes_json=json.dumps(impact_scopes, ensure_ascii=False),
            source=source, occurred_at=now,
        ))

    @staticmethod
    def _ensure_profile(session: Session, now: datetime) -> None:
        ensure_profile_model(session, now)

    @staticmethod
    def _preference_view(row: CareerPreferenceModel) -> dict[str, Any]:
        return {"id": row.id, "preference_key": row.preference_key, "value": json.loads(row.value_json),
                "status": row.status, "version": row.version, "created_at": row.created_at, "updated_at": row.updated_at}

    @staticmethod
    def _change_view(row: ProfileChangeEventModel) -> dict[str, Any]:
        return {"id": row.id, "event_type": row.event_type, "entity_type": row.entity_type,
                "entity_id": row.entity_id, "entity_revision": row.entity_revision,
                "changed_fields": json.loads(row.changed_fields_json), "impact_scopes": json.loads(row.impact_scopes_json),
                "source": row.source, "occurred_at": SqlAlchemyProfileMemoryGateway._utc(row.occurred_at)}

    @staticmethod
    def _impact_view(row: ProfileImpactRunModel) -> dict[str, Any]:
        return {"id": row.id, "change_event_id": row.change_event_id, "scope": row.scope,
                "status": row.status, "background_job_id": row.background_job_id,
                "input_revision": row.input_revision, "affected_count": row.affected_count,
                "error_code": row.error_code,
                "created_at": SqlAlchemyProfileMemoryGateway._utc(row.created_at),
                "started_at": SqlAlchemyProfileMemoryGateway._utc(row.started_at),
                "finished_at": SqlAlchemyProfileMemoryGateway._utc(row.finished_at)}

    @staticmethod
    def _insight_view(session: Session, row: ProfileInsightProposalModel) -> dict[str, Any]:
        task = session.scalar(select(ReviewTaskModel).where(ReviewTaskModel.entity_type == "profile_insight", ReviewTaskModel.entity_id == row.id))
        evidence = json.loads(row.evidence_refs_json)
        if isinstance(evidence, list):
            evidence_fact_ids = evidence
            evidence_improvement_ids: list[str] = []
        else:
            evidence_fact_ids = evidence.get("fact_ids", [])
            evidence_improvement_ids = evidence.get("improvement_ids", [])
        return {"id": row.id, "category": row.insight_type, "analysis": row.conclusion,
                "recommendation": row.recommended_action,
                "evidence_refs": [*evidence_fact_ids, *evidence_improvement_ids],
                "evidence_fact_ids": evidence_fact_ids,
                "evidence_improvement_ids": evidence_improvement_ids,
                "counter_evidence": json.loads(row.counter_evidence_json),
                "confidence": row.confidence, "source": row.source, "status": row.status, "version": row.version,
                "agent_run_id": row.agent_run_id, "review_task_id": task.id if task else None,
                "resolution_reason": row.resolution_reason, "created_at": row.created_at, "resolved_at": row.resolved_at}

    @staticmethod
    def _strategy_view(session: Session, row: StrategySnapshotModel) -> dict[str, Any]:
        task = session.scalar(select(ReviewTaskModel).where(ReviewTaskModel.entity_type == "strategy_snapshot", ReviewTaskModel.entity_id == row.id))
        return {"id": row.id, "version_number": row.version_number, "schema_version": row.schema_version,
                "period_start": row.period_start, "period_end": row.period_end, "content": json.loads(row.content_json),
                "evidence_refs": json.loads(row.evidence_refs_json), "status": row.status, "version": row.version,
                "review_task_id": task.id if task else None, "resolution_reason": row.resolution_reason,
                "created_at": row.created_at, "resolved_at": row.resolved_at}

    @staticmethod
    def _digest_view(row: DailyDigestModel) -> dict[str, Any]:
        return {"id": row.id, "digest_date": row.digest_date, "schema_version": row.schema_version,
                "content": json.loads(row.content_json), "input_hash": row.input_hash, "generated_at": row.generated_at}

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return cls._aware(value) if value else None
