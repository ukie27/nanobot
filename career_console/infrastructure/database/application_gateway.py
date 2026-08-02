"""SQLAlchemy adapter for applications, immutable events, and review proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from career_console.domain.applications import (
    ApplicationStatus,
    ProposalStatus,
    ensure_transition,
    event_type_for,
)
from career_console.domain.common.errors import CareerDomainError
from career_console.infrastructure.database.models import (
    ApplicationEventModel,
    ApplicationEventProposalModel,
    ApplicationMaterialSnapshotModel,
    ApplicationModel,
    ApplicationResumeBindingModel,
    CompanyModel,
    JobMatchAnalysisModel,
    JobPostModel,
    JobPostVersionModel,
    JobRequirementModel,
    MailIntelligenceAnalysisModel,
    MailIntelligenceItemModel,
    MailMessageModel,
    MaterialDraftModel,
    MaterialExportModel,
    ResumeDefaultModel,
    ResumeModel,
    ResumeVersionModel,
    ReviewTaskModel,
)
from career_console.infrastructure.database.profile_gateway import (
    EntityNotFoundError,
    VersionConflictError,
)
from career_console.infrastructure.database.review_runtime import (
    ensure_review_task,
    set_review_resolution,
)


class SqlAlchemyApplicationGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_application(self, *, job_post_id: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            existing = session.scalar(
                select(ApplicationModel)
                .where(
                    ApplicationModel.job_post_id == job_post_id,
                    ApplicationModel.archived_at.is_(None),
                )
                .order_by(ApplicationModel.created_at.desc())
            )
            if existing is not None:
                self._link_mail_to_application(session, existing)
                session.commit()
                return self._view(session, existing)
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
                select(JobMatchAnalysisModel.id)
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
            application = ApplicationModel(
                id=str(uuid4()),
                job_post_id=post.id,
                job_post_version_id=job_version.id,
                job_title_snapshot=post.title,
                company_name_snapshot=company.canonical_name,
                job_content_hash=job_version.content_hash,
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
                target=ApplicationStatus.DISCOVERED,
                occurred_at=now,
                note="Application tracking created from the selected job post.",
                source="user",
                idempotency_key=f"create:{application.id}",
                from_status=None,
            )
            session.flush()
            self._append_event(
                session,
                application,
                event_type="application_status_changed",
                target=ApplicationStatus.PREPARING_MATERIALS,
                occurred_at=now,
                note="Application materials must be bound before submission.",
                source="system",
                idempotency_key=f"initialize:{application.id}",
            )
            self._link_mail_to_application(session, application)
            session.commit()
            return self._view(session, application)

    def list_applications(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            items = session.scalars(
                select(ApplicationModel).order_by(ApplicationModel.updated_at.desc())
            ).all()
            return [self._summary(session, item) for item in items]

    def get_application(self, application_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            return self._view(session, self._application(session, application_id))

    def bind_resume(
        self,
        application_id: str,
        *,
        expected_version: int,
        command_id: str,
        resume_version_id: str | None,
        use_default: bool,
        source: str,
        reason: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            application = self._application(session, application_id)
            if self._command_exists(session, application.id, command_id):
                return self._view(session, application)
            self._expect_version(application, expected_version)
            if application.current_status not in {
                ApplicationStatus.DISCOVERED.value,
                ApplicationStatus.PREPARING_MATERIALS.value,
                ApplicationStatus.READY_TO_APPLY.value,
            }:
                raise CareerDomainError(
                    "Submitted or completed applications cannot replace their resume binding.",
                    code="application_resume_binding_locked",
                )
            version = (
                self._default_resume_version(session)
                if use_default
                else session.get(ResumeVersionModel, resume_version_id)
            )
            if version is None:
                raise EntityNotFoundError("Finalized resume version was not found.")
            self._validate_bindable_version(
                session, version, application_id=application.id
            )
            current = session.scalar(
                select(ApplicationResumeBindingModel).where(
                    ApplicationResumeBindingModel.application_id == application.id,
                    ApplicationResumeBindingModel.status == "active",
                )
            )
            if current is not None and current.resume_version_id == version.id:
                return self._view(session, application)
            binding_id = str(uuid4())
            binding = ApplicationResumeBindingModel(
                id=binding_id,
                application_id=application.id,
                resume_id=version.resume_id,
                resume_version_id=version.id,
                status="active",
                source=source,
                reason=reason.strip()[:500],
                version=1,
                replaced_by_binding_id=None,
                created_at=now,
                updated_at=now,
                replaced_at=None,
                locked_at=None,
            )
            if current is not None:
                current.status = "replaced"
                current.replaced_at = now
                current.updated_at = now
                current.version += 1
                session.flush()
            session.add(binding)
            session.flush()
            if current is not None:
                current.replaced_by_binding_id = binding_id
                session.flush()
            if application.current_status != ApplicationStatus.READY_TO_APPLY.value:
                self._append_event(
                    session,
                    application,
                    event_type="application_status_changed",
                    target=ApplicationStatus.READY_TO_APPLY,
                    occurred_at=now,
                    note="A finalized resume version was bound to this application.",
                    source=source,
                    idempotency_key=command_id,
                )
            else:
                self._append_event(
                    session,
                    application,
                    event_type="application_resume_rebound",
                    target=ApplicationStatus.READY_TO_APPLY,
                    occurred_at=now,
                    note="The active resume binding was replaced.",
                    source=source,
                    idempotency_key=command_id,
                )
            self._advance(application, now)
            session.commit()
            return self._view(session, application)

    def get_default_resume(self) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.scalar(select(ResumeDefaultModel))
            if row is None:
                return None
            return self._resume_default_view(session, row)

    def set_default_resume(
        self, *, resume_id: str, expected_version: int | None
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            resume = session.get(ResumeModel, resume_id)
            if resume is None:
                raise EntityNotFoundError("Resume series was not found.")
            if resume.scope != "library" or resume.retired_at is not None:
                raise CareerDomainError(
                    "Only an active library resume can be the default.",
                    code="default_resume_library_required",
                )
            self._latest_finalized_resume_version(session, resume.id)
            row = session.scalar(select(ResumeDefaultModel))
            if row is None:
                row = ResumeDefaultModel(
                    id=str(uuid4()),
                    resume_id=resume.id,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                if expected_version is None or row.version != expected_version:
                    raise VersionConflictError("Default resume changed after it was loaded.")
                if row.resume_id != resume.id:
                    row.resume_id = resume.id
                    row.version += 1
                    row.updated_at = now
            session.commit()
            return self._resume_default_view(session, row)

    def submit_application(
        self,
        application_id: str,
        *,
        expected_version: int,
        resume_version_id: str,
        occurred_at: datetime,
        note: str,
        command_id: str,
        source: str = "user",
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            application = self._application(session, application_id)
            if self._command_exists(session, application.id, command_id):
                return self._view(session, application)
            self._expect_version(application, expected_version)
            ensure_transition(
                ApplicationStatus(application.current_status), ApplicationStatus.SUBMITTED
            )
            binding = session.scalar(
                select(ApplicationResumeBindingModel).where(
                    ApplicationResumeBindingModel.application_id == application.id,
                    ApplicationResumeBindingModel.status == "active",
                )
            )
            if binding is None:
                raise CareerDomainError(
                    "A finalized resume must be bound before submission.",
                    code="application_resume_binding_required",
                )
            if binding.resume_version_id != resume_version_id:
                raise CareerDomainError(
                    "The confirmed resume version does not match the active binding.",
                    code="application_resume_confirmation_mismatch",
                )
            version = session.get(ResumeVersionModel, binding.resume_version_id)
            self._validate_bindable_version(
                session, version, application_id=application.id
            )
            self._snapshot_resume_version(session, application, version, now)
            binding.status = "locked"
            binding.locked_at = now
            binding.updated_at = now
            binding.version += 1
            self._append_event(
                session,
                application,
                event_type=event_type_for(ApplicationStatus.SUBMITTED),
                target=ApplicationStatus.SUBMITTED,
                occurred_at=occurred_at,
                note=note,
                source=source,
                idempotency_key=command_id,
            )
            self._advance(application, now)
            session.commit()
            return self._view(session, application)

    def add_event(
        self,
        application_id: str,
        *,
        expected_version: int,
        target_status: ApplicationStatus,
        occurred_at: datetime,
        note: str,
        command_id: str,
        source: str = "user",
        proposal_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            application = self._application(session, application_id)
            if self._command_exists(session, application.id, command_id):
                return self._view(session, application)
            self._expect_version(application, expected_version)
            self._require_dedicated_lifecycle_command(target_status)
            ensure_transition(ApplicationStatus(application.current_status), target_status)
            self._append_event(
                session,
                application,
                event_type=event_type_for(target_status),
                target=target_status,
                occurred_at=occurred_at,
                note=note,
                source=source,
                idempotency_key=command_id,
                proposal_id=proposal_id,
            )
            self._advance(application, now)
            session.commit()
            return self._view(session, application)

    def correct_event(
        self,
        application_id: str,
        event_id: str,
        *,
        expected_version: int,
        occurred_at: datetime,
        note: str,
        command_id: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            application = self._application(session, application_id)
            if self._command_exists(session, application.id, command_id):
                return self._view(session, application)
            self._expect_version(application, expected_version)
            original = session.get(ApplicationEventModel, event_id)
            if original is None or original.application_id != application.id:
                raise EntityNotFoundError("Application event was not found.")
            if original.event_type in {"application_created", "event_corrected"}:
                raise CareerDomainError(
                    "This event cannot be corrected.", code="application_event_not_correctable"
                )
            superseded = session.scalar(
                select(ApplicationEventModel.id).where(
                    ApplicationEventModel.supersedes_event_id == original.id
                )
            )
            if superseded is not None:
                raise CareerDomainError(
                    "The event already has a correction.", code="application_event_superseded"
                )
            self._append_event(
                session,
                application,
                event_type="event_corrected",
                target=ApplicationStatus(original.to_status),
                occurred_at=occurred_at,
                note=note,
                source="user",
                idempotency_key=command_id,
                from_status=original.from_status,
                supersedes_event_id=original.id,
                update_projection=False,
            )
            self._advance(application, now, update_status=False)
            session.commit()
            return self._view(session, application)

    def archive_application(
        self,
        application_id: str,
        *,
        expected_version: int,
        note: str,
        command_id: str,
    ) -> dict[str, Any]:
        return self.add_event(
            application_id,
            expected_version=expected_version,
            target_status=ApplicationStatus.ARCHIVED,
            occurred_at=datetime.now(UTC),
            note=note,
            command_id=command_id,
        )

    def propose_event(
        self,
        application_id: str,
        *,
        proposed_status: ApplicationStatus,
        occurred_at: datetime,
        note: str,
        source: str,
        source_ref: str | None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            existing = self._proposal_by_source(session, source=source, source_ref=source_ref)
            if existing is not None:
                return self._existing_proposal_view(session, existing, application_id)
            application = self._application(session, application_id)
            ensure_transition(ApplicationStatus(application.current_status), proposed_status)
            proposal = ApplicationEventProposalModel(
                id=str(uuid4()),
                application_id=application.id,
                proposed_status=proposed_status.value,
                occurred_at=occurred_at,
                note=note.strip(),
                source=source,
                source_ref=source_ref,
                status=ProposalStatus.PENDING.value,
                version=1,
                resolution_reason=None,
                created_at=now,
                resolved_at=None,
            )
            session.add(proposal)
            session.flush()
            task = ensure_review_task(
                session,
                task_type="application_event_proposal",
                entity_type="application_event_proposal",
                entity_id=proposal.id,
                title=(
                    f"确认申请进度：{application.company_name_snapshot} · "
                    f"{application.job_title_snapshot}"
                ),
                summary=proposal.note,
                source_type=source,
                priority=30,
                now=now,
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = self._proposal_by_source(session, source=source, source_ref=source_ref)
                if existing is None:
                    raise
                return self._existing_proposal_view(session, existing, application_id)
            return self._proposal_view(session, proposal, application, task)

    @staticmethod
    def _proposal_by_source(
        session: Session, *, source: str, source_ref: str | None
    ) -> ApplicationEventProposalModel | None:
        if not source_ref:
            return None
        return session.scalar(
            select(ApplicationEventProposalModel).where(
                ApplicationEventProposalModel.source == source,
                ApplicationEventProposalModel.source_ref == source_ref,
            )
        )

    def _existing_proposal_view(
        self,
        session: Session,
        proposal: ApplicationEventProposalModel,
        application_id: str,
    ) -> dict[str, Any]:
        if proposal.application_id != application_id:
            raise CareerDomainError(
                "The connector source event is already associated with another application.",
                code="proposal_source_conflict",
            )
        application = self._application(session, proposal.application_id)
        task = session.scalar(
            select(ReviewTaskModel).where(
                ReviewTaskModel.entity_type == "application_event_proposal",
                ReviewTaskModel.entity_id == proposal.id,
            )
        )
        if task is None:
            raise CareerDomainError(
                "The proposal review task is missing.", code="application_projection_invalid"
            )
        return self._proposal_view(session, proposal, application, task)

    def list_review_tasks(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            tasks = session.scalars(
                select(ReviewTaskModel)
                .where(ReviewTaskModel.task_type == "application_event_proposal")
                .order_by(ReviewTaskModel.created_at.desc())
            ).all()
            result = []
            for task in tasks:
                proposal = session.get(ApplicationEventProposalModel, task.entity_id)
                application = session.get(ApplicationModel, proposal.application_id)
                result.append(self._proposal_view(session, proposal, application, task))
            return result

    def resolve_proposal(
        self,
        proposal_id: str,
        *,
        expected_version: int,
        application_expected_version: int,
        resolution: str,
        reason: str,
        command_id: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            proposal = session.get(ApplicationEventProposalModel, proposal_id)
            if proposal is None:
                raise EntityNotFoundError("Application event proposal was not found.")
            application = self._application(session, proposal.application_id)
            task = session.scalar(
                select(ReviewTaskModel).where(ReviewTaskModel.entity_id == proposal.id)
            )
            if proposal.status != ProposalStatus.PENDING.value:
                if proposal.status == resolution:
                    return self._proposal_view(session, proposal, application, task)
                raise CareerDomainError(
                    "The proposal has already been resolved.", code="proposal_already_resolved"
                )
            if proposal.version != expected_version:
                raise VersionConflictError("Proposal changed after it was loaded.")
            if resolution == ProposalStatus.CONFIRMED.value:
                if self._command_exists(session, application.id, command_id):
                    return self._proposal_view(session, proposal, application, task)
                self._expect_version(application, application_expected_version)
                target = ApplicationStatus(proposal.proposed_status)
                self._require_dedicated_lifecycle_command(target)
                ensure_transition(ApplicationStatus(application.current_status), target)
                self._append_event(
                    session,
                    application,
                    event_type=event_type_for(target),
                    target=target,
                    occurred_at=proposal.occurred_at,
                    note=proposal.note,
                    source=proposal.source,
                    idempotency_key=command_id,
                    proposal_id=proposal.id,
                )
                self._advance(application, now)
            elif resolution != ProposalStatus.REJECTED.value:
                raise CareerDomainError(
                    "Unsupported proposal resolution.", code="invalid_resolution"
                )
            proposal.status = resolution
            proposal.version += 1
            proposal.resolution_reason = reason.strip()
            proposal.resolved_at = now
            set_review_resolution(
                task,
                now=now,
                resolution=resolution,
                reason=reason.strip(),
            )
            session.commit()
            return self._proposal_view(session, proposal, application, task)

    @staticmethod
    def _require_dedicated_lifecycle_command(target: ApplicationStatus) -> None:
        if target == ApplicationStatus.READY_TO_APPLY:
            raise CareerDomainError(
                "Ready-to-apply status is created only by binding a finalized resume.",
                code="application_resume_binding_required",
            )
        if target == ApplicationStatus.SUBMITTED:
            raise CareerDomainError(
                "Submitted status is created only by confirming the bound resume version.",
                code="application_submission_confirmation_required",
            )

    def _snapshot_resume_version(
        self,
        session: Session,
        application: ApplicationModel,
        version: ResumeVersionModel,
        now: datetime,
    ) -> None:
        draft = (
            session.get(MaterialDraftModel, version.material_draft_id)
            if version.material_draft_id is not None
            else None
        )
        export = session.scalar(
            select(MaterialExportModel)
            .where(
                MaterialExportModel.resume_version_id == version.id,
                MaterialExportModel.format == "docx",
                MaterialExportModel.text_layer_ok == 1,
                MaterialExportModel.render_ok == 1,
            )
            .order_by(MaterialExportModel.created_at.desc())
        )
        if export is None:
            export = session.scalar(
                select(MaterialExportModel)
                .where(
                    MaterialExportModel.resume_version_id == version.id,
                    MaterialExportModel.text_layer_ok == 1,
                    MaterialExportModel.render_ok == 1,
                )
                .order_by(MaterialExportModel.created_at.desc())
            )
        if export is None:
            raise CareerDomainError(
                "The bound resume version has no verified export.",
                code="application_resume_export_required",
            )
        session.add(
            ApplicationMaterialSnapshotModel(
                id=str(uuid4()),
                application_id=application.id,
                material_draft_id=draft.id if draft is not None else None,
                resume_version_id=version.id,
                material_type=draft.material_type if draft is not None else "resume",
                title=version.title,
                rendered_text=version.rendered_text,
                content_hash=version.content_hash,
                fact_set_hash=version.fact_set_hash,
                export_id=export.id,
                export_sha256=export.sha256,
                export_relative_path=export.relative_path,
                created_at=now,
            )
        )

    def _append_event(
        self,
        session: Session,
        application: ApplicationModel,
        *,
        event_type: str,
        target: ApplicationStatus,
        occurred_at: datetime,
        note: str,
        source: str,
        idempotency_key: str,
        from_status: str | None = None,
        proposal_id: str | None = None,
        supersedes_event_id: str | None = None,
        update_projection: bool = True,
    ) -> ApplicationEventModel:
        last = session.scalar(
            select(ApplicationEventModel)
            .where(ApplicationEventModel.application_id == application.id)
            .order_by(ApplicationEventModel.sequence_number.desc())
        )
        event = ApplicationEventModel(
            id=str(uuid4()),
            application_id=application.id,
            sequence_number=1 if last is None else last.sequence_number + 1,
            event_type=event_type,
            from_status=application.current_status if from_status is None else from_status,
            to_status=target.value,
            occurred_at=self._aware(occurred_at),
            note=note.strip(),
            source=source,
            proposal_id=proposal_id,
            supersedes_event_id=supersedes_event_id,
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
        )
        if event_type == "application_created":
            event.from_status = None
        session.add(event)
        if update_projection:
            application.current_status = target.value
            if target == ApplicationStatus.ARCHIVED:
                application.archived_at = datetime.now(UTC)
            if target in {
                ApplicationStatus.OFFER,
                ApplicationStatus.REJECTED,
                ApplicationStatus.ARCHIVED,
            }:
                SqlAlchemyApplicationGateway._retire_application_resumes(
                    session, application.id, datetime.now(UTC)
                )
        return event

    @staticmethod
    def _advance(
        application: ApplicationModel, now: datetime, *, update_status: bool = True
    ) -> None:
        del update_status
        application.version += 1
        application.updated_at = now

    @staticmethod
    def _expect_version(application: ApplicationModel, expected_version: int) -> None:
        if application.version != expected_version:
            raise VersionConflictError("Application changed after it was loaded.")

    @staticmethod
    def _command_exists(session: Session, application_id: str, command_id: str) -> bool:
        return (
            session.scalar(
                select(ApplicationEventModel.id).where(
                    ApplicationEventModel.application_id == application_id,
                    ApplicationEventModel.idempotency_key == command_id,
                )
            )
            is not None
        )

    @staticmethod
    def _application(session: Session, application_id: str) -> ApplicationModel:
        application = session.get(ApplicationModel, application_id)
        if application is None:
            raise EntityNotFoundError("Application was not found.")
        return application

    @staticmethod
    def _link_mail_to_application(session: Session, application: ApplicationModel) -> None:
        now = datetime.now(UTC)
        analyses = session.scalars(select(MailIntelligenceAnalysisModel).where(
            MailIntelligenceAnalysisModel.job_post_id == application.job_post_id,
            MailIntelligenceAnalysisModel.application_id.is_(None),
        )).all()
        for analysis in analyses:
            analysis.application_id = application.id
            analysis.create_record_recommended = 0
            analysis.updated_at = now
            create_items = session.scalars(
                select(MailIntelligenceItemModel).where(
                    MailIntelligenceItemModel.analysis_id == analysis.id,
                    MailIntelligenceItemModel.item_type == "create_application",
                    MailIntelligenceItemModel.status == "pending",
                )
            ).all()
            for item in create_items:
                item.status = "confirmed"
                item.version += 1
                item.resolution_reason = "已从该邮件建立正式申请档案。"
                item.resolved_at = now
                task = session.scalar(
                    select(ReviewTaskModel).where(
                        ReviewTaskModel.entity_type == "mail_intelligence_item",
                        ReviewTaskModel.entity_id == item.id,
                    )
                )
                if task is not None:
                    set_review_resolution(
                        task,
                        now=now,
                        resolution="confirmed",
                        reason=item.resolution_reason,
                    )

    @staticmethod
    def _validate_bindable_version(
        session: Session,
        version: ResumeVersionModel | None,
        *,
        application_id: str | None = None,
    ) -> None:
        if version is None or version.status != "final" or version.finalized_at is None:
            raise CareerDomainError(
                "Only a finalized resume version can be bound.",
                code="application_resume_version_not_final",
            )
        resume = session.get(ResumeModel, version.resume_id)
        if resume is None:
            raise EntityNotFoundError("Resume series was not found.")
        if resume.scope == "library" and resume.retired_at is not None:
            raise CareerDomainError(
                "Archived library resumes cannot be used for new bindings.",
                code="application_resume_retired",
            )
        if resume.scope == "application" and (
            application_id is None or resume.application_id != application_id
        ):
            raise CareerDomainError(
                "A job resume can only be used by its owning application.",
                code="application_resume_scope_mismatch",
            )
        export = session.scalar(
            select(MaterialExportModel.id).where(
                MaterialExportModel.resume_version_id == version.id,
                MaterialExportModel.text_layer_ok == 1,
                MaterialExportModel.render_ok == 1,
            )
        )
        if export is None:
            raise CareerDomainError(
                "The finalized resume version must have a verified export.",
                code="application_resume_export_required",
            )

    def _latest_finalized_resume_version(
        self, session: Session, resume_id: str
    ) -> ResumeVersionModel:
        version = session.scalar(
            select(ResumeVersionModel)
            .where(
                ResumeVersionModel.resume_id == resume_id,
                ResumeVersionModel.status == "final",
            )
            .order_by(
                ResumeVersionModel.finalized_at.desc(),
                ResumeVersionModel.version_number.desc(),
            )
        )
        if version is None:
            raise CareerDomainError(
                "The selected resume series has no finalized version.",
                code="default_resume_finalized_version_required",
            )
        resume = session.get(ResumeModel, resume_id)
        if (
            resume is None
            or resume.scope != "library"
            or resume.retired_at is not None
        ):
            raise CareerDomainError(
                "The default resume must be an active library resume.",
                code="default_resume_library_required",
            )
        self._validate_bindable_version(session, version)
        return version

    @staticmethod
    def _retire_application_resumes(
        session: Session, application_id: str, now: datetime
    ) -> None:
        rows = session.scalars(
            select(ResumeModel).where(
                ResumeModel.scope == "application",
                ResumeModel.application_id == application_id,
                ResumeModel.retired_at.is_(None),
            )
        ).all()
        for resume in rows:
            resume.retired_at = now
            resume.updated_at = now

    def _default_resume_version(self, session: Session) -> ResumeVersionModel:
        row = session.scalar(select(ResumeDefaultModel))
        if row is None:
            raise CareerDomainError(
                "No default resume is configured.",
                code="default_resume_required",
            )
        return self._latest_finalized_resume_version(session, row.resume_id)

    def _resume_default_view(
        self, session: Session, row: ResumeDefaultModel
    ) -> dict[str, Any]:
        resume = session.get(ResumeModel, row.resume_id)
        version = self._latest_finalized_resume_version(session, row.resume_id)
        material_count = session.scalar(
            select(func.count())
            .select_from(MaterialDraftModel)
            .where(MaterialDraftModel.resume_id == resume.id)
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
            "latest_version": self._resume_version_summary(version),
            "latest_finalized_version": self._resume_version_summary(version),
            "is_default": True,
            "default_version": row.version,
            "docx_export": self._export_view(
                session.scalar(
                    select(MaterialExportModel)
                    .where(
                        MaterialExportModel.resume_version_id == version.id,
                        MaterialExportModel.format == "docx",
                    )
                    .order_by(MaterialExportModel.created_at.desc())
                )
            ),
            "created_at": self._utc(resume.created_at),
            "updated_at": self._utc(resume.updated_at),
        }

    def _view(self, session: Session, application: ApplicationModel) -> dict[str, Any]:
        result = self._summary(session, application)
        events = session.scalars(
            select(ApplicationEventModel)
            .where(ApplicationEventModel.application_id == application.id)
            .order_by(ApplicationEventModel.sequence_number)
        ).all()
        superseded_ids = {item.supersedes_event_id for item in events if item.supersedes_event_id}
        snapshots = session.scalars(
            select(ApplicationMaterialSnapshotModel).where(
                ApplicationMaterialSnapshotModel.application_id == application.id
            )
        ).all()
        proposals = session.scalars(
            select(ApplicationEventProposalModel)
            .where(ApplicationEventProposalModel.application_id == application.id)
            .order_by(ApplicationEventProposalModel.created_at.desc())
        ).all()
        available = session.execute(
            select(ResumeVersionModel, ResumeModel)
            .join(ResumeModel, ResumeModel.id == ResumeVersionModel.resume_id)
            .where(
                ResumeVersionModel.status == "final",
                (
                    (
                        (ResumeModel.scope == "library")
                        & ResumeModel.retired_at.is_(None)
                    )
                    | (
                        (ResumeModel.scope == "application")
                        & (ResumeModel.application_id == application.id)
                        & ResumeModel.retired_at.is_(None)
                    )
                ),
            )
            .order_by(
                ResumeVersionModel.finalized_at.desc(),
                ResumeVersionModel.version_number.desc(),
            )
        ).all()
        bindings = session.scalars(
            select(ApplicationResumeBindingModel)
            .where(ApplicationResumeBindingModel.application_id == application.id)
            .order_by(ApplicationResumeBindingModel.created_at)
        ).all()
        binding_views = [self._binding_view(session, item) for item in bindings]
        mail_analyses = session.scalars(
            select(MailIntelligenceAnalysisModel)
            .where(MailIntelligenceAnalysisModel.application_id == application.id)
            .order_by(MailIntelligenceAnalysisModel.created_at.desc())
        ).all()
        result.update(
            {
                "events": [self._event_view(item, item.id in superseded_ids) for item in events],
                "material_snapshots": [self._snapshot_view(item) for item in snapshots],
                "proposals": [self._proposal_plain(item) for item in proposals],
                "resume_bindings": binding_views,
                "active_resume_binding": next(
                    (
                        item
                        for item in reversed(binding_views)
                        if item["status"] in {"active", "locked"}
                    ),
                    None,
                ),
                "available_final_materials": [
                    {
                        "id": item.material_draft_id or item.id,
                        "resume_id": item.resume_id,
                        "resume_version_id": item.id,
                        "version_number": item.version_number,
                        "name": resume.name,
                        "title": item.title,
                        "material_type": (
                            session.get(MaterialDraftModel, item.material_draft_id).material_type
                            if item.material_draft_id is not None
                            else "resume"
                        ),
                        "scope": resume.scope,
                        "application_id": resume.application_id,
                        "finalized_at": self._utc(item.finalized_at),
                    }
                    for item, resume in available
                ],
                "mail_evidence": [self._mail_evidence_view(session, item) for item in mail_analyses],
            }
        )
        return result

    def _binding_view(
        self, session: Session, binding: ApplicationResumeBindingModel
    ) -> dict[str, Any]:
        resume = session.get(ResumeModel, binding.resume_id)
        version = session.get(ResumeVersionModel, binding.resume_version_id)
        return {
            "id": binding.id,
            "application_id": binding.application_id,
            "resume_id": binding.resume_id,
            "resume_name": resume.name,
            "resume_version_id": binding.resume_version_id,
            "version_number": version.version_number,
            "version_title": version.title,
            "status": binding.status,
            "source": binding.source,
            "reason": binding.reason,
            "version": binding.version,
            "replaced_by_binding_id": binding.replaced_by_binding_id,
            "created_at": self._utc(binding.created_at),
            "updated_at": self._utc(binding.updated_at),
            "replaced_at": self._utc(binding.replaced_at),
            "locked_at": self._utc(binding.locked_at),
        }

    def _mail_evidence_view(
        self, session: Session, analysis: MailIntelligenceAnalysisModel
    ) -> dict[str, Any]:
        message = session.get(MailMessageModel, analysis.mail_message_id)
        items = session.scalars(
            select(MailIntelligenceItemModel)
            .where(MailIntelligenceItemModel.analysis_id == analysis.id)
            .order_by(MailIntelligenceItemModel.created_at, MailIntelligenceItemModel.id)
        ).all()
        return {
            "analysis_id": analysis.id,
            "message_id": analysis.mail_message_id,
            "agent_run_id": analysis.agent_run_id,
            "sender": message.sender if message else "",
            "subject": message.subject if message else "",
            "sent_at": self._utc(message.sent_at) if message else None,
            "message_type": analysis.message_type,
            "summary": analysis.summary,
            "match_confidence": analysis.match_confidence,
            "items": [
                {
                    "id": item.id, "item_type": item.item_type, "category": item.category,
                    "title": item.title, "details": item.details, "evidence": item.evidence,
                    "occurred_at": self._utc(item.occurred_at),
                    "scheduled_at": self._utc(item.scheduled_at), "status": item.status,
                }
                for item in items
            ],
            "created_at": self._utc(analysis.created_at),
        }

    def _summary(self, session: Session, application: ApplicationModel) -> dict[str, Any]:
        material_count = len(
            session.scalars(
                select(ApplicationMaterialSnapshotModel).where(
                    ApplicationMaterialSnapshotModel.application_id == application.id
                )
            ).all()
        )
        return {
            "id": application.id,
            "job_post_id": application.job_post_id,
            "job_post_version_id": application.job_post_version_id,
            "job_title": application.job_title_snapshot,
            "company": application.company_name_snapshot,
            "job_content_hash": application.job_content_hash,
            "current_status": self._project_status(session, application.id),
            "version": application.version,
            "material_count": material_count,
            "created_at": self._utc(application.created_at),
            "updated_at": self._utc(application.updated_at),
            "archived_at": self._utc(application.archived_at),
        }

    @staticmethod
    def _project_status(session: Session, application_id: str) -> str:
        events = session.scalars(
            select(ApplicationEventModel)
            .where(ApplicationEventModel.application_id == application_id)
            .order_by(ApplicationEventModel.sequence_number)
        ).all()
        corrections = {
            item.supersedes_event_id: item
            for item in events
            if item.event_type == "event_corrected" and item.supersedes_event_id
        }
        effective = [
            corrections.get(item.id, item)
            for item in events
            if item.event_type != "event_corrected"
        ]
        if not effective:
            raise CareerDomainError(
                "Application event stream is empty.", code="application_projection_invalid"
            )
        return effective[-1].to_status

    def _proposal_view(
        self,
        session: Session,
        proposal: ApplicationEventProposalModel,
        application: ApplicationModel,
        task: ReviewTaskModel,
    ) -> dict[str, Any]:
        del session
        return {
            **self._proposal_plain(proposal),
            "task_id": task.id,
            "task_status": task.status,
            "task_version": task.version,
            "resolution": task.resolution,
            "resolution_reason": task.resolution_reason,
            "resolved_by": task.resolved_by,
            "application_version": application.version,
            "job_title": application.job_title_snapshot,
            "company": application.company_name_snapshot,
        }

    def _proposal_plain(self, proposal: ApplicationEventProposalModel) -> dict[str, Any]:
        return {
            "id": proposal.id,
            "application_id": proposal.application_id,
            "proposed_status": proposal.proposed_status,
            "occurred_at": self._utc(proposal.occurred_at),
            "note": proposal.note,
            "source": proposal.source,
            "source_ref": proposal.source_ref,
            "status": proposal.status,
            "version": proposal.version,
            "resolution_reason": proposal.resolution_reason,
            "created_at": self._utc(proposal.created_at),
            "resolved_at": self._utc(proposal.resolved_at),
        }

    def _event_view(self, event: ApplicationEventModel, superseded: bool) -> dict[str, Any]:
        return {
            "id": event.id,
            "sequence_number": event.sequence_number,
            "event_type": event.event_type,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "occurred_at": self._utc(event.occurred_at),
            "note": event.note,
            "source": event.source,
            "proposal_id": event.proposal_id,
            "supersedes_event_id": event.supersedes_event_id,
            "superseded": superseded,
            "created_at": self._utc(event.created_at),
        }

    def _snapshot_view(self, item: ApplicationMaterialSnapshotModel) -> dict[str, Any]:
        return {
            "id": item.id,
            "material_draft_id": item.material_draft_id,
            "resume_version_id": item.resume_version_id,
            "material_type": item.material_type,
            "title": item.title,
            "rendered_text": item.rendered_text,
            "content_hash": item.content_hash,
            "fact_set_hash": item.fact_set_hash,
            "export_id": item.export_id,
            "export_sha256": item.export_sha256,
            "created_at": self._utc(item.created_at),
        }

    @staticmethod
    def _export_view(item: MaterialExportModel | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            "id": item.id,
            "format": item.format,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
            "page_count": item.page_count,
            "text_layer_ok": bool(item.text_layer_ok),
            "render_ok": bool(item.render_ok),
            "extracted_text_hash": item.extracted_text_hash,
            "created_at": SqlAlchemyApplicationGateway._utc(item.created_at),
            "download_url": f"/api/v1/material-exports/{item.id}/download",
            "preview_url": f"/api/v1/material-exports/{item.id}/preview",
        }

    @staticmethod
    def _resume_version_summary(version: ResumeVersionModel) -> dict[str, Any]:
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
            "created_at": SqlAlchemyApplicationGateway._utc(version.created_at),
            "finalized_at": SqlAlchemyApplicationGateway._utc(version.finalized_at),
        }

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
