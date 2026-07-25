"""SQLAlchemy profile and fact persistence adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from nanobot.career.application.ports.fact_extractor import ExtractedFact
from nanobot.career.domain.common.errors import CareerDomainError
from nanobot.career.domain.profile.entities import CandidateFact, FactCategory, FactStatus
from nanobot.career.infrastructure.database.models import (
    AgentRunModel,
    BlobModel,
    CandidateFactModel,
    CandidateProfileModel,
    DocumentModel,
    FactRevisionModel,
    FactSourceModel,
    ReviewTaskModel,
)

PROFILE_ID = "00000000-0000-4000-8000-000000000001"


class EntityNotFoundError(CareerDomainError):
    status_code = 404
    code = "entity_not_found"


class VersionConflictError(CareerDomainError):
    status_code = 409
    code = "version_conflict"


class DuplicateFactError(CareerDomainError):
    status_code = 409
    code = "duplicate_fact"


class SqlAlchemyProfileGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save_import(
        self,
        *,
        file_name: str,
        media_type: str,
        sha256: str,
        size_bytes: int,
        blob_relative_path: str,
        text: str,
        parser_name: str,
        extractor_name: str,
        extractor_schema_version: str,
        facts: list[ExtractedFact],
        run_status: str = "succeeded",
        error_code: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            existing = session.scalar(select(DocumentModel).where(DocumentModel.sha256 == sha256))
            retrying_failed_extraction = (
                existing is not None
                and existing.parse_status == "extraction_failed"
                and run_status == "succeeded"
            )
            if existing is not None and not retrying_failed_extraction:
                return self._document_view(session, existing, duplicate=True)
            profile = self._ensure_profile(session, now)
            if existing is None:
                blob = session.scalar(select(BlobModel).where(BlobModel.sha256 == sha256))
                if blob is None:
                    blob = BlobModel(
                        id=str(uuid4()),
                        sha256=sha256,
                        relative_path=blob_relative_path,
                        size_bytes=size_bytes,
                        created_at=now,
                    )
                    session.add(blob)
                document = DocumentModel(
                    id=str(uuid4()),
                    blob_id=blob.id,
                    file_name=file_name,
                    media_type=media_type,
                    sha256=sha256,
                    size_bytes=size_bytes,
                    parse_status="parsed" if run_status == "succeeded" else "extraction_failed",
                    extracted_text=text,
                    parser_name=parser_name,
                    created_at=now,
                )
                session.add(document)
            else:
                document = existing
                document.parse_status = "parsed"
            # The persistence models intentionally have no ORM relationships;
            # flush principals explicitly so SQLite foreign keys never depend
            # on mapper ordering heuristics.
            session.flush()
            run = AgentRunModel(
                id=str(uuid4()),
                task_type="profile_fact_extraction",
                implementation=extractor_name,
                schema_version=extractor_schema_version,
                document_id=document.id,
                status=run_status,
                output_count=len(facts),
                error_code=error_code,
                created_at=now,
                finished_at=now,
            )
            session.add(run)
            if run_status != "succeeded":
                session.commit()
                return self._document_view(session, document, duplicate=False)
            created_count = 0
            for extracted in facts:
                normalized = self._normalize(extracted.value)
                existing_fact = session.scalar(
                    select(CandidateFactModel).where(
                        CandidateFactModel.profile_id == profile.id,
                        CandidateFactModel.category == extracted.category.value,
                        CandidateFactModel.field_key == extracted.field_key,
                        CandidateFactModel.normalized_value == normalized,
                    )
                )
                if existing_fact is None:
                    existing_fact = CandidateFactModel(
                        id=str(uuid4()),
                        profile_id=profile.id,
                        category=extracted.category.value,
                        field_key=extracted.field_key,
                        value=extracted.value,
                        normalized_value=normalized,
                        status=FactStatus.PROPOSED.value,
                        confidence=extracted.confidence,
                        version=1,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(existing_fact)
                    session.flush()
                    session.add(
                        ReviewTaskModel(
                            id=str(uuid4()),
                            task_type="candidate_fact_review",
                            entity_type="candidate_fact",
                            entity_id=existing_fact.id,
                            status="open",
                            version=1,
                            created_at=now,
                        )
                    )
                    created_count += 1
                session.add(
                    FactSourceModel(
                        id=str(uuid4()),
                        fact_id=existing_fact.id,
                        document_id=document.id,
                        source_type="document_extraction",
                        evidence_text=extracted.evidence_text[:2000],
                        created_at=now,
                    )
                )
            session.commit()
            result = self._document_view(session, document, duplicate=False)
            result["proposed_fact_count"] = created_count
            result["extracted_candidate_count"] = len(facts)
            return result

    def get_profile(self) -> dict[str, Any]:
        with self._session_factory() as session:
            profile = self._ensure_profile(session, datetime.now(UTC))
            session.commit()
            counts = {
                status: len(
                    session.scalars(
                        select(CandidateFactModel).where(
                            CandidateFactModel.profile_id == profile.id,
                            CandidateFactModel.status == status,
                        )
                    ).all()
                )
                for status in ("proposed", "confirmed", "rejected")
            }
            return {
                "id": profile.id,
                "display_name": profile.display_name,
                "timezone": profile.timezone,
                "version": profile.version,
                "fact_counts": counts,
                "created_at": self._utc(profile.created_at),
                "updated_at": self._utc(profile.updated_at),
            }

    def list_documents(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            documents = session.scalars(
                select(DocumentModel).order_by(DocumentModel.created_at.desc())
            ).all()
            return [
                self._document_view(session, document, duplicate=False) for document in documents
            ]

    def list_facts(self, *, status: str | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            query = select(CandidateFactModel).order_by(
                CandidateFactModel.category, CandidateFactModel.created_at.desc()
            )
            if status:
                query = query.where(CandidateFactModel.status == status)
            facts = session.scalars(query).all()
            return [self._fact_view(session, fact) for fact in facts]

    def add_manual_fact(
        self,
        *,
        category: str,
        field_key: str,
        value: str,
        source_note: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        try:
            category_value = FactCategory(category).value
        except ValueError as exc:
            raise CareerDomainError("Unknown fact category.", code="invalid_fact_category") from exc
        normalized = self._normalize(value)
        normalized_field_key = field_key.strip()[:100]
        if not normalized:
            raise CareerDomainError("Fact value cannot be empty.", code="empty_fact_value")
        if not normalized_field_key:
            raise CareerDomainError("Fact field key cannot be empty.", code="invalid_fact_field")
        with self._session_factory() as session:
            profile = self._ensure_profile(session, now)
            duplicate = session.scalar(
                select(CandidateFactModel).where(
                    CandidateFactModel.profile_id == profile.id,
                    CandidateFactModel.category == category_value,
                    CandidateFactModel.field_key == normalized_field_key,
                    CandidateFactModel.normalized_value == normalized,
                )
            )
            if duplicate is not None:
                raise DuplicateFactError("An equivalent fact already exists.")
            fact = CandidateFactModel(
                id=str(uuid4()),
                profile_id=profile.id,
                category=category_value,
                field_key=normalized_field_key,
                value=value.strip(),
                normalized_value=normalized,
                status=FactStatus.PROPOSED.value,
                confidence=None,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(fact)
            session.add(
                FactSourceModel(
                    id=str(uuid4()),
                    fact_id=fact.id,
                    document_id=None,
                    source_type="manual",
                    evidence_text=source_note.strip()[:2000] or "Manually added by user.",
                    created_at=now,
                )
            )
            session.add(
                ReviewTaskModel(
                    id=str(uuid4()),
                    task_type="candidate_fact_review",
                    entity_type="candidate_fact",
                    entity_id=fact.id,
                    status="open",
                    version=1,
                    created_at=now,
                )
            )
            session.commit()
            return self._fact_view(session, fact)

    def change_fact(
        self,
        *,
        fact_id: str,
        expected_version: int,
        action: str,
        value: str | None = None,
        reason: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(CandidateFactModel, fact_id)
            if row is None:
                raise EntityNotFoundError("Candidate fact was not found.")
            if row.version != expected_version:
                raise VersionConflictError(
                    f"Fact changed after it was loaded; current version is {row.version}."
                )
            before = self._to_domain(row)
            if action == "confirm":
                after = before.confirm(now=now)
            elif action == "reject":
                after = before.reject(now=now)
            elif action == "edit":
                after = before.edit(value or "", now=now)
            else:
                raise CareerDomainError("Unsupported fact action.", code="invalid_fact_action")
            if after == before:
                return self._fact_view(session, row)
            duplicate = session.scalar(
                select(CandidateFactModel).where(
                    CandidateFactModel.id != fact_id,
                    CandidateFactModel.profile_id == row.profile_id,
                    CandidateFactModel.category == row.category,
                    CandidateFactModel.field_key == row.field_key,
                    CandidateFactModel.normalized_value == self._normalize(after.value),
                )
            )
            if duplicate is not None:
                raise DuplicateFactError("An equivalent fact already exists.")
            result = session.execute(
                update(CandidateFactModel)
                .where(
                    CandidateFactModel.id == fact_id,
                    CandidateFactModel.version == expected_version,
                )
                .values(
                    value=after.value,
                    normalized_value=self._normalize(after.value),
                    status=after.status.value,
                    version=after.version,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                raise VersionConflictError("Fact was changed concurrently.")
            session.add(
                FactRevisionModel(
                    id=str(uuid4()),
                    fact_id=fact_id,
                    revision_number=after.version,
                    previous_value=before.value,
                    new_value=after.value,
                    previous_status=before.status.value,
                    new_status=after.status.value,
                    reason=reason.strip()[:500] or action,
                    changed_by="user",
                    created_at=now,
                )
            )
            task = session.scalar(
                select(ReviewTaskModel).where(
                    ReviewTaskModel.entity_id == fact_id,
                    ReviewTaskModel.task_type == "candidate_fact_review",
                )
            )
            if task is not None:
                if after.status in {FactStatus.CONFIRMED, FactStatus.REJECTED}:
                    task.status = "resolved"
                    task.resolved_at = now
                else:
                    task.status = "open"
                    task.resolved_at = None
                task.version += 1
            if after.status is FactStatus.CONFIRMED and after.field_key == "name":
                profile = session.get(CandidateProfileModel, after.profile_id)
                if profile is not None:
                    profile.display_name = after.value
                    profile.version += 1
                    profile.updated_at = now
            session.commit()
            refreshed = session.get(CandidateFactModel, fact_id)
            if refreshed is None:
                raise EntityNotFoundError("Candidate fact was not found after update.")
            return self._fact_view(session, refreshed)

    def batch_confirm(self, *, items: list[tuple[str, int]]) -> list[dict[str, Any]]:
        """Confirm facts atomically after validating the complete selection."""
        if len({fact_id for fact_id, _version in items}) != len(items):
            raise CareerDomainError("Batch contains duplicate fact IDs.", code="invalid_batch")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            changes: list[tuple[CandidateFactModel, CandidateFact, CandidateFact]] = []
            for fact_id, expected_version in items:
                row = session.get(CandidateFactModel, fact_id)
                if row is None:
                    raise EntityNotFoundError(f"Candidate fact {fact_id} was not found.")
                if row.version != expected_version:
                    raise VersionConflictError(
                        f"Fact {fact_id} changed after it was loaded; current version is {row.version}."
                    )
                before = self._to_domain(row)
                changes.append((row, before, before.confirm(now=now)))
            for row, before, after in changes:
                if before == after:
                    continue
                row.status = after.status.value
                row.version = after.version
                row.updated_at = now
                session.add(
                    FactRevisionModel(
                        id=str(uuid4()),
                        fact_id=row.id,
                        revision_number=after.version,
                        previous_value=before.value,
                        new_value=after.value,
                        previous_status=before.status.value,
                        new_status=after.status.value,
                        reason="Batch confirmed by user",
                        changed_by="user",
                        created_at=now,
                    )
                )
                task = session.scalar(
                    select(ReviewTaskModel).where(
                        ReviewTaskModel.entity_id == row.id,
                        ReviewTaskModel.task_type == "candidate_fact_review",
                    )
                )
                if task is not None:
                    task.status = "resolved"
                    task.resolved_at = now
                    task.version += 1
                if after.field_key == "name":
                    profile = session.get(CandidateProfileModel, after.profile_id)
                    if profile is not None:
                        profile.display_name = after.value
                        profile.version += 1
                        profile.updated_at = now
            session.commit()
            return [self._fact_view(session, row) for row, _before, _after in changes]

    @staticmethod
    def _ensure_profile(session: Session, now: datetime) -> CandidateProfileModel:
        profile = session.get(CandidateProfileModel, PROFILE_ID)
        if profile is None:
            profile = CandidateProfileModel(
                id=PROFILE_ID,
                display_name=None,
                timezone="Asia/Shanghai",
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
            session.flush()
        return profile

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _to_domain(row: CandidateFactModel) -> CandidateFact:
        return CandidateFact(
            id=row.id,
            profile_id=row.profile_id,
            category=FactCategory(row.category),
            field_key=row.field_key,
            value=row.value,
            status=FactStatus(row.status),
            confidence=row.confidence,
            version=row.version,
            created_at=SqlAlchemyProfileGateway._utc(row.created_at),
            updated_at=SqlAlchemyProfileGateway._utc(row.updated_at),
        )

    @staticmethod
    def _document_view(
        session: Session, document: DocumentModel, *, duplicate: bool
    ) -> dict[str, Any]:
        fact_count = len(
            session.scalars(
                select(FactSourceModel).where(FactSourceModel.document_id == document.id)
            ).all()
        )
        return {
            "id": document.id,
            "file_name": document.file_name,
            "media_type": document.media_type,
            "sha256": document.sha256,
            "size_bytes": document.size_bytes,
            "parse_status": document.parse_status,
            "parser_name": document.parser_name,
            "text_preview": document.extracted_text[:300],
            "fact_source_count": fact_count,
            "duplicate": duplicate,
            "created_at": SqlAlchemyProfileGateway._utc(document.created_at),
        }

    @staticmethod
    def _fact_view(session: Session, fact: CandidateFactModel) -> dict[str, Any]:
        sources = session.scalars(
            select(FactSourceModel)
            .where(FactSourceModel.fact_id == fact.id)
            .order_by(FactSourceModel.created_at)
        ).all()
        revisions = session.scalars(
            select(FactRevisionModel)
            .where(FactRevisionModel.fact_id == fact.id)
            .order_by(FactRevisionModel.revision_number.desc())
        ).all()
        return {
            "id": fact.id,
            "profile_id": fact.profile_id,
            "category": fact.category,
            "field_key": fact.field_key,
            "value": fact.value,
            "status": fact.status,
            "confidence": fact.confidence,
            "version": fact.version,
            "sources": [
                {
                    "id": source.id,
                    "document_id": source.document_id,
                    "source_type": source.source_type,
                    "evidence_text": source.evidence_text,
                    "created_at": SqlAlchemyProfileGateway._utc(source.created_at),
                }
                for source in sources
            ],
            "revisions": [
                {
                    "id": revision.id,
                    "revision_number": revision.revision_number,
                    "previous_value": revision.previous_value,
                    "new_value": revision.new_value,
                    "previous_status": revision.previous_status,
                    "new_status": revision.new_status,
                    "reason": revision.reason,
                    "changed_by": revision.changed_by,
                    "created_at": SqlAlchemyProfileGateway._utc(revision.created_at),
                }
                for revision in revisions
            ],
            "created_at": SqlAlchemyProfileGateway._utc(fact.created_at),
            "updated_at": SqlAlchemyProfileGateway._utc(fact.updated_at),
        }

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
