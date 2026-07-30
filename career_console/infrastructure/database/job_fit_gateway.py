"""Persistence and deterministic promotion for semantic job-fit proposals."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.jobs import (
    CandidateEvidence,
    EvidenceDecision,
    JobFitAnalysisResult,
    JobRequirement,
    RequirementCategory,
    RequirementLevel,
    evaluate_match,
)
from career_console.infrastructure.database.models import (
    CandidateFactModel,
    CareerPreferenceModel,
    CompanyModel,
    JobFitProposalModel,
    JobMatchAnalysisModel,
    JobMatchEvidenceModel,
    JobPostModel,
    JobPostVersionModel,
    JobRequirementModel,
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


class SqlAlchemyJobFitGateway:
    _DIRECT_ONLY = {"education", "experience", "language", "location", "work_mode"}

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def context(self, job_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            post = session.get(JobPostModel, job_id)
            if post is None:
                raise LookupError("岗位不存在。")
            company = session.get(CompanyModel, post.company_id)
            version = self._latest_version(session, job_id)
            requirements = self._requirements(session, version.id)
            if not requirements:
                raise ValueError("岗位没有可分析的结构化要求。")
            facts = self._facts(session)
            if not facts:
                raise ValueError("至少需要一条已确认事实才能执行 Agent 岗位分析。")
            preferences = session.scalars(select(CareerPreferenceModel).where(
                CareerPreferenceModel.profile_id == PROFILE_ID,
                CareerPreferenceModel.status == "confirmed",
            ).order_by(CareerPreferenceModel.preference_key)).all()
            fact_set_hash = self._fact_set_hash(facts)
            preference_set_hash = self._preference_set_hash(preferences)
            return {
                "schemaVersion": "job_fit_context.v2",
                "businessTimezone": "Asia/Shanghai",
                "inputRevision": f"job:{version.id}:facts:{fact_set_hash}",
                "job": {
                    "id": post.id, "versionId": version.id, "versionNumber": version.version_number,
                    "company": company.canonical_name if company else "", "title": post.title,
                    "location": post.location, "workMode": post.work_mode,
                    "employmentType": post.employment_type, "targetAudience": post.target_audience,
                    "deadlineAt": post.deadline_at.isoformat() if post.deadline_at else None,
                },
                "requirements": [
                    {"id": item.id, "category": item.category, "level": item.level,
                     "description": item.description, "evidenceText": item.evidence_text,
                     "weight": item.weight}
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
                "factSetHash": fact_set_hash,
                "preferenceSetHash": preference_set_hash,
            }

    def existing(self, *, job_id: str, input_hash: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.scalar(select(JobFitProposalModel).where(
                JobFitProposalModel.job_post_id == job_id,
                JobFitProposalModel.input_hash == input_hash,
                JobFitProposalModel.status == "proposed",
            ).order_by(JobFitProposalModel.created_at.desc()))
            return self._view(session, row) if row else None

    def save(self, *, job_id: str, result: JobFitAnalysisResult, input_hash: str,
             output_hash: str, context: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            post = session.get(JobPostModel, job_id)
            if post is None:
                raise LookupError("岗位不存在。")
            run = create_agent_run(
                session, task_type="job_fit_analysis", implementation=audit["implementation"],
                schema_version=result.schema_version, status="succeeded", output_count=len(result.assessments),
                error_code=None, created_at=audit["created_at"], finished_at=now,
                provider=audit.get("provider"), model=audit.get("model"),
                prompt_version=audit.get("prompt_version"),
                skill_version=audit.get("skill_version"),
                input_entity_type="job_post",
                input_entity_id=job_id, input_revision=context["inputRevision"], input_hash=input_hash,
                output_hash=output_hash, input_tokens=audit.get("input_tokens"),
                output_tokens=audit.get("output_tokens"), duration_ms=audit.get("duration_ms"),
                retry_count=audit.get("retry_count", 0), sensitivity="sensitive",
            )
            row = JobFitProposalModel(
                id=str(uuid4()), job_post_id=job_id,
                job_post_version_id=context["job"]["versionId"], profile_id=PROFILE_ID,
                fact_set_hash=context["factSetHash"],
                preference_set_hash=context["preferenceSetHash"], schema_version=result.schema_version,
                content_json=result.model_dump_json(by_alias=True), input_hash=input_hash,
                output_hash=output_hash, status="proposed", version=1, agent_run_id=run.id,
                formal_analysis_id=None, resolution_reason=None, created_at=now, resolved_at=None,
            )
            session.add(row)
            session.flush()
            ensure_review_task(
                session, task_type="job_fit_review", entity_type="job_fit_proposal",
                entity_id=row.id, title=f"确认 Agent 岗位分析：{post.title}",
                summary=result.summary, source_type="career_console_job_fit", priority=20,
                agent_run_id=run.id, now=now,
            )
            session.commit()
            return self._view(session, row)

    def save_failure(self, *, job_id: str, input_hash: str, input_revision: str,
                     error_code: str, audit: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            create_agent_run(
                session, task_type="job_fit_analysis", implementation=audit["implementation"],
                schema_version="job_fit_analysis.v2", status="failed", output_count=0,
                error_code=error_code, created_at=audit["created_at"], finished_at=now,
                provider=audit.get("provider"), model=audit.get("model"),
                prompt_version=audit.get("prompt_version"),
                skill_version=audit.get("skill_version"),
                input_entity_type="job_post",
                input_entity_id=job_id, input_revision=input_revision, input_hash=input_hash,
                input_tokens=audit.get("input_tokens"), output_tokens=audit.get("output_tokens"),
                duration_ms=audit.get("duration_ms"), retry_count=audit.get("retry_count", 0),
                sensitivity="sensitive",
            )
            session.commit()

    def list_for_job(self, job_id: str) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(select(JobFitProposalModel).where(
                JobFitProposalModel.job_post_id == job_id
            ).order_by(JobFitProposalModel.created_at.desc())).all()
            return [self._view(session, row) for row in rows]

    def resolve(self, proposal_id: str, *, expected_version: int, resolution: str,
                reason: str) -> dict[str, Any]:
        if resolution not in {"confirmed", "rejected"}:
            raise ValueError("不支持的审核结果。")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(JobFitProposalModel, proposal_id)
            if row is None:
                raise LookupError("岗位分析候选不存在。")
            if row.status != "proposed":
                return self._view(session, row)
            if row.version != expected_version:
                raise VersionConflictError("岗位分析候选已变化，请刷新后重试。")
            if resolution == "confirmed":
                current_version = self._latest_version(session, row.job_post_id)
                facts = self._facts(session)
                preferences = self._preferences(session)
                if (
                    current_version.id != row.job_post_version_id
                    or self._fact_set_hash(facts) != row.fact_set_hash
                    or self._preference_set_hash(preferences) != row.preference_set_hash
                ):
                    raise VersionConflictError("岗位版本或可信档案已经变化，请重新运行 Agent 分析。")
                result = JobFitAnalysisResult.model_validate_json(row.content_json)
                analysis = self._promote(session, row, result, facts, preferences, now)
                row.formal_analysis_id = analysis.id
            row.status = resolution
            row.version += 1
            row.resolution_reason = reason[:500]
            row.resolved_at = now
            task = session.scalar(select(ReviewTaskModel).where(
                ReviewTaskModel.entity_type == "job_fit_proposal",
                ReviewTaskModel.entity_id == row.id,
            ))
            if task:
                set_review_resolution(task, now=now, resolution=resolution, reason=reason)
            session.commit()
            return self._view(session, row)

    def _promote(self, session: Session, row: JobFitProposalModel, result: JobFitAnalysisResult,
                 facts: list[CandidateFactModel], preferences: list[CareerPreferenceModel],
                 now: datetime) -> JobMatchAnalysisModel:
        requirements = self._requirements(session, row.job_post_version_id)
        requirement_map = {item.id: item for item in requirements}
        fact_map = {item.id: item for item in facts}
        domain_requirements = [JobRequirement(
            item.id, RequirementCategory(item.category), RequirementLevel(item.level),
            item.description, item.evidence_text, item.weight,
        ) for item in requirements]
        domain_evidence: list[CandidateEvidence] = []
        effective_ids: dict[str, list[str]] = {}
        for item in result.assessments:
            requirement = requirement_map[item.requirement_id]
            ids = list(item.evidence_fact_ids)
            if requirement.category not in self._DIRECT_ONLY:
                ids.extend(item.transferable_fact_ids)
            decision = EvidenceDecision.MATCHED if item.decision == "matched" and ids else EvidenceDecision.GAP
            effective_ids[item.requirement_id] = ids if decision is EvidenceDecision.MATCHED else []
            domain_evidence.append(CandidateEvidence(
                item.requirement_id, decision, tuple(effective_ids[item.requirement_id]), item.rationale
            ))
        projection = evaluate_match(domain_requirements, domain_evidence)
        decision = self._decision_projection(
            session.get(JobPostModel, row.job_post_id), result, preferences, projection
        )
        analysis = JobMatchAnalysisModel(
            id=str(uuid4()), job_post_id=row.job_post_id, job_post_version_id=row.job_post_version_id,
            profile_id=row.profile_id, fact_set_hash=row.fact_set_hash,
            analysis_origin="agent_confirmed",
            hard_gate_passed=int(projection.hard_gate_passed), score=projection.score,
            matched_count=projection.matched_count, gap_count=projection.gap_count,
            must_gap_count=projection.must_gap_count, recommendation=decision["priority"],
            created_at=now,
        )
        session.add(analysis)
        session.flush()
        assessment_map = {item.requirement_id: item for item in result.assessments}
        for requirement in requirements:
            assessment = assessment_map[requirement.id]
            ids = effective_ids[requirement.id]
            if not ids:
                session.add(JobMatchEvidenceModel(
                    id=str(uuid4()), analysis_id=analysis.id, requirement_id=requirement.id,
                    fact_id=None, fact_version=None, fact_value_snapshot=None, decision="gap",
                    rationale=assessment.rationale,
                ))
            for fact_id in ids:
                fact = fact_map[fact_id]
                session.add(JobMatchEvidenceModel(
                    id=str(uuid4()), analysis_id=analysis.id, requirement_id=requirement.id,
                    fact_id=fact.id, fact_version=fact.version, fact_value_snapshot=fact.value,
                    decision="matched", rationale=assessment.rationale,
                ))
        session.flush()
        return analysis

    def _view(self, session: Session, row: JobFitProposalModel) -> dict[str, Any]:
        content = json.loads(row.content_json)
        task = session.scalar(select(ReviewTaskModel).where(
            ReviewTaskModel.entity_type == "job_fit_proposal",
            ReviewTaskModel.entity_id == row.id,
        ))
        return {
            "id": row.id, "job_post_id": row.job_post_id,
            "job_post_version_id": row.job_post_version_id, "fact_set_hash": row.fact_set_hash,
            "preference_set_hash": row.preference_set_hash,
            "schema_version": row.schema_version, "content": content, "status": row.status,
            "version": row.version, "agent_run_id": row.agent_run_id,
            "review_task_id": task.id if task else None,
            "formal_analysis_id": row.formal_analysis_id,
            "resolution_reason": row.resolution_reason, "created_at": self._utc(row.created_at),
            "resolved_at": self._utc(row.resolved_at),
            "decision_projection": self._proposal_projection(session, row, content),
        }

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
    def _fact_set_hash(facts: list[CandidateFactModel]) -> str:
        return hashlib.sha256(
            "\n".join(f"{item.id}:{item.version}:{item.value}" for item in facts).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _preference_set_hash(preferences: list[CareerPreferenceModel]) -> str:
        return hashlib.sha256(
            "\n".join(
                f"{item.id}:{item.version}:{item.preference_key}:{item.value_json}"
                for item in preferences
            ).encode("utf-8")
        ).hexdigest()

    def _proposal_projection(
        self, session: Session, row: JobFitProposalModel, content: dict[str, Any]
    ) -> dict[str, Any]:
        result = JobFitAnalysisResult.model_validate(content)
        requirements = self._requirements(session, row.job_post_version_id)
        assessment_map = {item.requirement_id: item for item in result.assessments}
        domain_requirements = [JobRequirement(
            item.id, RequirementCategory(item.category), RequirementLevel(item.level),
            item.description, item.evidence_text, item.weight,
        ) for item in requirements]
        domain_evidence = []
        for requirement in requirements:
            item = assessment_map[requirement.id]
            ids = list(item.evidence_fact_ids)
            if requirement.category not in self._DIRECT_ONLY:
                ids.extend(item.transferable_fact_ids)
            decision = EvidenceDecision.MATCHED if item.decision == "matched" and ids else EvidenceDecision.GAP
            domain_evidence.append(CandidateEvidence(
                requirement.id, decision, tuple(ids if decision is EvidenceDecision.MATCHED else []),
                item.rationale,
            ))
        match = evaluate_match(domain_requirements, domain_evidence)
        return self._decision_projection(
            session.get(JobPostModel, row.job_post_id), result, self._preferences(session), match
        )

    @staticmethod
    def _decision_projection(post: JobPostModel, result: JobFitAnalysisResult,
                             preferences: list[CareerPreferenceModel], match: Any) -> dict[str, Any]:
        values = {item.preference_key: json.loads(item.value_json) for item in preferences}
        adjustment = 0
        reasons: list[str] = []
        roles = [str(value).casefold() for value in values.get("target_roles", [])]
        if roles:
            aligned = any(value in post.title.casefold() for value in roles)
            adjustment += 10 if aligned else -10
            reasons.append("目标岗位方向一致" if aligned else "不在已确认目标岗位方向中")
        cities = [str(value).casefold() for value in values.get("target_cities", [])]
        if cities and post.location:
            aligned = any(value in post.location.casefold() for value in cities)
            adjustment += 5 if aligned else -10
            reasons.append("目标城市一致" if aligned else "目标城市不一致")
        cost_adjustment = {"low": 0, "medium": -5, "high": -10}[result.material_effort]
        if result.preparation_hours >= 20:
            cost_adjustment -= 10
        elif result.preparation_hours >= 8:
            cost_adjustment -= 5
        decision_score = max(0, min(100, match.score + adjustment + cost_adjustment))
        priority = (
            "blocked" if not match.hard_gate_passed else
            "high_priority" if decision_score >= 75 else
            "consider" if decision_score >= 50 else "low_priority"
        )
        return {
            "requirement_score": match.score, "hard_gate_passed": match.hard_gate_passed,
            "preference_adjustment": adjustment, "cost_adjustment": cost_adjustment,
            "decision_score": decision_score, "priority": priority, "reasons": reasons,
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
    def _requirements(session: Session, version_id: str) -> list[JobRequirementModel]:
        return list(session.scalars(select(JobRequirementModel).where(
            JobRequirementModel.job_post_version_id == version_id
        ).order_by(JobRequirementModel.ordinal)).all())

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
