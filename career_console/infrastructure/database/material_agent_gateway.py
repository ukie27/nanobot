"""Persistence and atomic promotion for Agent-authored material proposals."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.materials import (
    FactSnapshot,
    MaterialBlock,
    MaterialReviewResult,
    ResumeDraftResult,
    review_material,
)
from career_console.infrastructure.database.models import (
    CandidateFactModel,
    CompanyModel,
    FactReferenceModel,
    FactSnapshotModel,
    JobPostModel,
    JobPostVersionModel,
    JobRequirementModel,
    MaterialAgentProposalModel,
    MaterialDraftModel,
    MaterialReviewModel,
    ResumeDirectionSelectionModel,
    ResumeModel,
    ResumeVersionModel,
    ReviewFindingModel,
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


class SqlAlchemyMaterialAgentGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def context(self, job_id: str, *, resume_id: str | None, resume_name: str) -> dict[str, Any]:
        with self._session_factory() as session:
            post = session.get(JobPostModel, job_id)
            if post is None:
                raise LookupError("岗位不存在。")
            version = self._latest_job_version(session, job_id)
            selection = session.scalar(select(ResumeDirectionSelectionModel).where(
                ResumeDirectionSelectionModel.job_post_id == job_id,
                ResumeDirectionSelectionModel.status == "active",
            ).order_by(ResumeDirectionSelectionModel.created_at.desc()))
            if selection is None:
                raise CareerDomainError("请先确认一个简历方向。", code="active_resume_direction_required")
            facts = self._facts(session)
            fact_hash = self._fact_hash(facts)
            if selection.job_post_version_id != version.id or selection.fact_set_hash != fact_hash:
                raise VersionConflictError("当前简历方向已过期，请重新生成并确认方向。")
            base_version = None
            if resume_id is not None:
                if session.get(ResumeModel, resume_id) is None:
                    raise LookupError("基础简历系列不存在。")
                base_version = self._latest_resume_version(session, resume_id)
            requirements = list(session.scalars(select(JobRequirementModel).where(
                JobRequirementModel.job_post_version_id == version.id
            ).order_by(JobRequirementModel.ordinal)).all())
            company = session.get(CompanyModel, post.company_id)
            return {
                "schemaVersion": "resume_draft_context.v2",
                "businessTimezone": "Asia/Shanghai",
                "inputRevision": (
                    f"job:{version.id}:selection:{selection.id}:v{selection.version}:facts:{fact_hash}:"
                    f"base:{base_version.id if base_version else 'none'}:"
                    f"{base_version.content_hash if base_version else 'none'}"
                ),
                "job": {"id": post.id, "versionId": version.id, "title": post.title,
                        "company": company.canonical_name if company else "", "location": post.location},
                "activeDirectionSelection": {
                    "id": selection.id, "version": selection.version,
                    "selectedDirectionIds": json.loads(selection.selected_direction_ids_json),
                    "directions": json.loads(selection.selected_content_json),
                },
                "requirements": [{"id": item.id, "category": item.category, "level": item.level,
                                  "description": item.description} for item in requirements],
                "confirmedFacts": [{"id": item.id, "version": item.version, "category": item.category,
                                    "fieldKey": item.field_key, "value": item.value} for item in facts],
                "factSetHash": fact_hash, "resumeId": resume_id,
                "baseResumeVersion": None if base_version is None else {
                    "id": base_version.id, "versionNumber": base_version.version_number,
                    "status": base_version.status, "title": base_version.title,
                    "contentHash": base_version.content_hash,
                    "blocks": json.loads(base_version.content_json),
                },
                "resumeName": resume_name.strip() or "我的基础简历",
            }

    def existing(self, job_id: str, input_hash: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.scalar(select(MaterialAgentProposalModel).where(
                MaterialAgentProposalModel.job_post_id == job_id,
                MaterialAgentProposalModel.input_hash == input_hash,
                MaterialAgentProposalModel.status == "proposed",
            ).order_by(MaterialAgentProposalModel.created_at.desc()))
            return self._view(session, row) if row else None

    def save(self, *, context: dict[str, Any], draft: ResumeDraftResult,
             review: MaterialReviewResult, input_hash: str, output_hash: str,
             draft_audit: dict[str, Any], review_audit: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            draft_run = self._run(session, "resume_draft", draft.schema_version, "succeeded",
                                  len(draft.blocks), None, context, input_hash, output_hash, draft_audit, now)
            review_hash = self._hash(review.model_dump(mode="json", by_alias=True))
            review_run = self._run(session, "material_review", review.schema_version, "succeeded",
                                   len(review.findings), None, context, output_hash, review_hash, review_audit, now)
            row = MaterialAgentProposalModel(
                id=str(uuid4()), job_post_id=context["job"]["id"],
                job_post_version_id=context["job"]["versionId"],
                resume_direction_selection_id=context["activeDirectionSelection"]["id"],
                profile_id=PROFILE_ID, resume_id=context["resumeId"],
                base_resume_version_id=(context["baseResumeVersion"] or {}).get("id"),
                resume_name=context["resumeName"][:300], material_type="resume",
                fact_set_hash=context["factSetHash"], schema_version=draft.schema_version,
                content_json=draft.model_dump_json(by_alias=True),
                review_schema_version=review.schema_version,
                review_json=review.model_dump_json(by_alias=True), input_hash=input_hash,
                output_hash=output_hash, status="proposed", version=1,
                drafter_run_id=draft_run.id, reviewer_run_id=review_run.id,
                material_draft_id=None, resolution_reason=None, created_at=now, resolved_at=None,
            )
            session.add(row)
            session.flush()
            ensure_review_task(
                session, task_type="material_agent_review", entity_type="material_agent_proposal",
                entity_id=row.id, title=f"审核 Agent 简历草稿：{context['job']['title']}",
                summary=review.summary, source_type="career_console_material_drafter_reviewer",
                priority=30 if review.verdict == "needs_revision" else 20,
                agent_run_id=review_run.id, now=now,
            )
            session.commit()
            return self._view(session, row)

    def save_failure(self, *, context: dict[str, Any], input_hash: str, stage: str,
                     error_code: str, draft: ResumeDraftResult | None,
                     draft_audit: dict[str, Any], review_audit: dict[str, Any] | None) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            if stage == "draft":
                self._run(session, "resume_draft", "resume_draft.v2", "failed", 0,
                          error_code, context, input_hash, None, draft_audit, now)
            else:
                draft_hash = self._hash(draft.model_dump(mode="json", by_alias=True)) if draft else None
                self._run(session, "resume_draft", "resume_draft.v2", "succeeded",
                          len(draft.blocks) if draft else 0, None, context, input_hash,
                          draft_hash, draft_audit, now)
                self._run(session, "material_review", "material_review.v2", "failed", 0,
                          error_code, context, draft_hash, None, review_audit or draft_audit, now)
            session.commit()

    def list_for_job(self, job_id: str) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(select(MaterialAgentProposalModel).where(
                MaterialAgentProposalModel.job_post_id == job_id
            ).order_by(MaterialAgentProposalModel.created_at.desc())).all()
            return [self._view(session, row) for row in rows]

    def resolve(self, proposal_id: str, *, expected_version: int, resolution: str,
                reason: str) -> dict[str, Any]:
        if resolution not in {"confirmed", "rejected"}:
            raise ValueError("不支持的审核结果。")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(MaterialAgentProposalModel, proposal_id)
            if row is None:
                raise LookupError("Agent 材料候选不存在。")
            if row.status != "proposed":
                return self._view(session, row)
            if row.version != expected_version:
                raise VersionConflictError("材料候选已变化，请刷新后重试。")
            if resolution == "confirmed":
                self._assert_current(session, row)
                review = MaterialReviewResult.model_validate_json(row.review_json)
                if review.verdict != "pass":
                    raise CareerDomainError("Reviewer 仍有阻断问题，不能确认。", code="agent_material_review_blocked")
                row.material_draft_id = self._promote(session, row, now).id
            row.status = resolution
            row.version += 1
            row.resolution_reason = reason[:500]
            row.resolved_at = now
            task = session.scalar(select(ReviewTaskModel).where(
                ReviewTaskModel.entity_type == "material_agent_proposal", ReviewTaskModel.entity_id == row.id
            ))
            if task:
                set_review_resolution(task, now=now, resolution=resolution, reason=reason)
            session.commit()
            return self._view(session, row)

    def _promote(self, session: Session, row: MaterialAgentProposalModel, now: datetime) -> MaterialDraftModel:
        result = ResumeDraftResult.model_validate_json(row.content_json)
        facts = self._facts(session)
        domain_snapshots = [FactSnapshot(item.id, item.id, item.version, item.value) for item in facts]
        domain_blocks = [MaterialBlock(item.block_id, item.section, item.text, tuple(item.fact_ids)) for item in result.blocks]
        deterministic = review_material(domain_blocks, domain_snapshots)
        if any(item.severity == "error" for item in deterministic):
            raise CareerDomainError("确定性事实审查未通过，不能生成正式材料。", code="material_review_blocked")
        post = session.get(JobPostModel, row.job_post_id)
        company = session.get(CompanyModel, post.company_id)
        resume = session.get(ResumeModel, row.resume_id) if row.resume_id else None
        if resume is None:
            resume = ResumeModel(
                id=str(uuid4()), name=row.resume_name, series_type="base",
                parent_resume_id=None, direction_label=None, created_at=now, updated_at=now,
            )
            session.add(resume)
            session.flush()
        else:
            resume.updated_at = now
        material = MaterialDraftModel(
            id=str(uuid4()), resume_id=resume.id, job_post_id=row.job_post_id,
            job_post_version_id=row.job_post_version_id, job_title_snapshot=post.title,
            source_resume_version_id=row.base_resume_version_id,
            resume_direction_selection_id=row.resume_direction_selection_id,
            company_name_snapshot=company.canonical_name if company else "",
            material_type=row.material_type, status="reviewed", version=1,
            strategy_stale=0, strategy_stale_reason=None, strategy_stale_at=None,
            created_at=now, updated_at=now,
        )
        session.add(material)
        session.flush()
        version = ResumeVersionModel(
            id=str(uuid4()), resume_id=resume.id, material_draft_id=material.id,
            parent_version_id=None, version_number=1, status="reviewed", title=result.title,
            source_resume_version_id=row.base_resume_version_id,
            version_scope="job_tailored",
            content_json="[]", rendered_text="", content_hash="", fact_set_hash=row.fact_set_hash,
            created_at=now, finalized_at=None,
        )
        session.add(version)
        session.flush()
        snapshot_ids: dict[str, str] = {}
        for fact in facts:
            snap = FactSnapshotModel(id=str(uuid4()), resume_version_id=version.id, fact_id=fact.id,
                                     fact_version=fact.version, category=fact.category,
                                     field_key=fact.field_key, value=fact.value, created_at=now)
            session.add(snap)
            snapshot_ids[fact.id] = snap.id
        session.flush()
        payload = []
        for block in result.blocks:
            ids = [snapshot_ids[fid] for fid in block.fact_ids]
            payload.append({"id": block.block_id, "section": block.section, "text": block.text,
                            "fact_snapshot_ids": ids})
            for sid in ids:
                session.add(FactReferenceModel(id=str(uuid4()), resume_version_id=version.id,
                                              fact_snapshot_id=sid, block_id=block.block_id))
        version.content_json = json.dumps(payload, ensure_ascii=False)
        version.rendered_text = "\n".join(item.text for item in result.blocks)
        version.content_hash = hashlib.sha256(version.content_json.encode()).hexdigest()
        formal_review = MaterialReviewModel(id=str(uuid4()), resume_version_id=version.id,
                                            schema_version="material_review.v2", status="passed",
                                            error_count=0,
                                            warning_count=sum(x.severity == "warning" for x in deterministic),
                                            created_at=now)
        session.add(formal_review)
        session.flush()
        for finding in deterministic:
            session.add(ReviewFindingModel(id=str(uuid4()), review_id=formal_review.id,
                                          severity=finding.severity, code=finding.code,
                                          message=finding.message, block_id=finding.block_id, created_at=now))
        return material

    def _assert_current(self, session: Session, row: MaterialAgentProposalModel) -> None:
        selection = session.get(ResumeDirectionSelectionModel, row.resume_direction_selection_id)
        if (self._latest_job_version(session, row.job_post_id).id != row.job_post_version_id
                or selection is None or selection.status != "active"
                or self._fact_hash(self._facts(session)) != row.fact_set_hash):
            raise VersionConflictError("岗位、方向选择或可信事实已变化，请重新生成草稿。")
        if row.base_resume_version_id is not None:
            latest_base = self._latest_resume_version(session, row.resume_id)
            if latest_base is None or latest_base.id != row.base_resume_version_id:
                raise VersionConflictError("基础简历版本已变化，请重新生成草稿。")

    def _view(self, session: Session, row: MaterialAgentProposalModel) -> dict[str, Any]:
        task = session.scalar(select(ReviewTaskModel).where(
            ReviewTaskModel.entity_type == "material_agent_proposal", ReviewTaskModel.entity_id == row.id
        ))
        return {"id": row.id, "job_post_id": row.job_post_id,
                "job_post_version_id": row.job_post_version_id,
                "resume_direction_selection_id": row.resume_direction_selection_id,
                "base_resume_version_id": row.base_resume_version_id,
                "schema_version": row.schema_version, "content": json.loads(row.content_json),
                "review_schema_version": row.review_schema_version, "review": json.loads(row.review_json),
                "status": row.status, "version": row.version, "drafter_run_id": row.drafter_run_id,
                "reviewer_run_id": row.reviewer_run_id, "review_task_id": task.id if task else None,
                "material_draft_id": row.material_draft_id, "resolution_reason": row.resolution_reason,
                "created_at": self._utc(row.created_at), "resolved_at": self._utc(row.resolved_at)}

    def _run(self, session: Session, task_type: str, schema: str, status: str, count: int,
             error: str | None, context: dict, input_hash: str | None, output_hash: str | None,
             audit: dict, now: datetime):
        return create_agent_run(session, task_type=task_type, implementation=audit["implementation"],
                                schema_version=schema, status=status, output_count=count,
                                error_code=error, created_at=audit["created_at"], finished_at=now,
                                provider=audit.get("provider"), model=audit.get("model"),
                                prompt_version=audit.get("prompt_version"),
                                skill_version=audit.get("skill_version"),
                                input_entity_type="job_post",
                                input_entity_id=context["job"]["id"], input_revision=context["inputRevision"],
                                input_hash=input_hash, output_hash=output_hash,
                                input_tokens=audit.get("input_tokens"), output_tokens=audit.get("output_tokens"),
                                duration_ms=audit.get("duration_ms"), retry_count=audit.get("retry_count", 0),
                                sensitivity="sensitive")

    @staticmethod
    def _facts(session: Session) -> list[CandidateFactModel]:
        return list(session.scalars(select(CandidateFactModel).where(
            CandidateFactModel.profile_id == PROFILE_ID, CandidateFactModel.status == "confirmed"
        ).order_by(CandidateFactModel.id)).all())

    @staticmethod
    def _fact_hash(rows: list[CandidateFactModel]) -> str:
        return hashlib.sha256("\n".join(f"{x.id}:{x.version}:{x.value}" for x in rows).encode()).hexdigest()

    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _latest_job_version(session: Session, job_id: str) -> JobPostVersionModel:
        row = session.scalar(select(JobPostVersionModel).where(
            JobPostVersionModel.job_post_id == job_id
        ).order_by(JobPostVersionModel.version_number.desc()))
        if row is None:
            raise LookupError("岗位版本不存在。")
        return row

    @staticmethod
    def _latest_resume_version(session: Session, resume_id: str) -> ResumeVersionModel | None:
        return session.scalar(select(ResumeVersionModel).where(
            ResumeVersionModel.resume_id == resume_id
        ).order_by(ResumeVersionModel.created_at.desc()))

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
