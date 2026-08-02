"""SQLAlchemy profile and fact persistence adapter."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from career_console.application.ports.fact_extractor import ExtractedFact
from career_console.domain.common.errors import CareerDomainError
from career_console.domain.profile.entities import CandidateFact, FactCategory, FactStatus
from career_console.domain.profile.privacy import contains_contact_information
from career_console.infrastructure.database.models import (
    AgentRunModel,
    BlobModel,
    CandidateFactModel,
    CandidateProfileModel,
    DocumentModel,
    FactRevisionModel,
    FactSourceModel,
    ProfileChangeEventModel,
    ReviewBundleItemModel,
    ReviewTaskModel,
)
from career_console.infrastructure.database.review_runtime import (
    create_agent_run,
    refresh_bundle_resolution,
    set_review_resolution,
)

PROFILE_ID = "00000000-0000-4000-8000-000000000001"


def ensure_profile_model(session: Session, now: datetime) -> CandidateProfileModel:
    """Create the singleton profile atomically across API and scheduler workers."""
    session.execute(
        sqlite_insert(CandidateProfileModel)
        .values(
            id=PROFILE_ID,
            display_name=None,
            timezone="Asia/Shanghai",
            version=1,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=[CandidateProfileModel.id])
    )
    profile = session.get(CandidateProfileModel, PROFILE_ID)
    if profile is None:
        raise RuntimeError("Candidate profile could not be initialized.")
    return profile


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

    def get_completed_import(
        self,
        *,
        sha256: str,
        extractor_name: str,
        extractor_schema_version: str,
    ) -> dict[str, Any] | None:
        with self._session_factory() as session:
            document = session.scalar(
                select(DocumentModel).where(DocumentModel.sha256 == sha256)
            )
            if document is None:
                return None
            latest_run = self._latest_extraction_run(session, document.id)
            if (
                latest_run is None
                or latest_run.status != "succeeded"
                or latest_run.implementation != extractor_name
                or latest_run.schema_version != extractor_schema_version
            ):
                return None
            result = self._document_view(session, document, duplicate=True)
            result["proposed_fact_count"] = 0
            result["maintained_fact_count"] = 0
            result["extracted_candidate_count"] = latest_run.output_count
            return result

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
        provider: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        skill_version: str | None = None,
        duration_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        retry_count: int = 0,
        replace_document_facts: bool = False,
    ) -> dict[str, Any]:
        for fact in facts:
            if any(
                contains_contact_information(value)
                for value in (fact.title or "", fact.value, fact.evidence_text)
            ):
                raise CareerDomainError(
                    "Contact information cannot be stored as a career fact.",
                    code="contact_information_not_allowed_in_fact",
                )
        now = datetime.now(UTC)
        with self._session_factory() as session:
            existing = session.scalar(select(DocumentModel).where(DocumentModel.sha256 == sha256))
            if existing is not None:
                latest_run = self._latest_extraction_run(session, existing.id)
                current_extraction_completed = (
                    latest_run is not None
                    and latest_run.status == "succeeded"
                    and latest_run.implementation == extractor_name
                    and latest_run.schema_version == extractor_schema_version
                )
                if current_extraction_completed and not replace_document_facts:
                    result = self._document_view(session, existing, duplicate=True)
                    result["proposed_fact_count"] = 0
                    result["maintained_fact_count"] = 0
                    result["extracted_candidate_count"] = latest_run.output_count
                    return result
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
                if run_status == "succeeded":
                    document.parse_status = "parsed"
                elif not replace_document_facts:
                    document.parse_status = "extraction_failed"
            # The persistence models intentionally have no ORM relationships;
            # flush principals explicitly so SQLite foreign keys never depend
            # on mapper ordering heuristics.
            session.flush()
            prior_document_fact_ids = set(
                session.scalars(
                    select(FactSourceModel.fact_id).where(
                        FactSourceModel.document_id == document.id
                    )
                ).all()
            )
            output_payload = [
                {
                    "category": item.category.value,
                    "field_key": item.field_key,
                    "value": item.value,
                    "evidence_text": item.evidence_text,
                    "confidence": item.confidence,
                }
                for item in facts
            ]
            output_hash = hashlib.sha256(
                json.dumps(
                    output_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            run = create_agent_run(
                session,
                task_type="profile_fact_extraction",
                implementation=extractor_name,
                schema_version=extractor_schema_version,
                document_id=document.id,
                status=run_status,
                output_count=len(facts),
                error_code=error_code,
                created_at=now,
                finished_at=now,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                skill_version=skill_version,
                input_entity_type="document",
                input_entity_id=document.id,
                input_revision=sha256,
                input_hash=sha256,
                output_hash=output_hash,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                retry_count=retry_count,
                sensitivity="sensitive",
            )
            if run_status != "succeeded":
                session.commit()
                result = self._document_view(session, document, duplicate=False)
                result["proposed_fact_count"] = 0
                result["maintained_fact_count"] = 0
                result["extracted_candidate_count"] = 0
                return result
            maintained_count = 0
            maintained_fact_ids: set[str] = set()
            display_name: str | None = None
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
                        status=FactStatus.CONFIRMED.value,
                        confidence=extracted.confidence,
                        version=1,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(existing_fact)
                    session.flush()
                    self._add_profile_change(
                        session,
                        existing_fact,
                        event_type="fact_maintained",
                        changed_fields={"status": FactStatus.CONFIRMED.value},
                        impact_scopes=[
                            "profile",
                            "job_fit",
                            "material_strategy",
                            "career_strategy",
                        ],
                        source="agent_extraction",
                        now=now,
                    )
                    maintained_count += 1
                    display_name = display_name or self._display_name(
                        self._to_domain(existing_fact)
                    )
                elif existing_fact.status == FactStatus.PROPOSED.value:
                    previous_version = existing_fact.version
                    session.add(
                        FactRevisionModel(
                            id=str(uuid4()),
                            fact_id=existing_fact.id,
                            revision_number=previous_version + 1,
                            previous_value=existing_fact.value,
                            new_value=existing_fact.value,
                            previous_status=FactStatus.PROPOSED.value,
                            new_status=FactStatus.CONFIRMED.value,
                            reason="新版档案维护流程自动写入正式档案",
                            changed_by="system",
                            created_at=now,
                        )
                    )
                    existing_fact.status = FactStatus.CONFIRMED.value
                    existing_fact.version = previous_version + 1
                    existing_fact.updated_at = now
                    task = session.scalar(
                        select(ReviewTaskModel).where(
                            ReviewTaskModel.entity_id == existing_fact.id,
                            ReviewTaskModel.task_type == "candidate_fact_review",
                            ReviewTaskModel.status == "open",
                        )
                    )
                    if task is not None:
                        set_review_resolution(
                            task,
                            now=now,
                            resolution="confirmed",
                            reason="新版档案维护流程已直接写入正式档案。",
                            resolved_by="system",
                        )
                        for bundle_id in session.scalars(
                            select(ReviewBundleItemModel.bundle_id).where(
                                ReviewBundleItemModel.review_task_id == task.id
                            )
                        ).all():
                            refresh_bundle_resolution(session, bundle_id, now=now)
                    self._add_profile_change(
                        session,
                        existing_fact,
                        event_type="fact_maintained",
                        changed_fields={
                            "previous_status": FactStatus.PROPOSED.value,
                            "status": FactStatus.CONFIRMED.value,
                        },
                        impact_scopes=[
                            "profile",
                            "job_fit",
                            "material_strategy",
                            "career_strategy",
                        ],
                        source="system",
                        now=now,
                        revision=existing_fact.version,
                    )
                    maintained_count += 1
                    display_name = display_name or self._display_name(
                        self._to_domain(existing_fact)
                    )
                maintained_fact_ids.add(existing_fact.id)
                evidence_text = extracted.evidence_text[:2000]
                existing_source = session.scalar(
                    select(FactSourceModel).where(
                        FactSourceModel.fact_id == existing_fact.id,
                        FactSourceModel.document_id == document.id,
                        FactSourceModel.source_type == "document_extraction",
                        FactSourceModel.evidence_text == evidence_text,
                    )
                )
                if existing_source is None:
                    session.add(
                        FactSourceModel(
                            id=str(uuid4()),
                            fact_id=existing_fact.id,
                            document_id=document.id,
                            source_type="document_extraction",
                            evidence_text=evidence_text,
                            created_at=now,
                        )
                    )
            self._supersede_prior_extraction_proposals(
                session,
                document_id=document.id,
                current_run_id=run.id,
                now=now,
                skip_fact_ids=maintained_fact_ids,
            )
            superseded_count = 0
            if replace_document_facts:
                superseded_count = self._supersede_prior_document_facts(
                    session,
                    document_id=document.id,
                    prior_fact_ids=prior_document_fact_ids,
                    current_fact_ids=maintained_fact_ids,
                    now=now,
                )
            if maintained_count:
                profile.version += 1
                profile.updated_at = now
                if display_name:
                    profile.display_name = display_name
            if superseded_count:
                profile.version += 1
                profile.updated_at = now
            session.commit()
            result = self._document_view(session, document, duplicate=False)
            result["proposed_fact_count"] = 0
            result["maintained_fact_count"] = (
                len(maintained_fact_ids) if replace_document_facts else maintained_count
            )
            result["extracted_candidate_count"] = len(facts)
            result["superseded_fact_count"] = superseded_count
            return result

    @staticmethod
    def _supersede_prior_document_facts(
        session: Session,
        *,
        document_id: str,
        prior_fact_ids: set[str],
        current_fact_ids: set[str],
        now: datetime,
    ) -> int:
        superseded = 0
        for fact_id in prior_fact_ids - current_fact_ids:
            fact = session.get(CandidateFactModel, fact_id)
            if fact is None or fact.status == FactStatus.REJECTED.value:
                continue
            sources = session.scalars(
                select(FactSourceModel).where(FactSourceModel.fact_id == fact_id)
            ).all()
            if any(source.document_id != document_id for source in sources):
                continue
            previous_status = fact.status
            next_version = fact.version + 1
            session.add(
                FactRevisionModel(
                    id=str(uuid4()),
                    fact_id=fact.id,
                    revision_number=next_version,
                    previous_value=fact.value,
                    new_value=fact.value,
                    previous_status=previous_status,
                    new_status=FactStatus.REJECTED.value,
                    reason="由同一资料的最新 Agent 整理结果替代",
                    changed_by="system",
                    created_at=now,
                )
            )
            fact.status = FactStatus.REJECTED.value
            fact.version = next_version
            fact.updated_at = now
            SqlAlchemyProfileGateway._add_profile_change(
                session,
                fact,
                event_type="fact_superseded",
                changed_fields={
                    "previous_status": previous_status,
                    "status": FactStatus.REJECTED.value,
                    "document_id": document_id,
                },
                impact_scopes=[
                    "profile",
                    "job_fit",
                    "material_strategy",
                    "career_strategy",
                ],
                source="agent_reprocessing",
                now=now,
                revision=next_version,
            )
            superseded += 1
        return superseded

    @staticmethod
    def _supersede_prior_extraction_proposals(
        session: Session,
        *,
        document_id: str,
        current_run_id: str,
        now: datetime,
        skip_fact_ids: set[str],
    ) -> None:
        tasks = session.scalars(
            select(ReviewTaskModel)
            .join(AgentRunModel, AgentRunModel.id == ReviewTaskModel.agent_run_id)
            .where(
                AgentRunModel.document_id == document_id,
                AgentRunModel.task_type == "profile_fact_extraction",
                AgentRunModel.id != current_run_id,
                ReviewTaskModel.task_type == "candidate_fact_review",
                ReviewTaskModel.entity_type == "candidate_fact",
                ReviewTaskModel.status == "open",
            )
        ).all()
        bundle_ids: set[str] = set()
        for task in tasks:
            fact = session.get(CandidateFactModel, task.entity_id)
            if (
                fact is None
                or fact.id in skip_fact_ids
                or fact.status != FactStatus.PROPOSED.value
            ):
                continue
            session.add(
                FactRevisionModel(
                    id=str(uuid4()),
                    fact_id=fact.id,
                    revision_number=fact.version,
                    previous_value=fact.value,
                    new_value=fact.value,
                    previous_status=fact.status,
                    new_status=FactStatus.REJECTED.value,
                    reason="由新版档案提取结果替代",
                    changed_by="system",
                    created_at=now,
                )
            )
            fact.status = FactStatus.REJECTED.value
            fact.version += 1
            fact.updated_at = now
            set_review_resolution(
                task,
                now=now,
                resolution="rejected",
                reason="同一文档已由新版档案提取 Skill 重新处理。",
                resolved_by="system",
            )
            bundle_ids.update(
                session.scalars(
                    select(ReviewBundleItemModel.bundle_id).where(
                        ReviewBundleItemModel.review_task_id == task.id
                    )
                ).all()
            )
        for bundle_id in bundle_ids:
            refresh_bundle_resolution(session, bundle_id, now=now)

    @staticmethod
    def _latest_extraction_run(
        session: Session, document_id: str
    ) -> AgentRunModel | None:
        return session.scalar(
            select(AgentRunModel)
            .where(
                AgentRunModel.document_id == document_id,
                AgentRunModel.task_type == "profile_fact_extraction",
            )
            .order_by(AgentRunModel.created_at.desc(), AgentRunModel.id.desc())
            .limit(1)
        )

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

    def get_document_for_reprocessing(self, *, document_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            document = session.get(DocumentModel, document_id)
            if document is None:
                raise EntityNotFoundError("Imported document was not found.")
            blob = session.get(BlobModel, document.blob_id)
            if blob is None:
                raise EntityNotFoundError("Imported document content was not found.")
            return {
                "id": document.id,
                "file_name": document.file_name,
                "media_type": document.media_type,
                "sha256": document.sha256,
                "size_bytes": document.size_bytes,
                "blob_relative_path": blob.relative_path,
                "text": document.extracted_text,
                "parser_name": document.parser_name,
            }

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
        self._reject_contact_information(value, source_note)
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
                status=FactStatus.CONFIRMED.value,
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
            self._add_profile_change(
                session,
                fact,
                event_type="fact_maintained",
                changed_fields={"status": FactStatus.CONFIRMED.value},
                impact_scopes=[
                    "profile",
                    "job_fit",
                    "material_strategy",
                    "career_strategy",
                ],
                source="user",
                now=now,
            )
            profile.version += 1
            profile.updated_at = now
            display_name = self._display_name(self._to_domain(fact))
            if display_name:
                profile.display_name = display_name
            session.commit()
            return self._fact_view(session, fact)

    def get_fact_for_revision(self, *, fact_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            fact = session.get(CandidateFactModel, fact_id)
            if fact is None:
                raise EntityNotFoundError("Candidate fact was not found.")
            if fact.status != FactStatus.CONFIRMED.value:
                raise CareerDomainError(
                    "Only maintained profile facts can be revised.",
                    code="profile_fact_revision_status_invalid",
                )
            return self._fact_view(session, fact)

    def save_agent_revision(
        self,
        *,
        fact_id: str,
        expected_version: int,
        instruction: str,
        revised_value: str | None,
        rationale: str | None,
        reviser_name: str,
        reviser_schema_version: str,
        run_status: str,
        error_code: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        skill_version: str | None = None,
        duration_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        input_hash = hashlib.sha256(
            json.dumps(
                {
                    "fact_id": fact_id,
                    "expected_version": expected_version,
                    "instruction": instruction,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        output_hash = (
            hashlib.sha256((revised_value or "").encode("utf-8")).hexdigest()
            if revised_value is not None
            else None
        )
        with self._session_factory() as session:
            run = create_agent_run(
                session,
                task_type="profile_fact_revision",
                implementation=reviser_name,
                schema_version=reviser_schema_version,
                status=run_status,
                output_count=1 if run_status == "succeeded" else 0,
                error_code=error_code,
                created_at=now,
                finished_at=now,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                skill_version=skill_version,
                input_entity_type="candidate_fact",
                input_entity_id=fact_id,
                input_revision=str(expected_version),
                input_hash=input_hash,
                output_hash=output_hash,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                retry_count=retry_count,
                sensitivity="sensitive",
            )
            if run_status != "succeeded":
                session.commit()
                return None
            fact = session.get(CandidateFactModel, fact_id)
            validation_error: CareerDomainError | None = None
            if fact is None:
                validation_error = EntityNotFoundError("Candidate fact was not found.")
            elif fact.status != FactStatus.CONFIRMED.value:
                validation_error = CareerDomainError(
                    "Only maintained profile facts can be revised.",
                    code="profile_fact_revision_status_invalid",
                )
            elif fact.version != expected_version:
                validation_error = VersionConflictError(
                    f"Fact changed after it was loaded; current version is {fact.version}."
                )
            normalized_value = self._normalize(revised_value or "")
            if validation_error is None and not normalized_value:
                validation_error = CareerDomainError(
                    "Fact value cannot be empty.", code="empty_fact_value"
                )
            if validation_error is None:
                try:
                    self._reject_contact_information(revised_value or "")
                except CareerDomainError as exc:
                    validation_error = exc
            if (
                validation_error is None
                and normalized_value == self._normalize(fact.value)
            ):
                validation_error = CareerDomainError(
                    "档案内容没有发生变化。", code="profile_revision_unchanged"
                )
            if validation_error is None:
                duplicate = session.scalar(
                    select(CandidateFactModel).where(
                        CandidateFactModel.id != fact_id,
                        CandidateFactModel.profile_id == fact.profile_id,
                        CandidateFactModel.category == fact.category,
                        CandidateFactModel.field_key == fact.field_key,
                        CandidateFactModel.normalized_value == normalized_value,
                    )
                )
                if duplicate is not None:
                    validation_error = DuplicateFactError(
                        "An equivalent fact already exists."
                    )
            if validation_error is not None:
                run.status = "failed"
                run.output_count = 0
                run.error_code = validation_error.code
                session.commit()
                raise validation_error
            previous_value = fact.value
            fact.value = (revised_value or "").strip()
            fact.normalized_value = normalized_value
            fact.version += 1
            fact.updated_at = now
            session.add(
                FactRevisionModel(
                    id=str(uuid4()),
                    fact_id=fact.id,
                    revision_number=fact.version,
                    previous_value=previous_value,
                    new_value=fact.value,
                    previous_status=FactStatus.CONFIRMED.value,
                    new_status=FactStatus.CONFIRMED.value,
                    reason=(rationale or instruction).strip()[:500],
                    changed_by="agent",
                    created_at=now,
                )
            )
            self._add_profile_change(
                session,
                fact,
                event_type="fact_agent_revised",
                changed_fields={
                    "previous_value": previous_value,
                    "value": fact.value,
                    "instruction_hash": hashlib.sha256(
                        instruction.encode("utf-8")
                    ).hexdigest(),
                },
                impact_scopes=[
                    "profile",
                    "job_fit",
                    "material_strategy",
                    "career_strategy",
                ],
                source="agent",
                now=now,
                revision=fact.version,
            )
            profile = session.get(CandidateProfileModel, fact.profile_id)
            if profile is not None:
                profile.version += 1
                profile.updated_at = now
                display_name = self._display_name(self._to_domain(fact))
                if display_name:
                    profile.display_name = display_name
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
                self._reject_contact_information(value or "")
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
                    set_review_resolution(
                        task,
                        now=now,
                        resolution=after.status.value,
                        reason=reason,
                    )
                else:
                    set_review_resolution(
                        task,
                        now=now,
                        resolution=None,
                        reason=reason,
                        reopen=True,
                    )
                bundle_ids = session.scalars(
                    select(ReviewBundleItemModel.bundle_id).where(
                        ReviewBundleItemModel.review_task_id == task.id
                    )
                ).all()
                for bundle_id in bundle_ids:
                    refresh_bundle_resolution(session, bundle_id, now=now)
            display_name = self._display_name(after)
            if after.status is FactStatus.CONFIRMED and display_name:
                profile = session.get(CandidateProfileModel, after.profile_id)
                if profile is not None:
                    profile.display_name = display_name
                    profile.version += 1
                    profile.updated_at = now
            self._add_profile_change(
                session, row, event_type=f"fact_{action}",
                changed_fields={
                    "previous_status": before.status.value, "status": after.status.value,
                    "previous_value": before.value, "value": after.value,
                },
                impact_scopes=(
                    ["profile", "job_fit", "material_strategy", "career_strategy"]
                    if after.status is FactStatus.CONFIRMED else ["profile_review"]
                ),
                source="user", now=now, revision=after.version,
            )
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
                    set_review_resolution(
                        task,
                        now=now,
                        resolution="confirmed",
                        reason="Batch confirmed by user",
                    )
                    bundle_ids = session.scalars(
                        select(ReviewBundleItemModel.bundle_id).where(
                            ReviewBundleItemModel.review_task_id == task.id
                        )
                    ).all()
                    for bundle_id in bundle_ids:
                        refresh_bundle_resolution(session, bundle_id, now=now)
                display_name = self._display_name(after)
                if display_name:
                    profile = session.get(CandidateProfileModel, after.profile_id)
                    if profile is not None:
                        profile.display_name = display_name
                        profile.version += 1
                        profile.updated_at = now
                self._add_profile_change(
                    session, row, event_type="fact_confirm",
                    changed_fields={"previous_status": before.status.value, "status": "confirmed"},
                    impact_scopes=["profile", "job_fit", "material_strategy", "career_strategy"],
                    source="user", now=now, revision=after.version,
                )
            session.commit()
            return [self._fact_view(session, row) for row, _before, _after in changes]

    def batch_reject(
        self,
        *,
        items: list[tuple[str, int]],
        reason: str,
        changed_by: str = "user",
    ) -> list[dict[str, Any]]:
        """Reject proposed facts atomically while retaining their audit trail."""
        if len({fact_id for fact_id, _version in items}) != len(items):
            raise CareerDomainError("Batch contains duplicate fact IDs.", code="invalid_batch")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise CareerDomainError("Batch rejection requires a reason.", code="reason_required")
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
                if before.status is not FactStatus.PROPOSED:
                    raise CareerDomainError(
                        f"Fact {fact_id} is not proposed and cannot be batch rejected.",
                        code="invalid_fact_status",
                    )
                changes.append((row, before, before.reject(now=now)))
            for row, before, after in changes:
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
                        reason=normalized_reason[:500],
                        changed_by=changed_by.strip()[:32] or "user",
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
                    set_review_resolution(
                        task,
                        now=now,
                        resolution="rejected",
                        reason=normalized_reason,
                        resolved_by=changed_by,
                    )
                    bundle_ids = session.scalars(
                        select(ReviewBundleItemModel.bundle_id).where(
                            ReviewBundleItemModel.review_task_id == task.id
                        )
                    ).all()
                    for bundle_id in bundle_ids:
                        refresh_bundle_resolution(session, bundle_id, now=now)
                self._add_profile_change(
                    session,
                    row,
                    event_type="fact_reject",
                    changed_fields={
                        "previous_status": before.status.value,
                        "status": "rejected",
                    },
                    impact_scopes=["profile_review"],
                    source=changed_by,
                    now=now,
                    revision=after.version,
                )
            session.commit()
            return [self._fact_view(session, row) for row, _before, _after in changes]

    @staticmethod
    def _ensure_profile(session: Session, now: datetime) -> CandidateProfileModel:
        return ensure_profile_model(session, now)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _add_profile_change(
        session: Session, fact: CandidateFactModel, *, event_type: str,
        changed_fields: dict[str, Any], impact_scopes: list[str], source: str,
        now: datetime, revision: int | None = None,
    ) -> None:
        session.add(ProfileChangeEventModel(
            id=str(uuid4()), profile_id=fact.profile_id, event_type=event_type,
            entity_type="candidate_fact", entity_id=fact.id,
            entity_revision=revision or fact.version,
            changed_fields_json=json.dumps(changed_fields, ensure_ascii=False),
            impact_scopes_json=json.dumps(impact_scopes, ensure_ascii=False),
            source=source, occurred_at=now,
        ))

    @staticmethod
    def _display_name(fact: CandidateFact) -> str | None:
        if fact.field_key == "name":
            return fact.value
        if fact.category is not FactCategory.BASIC:
            return None
        for line in fact.value.splitlines():
            match = re.match(r"^\s*(?:姓名|name)\s*[：:]\s*(.+?)\s*$", line, re.IGNORECASE)
            if match:
                return match.group(1)[:200]
        return None

    @staticmethod
    def _reject_contact_information(*values: str) -> None:
        if any(contains_contact_information(value) for value in values):
            raise CareerDomainError(
                "Contact information cannot be stored as a career fact.",
                code="contact_information_not_allowed_in_fact",
            )

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
