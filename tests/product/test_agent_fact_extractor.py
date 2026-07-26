from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from career_console.application.services import ProfileApplicationService
from career_console.domain.common.errors import CareerDomainError
from career_console.infrastructure.agents import CareerProfileFactExtractor
from career_console.infrastructure.database import Database
from career_console.infrastructure.database.migrations import upgrade_to_head
from career_console.infrastructure.database.models import AgentRunModel, DocumentModel
from career_console.infrastructure.database.profile_gateway import SqlAlchemyProfileGateway
from career_console.infrastructure.extraction import LocalResumeFactExtractor
from career_console.infrastructure.files import DocumentParser, LocalBlobStore
from career_console.infrastructure.settings import CareerSettings
from career_console.runtime.providers.base import LLMResponse


class FakeProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.kwargs: dict[str, Any] = {}

    def get_default_model(self) -> str:
        return "fake-model"

    async def chat_with_retry(self, **kwargs: Any) -> LLMResponse:
        self.kwargs = kwargs
        return LLMResponse(content=json.dumps(self.payload, ensure_ascii=False))


def test_agent_extractor_has_no_tools_and_validates_evidence() -> None:
    text = "姓名：张三\n技能：Python"
    provider = FakeProvider(
        {
            "schemaVersion": "candidate_fact.v1",
            "facts": [
                {
                    "category": "skill",
                    "fieldKey": "skill",
                    "value": "Python",
                    "evidenceText": "技能：Python",
                    "confidence": 0.95,
                }
            ],
        }
    )
    extractor = CareerProfileFactExtractor(provider)  # type: ignore[arg-type]
    result = extractor.extract(document_id="document-id", text=text)
    assert result[0].value == "Python"
    assert provider.kwargs["tools"] is None
    assert len(provider.kwargs["messages"]) == 2
    assert "<document>" in provider.kwargs["messages"][1]["content"]


def test_agent_extractor_rejects_hallucinated_evidence() -> None:
    provider = FakeProvider(
        {
            "schemaVersion": "candidate_fact.v1",
            "facts": [
                {
                    "category": "award",
                    "fieldKey": "award",
                    "value": "全国一等奖",
                    "evidenceText": "获得全国一等奖",
                    "confidence": 0.8,
                }
            ],
        }
    )
    extractor = CareerProfileFactExtractor(provider)  # type: ignore[arg-type]
    with pytest.raises(CareerDomainError) as caught:
        extractor.extract(document_id="document-id", text="技能：Python")
    assert caught.value.code == "fact_evidence_invalid"


class FailingExtractor:
    name = "failing_test_extractor"
    schema_version = "candidate_fact.v1"

    def extract(self, *, document_id: str, text: str):
        del document_id, text
        raise CareerDomainError("Invalid agent schema", code="fact_extraction_schema_invalid")


def test_failed_agent_run_is_audited_and_can_be_retried_locally(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    upgrade_to_head(settings)
    database = Database(settings)
    gateway = SqlAlchemyProfileGateway(database.session_factory)
    try:
        failing = ProfileApplicationService(
            gateway=gateway,
            parser=DocumentParser(max_bytes=settings.max_document_bytes),
            blob_store=LocalBlobStore(settings.blobs_dir),
            extractor=FailingExtractor(),  # type: ignore[arg-type]
        )
        with pytest.raises(CareerDomainError):
            failing.import_text(name="resume", text="技能：Python")
        with database.session_factory() as session:
            document = session.scalar(select(DocumentModel))
            run = session.scalar(select(AgentRunModel))
            assert document is not None and document.parse_status == "extraction_failed"
            assert run is not None and run.status == "failed"
            assert run.error_code == "fact_extraction_schema_invalid"

        retry = ProfileApplicationService(
            gateway=gateway,
            parser=DocumentParser(max_bytes=settings.max_document_bytes),
            blob_store=LocalBlobStore(settings.blobs_dir),
            extractor=LocalResumeFactExtractor(),
        )
        result = retry.import_text(name="resume", text="技能：Python")
        assert result["proposed_fact_count"] == 1
        assert result["duplicate"] is False
        with database.session_factory() as session:
            runs = session.scalars(select(AgentRunModel)).all()
            assert [run.status for run in runs] == ["failed", "succeeded"]
    finally:
        database.close()
