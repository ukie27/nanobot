"""SQLAlchemy application-material workflow adapter."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.materials import (
    FactSnapshot,
    MaterialBlock,
    MaterialType,
    VersionStatus,
    review_material,
)
from career_console.infrastructure.database.models import (
    ApplicationModel,
    CandidateFactModel,
    CompanyModel,
    FactReferenceModel,
    FactSnapshotModel,
    JobMatchAnalysisModel,
    JobMatchEvidenceModel,
    JobPostModel,
    JobPostVersionModel,
    JobRequirementModel,
    MaterialDraftModel,
    MaterialExportModel,
    MaterialReviewModel,
    ResumeDefaultModel,
    ResumeModel,
    ResumeVersionModel,
    ReviewFindingModel,
)
from career_console.infrastructure.database.profile_gateway import (
    PROFILE_ID,
    EntityNotFoundError,
    VersionConflictError,
)
from career_console.infrastructure.materials import StructuredDocxExporter, VerifiedPdfExporter

_SECTION_LABELS = {
    "basic": "基本信息",
    "education": "教育经历",
    "internship": "实习经历",
    "work": "工作经历",
    "project": "项目经历",
    "skill": "专业技能",
    "award": "奖项",
    "certificate": "证书",
    "preference": "求职偏好",
    "constraint": "限制条件",
    "imported": "简历内容",
}


class SqlAlchemyMaterialGateway:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        exports_dir: Path,
        pdf_exporter: VerifiedPdfExporter,
        docx_exporter: StructuredDocxExporter,
    ) -> None:
        self._session_factory = session_factory
        self._exports_dir = exports_dir
        self._pdf_exporter = pdf_exporter
        self._docx_exporter = docx_exporter

    def create_material(
        self,
        *,
        job_post_id: str,
        material_type: MaterialType,
        name: str,
        resume_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            normalized_name = name.strip()
            if resume_id is None and not normalized_name:
                raise CareerDomainError(
                    "Resume series name cannot be empty.", code="empty_resume_name"
                )
            post = session.get(JobPostModel, job_post_id)
            if post is None:
                raise EntityNotFoundError("Job post was not found.")
            job_version = session.scalar(
                select(JobPostVersionModel)
                .where(JobPostVersionModel.job_post_id == post.id)
                .order_by(JobPostVersionModel.version_number.desc())
            )
            requirement_count = session.scalar(
                select(func.count())
                .select_from(JobRequirementModel)
                .where(JobRequirementModel.job_post_version_id == job_version.id)
            )
            analysis = session.scalar(
                select(JobMatchAnalysisModel)
                .where(
                    JobMatchAnalysisModel.job_post_id == post.id,
                    JobMatchAnalysisModel.job_post_version_id == job_version.id,
                )
                .order_by(JobMatchAnalysisModel.created_at.desc())
            )
            if not requirement_count or analysis is None:
                raise CareerDomainError(
                    "岗位尚未提取出有效要求，请先重新分析岗位。",
                    code="job_analysis_required",
                )
            company = session.get(CompanyModel, post.company_id)
            facts = session.scalars(
                select(CandidateFactModel)
                .where(
                    CandidateFactModel.profile_id == PROFILE_ID,
                    CandidateFactModel.status == "confirmed",
                )
                .order_by(CandidateFactModel.category, CandidateFactModel.created_at)
            ).all()
            if not facts:
                raise CareerDomainError(
                    "At least one confirmed candidate fact is required.",
                    code="confirmed_facts_required",
                )
            if resume_id is None:
                resume = ResumeModel(
                    id=str(uuid4()), name=normalized_name[:300], series_type="base",
                    parent_resume_id=None, direction_label=None, created_at=now, updated_at=now
                )
                session.add(resume)
                session.flush()
                source_version = None
            else:
                resume = session.get(ResumeModel, resume_id)
                if resume is None:
                    raise EntityNotFoundError("Resume series was not found.")
                source_version = self._latest_resume_series_version(session, resume.id)
                resume.updated_at = now
            draft = MaterialDraftModel(
                id=str(uuid4()),
                resume_id=resume.id,
                job_post_id=post.id,
                job_post_version_id=job_version.id,
                source_resume_version_id=source_version.id if source_version else None,
                resume_direction_selection_id=None,
                job_title_snapshot=post.title,
                company_name_snapshot=company.canonical_name,
                material_type=material_type.value,
                status=VersionStatus.DRAFT.value,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(draft)
            session.flush()
            version = ResumeVersionModel(
                id=str(uuid4()),
                resume_id=resume.id,
                material_draft_id=draft.id,
                parent_version_id=None,
                source_resume_version_id=source_version.id if source_version else None,
                version_scope="job_tailored",
                version_number=1,
                status=VersionStatus.DRAFT.value,
                title=self._title(post, material_type, facts),
                content_json="[]",
                rendered_text="",
                content_hash="",
                fact_set_hash=self._fact_set_hash(facts),
                created_at=now,
                finalized_at=None,
            )
            session.add(version)
            session.flush()
            snapshots = self._snapshot_facts(session, version.id, facts, now)
            selected = self._selected_fact_ids(session, post.id, material_type, facts)
            blocks = self._draft_blocks(material_type, snapshots, selected)
            self._save_content(session, version, blocks)
            findings = self._perform_review(session, draft, version, now)
            version.status = (
                VersionStatus.REVIEWED.value
                if not any(item.severity == "error" for item in findings)
                else VersionStatus.DRAFT.value
            )
            draft.status = version.status
            session.commit()
            return self._material_view(session, draft)

    def list_resumes(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            default = session.scalar(select(ResumeDefaultModel))
            rows = session.execute(
                select(ResumeModel, func.count(MaterialDraftModel.id))
                .outerjoin(MaterialDraftModel, MaterialDraftModel.resume_id == ResumeModel.id)
                .where(
                    ResumeModel.scope == "library",
                    ResumeModel.retired_at.is_(None),
                )
                .group_by(ResumeModel.id)
                .order_by(ResumeModel.updated_at.desc())
            ).all()
            return [
                {
                    "id": resume.id,
                    "name": resume.name,
                    "series_type": resume.series_type,
                    "parent_resume_id": resume.parent_resume_id,
                    "direction_label": resume.direction_label,
                    "scope": resume.scope,
                    "application_id": resume.application_id,
                    "source_file_name": resume.source_file_name,
                    "material_count": material_count,
                    "latest_version": self._resume_series_version_summary(session, resume.id),
                    "latest_finalized_version": self._resume_series_version_summary(
                        session, resume.id, finalized_only=True
                    ),
                    "is_default": default is not None and default.resume_id == resume.id,
                    "default_version": (
                        default.version
                        if default is not None and default.resume_id == resume.id
                        else None
                    ),
                    "docx_export": self._latest_docx_export_view(
                        session, resume.id
                    ),
                    "created_at": self._utc(resume.created_at),
                    "updated_at": self._utc(resume.updated_at),
                }
                for resume, material_count in rows
            ]

    def list_application_resumes(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(
                select(ResumeModel, ApplicationModel)
                .join(ApplicationModel, ApplicationModel.id == ResumeModel.application_id)
                .where(
                    ResumeModel.scope == "application",
                    ResumeModel.retired_at.is_(None),
                )
                .order_by(ResumeModel.updated_at.desc())
            ).all()
            items = []
            for resume, application in rows:
                item = self._resume_detail_view(session, resume)
                item["application_status"] = application.current_status
                item["job_title"] = application.job_title_snapshot
                item["company"] = application.company_name_snapshot
                items.append(item)
            return items

    def import_resume(
        self, *, name: str, file_name: str, text: str
    ) -> dict[str, Any]:
        normalized_name = name.strip()
        if not normalized_name:
            raise CareerDomainError("请填写简历名称。", code="empty_resume_name")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise CareerDomainError("简历文件没有可用内容。", code="empty_document")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            resume = ResumeModel(
                id=str(uuid4()),
                name=normalized_name[:300],
                series_type="base",
                parent_resume_id=None,
                direction_label=None,
                scope="library",
                application_id=None,
                source_file_name=file_name[:255],
                retired_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(resume)
            session.flush()
            payload = [
                {
                    "id": f"import-{index}",
                    "section": "imported",
                    "text": line,
                    "fact_snapshot_ids": [],
                }
                for index, line in enumerate(lines, start=1)
            ]
            content_json = json.dumps(payload, ensure_ascii=False)
            version = ResumeVersionModel(
                id=str(uuid4()),
                resume_id=resume.id,
                material_draft_id=None,
                parent_version_id=None,
                source_resume_version_id=None,
                version_scope="base",
                version_number=1,
                status=VersionStatus.FINAL.value,
                title=normalized_name[:300],
                content_json=content_json,
                rendered_text="\n".join(lines),
                content_hash=hashlib.sha256(content_json.encode("utf-8")).hexdigest(),
                fact_set_hash="user-authored-import",
                created_at=now,
                finalized_at=now,
            )
            session.add(version)
            session.flush()
            written = self._write_exports(
                session,
                version=version,
                title=version.title,
                subtitle="用户导入简历",
                grouped={"imported": lines},
                file_stem=f"resume-{resume.id}-v1",
                now=now,
            )
            try:
                session.commit()
            except Exception:
                self._remove_written_exports(written)
                raise
            return self._resume_detail_view(session, resume)

    def retire_resume(self, resume_id: str) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            resume = session.get(ResumeModel, resume_id)
            if resume is None or resume.scope != "library":
                raise EntityNotFoundError("Resume series was not found.")
            if resume.retired_at is not None:
                return
            resume.retired_at = now
            resume.updated_at = now
            default = session.scalar(
                select(ResumeDefaultModel).where(ResumeDefaultModel.resume_id == resume.id)
            )
            if default is not None:
                session.delete(default)
            session.commit()

    def save_application_resume_to_library(
        self, resume_id: str, *, name: str
    ) -> dict[str, Any]:
        normalized_name = name.strip()
        if not normalized_name:
            raise CareerDomainError("请填写简历名称。", code="empty_resume_name")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            source_resume = session.get(ResumeModel, resume_id)
            if source_resume is None or source_resume.scope != "application":
                raise EntityNotFoundError("岗位简历不存在。")
            source = self._latest_resume_series_version(session, source_resume.id)
            if source is None or source.status != VersionStatus.FINAL.value:
                raise CareerDomainError(
                    "岗位简历尚未生成可下载版本。", code="application_resume_not_final"
                )
            resume = ResumeModel(
                id=str(uuid4()),
                name=normalized_name[:300],
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
            version = self._clone_standalone_version(
                session,
                source=source,
                lineage_source=source,
                resume=resume,
                scope="base",
                now=now,
            )
            version.status = VersionStatus.FINAL.value
            version.finalized_at = now
            grouped: dict[str, list[str]] = defaultdict(list)
            for block in self._blocks(version):
                grouped[block.section].append(block.text)
            written = self._write_exports(
                session,
                version=version,
                title=version.title,
                subtitle=f"保存自岗位简历 · {source_resume.name}",
                grouped=grouped,
                file_stem=f"resume-{resume.id}-v1",
                now=now,
            )
            try:
                session.commit()
            except Exception:
                self._remove_written_exports(written)
                raise
            return self._resume_detail_view(session, resume)

    def get_resume(self, resume_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            resume = session.get(ResumeModel, resume_id)
            if resume is None:
                raise EntityNotFoundError("Resume series was not found.")
            return self._resume_detail_view(session, resume)

    def edit_resume(
        self,
        resume_id: str,
        *,
        expected_version_id: str,
        blocks: list[dict[str, str]],
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            resume = session.get(ResumeModel, resume_id)
            if resume is None:
                raise EntityNotFoundError("Resume series was not found.")
            parent = self._latest_resume_series_version(session, resume.id)
            if parent is None or parent.id != expected_version_id:
                raise VersionConflictError("简历版本已变化，请刷新后重试。")
            if parent.status == VersionStatus.FINAL.value:
                raise CareerDomainError(
                    "已定稿简历不可继续编辑，请基于它创建新版本。",
                    code="final_resume_immutable",
                )
            old_blocks = self._blocks(parent)
            edits = {item["id"]: item["text"].strip() for item in blocks}
            if len(edits) != len(blocks) or set(edits) != {
                item.id for item in old_blocks
            }:
                raise CareerDomainError(
                    "编辑内容必须完整包含当前版本的所有内容块。",
                    code="material_block_set_invalid",
                )
            latest_number = session.scalar(
                select(func.max(ResumeVersionModel.version_number)).where(
                    ResumeVersionModel.resume_id == resume.id
                )
            ) or 0
            version = ResumeVersionModel(
                id=str(uuid4()),
                resume_id=resume.id,
                material_draft_id=None,
                parent_version_id=parent.id,
                source_resume_version_id=parent.source_resume_version_id,
                version_scope=parent.version_scope,
                version_number=latest_number + 1,
                status=VersionStatus.DRAFT.value,
                title=parent.title,
                content_json="[]",
                rendered_text="",
                content_hash="",
                fact_set_hash=parent.fact_set_hash,
                created_at=now,
                finalized_at=None,
            )
            session.add(version)
            session.flush()
            snapshot_map = self._clone_snapshots(session, parent.id, version.id, now)
            new_blocks = [
                MaterialBlock(
                    item.id,
                    item.section,
                    edits[item.id],
                    tuple(
                        snapshot_map[snapshot_id].id
                        for snapshot_id in item.fact_snapshot_ids
                    ),
                )
                for item in old_blocks
            ]
            self._save_content(session, version, new_blocks)
            self._perform_standalone_review(session, version, now)
            resume.updated_at = now
            session.commit()
            return self._resume_detail_view(session, resume)

    def review_resume(self, resume_id: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            resume = session.get(ResumeModel, resume_id)
            if resume is None:
                raise EntityNotFoundError("Resume series was not found.")
            version = self._latest_resume_series_version(session, resume.id)
            if version is None:
                raise EntityNotFoundError("Resume version was not found.")
            if version.status == VersionStatus.FINAL.value:
                return self._resume_detail_view(session, resume)
            self._perform_standalone_review(session, version, now)
            resume.updated_at = now
            session.commit()
            return self._resume_detail_view(session, resume)

    def finalize_resume(
        self, resume_id: str, *, expected_version_id: str
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            resume = session.get(ResumeModel, resume_id)
            if resume is None:
                raise EntityNotFoundError("Resume series was not found.")
            version = self._latest_resume_series_version(session, resume.id)
            if version is None or version.id != expected_version_id:
                raise VersionConflictError("简历版本已变化，请刷新后重试。")
            if version.status == VersionStatus.FINAL.value:
                return self._resume_detail_view(session, resume)
            findings = self._perform_standalone_review(session, version, now)
            if any(item.severity == "error" for item in findings):
                raise CareerDomainError(
                    "简历复核仍有阻断问题，暂不能定稿。",
                    code="material_review_blocked",
                )
            blocks = self._blocks(version)
            grouped: dict[str, list[str]] = defaultdict(list)
            for block in blocks:
                grouped[block.section].append(block.text)
            written = self._write_exports(
                session,
                version=version,
                title=version.title,
                subtitle=f"可复用简历 · {resume.name}",
                grouped=grouped,
                file_stem=f"resume-{resume.id}-v{version.version_number}",
                now=now,
            )
            version.status = VersionStatus.FINAL.value
            version.finalized_at = now
            resume.updated_at = now
            try:
                session.commit()
            except Exception:
                self._remove_written_exports(written)
                raise
            return self._resume_detail_view(session, resume)

    def list_materials(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            drafts = session.scalars(
                select(MaterialDraftModel).order_by(MaterialDraftModel.updated_at.desc())
            ).all()
            return [self._summary(session, item) for item in drafts]

    def get_material(self, material_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            return self._material_view(session, self._draft(session, material_id))

    def fork_resume(
        self,
        material_id: str,
        *,
        series_type: str,
        name: str,
        parent_resume_id: str | None,
        direction_label: str | None,
    ) -> dict[str, Any]:
        if series_type not in {"base", "direction"}:
            raise ValueError("只支持保存为基础简历或方向简历。")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            draft = self._draft(session, material_id)
            source = self._latest_version(session, draft.id)
            if source.status not in {VersionStatus.REVIEWED.value, VersionStatus.FINAL.value}:
                raise CareerDomainError(
                    "只有审查通过的材料才能保存为可复用简历。",
                    code="resume_fork_review_required",
                )
            normalized_name = name.strip()
            if not normalized_name:
                raise CareerDomainError("简历名称不能为空。", code="empty_resume_name")
            parent = None
            parent_version = None
            if series_type == "direction":
                parent = session.get(ResumeModel, parent_resume_id) if parent_resume_id else None
                if parent is None or parent.series_type != "base":
                    raise CareerDomainError(
                        "方向简历必须关联一个基础简历系列。",
                        code="direction_parent_required",
                    )
                if not (direction_label or "").strip():
                    raise CareerDomainError(
                        "方向简历必须填写方向名称。", code="direction_label_required"
                    )
                parent_version = self._latest_resume_series_version(session, parent.id)
                if parent_version is None:
                    raise CareerDomainError(
                        "基础简历尚无可用版本。", code="base_resume_version_required"
                    )
            elif parent_resume_id is not None:
                raise ValueError("基础简历不能设置父系列。")
            resume = ResumeModel(
                id=str(uuid4()),
                name=normalized_name[:300],
                series_type=series_type,
                parent_resume_id=parent.id if parent else None,
                direction_label=(direction_label or "").strip()[:120] or None,
                scope="library",
                application_id=None,
                source_file_name=None,
                retired_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(resume)
            session.flush()
            version = self._clone_standalone_version(
                session,
                source=source,
                lineage_source=parent_version or source,
                resume=resume,
                scope=series_type,
                now=now,
            )
            session.commit()
            return self._resume_view(session, resume, version)

    def diff_versions(self, from_version_id: str, to_version_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            before = session.get(ResumeVersionModel, from_version_id)
            after = session.get(ResumeVersionModel, to_version_id)
            if before is None or after is None:
                raise EntityNotFoundError("Resume version was not found.")
            before_blocks = self._diff_blocks(session, before)
            after_blocks = self._diff_blocks(session, after)
            before_by_id = {item["id"]: item for item in before_blocks}
            after_by_id = {item["id"]: item for item in after_blocks}
            changes = []
            for block_id in dict.fromkeys([*before_by_id, *after_by_id]):
                old = before_by_id.get(block_id)
                new = after_by_id.get(block_id)
                if old is None:
                    change = "added"
                elif new is None:
                    change = "removed"
                elif old == new:
                    change = "unchanged"
                else:
                    change = "changed"
                changes.append(
                    {"block_id": block_id, "change": change, "before": old, "after": new}
                )
            before_facts = {fact_id for item in before_blocks for fact_id in item["fact_ids"]}
            after_facts = {fact_id for item in after_blocks for fact_id in item["fact_ids"]}
            counts = {
                key: sum(item["change"] == key for item in changes)
                for key in ("added", "removed", "changed", "unchanged")
            }
            return {
                "from_version": self._version_summary(before),
                "to_version": self._version_summary(after),
                "summary": counts,
                "fact_changes": {
                    "added_fact_ids": sorted(after_facts - before_facts),
                    "removed_fact_ids": sorted(before_facts - after_facts),
                },
                "blocks": changes,
            }

    def edit_material(
        self, material_id: str, *, expected_version: int, blocks: list[dict[str, str]]
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            draft = self._draft(session, material_id)
            self._expect_editable(draft, expected_version)
            parent = self._latest_version(session, draft.id)
            old_blocks = self._blocks(parent)
            edits = {item["id"]: item["text"].strip() for item in blocks}
            if len(edits) != len(blocks) or set(edits) != {item.id for item in old_blocks}:
                raise CareerDomainError(
                    "Edits must include every existing material block exactly once.",
                    code="material_block_set_invalid",
                )
            version = ResumeVersionModel(
                id=str(uuid4()),
                resume_id=draft.resume_id,
                material_draft_id=draft.id,
                parent_version_id=parent.id,
                source_resume_version_id=parent.source_resume_version_id,
                version_scope=parent.version_scope,
                version_number=parent.version_number + 1,
                status=VersionStatus.DRAFT.value,
                title=parent.title,
                content_json="[]",
                rendered_text="",
                content_hash="",
                fact_set_hash=parent.fact_set_hash,
                created_at=now,
                finalized_at=None,
            )
            session.add(version)
            session.flush()
            old_snapshots = session.scalars(
                select(FactSnapshotModel).where(FactSnapshotModel.resume_version_id == parent.id)
            ).all()
            snapshot_map: dict[str, FactSnapshotModel] = {}
            for old in old_snapshots:
                new = FactSnapshotModel(
                    id=str(uuid4()),
                    resume_version_id=version.id,
                    fact_id=old.fact_id,
                    fact_version=old.fact_version,
                    category=old.category,
                    field_key=old.field_key,
                    value=old.value,
                    created_at=now,
                )
                session.add(new)
                snapshot_map[old.id] = new
            session.flush()
            new_blocks = [
                MaterialBlock(
                    item.id,
                    item.section,
                    edits[item.id],
                    tuple(snapshot_map[snapshot_id].id for snapshot_id in item.fact_snapshot_ids),
                )
                for item in old_blocks
            ]
            self._save_content(session, version, new_blocks)
            findings = self._perform_review(session, draft, version, now)
            version.status = (
                VersionStatus.REVIEWED.value
                if not any(item.severity == "error" for item in findings)
                else VersionStatus.DRAFT.value
            )
            draft.status = version.status
            draft.version += 1
            draft.updated_at = now
            self._clear_strategy_stale(draft)
            session.commit()
            return self._material_view(session, draft)

    def review_material(self, material_id: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            draft = self._draft(session, material_id)
            if draft.status == VersionStatus.FINAL.value:
                raise CareerDomainError(
                    "Final materials are immutable.", code="final_material_immutable"
                )
            version = self._latest_version(session, draft.id)
            findings = self._perform_review(session, draft, version, now)
            version.status = (
                VersionStatus.REVIEWED.value
                if not any(item.severity == "error" for item in findings)
                else VersionStatus.DRAFT.value
            )
            draft.status = version.status
            draft.updated_at = now
            session.commit()
            return self._material_view(session, draft)

    def finalize_material(self, material_id: str, *, expected_version: int) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            draft = self._draft(session, material_id)
            if draft.version != expected_version:
                raise VersionConflictError("Material changed after it was loaded.")
            if draft.status == VersionStatus.FINAL.value:
                return self._material_view(session, draft)
            version = self._latest_version(session, draft.id)
            findings = self._perform_review(session, draft, version, now)
            if any(item.severity == "error" for item in findings):
                raise CareerDomainError(
                    "Material review contains blocking findings.", code="material_review_blocked"
                )
            blocks = self._blocks(version)
            grouped: dict[str, list[str]] = defaultdict(list)
            for block in blocks:
                grouped[block.section].append(block.text)
            written = self._write_exports(
                session,
                version=version,
                title=version.title,
                subtitle=f"目标岗位：{draft.company_name_snapshot} · {draft.job_title_snapshot}",
                grouped=grouped,
                file_stem=f"{draft.id}-v{version.version_number}",
                now=now,
            )
            version.status = VersionStatus.FINAL.value
            version.finalized_at = now
            draft.status = VersionStatus.FINAL.value
            draft.version += 1
            draft.updated_at = now
            try:
                session.commit()
            except Exception:
                self._remove_written_exports(written)
                raise
            return self._material_view(session, draft)

    def export_path(self, export_id: str, *, preview: bool = False) -> tuple[str, str]:
        with self._session_factory() as session:
            export = session.get(MaterialExportModel, export_id)
            if export is None:
                raise EntityNotFoundError("Material export was not found.")
            name = export.preview_relative_path if preview else export.relative_path
            path = (self._exports_dir / name).resolve(strict=True)
            if self._exports_dir.resolve(strict=True) not in path.parents:
                raise CareerDomainError(
                    "Export path is outside the controlled directory.", code="invalid_export_path"
                )
            if preview:
                return str(path), "image/png"
            media_type = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if export.format == "docx"
                else "application/pdf"
            )
            return str(path), media_type

    def _perform_review(
        self,
        session: Session,
        draft: MaterialDraftModel,
        version: ResumeVersionModel,
        now: datetime,
    ):
        blocks = self._blocks(version)
        snapshots = self._domain_snapshots(session, version.id)
        referenced_fact_ids = {
            snapshot.fact_id
            for snapshot in snapshots
            if any(snapshot.id in block.fact_snapshot_ids for block in blocks)
        }
        analysis = session.scalar(
            select(JobMatchAnalysisModel)
            .where(JobMatchAnalysisModel.job_post_id == draft.job_post_id)
            .order_by(JobMatchAnalysisModel.created_at.desc())
        )
        matched_fact_ids: set[str] = set()
        if analysis:
            matched_fact_ids = set(
                session.scalars(
                    select(JobMatchEvidenceModel.fact_id).where(
                        JobMatchEvidenceModel.analysis_id == analysis.id,
                        JobMatchEvidenceModel.decision == "matched",
                        JobMatchEvidenceModel.fact_id.is_not(None),
                    )
                ).all()
            )
        findings = review_material(
            blocks,
            snapshots,
            material_type=MaterialType(draft.material_type),
            uncovered_requirement_count=len(matched_fact_ids - referenced_fact_ids),
            hard_gap_count=analysis.must_gap_count if analysis else 0,
        )
        review = MaterialReviewModel(
            id=str(uuid4()),
            resume_version_id=version.id,
            schema_version="material_review.v1",
            status="passed" if not any(item.severity == "error" for item in findings) else "failed",
            error_count=sum(item.severity == "error" for item in findings),
            warning_count=sum(item.severity == "warning" for item in findings),
            created_at=now,
        )
        session.add(review)
        session.flush()
        for item in findings:
            session.add(
                ReviewFindingModel(
                    id=str(uuid4()),
                    review_id=review.id,
                    severity=item.severity,
                    code=item.code,
                    message=item.message,
                    block_id=item.block_id,
                    created_at=now,
                )
            )
        return findings

    def _perform_standalone_review(
        self, session: Session, version: ResumeVersionModel, now: datetime
    ):
        findings = review_material(
            self._blocks(version),
            self._domain_snapshots(session, version.id),
            material_type=MaterialType.RESUME,
        )
        review = MaterialReviewModel(
            id=str(uuid4()),
            resume_version_id=version.id,
            schema_version="material_review.v1",
            status=(
                "failed"
                if any(item.severity == "error" for item in findings)
                else "passed"
            ),
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
        version.status = (
            VersionStatus.DRAFT.value
            if any(item.severity == "error" for item in findings)
            else VersionStatus.REVIEWED.value
        )
        return findings

    def _save_content(
        self, session: Session, version: ResumeVersionModel, blocks: list[MaterialBlock]
    ) -> None:
        payload = [
            {
                "id": item.id,
                "section": item.section,
                "text": item.text,
                "fact_snapshot_ids": list(item.fact_snapshot_ids),
            }
            for item in blocks
        ]
        version.content_json = json.dumps(payload, ensure_ascii=False)
        version.rendered_text = "\n".join(item.text for item in blocks)
        version.content_hash = hashlib.sha256(version.content_json.encode("utf-8")).hexdigest()
        for block in blocks:
            for snapshot_id in block.fact_snapshot_ids:
                session.add(
                    FactReferenceModel(
                        id=str(uuid4()),
                        resume_version_id=version.id,
                        fact_snapshot_id=snapshot_id,
                        block_id=block.id,
                    )
                )
        session.flush()

    @staticmethod
    def _clone_snapshots(
        session: Session,
        source_version_id: str,
        target_version_id: str,
        now: datetime,
    ) -> dict[str, FactSnapshotModel]:
        result: dict[str, FactSnapshotModel] = {}
        snapshots = session.scalars(
            select(FactSnapshotModel).where(
                FactSnapshotModel.resume_version_id == source_version_id
            )
        ).all()
        for source in snapshots:
            target = FactSnapshotModel(
                id=str(uuid4()),
                resume_version_id=target_version_id,
                fact_id=source.fact_id,
                fact_version=source.fact_version,
                category=source.category,
                field_key=source.field_key,
                value=source.value,
                created_at=now,
            )
            session.add(target)
            result[source.id] = target
        session.flush()
        return result

    @staticmethod
    def _snapshot_facts(
        session: Session, version_id: str, facts: list[CandidateFactModel], now: datetime
    ) -> list[FactSnapshotModel]:
        result = []
        for fact in facts:
            snapshot = FactSnapshotModel(
                id=str(uuid4()),
                resume_version_id=version_id,
                fact_id=fact.id,
                fact_version=fact.version,
                category=fact.category,
                field_key=fact.field_key,
                value=fact.value,
                created_at=now,
            )
            session.add(snapshot)
            result.append(snapshot)
        session.flush()
        return result

    def _selected_fact_ids(
        self,
        session: Session,
        job_id: str,
        material_type: MaterialType,
        facts: list[CandidateFactModel],
    ) -> list[str]:
        analysis = session.scalar(
            select(JobMatchAnalysisModel)
            .where(JobMatchAnalysisModel.job_post_id == job_id)
            .order_by(JobMatchAnalysisModel.created_at.desc())
        )
        relevant = (
            []
            if analysis is None
            else list(
                session.scalars(
                    select(JobMatchEvidenceModel.fact_id).where(
                        JobMatchEvidenceModel.analysis_id == analysis.id,
                        JobMatchEvidenceModel.decision == "matched",
                        JobMatchEvidenceModel.fact_id.is_not(None),
                    )
                ).all()
            )
        )
        if material_type is MaterialType.RESUME:
            category_order = {
                name: index
                for index, name in enumerate(
                    (
                        "basic",
                        "preference",
                        "skill",
                        "work",
                        "internship",
                        "project",
                        "education",
                        "award",
                        "certificate",
                        "constraint",
                    )
                )
            }
            relevant_set = set(relevant)
            ordered = [
                item.id
                for item in sorted(
                    facts,
                    key=lambda item: (
                        category_order.get(item.category, 99),
                        0 if item.id in relevant_set else 1,
                        item.created_at,
                    ),
                )
            ]
        else:
            all_ids = [fact.id for fact in facts]
            ordered = list(dict.fromkeys([*relevant, *all_ids]))
        return ordered[: 25 if material_type is MaterialType.RESUME else 6]

    @staticmethod
    def _draft_blocks(
        material_type: MaterialType, snapshots: list[FactSnapshotModel], selected_ids: list[str]
    ) -> list[MaterialBlock]:
        by_fact = {item.fact_id: item for item in snapshots}
        if material_type is MaterialType.INTRODUCTION:
            selected = [by_fact[fact_id] for fact_id in selected_ids]
            return [
                MaterialBlock(
                    "claim-1",
                    "自我介绍",
                    "；".join(item.value for item in selected),
                    tuple(item.id for item in selected),
                )
            ]
        result = []
        for index, fact_id in enumerate(selected_ids):
            snapshot = by_fact[fact_id]
            section = snapshot.category if material_type is MaterialType.RESUME else "相关经历"
            result.append(
                MaterialBlock(f"claim-{index + 1}", section, snapshot.value, (snapshot.id,))
            )
        return result

    @staticmethod
    def _blocks(version: ResumeVersionModel) -> list[MaterialBlock]:
        return [
            MaterialBlock(
                item["id"], item["section"], item["text"], tuple(item["fact_snapshot_ids"])
            )
            for item in json.loads(version.content_json)
        ]

    @staticmethod
    def _domain_snapshots(session: Session, version_id: str) -> list[FactSnapshot]:
        return [
            FactSnapshot(item.id, item.fact_id, item.fact_version, item.value)
            for item in session.scalars(
                select(FactSnapshotModel).where(FactSnapshotModel.resume_version_id == version_id)
            ).all()
        ]

    def _material_view(self, session: Session, draft: MaterialDraftModel) -> dict[str, Any]:
        result = self._summary(session, draft)
        versions = session.scalars(
            select(ResumeVersionModel)
            .where(ResumeVersionModel.material_draft_id == draft.id)
            .order_by(ResumeVersionModel.version_number.desc())
        ).all()
        current = versions[0]
        snapshots = {
            item.id: item
            for item in session.scalars(
                select(FactSnapshotModel).where(FactSnapshotModel.resume_version_id == current.id)
            ).all()
        }
        review = session.scalar(
            select(MaterialReviewModel)
            .where(MaterialReviewModel.resume_version_id == current.id)
            .order_by(MaterialReviewModel.created_at.desc())
        )
        findings = (
            []
            if review is None
            else session.scalars(
                select(ReviewFindingModel).where(ReviewFindingModel.review_id == review.id)
            ).all()
        )
        exports = session.scalars(
            select(MaterialExportModel)
            .where(MaterialExportModel.resume_version_id == current.id)
            .order_by(MaterialExportModel.created_at.desc())
        ).all()
        export = next((item for item in exports if item.format == "pdf"), None)
        blocks = self._blocks(current)
        result.update(
            {
                "current_version": self._version_view(current, blocks, snapshots),
                "versions": [self._version_summary(item) for item in versions],
                "review": None
                if review is None
                else {
                    "id": review.id,
                    "status": review.status,
                    "schema_version": review.schema_version,
                    "error_count": review.error_count,
                    "warning_count": review.warning_count,
                    "created_at": self._utc(review.created_at),
                    "findings": [
                        {
                            "id": item.id,
                            "severity": item.severity,
                            "code": item.code,
                            "message": item.message,
                            "block_id": item.block_id,
                        }
                        for item in findings
                    ],
                },
                "export": None if export is None else self._export_view(export),
                "exports": [self._export_view(item) for item in exports],
            }
        )
        return result

    def _summary(self, session: Session, draft: MaterialDraftModel) -> dict[str, Any]:
        post = session.get(JobPostModel, draft.job_post_id)
        version = self._latest_version(session, draft.id)
        resume = session.get(ResumeModel, draft.resume_id)
        return {
            "id": draft.id,
            "resume_id": draft.resume_id,
            "name": resume.name,
            "resume_series_type": resume.series_type,
            "source_resume_version_id": draft.source_resume_version_id,
            "resume_direction_selection_id": draft.resume_direction_selection_id,
            "material_type": draft.material_type,
            "status": draft.status,
            "version": draft.version,
            "strategy_stale": bool(draft.strategy_stale),
            "strategy_stale_reason": draft.strategy_stale_reason,
            "strategy_stale_at": self._utc(draft.strategy_stale_at),
            "job_post_id": post.id,
            "job_post_version_id": draft.job_post_version_id,
            "job_title": draft.job_title_snapshot,
            "company": draft.company_name_snapshot,
            "current_version_number": version.version_number,
            "created_at": self._utc(draft.created_at),
            "updated_at": self._utc(draft.updated_at),
        }

    @staticmethod
    def _version_view(
        version: ResumeVersionModel,
        blocks: list[MaterialBlock],
        snapshots: dict[str, FactSnapshotModel],
    ) -> dict[str, Any]:
        return {
            **SqlAlchemyMaterialGateway._version_summary(version),
            "rendered_text": version.rendered_text,
            "blocks": [
                {
                    "id": item.id,
                    "section": item.section,
                    "text": item.text,
                    "fact_snapshots": [
                        {
                            "id": snapshots[sid].id,
                            "fact_id": snapshots[sid].fact_id,
                            "fact_version": snapshots[sid].fact_version,
                            "category": snapshots[sid].category,
                            "field_key": snapshots[sid].field_key,
                            "value": snapshots[sid].value,
                        }
                        for sid in item.fact_snapshot_ids
                    ],
                }
                for item in blocks
            ],
        }

    @staticmethod
    def _version_summary(version: ResumeVersionModel) -> dict[str, Any]:
        return {
            "id": version.id,
            "parent_version_id": version.parent_version_id,
            "source_resume_version_id": version.source_resume_version_id,
            "version_scope": version.version_scope,
            "version_number": version.version_number,
            "status": version.status,
            "title": version.title,
            "content_hash": version.content_hash,
            "fact_set_hash": version.fact_set_hash,
            "created_at": SqlAlchemyMaterialGateway._utc(version.created_at),
            "finalized_at": SqlAlchemyMaterialGateway._utc(version.finalized_at),
        }

    def _clone_standalone_version(
        self,
        session: Session,
        *,
        source: ResumeVersionModel,
        lineage_source: ResumeVersionModel,
        resume: ResumeModel,
        scope: str,
        now: datetime,
    ) -> ResumeVersionModel:
        version = ResumeVersionModel(
            id=str(uuid4()),
            resume_id=resume.id,
            material_draft_id=None,
            parent_version_id=None,
            source_resume_version_id=lineage_source.id,
            version_scope=scope,
            version_number=1,
            status=VersionStatus.REVIEWED.value,
            title=source.title,
            content_json="[]",
            rendered_text=source.rendered_text,
            content_hash="",
            fact_set_hash=source.fact_set_hash,
            created_at=now,
            finalized_at=None,
        )
        session.add(version)
        session.flush()
        old_snapshots = session.scalars(
            select(FactSnapshotModel).where(FactSnapshotModel.resume_version_id == source.id)
        ).all()
        snapshot_map: dict[str, FactSnapshotModel] = {}
        for old in old_snapshots:
            new = FactSnapshotModel(
                id=str(uuid4()),
                resume_version_id=version.id,
                fact_id=old.fact_id,
                fact_version=old.fact_version,
                category=old.category,
                field_key=old.field_key,
                value=old.value,
                created_at=now,
            )
            session.add(new)
            snapshot_map[old.id] = new
        session.flush()
        payload = []
        for block in json.loads(source.content_json):
            snapshot_ids = [snapshot_map[item].id for item in block["fact_snapshot_ids"]]
            payload.append({**block, "fact_snapshot_ids": snapshot_ids})
            for snapshot_id in snapshot_ids:
                session.add(
                    FactReferenceModel(
                        id=str(uuid4()),
                        resume_version_id=version.id,
                        fact_snapshot_id=snapshot_id,
                        block_id=block["id"],
                    )
                )
        version.content_json = json.dumps(payload, ensure_ascii=False)
        version.content_hash = hashlib.sha256(version.content_json.encode("utf-8")).hexdigest()
        session.flush()
        return version

    def _resume_series_version_summary(
        self, session: Session, resume_id: str, *, finalized_only: bool = False
    ) -> dict[str, Any] | None:
        if finalized_only:
            version = session.scalar(
                select(ResumeVersionModel)
                .where(
                    ResumeVersionModel.resume_id == resume_id,
                    ResumeVersionModel.status == VersionStatus.FINAL.value,
                )
                .order_by(
                    ResumeVersionModel.finalized_at.desc(),
                    ResumeVersionModel.version_number.desc(),
                )
            )
        else:
            version = self._latest_resume_series_version(session, resume_id)
        return None if version is None else self._version_summary(version)

    def _latest_docx_export_view(
        self, session: Session, resume_id: str
    ) -> dict[str, Any] | None:
        version = session.scalar(
            select(ResumeVersionModel)
            .where(
                ResumeVersionModel.resume_id == resume_id,
                ResumeVersionModel.status == VersionStatus.FINAL.value,
            )
            .order_by(
                ResumeVersionModel.finalized_at.desc(),
                ResumeVersionModel.version_number.desc(),
            )
        )
        if version is None:
            return None
        export = session.scalar(
            select(MaterialExportModel)
            .where(
                MaterialExportModel.resume_version_id == version.id,
                MaterialExportModel.format == "docx",
            )
            .order_by(MaterialExportModel.created_at.desc())
        )
        return None if export is None else self._export_view(export)

    def _resume_view(
        self, session: Session, resume: ResumeModel, version: ResumeVersionModel
    ) -> dict[str, Any]:
        material_count = session.scalar(
            select(func.count()).select_from(MaterialDraftModel).where(
                MaterialDraftModel.resume_id == resume.id
            )
        )
        default = session.scalar(select(ResumeDefaultModel))
        docx_export = session.scalar(
            select(MaterialExportModel)
            .where(
                MaterialExportModel.resume_version_id == version.id,
                MaterialExportModel.format == "docx",
            )
            .order_by(MaterialExportModel.created_at.desc())
        )
        return {
            "id": resume.id,
            "name": resume.name,
            "series_type": resume.series_type,
            "parent_resume_id": resume.parent_resume_id,
            "direction_label": resume.direction_label,
            "scope": resume.scope,
            "application_id": resume.application_id,
            "source_file_name": resume.source_file_name,
            "material_count": material_count,
            "latest_version": self._version_summary(version),
            "latest_finalized_version": self._resume_series_version_summary(
                session, resume.id, finalized_only=True
            ),
            "is_default": default is not None and default.resume_id == resume.id,
            "default_version": (
                default.version
                if default is not None and default.resume_id == resume.id
                else None
            ),
            "docx_export": (
                None if docx_export is None else self._export_view(docx_export)
            ),
            "created_at": self._utc(resume.created_at),
            "updated_at": self._utc(resume.updated_at),
        }

    def _resume_detail_view(
        self, session: Session, resume: ResumeModel
    ) -> dict[str, Any]:
        versions = session.scalars(
            select(ResumeVersionModel)
            .where(
                ResumeVersionModel.resume_id == resume.id,
                ResumeVersionModel.version_scope.in_(["base", "direction"]),
            )
            .order_by(
                ResumeVersionModel.version_number.desc(),
                ResumeVersionModel.created_at.desc(),
            )
        ).all()
        if not versions:
            fallback = self._latest_resume_series_version(session, resume.id)
            versions = [] if fallback is None else [fallback]
        if not versions:
            raise EntityNotFoundError("Resume version was not found.")
        current = versions[0]
        snapshots = {
            item.id: item
            for item in session.scalars(
                select(FactSnapshotModel).where(
                    FactSnapshotModel.resume_version_id == current.id
                )
            ).all()
        }
        review = session.scalar(
            select(MaterialReviewModel)
            .where(MaterialReviewModel.resume_version_id == current.id)
            .order_by(MaterialReviewModel.created_at.desc())
        )
        findings = (
            []
            if review is None
            else session.scalars(
                select(ReviewFindingModel).where(
                    ReviewFindingModel.review_id == review.id
                )
            ).all()
        )
        exports = session.scalars(
            select(MaterialExportModel)
            .where(MaterialExportModel.resume_version_id == current.id)
            .order_by(MaterialExportModel.created_at.desc())
        ).all()
        export = next((item for item in exports if item.format == "pdf"), None)
        result = self._resume_view(session, resume, current)
        result.update(
            {
                "current_version": self._version_view(
                    current, self._blocks(current), snapshots
                ),
                "versions": [self._version_summary(item) for item in versions],
                "review": (
                    None
                    if review is None
                    else {
                        "id": review.id,
                        "status": review.status,
                        "schema_version": review.schema_version,
                        "error_count": review.error_count,
                        "warning_count": review.warning_count,
                        "created_at": self._utc(review.created_at),
                        "findings": [
                            {
                                "id": item.id,
                                "severity": item.severity,
                                "code": item.code,
                                "message": item.message,
                                "block_id": item.block_id,
                            }
                            for item in findings
                        ],
                    }
                ),
                "export": None if export is None else self._export_view(export),
                "exports": [self._export_view(item) for item in exports],
            }
        )
        return result

    def _write_exports(
        self,
        session: Session,
        *,
        version: ResumeVersionModel,
        title: str,
        subtitle: str,
        grouped: dict[str, list[str]],
        file_stem: str,
        now: datetime,
    ) -> list[Path]:
        sections = [
            (_SECTION_LABELS.get(section, section), lines)
            for section, lines in grouped.items()
        ]
        pdf = self._pdf_exporter.generate(
            title=title, subtitle=subtitle, sections=sections
        )
        docx = self._docx_exporter.generate(
            title=title, subtitle=subtitle, sections=sections
        )
        pdf_name = f"{file_stem}-{pdf.sha256[:12]}.pdf"
        preview_name = f"{file_stem}-{pdf.sha256[:12]}.png"
        docx_name = f"{file_stem}-{docx.sha256[:12]}.docx"
        docx_preview_name = f"{file_stem}-{docx.sha256[:12]}.docx-preview"
        pdf_path = self._exports_dir / pdf_name
        preview_path = self._exports_dir / preview_name
        docx_path = self._exports_dir / docx_name
        written = [pdf_path, preview_path, docx_path]
        try:
            self._atomic_write(pdf_path, pdf.pdf_bytes)
            self._atomic_write(preview_path, pdf.preview_png)
            self._atomic_write(docx_path, docx.docx_bytes)
        except Exception:
            self._remove_written_exports(written)
            raise
        session.add_all(
            [
                MaterialExportModel(
                    id=str(uuid4()),
                    resume_version_id=version.id,
                    format="pdf",
                    relative_path=pdf_name,
                    preview_relative_path=preview_name,
                    sha256=pdf.sha256,
                    size_bytes=pdf.size_bytes,
                    page_count=pdf.page_count,
                    text_layer_ok=int(pdf.text_layer_ok),
                    render_ok=int(pdf.render_ok),
                    extracted_text_hash=pdf.extracted_text_hash,
                    created_at=now,
                ),
                MaterialExportModel(
                    id=str(uuid4()),
                    resume_version_id=version.id,
                    format="docx",
                    relative_path=docx_name,
                    preview_relative_path=docx_preview_name,
                    sha256=docx.sha256,
                    size_bytes=docx.size_bytes,
                    page_count=0,
                    text_layer_ok=1,
                    render_ok=1,
                    extracted_text_hash=docx.extracted_text_hash,
                    created_at=now,
                ),
            ]
        )
        return written

    @staticmethod
    def _remove_written_exports(paths: list[Path]) -> None:
        for path in paths:
            path.unlink(missing_ok=True)

    @staticmethod
    def _diff_blocks(session: Session, version: ResumeVersionModel) -> list[dict[str, Any]]:
        snapshots = {
            item.id: item
            for item in session.scalars(
                select(FactSnapshotModel).where(FactSnapshotModel.resume_version_id == version.id)
            ).all()
        }
        return [
            {
                "id": item["id"],
                "section": item["section"],
                "text": item["text"],
                "fact_ids": [snapshots[sid].fact_id for sid in item["fact_snapshot_ids"]],
            }
            for item in json.loads(version.content_json)
        ]

    @staticmethod
    def _export_view(export: MaterialExportModel) -> dict[str, Any]:
        return {
            "id": export.id,
            "format": export.format,
            "sha256": export.sha256,
            "size_bytes": export.size_bytes,
            "page_count": export.page_count,
            "text_layer_ok": bool(export.text_layer_ok),
            "render_ok": bool(export.render_ok),
            "extracted_text_hash": export.extracted_text_hash,
            "created_at": SqlAlchemyMaterialGateway._utc(export.created_at),
            "download_url": f"/api/v1/material-exports/{export.id}/download",
            "preview_url": f"/api/v1/material-exports/{export.id}/preview",
        }

    @staticmethod
    def _fact_set_hash(facts: list[CandidateFactModel]) -> str:
        return hashlib.sha256(
            "\n".join(f"{item.id}:{item.version}:{item.value}" for item in facts).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _title(
        post: JobPostModel, material_type: MaterialType, facts: list[CandidateFactModel]
    ) -> str:
        labels = {
            MaterialType.RESUME: "定制简历",
            MaterialType.COVER_LETTER: "求职信",
            MaterialType.INTRODUCTION: "自我介绍",
        }
        name = next(
            (
                item.value
                for item in facts
                if item.category == "basic"
                and item.field_key in {"name", "full_name", "display_name"}
            ),
            "个人",
        )
        return f"{name} · {post.title} · {labels[material_type]}"

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".material-", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _latest_version(session: Session, draft_id: str) -> ResumeVersionModel:
        return session.scalar(
            select(ResumeVersionModel)
            .where(ResumeVersionModel.material_draft_id == draft_id)
            .order_by(ResumeVersionModel.version_number.desc())
        )

    @staticmethod
    def _latest_resume_series_version(
        session: Session, resume_id: str
    ) -> ResumeVersionModel | None:
        reusable = session.scalar(
            select(ResumeVersionModel)
            .where(
                ResumeVersionModel.resume_id == resume_id,
                ResumeVersionModel.version_scope.in_(["base", "direction"]),
            )
            .order_by(
                ResumeVersionModel.version_number.desc(),
                ResumeVersionModel.created_at.desc(),
            )
        )
        if reusable is not None:
            return reusable
        return session.scalar(
            select(ResumeVersionModel)
            .where(ResumeVersionModel.resume_id == resume_id)
            .order_by(
                ResumeVersionModel.version_number.desc(),
                ResumeVersionModel.created_at.desc(),
            )
        )

    @staticmethod
    def _draft(session: Session, material_id: str) -> MaterialDraftModel:
        draft = session.get(MaterialDraftModel, material_id)
        if draft is None:
            raise EntityNotFoundError("Material was not found.")
        return draft

    @staticmethod
    def _expect_editable(draft: MaterialDraftModel, expected_version: int) -> None:
        if draft.version != expected_version:
            raise VersionConflictError("Material changed after it was loaded.")
        if draft.status == VersionStatus.FINAL.value:
            raise CareerDomainError(
                "Final materials are immutable.", code="final_material_immutable"
            )

    @staticmethod
    def _clear_strategy_stale(draft: MaterialDraftModel) -> None:
        draft.strategy_stale = 0
        draft.strategy_stale_reason = None
        draft.strategy_stale_at = None
