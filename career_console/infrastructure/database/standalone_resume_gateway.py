"""Persistence and promotion for standalone resume Agent proposals."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.materials import (
    FactSnapshot,
    MaterialBlock,
    MaterialType,
    ResumeDraftResult,
    VersionStatus,
    review_material,
)
from career_console.infrastructure.database.models import (
    CandidateFactModel,
    FactReferenceModel,
    FactSnapshotModel,
    MaterialReviewModel,
    ResumeModel,
    ResumeVersionModel,
    ReviewFindingModel,
    ReviewTaskModel,
    StandaloneResumeProposalModel,
)
from career_console.infrastructure.database.profile_gateway import (
    PROFILE_ID,
    VersionConflictError,
)
from career_console.infrastructure.database.review_runtime import (
    create_agent_run,
    set_review_resolution,
)


class SqlAlchemyStandaloneResumeGateway:
    def __init__(self, session_factory: sessionmaker[Session], publisher: Any) -> None:
        self._session_factory = session_factory
        self._publisher = publisher

    def context(self, *, name: str, prompt: str) -> dict[str, Any]:
        normalized_name = name.strip()
        normalized_prompt = prompt.strip()
        if not normalized_name:
            raise CareerDomainError("请填写简历名称。", code="empty_resume_name")
        if not normalized_prompt:
            raise CareerDomainError("请填写生成要求。", code="empty_resume_prompt")
        with self._session_factory() as session:
            facts = self._facts(session)
            if not facts:
                raise CareerDomainError(
                    "个人档案至少需要一项可用事实。",
                    code="confirmed_facts_required",
                )
            fact_hash = self._fact_hash(facts)
            return {
                "schemaVersion": "standalone_resume_context.v1",
                "businessTimezone": "Asia/Shanghai",
                "inputRevision": f"profile:{PROFILE_ID}:facts:{fact_hash}",
                "resumeName": normalized_name[:300],
                "userPrompt": normalized_prompt[:4_000],
                "profileFacts": [
                    {
                        "id": item.id,
                        "version": item.version,
                        "category": item.category,
                        "fieldKey": item.field_key,
                        "value": item.value,
                    }
                    for item in facts
                ],
                # Kept for existing Agent prompt adapters during the schema transition.
                "confirmedFacts": [
                    {
                        "id": item.id,
                        "version": item.version,
                        "category": item.category,
                        "fieldKey": item.field_key,
                        "value": item.value,
                    }
                    for item in facts
                ],
                "factSetHash": fact_hash,
            }

    def existing(self, input_hash: str) -> dict[str, Any] | None:
        del input_hash
        return None

    def save(
        self,
        *,
        context: dict[str, Any],
        draft: ResumeDraftResult,
        input_hash: str,
        output_hash: str,
        audit: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            run = self._run(
                session,
                context=context,
                status="succeeded",
                output_count=len(draft.blocks),
                error_code=None,
                input_hash=input_hash,
                output_hash=output_hash,
                audit=audit,
                now=now,
            )
            resume, version = self._promote(
                session,
                SimpleNamespace(
                    resume_name=context["resumeName"],
                    content_json=draft.model_dump_json(by_alias=True),
                    fact_set_hash=context["factSetHash"],
                ),
                now,
            )
            session.commit()
            resume_id = resume.id
            version_id = version.id
            run_id = run.id
        try:
            detail = self._publisher.finalize_resume(
                resume_id, expected_version_id=version_id
            )
        except Exception:
            with self._session_factory() as cleanup:
                resume = cleanup.get(ResumeModel, resume_id)
                if resume is not None and resume.scope == "library":
                    cleanup.delete(resume)
                    cleanup.commit()
            raise
        detail["agent_run_id"] = run_id
        return detail

    def save_failure(
        self,
        *,
        context: dict[str, Any],
        input_hash: str,
        error_code: str,
        audit: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            self._run(
                session,
                context=context,
                status="failed",
                output_count=0,
                error_code=error_code,
                input_hash=input_hash,
                output_hash=None,
                audit=audit,
                now=now,
            )
            session.commit()

    def list(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(StandaloneResumeProposalModel).order_by(
                    StandaloneResumeProposalModel.created_at.desc()
                )
            ).all()
            return [self._view(session, row) for row in rows]

    def resolve(
        self,
        proposal_id: str,
        *,
        expected_version: int,
        resolution: str,
        reason: str,
    ) -> dict[str, Any]:
        if resolution not in {"confirmed", "rejected"}:
            raise ValueError("不支持的审核结果。")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(StandaloneResumeProposalModel, proposal_id)
            if row is None:
                raise LookupError("简历候选不存在。")
            if row.status != "proposed":
                return self._view(session, row)
            if row.version != expected_version:
                raise VersionConflictError("简历候选已变化，请刷新后重试。")
            if resolution == "confirmed":
                if self._fact_hash(self._facts(session)) != row.fact_set_hash:
                    raise VersionConflictError(
                        "职业档案已变化，请重新生成简历候选。"
                    )
                resume, version = self._promote(session, row, now)
                row.resume_id = resume.id
                row.resume_version_id = version.id
            row.status = resolution
            row.version += 1
            row.resolution_reason = reason[:500]
            row.resolved_at = now
            task = session.scalar(
                select(ReviewTaskModel).where(
                    ReviewTaskModel.entity_type == "standalone_resume_proposal",
                    ReviewTaskModel.entity_id == row.id,
                )
            )
            if task:
                set_review_resolution(
                    task, now=now, resolution=resolution, reason=reason
                )
            session.commit()
            return self._view(session, row)

    def _promote(
        self, session: Session, row: StandaloneResumeProposalModel, now: datetime
    ) -> tuple[ResumeModel, ResumeVersionModel]:
        result = ResumeDraftResult.model_validate_json(row.content_json)
        facts = self._facts(session)
        resume = ResumeModel(
            id=str(uuid4()),
            name=row.resume_name,
            series_type="base",
            parent_resume_id=None,
            direction_label=None,
            scope="library",
            application_id=None,
            source_file_name=None,
            retired_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(resume)
        session.flush()
        version = ResumeVersionModel(
            id=str(uuid4()),
            resume_id=resume.id,
            material_draft_id=None,
            parent_version_id=None,
            source_resume_version_id=None,
            version_scope="base",
            version_number=1,
            status=VersionStatus.DRAFT.value,
            title=result.title,
            content_json="[]",
            rendered_text="",
            content_hash="",
            fact_set_hash=row.fact_set_hash,
            created_at=now,
            finalized_at=None,
        )
        session.add(version)
        session.flush()
        snapshots: dict[str, FactSnapshotModel] = {}
        for fact in facts:
            snapshot = FactSnapshotModel(
                id=str(uuid4()),
                resume_version_id=version.id,
                fact_id=fact.id,
                fact_version=fact.version,
                category=fact.category,
                field_key=fact.field_key,
                value=fact.value,
                created_at=now,
            )
            session.add(snapshot)
            snapshots[fact.id] = snapshot
        session.flush()
        payload = []
        for block in result.blocks:
            snapshot_ids = [snapshots[fact_id].id for fact_id in block.fact_ids]
            payload.append(
                {
                    "id": block.block_id,
                    "section": block.section,
                    "text": block.text,
                    "fact_snapshot_ids": snapshot_ids,
                }
            )
            for snapshot_id in snapshot_ids:
                session.add(
                    FactReferenceModel(
                        id=str(uuid4()),
                        resume_version_id=version.id,
                        fact_snapshot_id=snapshot_id,
                        block_id=block.block_id,
                    )
                )
        version.content_json = json.dumps(payload, ensure_ascii=False)
        version.rendered_text = "\n".join(block.text for block in result.blocks)
        version.content_hash = hashlib.sha256(version.content_json.encode()).hexdigest()
        domain_blocks = [
            MaterialBlock(
                block.block_id,
                block.section,
                block.text,
                tuple(snapshots[fact_id].id for fact_id in block.fact_ids),
            )
            for block in result.blocks
        ]
        domain_snapshots = [
            FactSnapshot(
                snapshot.id,
                snapshot.fact_id,
                snapshot.fact_version,
                snapshot.value,
            )
            for snapshot in snapshots.values()
        ]
        findings = review_material(
            domain_blocks, domain_snapshots, material_type=MaterialType.RESUME
        )
        version.status = (
            VersionStatus.DRAFT.value
            if any(item.severity == "error" for item in findings)
            else VersionStatus.REVIEWED.value
        )
        review = MaterialReviewModel(
            id=str(uuid4()),
            resume_version_id=version.id,
            schema_version="material_review.v1",
            status="failed" if version.status == VersionStatus.DRAFT.value else "passed",
            error_count=sum(item.severity == "error" for item in findings),
            warning_count=sum(item.severity == "warning" for item in findings),
            created_at=now,
        )
        session.add(review)
        session.flush()
        for finding in findings:
            session.add(
                ReviewFindingModel(
                    id=str(uuid4()),
                    review_id=review.id,
                    severity=finding.severity,
                    code=finding.code,
                    message=finding.message,
                    block_id=finding.block_id,
                    created_at=now,
                )
            )
        return resume, version

    def _view(
        self, session: Session, row: StandaloneResumeProposalModel
    ) -> dict[str, Any]:
        task = session.scalar(
            select(ReviewTaskModel).where(
                ReviewTaskModel.entity_type == "standalone_resume_proposal",
                ReviewTaskModel.entity_id == row.id,
            )
        )
        return {
            "id": row.id,
            "resume_name": row.resume_name,
            "user_prompt": row.user_prompt,
            "fact_set_hash": row.fact_set_hash,
            "schema_version": row.schema_version,
            "content": json.loads(row.content_json),
            "status": row.status,
            "version": row.version,
            "drafter_run_id": row.drafter_run_id,
            "review_task_id": task.id if task else None,
            "resume_id": row.resume_id,
            "resume_version_id": row.resume_version_id,
            "resolution_reason": row.resolution_reason,
            "created_at": self._utc(row.created_at),
            "resolved_at": self._utc(row.resolved_at),
        }

    def _run(
        self,
        session: Session,
        *,
        context: dict[str, Any],
        status: str,
        output_count: int,
        error_code: str | None,
        input_hash: str,
        output_hash: str | None,
        audit: dict[str, Any],
        now: datetime,
    ):
        return create_agent_run(
            session,
            task_type="standalone_resume_draft",
            implementation=audit["implementation"],
            schema_version="resume_draft.v2",
            status=status,
            output_count=output_count,
            error_code=error_code,
            created_at=audit["created_at"],
            finished_at=now,
            provider=audit.get("provider"),
            model=audit.get("model"),
            prompt_version=audit.get("prompt_version"),
            skill_version=audit.get("skill_version"),
            input_entity_type="candidate_profile",
            input_entity_id=PROFILE_ID,
            input_revision=context["inputRevision"],
            input_hash=input_hash,
            output_hash=output_hash,
            input_tokens=audit.get("input_tokens"),
            output_tokens=audit.get("output_tokens"),
            duration_ms=audit.get("duration_ms"),
            retry_count=audit.get("retry_count", 0),
            sensitivity="sensitive",
        )

    @staticmethod
    def _facts(session: Session) -> list[CandidateFactModel]:
        return list(
            session.scalars(
                select(CandidateFactModel)
                .where(
                    CandidateFactModel.profile_id == PROFILE_ID,
                    CandidateFactModel.status == "confirmed",
                )
                .order_by(CandidateFactModel.id)
            ).all()
        )

    @staticmethod
    def _fact_hash(rows: list[CandidateFactModel]) -> str:
        return hashlib.sha256(
            "\n".join(f"{item.id}:{item.version}:{item.value}" for item in rows).encode()
        ).hexdigest()

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
