"""Profile and fact library use-case orchestration."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Protocol

from career_console.application.ports import (
    FactExtractor,
    ProfileFactReviser,
    ProfileGateway,
)
from career_console.domain.common.errors import CareerDomainError


class ParsedDocumentLike(Protocol):
    file_name: str
    media_type: str
    text: str
    parser_name: str


class DocumentParserLike(Protocol):
    def parse(
        self, *, file_name: str, content: bytes, media_type: str | None = None
    ) -> ParsedDocumentLike: ...

    def parse_pasted_text(self, *, name: str, text: str) -> ParsedDocumentLike: ...


class StoredBlobLike(Protocol):
    sha256: str
    relative_path: str
    size_bytes: int


class BlobStoreLike(Protocol):
    def put(self, content: bytes) -> StoredBlobLike: ...


class ProfileApplicationService:
    def __init__(
        self,
        *,
        gateway: ProfileGateway,
        parser: DocumentParserLike,
        blob_store: BlobStoreLike,
        extractor: FactExtractor,
        reviser: ProfileFactReviser,
    ) -> None:
        self.gateway = gateway
        self.parser = parser
        self.blob_store = blob_store
        self.extractor = extractor
        self.reviser = reviser

    def import_file(
        self, *, file_name: str, content: bytes, media_type: str | None
    ) -> dict[str, Any]:
        parsed = self.parser.parse(file_name=file_name, content=content, media_type=media_type)
        return self._save(parsed=parsed, raw_content=content)

    def import_text(self, *, name: str, text: str) -> dict[str, Any]:
        parsed = self.parser.parse_pasted_text(name=name, text=text)
        return self._save(parsed=parsed, raw_content=parsed.text.encode("utf-8"))

    def reprocess_document(self, *, document_id: str) -> dict[str, Any]:
        document = self.gateway.get_document_for_reprocessing(document_id=document_id)
        started = perf_counter()
        try:
            facts = self.extractor.extract(
                document_id=document["sha256"],
                text=document["text"],
            )
        except CareerDomainError as exc:
            self.gateway.save_import(
                file_name=document["file_name"],
                media_type=document["media_type"],
                sha256=document["sha256"],
                size_bytes=document["size_bytes"],
                blob_relative_path=document["blob_relative_path"],
                text=document["text"],
                parser_name=document["parser_name"],
                extractor_name=self.extractor.name,
                extractor_schema_version=self.extractor.schema_version,
                facts=[],
                run_status="failed",
                error_code=exc.code,
                replace_document_facts=True,
                **self._audit_metadata(started),
            )
            raise
        return self.gateway.save_import(
            file_name=document["file_name"],
            media_type=document["media_type"],
            sha256=document["sha256"],
            size_bytes=document["size_bytes"],
            blob_relative_path=document["blob_relative_path"],
            text=document["text"],
            parser_name=document["parser_name"],
            extractor_name=self.extractor.name,
            extractor_schema_version=self.extractor.schema_version,
            facts=facts,
            replace_document_facts=True,
            **self._audit_metadata(started),
        )

    def _save(self, *, parsed: ParsedDocumentLike, raw_content: bytes) -> dict[str, Any]:
        blob = self.blob_store.put(raw_content)
        completed = self.gateway.get_completed_import(
            sha256=blob.sha256,
            extractor_name=self.extractor.name,
            extractor_schema_version=self.extractor.schema_version,
        )
        if completed is not None:
            return completed
        started = perf_counter()
        try:
            facts = self.extractor.extract(document_id=blob.sha256, text=parsed.text)
        except CareerDomainError as exc:
            audit = self._audit_metadata(started)
            self.gateway.save_import(
                file_name=parsed.file_name,
                media_type=parsed.media_type,
                sha256=blob.sha256,
                size_bytes=blob.size_bytes,
                blob_relative_path=blob.relative_path,
                text=parsed.text,
                parser_name=parsed.parser_name,
                extractor_name=self.extractor.name,
                extractor_schema_version=self.extractor.schema_version,
                facts=[],
                run_status="failed",
                error_code=exc.code,
                **audit,
            )
            raise
        audit = self._audit_metadata(started)
        return self.gateway.save_import(
            file_name=parsed.file_name,
            media_type=parsed.media_type,
            sha256=blob.sha256,
            size_bytes=blob.size_bytes,
            blob_relative_path=blob.relative_path,
            text=parsed.text,
            parser_name=parsed.parser_name,
            extractor_name=self.extractor.name,
            extractor_schema_version=self.extractor.schema_version,
            facts=facts,
            **audit,
        )

    def _audit_metadata(self, started: float) -> dict[str, Any]:
        provider = getattr(self.extractor, "provider", None)
        usage = getattr(self.extractor, "last_usage", {}) or {}
        return {
            "provider": type(provider).__name__ if provider is not None else "local",
            "model": getattr(self.extractor, "model", None),
            "prompt_version": getattr(
                self.extractor, "prompt_version", "profile_fact_extraction.v1"
            ),
            "skill_version": getattr(self.extractor, "skill_version", None),
            "duration_ms": max(0, round((perf_counter() - started) * 1000)),
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "retry_count": int(getattr(self.extractor, "last_retry_count", 0)),
        }

    def revise_fact(
        self,
        *,
        fact_id: str,
        expected_version: int,
        instruction: str,
    ) -> dict[str, Any]:
        context = self.gateway.get_fact_for_revision(fact_id=fact_id)
        started = perf_counter()
        try:
            revision = self.reviser.revise(
                fact_id=fact_id,
                category=context["category"],
                field_key=context["field_key"],
                current_value=context["value"],
                instruction=instruction,
                evidence_texts=tuple(
                    source["evidence_text"] for source in context["sources"]
                ),
            )
        except CareerDomainError as exc:
            self.gateway.save_agent_revision(
                fact_id=fact_id,
                expected_version=expected_version,
                instruction=instruction,
                revised_value=None,
                rationale=None,
                run_status="failed",
                error_code=exc.code,
                **self._revision_audit_metadata(started),
            )
            raise
        result = self.gateway.save_agent_revision(
            fact_id=fact_id,
            expected_version=expected_version,
            instruction=instruction,
            revised_value=revision.value,
            rationale=revision.rationale,
            run_status="succeeded",
            **self._revision_audit_metadata(started),
        )
        if result is None:
            raise RuntimeError("Successful profile revision did not return a fact.")
        return result

    def _revision_audit_metadata(self, started: float) -> dict[str, Any]:
        provider = getattr(self.reviser, "provider", None)
        usage = getattr(self.reviser, "last_usage", {}) or {}
        return {
            "reviser_name": self.reviser.name,
            "reviser_schema_version": self.reviser.schema_version,
            "provider": type(provider).__name__ if provider is not None else "local",
            "model": getattr(self.reviser, "model", None),
            "prompt_version": getattr(
                self.reviser, "prompt_version", "profile_fact_revision.v1"
            ),
            "skill_version": getattr(self.reviser, "skill_version", None),
            "duration_ms": max(0, round((perf_counter() - started) * 1000)),
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "retry_count": int(getattr(self.reviser, "last_retry_count", 0)),
        }
