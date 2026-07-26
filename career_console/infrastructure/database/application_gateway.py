"""SQLAlchemy adapter for applications, immutable events, and review proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
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
    CompanyModel,
    JobPostModel,
    JobPostVersionModel,
    MailIntelligenceAnalysisModel,
    MailIntelligenceItemModel,
    MailMessageModel,
    MaterialDraftModel,
    MaterialExportModel,
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
                select(ApplicationModel).where(ApplicationModel.job_post_id == job_post_id)
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
            company = session.get(CompanyModel, post.company_id)
            has_final = session.scalar(
                select(MaterialDraftModel.id).where(
                    MaterialDraftModel.job_post_id == post.id,
                    MaterialDraftModel.status == "final",
                )
            )
            initial_status = (
                ApplicationStatus.READY_TO_APPLY
                if has_final is not None
                else ApplicationStatus.PREPARING_MATERIALS
            )
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
                target=initial_status,
                occurred_at=now,
                note=(
                    "Final material is available."
                    if initial_status == ApplicationStatus.READY_TO_APPLY
                    else "Application materials must be prepared before submission."
                ),
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

    def submit_application(
        self,
        application_id: str,
        *,
        expected_version: int,
        material_ids: list[str],
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
            ensure_transition(
                ApplicationStatus(application.current_status), ApplicationStatus.SUBMITTED
            )
            unique_ids = list(dict.fromkeys(material_ids))
            if not unique_ids:
                raise CareerDomainError(
                    "At least one Final material must be selected for submission.",
                    code="submission_material_required",
                )
            for material_id in unique_ids:
                self._snapshot_material(session, application, material_id, now)
            self._append_event(
                session,
                application,
                event_type=event_type_for(ApplicationStatus.SUBMITTED),
                target=ApplicationStatus.SUBMITTED,
                occurred_at=occurred_at,
                note=note,
                source="user",
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

    def _snapshot_material(
        self, session: Session, application: ApplicationModel, material_id: str, now: datetime
    ) -> None:
        draft = session.get(MaterialDraftModel, material_id)
        if draft is None:
            raise EntityNotFoundError("Selected material was not found.")
        if draft.job_post_id != application.job_post_id:
            raise CareerDomainError(
                "Submission material belongs to another job post.",
                code="application_material_job_mismatch",
            )
        if draft.status != "final":
            raise CareerDomainError(
                "Only Final materials can be submitted.", code="application_material_not_final"
            )
        version = session.scalar(
            select(ResumeVersionModel)
            .where(ResumeVersionModel.material_draft_id == draft.id)
            .order_by(ResumeVersionModel.version_number.desc())
        )
        export = session.scalar(
            select(MaterialExportModel).where(MaterialExportModel.resume_version_id == version.id)
        )
        session.add(
            ApplicationMaterialSnapshotModel(
                id=str(uuid4()),
                application_id=application.id,
                material_draft_id=draft.id,
                resume_version_id=version.id,
                material_type=draft.material_type,
                title=version.title,
                rendered_text=version.rendered_text,
                content_hash=version.content_hash,
                fact_set_hash=version.fact_set_hash,
                export_id=None if export is None else export.id,
                export_sha256=None if export is None else export.sha256,
                export_relative_path=None if export is None else export.relative_path,
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
        analyses = session.scalars(select(MailIntelligenceAnalysisModel).where(
            MailIntelligenceAnalysisModel.job_post_id == application.job_post_id,
            MailIntelligenceAnalysisModel.application_id.is_(None),
        )).all()
        for analysis in analyses:
            analysis.application_id = application.id
            analysis.updated_at = datetime.now(UTC)

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
        available = session.scalars(
            select(MaterialDraftModel).where(
                MaterialDraftModel.job_post_id == application.job_post_id,
                MaterialDraftModel.status == "final",
            )
        ).all()
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
                "available_final_materials": [
                    {
                        "id": item.id,
                        "name": session.get(ResumeModel, item.resume_id).name,
                        "material_type": item.material_type,
                    }
                    for item in available
                ],
                "mail_evidence": [self._mail_evidence_view(session, item) for item in mail_analyses],
            }
        )
        return result

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
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
