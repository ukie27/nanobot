"""Persistence port for profile, document, and fact use cases."""

from __future__ import annotations

from typing import Any, Protocol

from career_console.application.ports.fact_extractor import ExtractedFact


class ProfileGateway(Protocol):
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
        duration_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]: ...

    def get_profile(self) -> dict[str, Any]: ...

    def list_documents(self) -> list[dict[str, Any]]: ...

    def list_facts(self, *, status: str | None = None) -> list[dict[str, Any]]: ...

    def add_manual_fact(
        self,
        *,
        category: str,
        field_key: str,
        value: str,
        source_note: str,
    ) -> dict[str, Any]: ...

    def change_fact(
        self,
        *,
        fact_id: str,
        expected_version: int,
        action: str,
        value: str | None = None,
        reason: str,
    ) -> dict[str, Any]: ...

    def batch_confirm(self, *, items: list[tuple[str, int]]) -> list[dict[str, Any]]: ...
