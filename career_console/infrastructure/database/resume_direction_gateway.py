"""Persistence for Resume Direction Agent proposals and user selections."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.materials import ResumeDirectionResult
from career_console.infrastructure.database.models import (
    CandidateFactModel,
    CareerPreferenceModel,
    CompanyModel,
    JobMatchAnalysisModel,
    JobMatchEvidenceModel,
    JobPostModel,
    JobPostVersionModel,
    JobRequirementModel,
    ResumeDirectionProposalModel,
    ResumeDirectionSelectionModel,
    ReviewTaskModel,
)
from career_console.infrastructure.database.profile_gateway import (
    PROFILE_ID,
    VersionConflictError,
)
from career_console.infrastructure.database.review_runtime import (
    create_agent_run,
    ensure_review_task,
    set_review_resolution,
)


class SqlAlchemyResumeDirectionGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def context(self, job_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            post = session.get(JobPostModel, job_id)
            if post is None:
                raise LookupError("岗位不存在。")
            company = session.get(CompanyModel, post.company_id)
            version = self._latest_version(session, job_id)
            analysis = self._latest_analysis(session, job_id)
            requirements = self._requirements(session, version.id)
            facts = self._facts(session)
            if not facts:
                raise ValueError("至少需要一条已确认事实才能规划简历方向。")
            preferences = self._preferences(session)
            evidence_rows = session.scalars(select(JobMatchEvidenceModel).where(
                JobMatchEvidenceModel.analysis_id == analysis.id
            )).all()
            evidence_by_requirement: dict[str, list[str]] = {}
            for row in evidence_rows:
                if row.fact_id:
                    evidence_by_requirement.setdefault(row.requirement_id, []).append(row.fact_id)
            fact_hash = self._fact_hash(facts)
            preference_hash = self._preference_hash(preferences)
            return {
                "schemaVersion": "resume_direction_context.v1",
                "businessTimezone": "Asia/Shanghai",
                "inputRevision": (
                    f"job:{version.id}:analysis:{analysis.id}:facts:{fact_hash}:"
                    f"preferences:{preference_hash}"
                ),
                "job": {
                    "id": post.id, "versionId": version.id,
                    "company": company.canonical_name if company else "", "title": post.title,
                    "location": post.location, "workMode": post.work_mode,
                    "targetAudience": post.target_audience,
                },
                "formalMatch": {
                    "analysisId": analysis.id, "score": analysis.score,
                    "hardGatePassed": bool(analysis.hard_gate_passed),
                    "recommendation": analysis.recommendation,
                },
                "requirements": [
                    {"id": item.id, "category": item.category, "level": item.level,
                     "description": item.description,
                     "matchedFactIds": evidence_by_requirement.get(item.id, [])}
                    for item in requirements
                ],
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
                "factSetHash": fact_hash,
                "preferenceSetHash": preference_hash,
            }

    def existing(self, job_id: str, input_hash: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.scalar(select(ResumeDirectionProposalModel).where(
                ResumeDirectionProposalModel.job_post_id == job_id,
                ResumeDirectionProposalModel.input_hash == input_hash,
                ResumeDirectionProposalModel.status == "proposed",
            ).order_by(ResumeDirectionProposalModel.created_at.desc()))
            return self._proposal_view(session, row) if row else None

    def save(self, *, job_id: str, result: ResumeDirectionResult, context: dict[str, Any],
             input_hash: str, output_hash: str, audit: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            post = session.get(JobPostModel, job_id)
            if post is None:
                raise LookupError("岗位不存在。")
            run = create_agent_run(
                session, task_type="resume_direction", implementation=audit["implementation"],
                schema_version=result.schema_version, status="succeeded",
                output_count=len(result.directions), error_code=None,
                created_at=audit["created_at"], finished_at=now,
                provider=audit.get("provider"), model=audit.get("model"),
                prompt_version=audit.get("prompt_version"), input_entity_type="job_post",
                input_entity_id=job_id, input_revision=context["inputRevision"],
                input_hash=input_hash, output_hash=output_hash,
                input_tokens=audit.get("input_tokens"), output_tokens=audit.get("output_tokens"),
                duration_ms=audit.get("duration_ms"), retry_count=audit.get("retry_count", 0),
                sensitivity="sensitive",
            )
            row = ResumeDirectionProposalModel(
                id=str(uuid4()), job_post_id=job_id,
                job_post_version_id=context["job"]["versionId"],
                job_match_analysis_id=context["formalMatch"]["analysisId"], profile_id=PROFILE_ID,
                fact_set_hash=context["factSetHash"],
                preference_set_hash=context["preferenceSetHash"],
                schema_version=result.schema_version,
                content_json=result.model_dump_json(by_alias=True), input_hash=input_hash,
                output_hash=output_hash, status="proposed", version=1, agent_run_id=run.id,
                resolution_reason=None, created_at=now, resolved_at=None,
            )
            session.add(row)
            session.flush()
            ensure_review_task(
                session, task_type="resume_direction_review",
                entity_type="resume_direction_proposal", entity_id=row.id,
                title=f"选择简历方向：{post.title}", summary=result.comparison_note,
                source_type="career_console_resume_direction", priority=20,
                agent_run_id=run.id, now=now,
            )
            session.commit()
            return self._proposal_view(session, row)

    def save_failure(self, *, job_id: str, input_hash: str, input_revision: str,
                     error_code: str, audit: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            create_agent_run(
                session, task_type="resume_direction", implementation=audit["implementation"],
                schema_version="resume_direction.v1", status="failed", output_count=0,
                error_code=error_code, created_at=audit["created_at"], finished_at=now,
                provider=audit.get("provider"), model=audit.get("model"),
                prompt_version=audit.get("prompt_version"), input_entity_type="job_post",
                input_entity_id=job_id, input_revision=input_revision, input_hash=input_hash,
                input_tokens=audit.get("input_tokens"), output_tokens=audit.get("output_tokens"),
                duration_ms=audit.get("duration_ms"), retry_count=audit.get("retry_count", 0),
                sensitivity="sensitive",
            )
            session.commit()

    def list_for_job(self, job_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            proposals = session.scalars(select(ResumeDirectionProposalModel).where(
                ResumeDirectionProposalModel.job_post_id == job_id
            ).order_by(ResumeDirectionProposalModel.created_at.desc())).all()
            selections = session.scalars(select(ResumeDirectionSelectionModel).where(
                ResumeDirectionSelectionModel.job_post_id == job_id
            ).order_by(ResumeDirectionSelectionModel.created_at.desc())).all()
            return {
                "proposals": [self._proposal_view(session, row) for row in proposals],
                "selections": [self._selection_view(row) for row in selections],
            }

    def resolve(self, proposal_id: str, *, expected_version: int, resolution: str,
                selected_direction_ids: list[str], reason: str) -> dict[str, Any]:
        if resolution not in {"confirmed", "rejected"}:
            raise ValueError("不支持的审核结果。")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(ResumeDirectionProposalModel, proposal_id)
            if row is None:
                raise LookupError("简历方向候选不存在。")
            if row.status != "proposed":
                return self._proposal_view(session, row)
            if row.version != expected_version:
                raise VersionConflictError("简历方向候选已变化，请刷新后重试。")
            result = ResumeDirectionResult.model_validate_json(row.content_json)
            if resolution == "confirmed":
                chosen = list(dict.fromkeys(selected_direction_ids))
                available = {item.direction_id: item for item in result.directions}
                if not 1 <= len(chosen) <= 2 or not set(chosen) <= set(available):
                    raise ValueError("必须从当前候选中选择一个方向，或组合两个方向。")
                self._assert_current(session, row)
                for old in session.scalars(select(ResumeDirectionSelectionModel).where(
                    ResumeDirectionSelectionModel.job_post_id == row.job_post_id,
                    ResumeDirectionSelectionModel.status == "active",
                )).all():
                    old.status = "superseded"
                    old.version += 1
                selection = ResumeDirectionSelectionModel(
                    id=str(uuid4()), proposal_id=row.id, job_post_id=row.job_post_id,
                    job_post_version_id=row.job_post_version_id, profile_id=row.profile_id,
                    fact_set_hash=row.fact_set_hash, preference_set_hash=row.preference_set_hash,
                    selected_direction_ids_json=json.dumps(chosen),
                    selected_content_json=json.dumps(
                        [available[item].model_dump(mode="json", by_alias=True) for item in chosen],
                        ensure_ascii=False,
                    ),
                    status="active", version=1, created_at=now,
                )
                session.add(selection)
            elif selected_direction_ids:
                raise ValueError("拒绝候选时不能选择方向。")
            row.status = resolution
            row.version += 1
            row.resolution_reason = reason[:500]
            row.resolved_at = now
            task = session.scalar(select(ReviewTaskModel).where(
                ReviewTaskModel.entity_type == "resume_direction_proposal",
                ReviewTaskModel.entity_id == row.id,
            ))
            if task:
                set_review_resolution(task, now=now, resolution=resolution, reason=reason)
            session.commit()
            return self._proposal_view(session, row)

    def _assert_current(self, session: Session, row: ResumeDirectionProposalModel) -> None:
        if (
            self._latest_version(session, row.job_post_id).id != row.job_post_version_id
            or self._latest_analysis(session, row.job_post_id).id != row.job_match_analysis_id
            or self._fact_hash(self._facts(session)) != row.fact_set_hash
            or self._preference_hash(self._preferences(session)) != row.preference_set_hash
        ):
            raise VersionConflictError("岗位、正式匹配或可信档案已变化，请重新生成简历方向。")

    def _proposal_view(self, session: Session, row: ResumeDirectionProposalModel) -> dict[str, Any]:
        task = session.scalar(select(ReviewTaskModel).where(
            ReviewTaskModel.entity_type == "resume_direction_proposal",
            ReviewTaskModel.entity_id == row.id,
        ))
        selection = session.scalar(select(ResumeDirectionSelectionModel).where(
            ResumeDirectionSelectionModel.proposal_id == row.id
        ))
        return {
            "id": row.id, "job_post_id": row.job_post_id,
            "job_post_version_id": row.job_post_version_id,
            "job_match_analysis_id": row.job_match_analysis_id,
            "fact_set_hash": row.fact_set_hash, "preference_set_hash": row.preference_set_hash,
            "schema_version": row.schema_version, "content": json.loads(row.content_json),
            "status": row.status, "version": row.version, "agent_run_id": row.agent_run_id,
            "review_task_id": task.id if task else None,
            "selection_id": selection.id if selection else None,
            "resolution_reason": row.resolution_reason, "created_at": self._utc(row.created_at),
            "resolved_at": self._utc(row.resolved_at),
        }

    @staticmethod
    def _selection_view(row: ResumeDirectionSelectionModel) -> dict[str, Any]:
        return {
            "id": row.id, "proposal_id": row.proposal_id, "job_post_id": row.job_post_id,
            "job_post_version_id": row.job_post_version_id,
            "selected_direction_ids": json.loads(row.selected_direction_ids_json),
            "selected_directions": json.loads(row.selected_content_json),
            "status": row.status, "version": row.version,
            "created_at": SqlAlchemyResumeDirectionGateway._utc(row.created_at),
        }

    @staticmethod
    def _latest_version(session: Session, job_id: str) -> JobPostVersionModel:
        row = session.scalar(select(JobPostVersionModel).where(
            JobPostVersionModel.job_post_id == job_id
        ).order_by(JobPostVersionModel.version_number.desc()))
        if row is None:
            raise LookupError("岗位版本不存在。")
        return row

    @staticmethod
    def _latest_analysis(session: Session, job_id: str) -> JobMatchAnalysisModel:
        row = session.scalar(select(JobMatchAnalysisModel).where(
            JobMatchAnalysisModel.job_post_id == job_id
        ).order_by(JobMatchAnalysisModel.created_at.desc()))
        if row is None:
            raise ValueError("请先完成岗位匹配分析。")
        return row

    @staticmethod
    def _requirements(session: Session, version_id: str) -> list[JobRequirementModel]:
        return list(session.scalars(select(JobRequirementModel).where(
            JobRequirementModel.job_post_version_id == version_id
        ).order_by(JobRequirementModel.ordinal)).all())

    @staticmethod
    def _facts(session: Session) -> list[CandidateFactModel]:
        return list(session.scalars(select(CandidateFactModel).where(
            CandidateFactModel.profile_id == PROFILE_ID,
            CandidateFactModel.status == "confirmed",
        ).order_by(CandidateFactModel.id)).all())

    @staticmethod
    def _preferences(session: Session) -> list[CareerPreferenceModel]:
        return list(session.scalars(select(CareerPreferenceModel).where(
            CareerPreferenceModel.profile_id == PROFILE_ID,
            CareerPreferenceModel.status == "confirmed",
        ).order_by(CareerPreferenceModel.preference_key)).all())

    @staticmethod
    def _fact_hash(rows: list[CandidateFactModel]) -> str:
        return hashlib.sha256("\n".join(
            f"{item.id}:{item.version}:{item.value}" for item in rows
        ).encode()).hexdigest()

    @staticmethod
    def _preference_hash(rows: list[CareerPreferenceModel]) -> str:
        return hashlib.sha256("\n".join(
            f"{item.id}:{item.version}:{item.preference_key}:{item.value_json}" for item in rows
        ).encode()).hexdigest()

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
