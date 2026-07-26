"""Job pool import and analysis use cases."""

from __future__ import annotations

from typing import Any, Protocol

from career_console.application.ports.job_extractor import JobExtractor
from career_console.application.ports.job_gateway import JobGateway


class ParsedDocumentLike(Protocol):
    file_name: str
    media_type: str
    text: str


class DocumentParserLike(Protocol):
    def parse(
        self, *, file_name: str, content: bytes, media_type: str | None = None
    ) -> ParsedDocumentLike: ...

    def parse_pasted_text(self, *, name: str, text: str) -> ParsedDocumentLike: ...


class JobApplicationService:
    def __init__(
        self, *, gateway: JobGateway, extractor: JobExtractor, parser: DocumentParserLike
    ) -> None:
        self.gateway = gateway
        self.extractor = extractor
        self.parser = parser

    def import_text(
        self,
        *,
        name: str,
        text: str,
        source_url: str | None = None,
        opportunity_id: str | None = None,
        mail_analysis_id: str | None = None,
    ) -> dict[str, Any]:
        parsed = self.parser.parse_pasted_text(
            name="fetched-job" if source_url else name,
            text=text,
        )
        return self._save(
            name=name,
            text=parsed.text,
            source_url=source_url,
            source_type="url" if source_url else "paste",
            opportunity_id=opportunity_id,
            mail_analysis_id=mail_analysis_id,
        )

    def import_connector(
        self, *, name: str, text: str, source_url: str, source_type: str
    ) -> dict[str, Any]:
        """Import validated content from a deterministic external connector."""
        parsed = self.parser.parse_pasted_text(name=name, text=text)
        return self._save(
            name=name,
            text=parsed.text,
            source_url=source_url,
            source_type=source_type,
        )

    def import_file(
        self,
        *,
        file_name: str,
        content: bytes,
        media_type: str | None,
        opportunity_id: str | None = None,
        mail_analysis_id: str | None = None,
    ) -> dict[str, Any]:
        parsed = self.parser.parse(file_name=file_name, content=content, media_type=media_type)
        return self._save(
            name=parsed.file_name,
            text=parsed.text,
            source_url=None,
            source_type="file",
            opportunity_id=opportunity_id,
            mail_analysis_id=mail_analysis_id,
        )

    def _save(
        self,
        *,
        name: str,
        text: str,
        source_url: str | None,
        source_type: str,
        opportunity_id: str | None = None,
        mail_analysis_id: str | None = None,
    ) -> dict[str, Any]:
        extracted = self.extractor.extract(text)
        return self.gateway.import_job(
            name=name,
            text=text,
            source_url=source_url,
            source_type=source_type,
            extracted=extracted,
            extractor_name=self.extractor.name,
            extractor_schema_version=self.extractor.schema_version,
            opportunity_id=opportunity_id,
            mail_analysis_id=mail_analysis_id,
        )
