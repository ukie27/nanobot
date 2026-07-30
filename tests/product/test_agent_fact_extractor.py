from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from career_console.application.services import ProfileApplicationService
from career_console.domain.common.errors import CareerDomainError
from career_console.infrastructure.agents import (
    CareerProfileFactExtractor,
    RuntimeConfiguredProfileFactExtractor,
)
from career_console.infrastructure.database import Database
from career_console.infrastructure.database.migrations import upgrade_to_head
from career_console.infrastructure.database.models import AgentRunModel, DocumentModel
from career_console.infrastructure.database.profile_gateway import SqlAlchemyProfileGateway
from career_console.infrastructure.extraction import LocalResumeFactExtractor
from career_console.infrastructure.files import DocumentParser, LocalBlobStore
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http.app import _create_fact_extractor
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


class AuthenticationFailingProvider:
    def get_default_model(self) -> str:
        return "fake-model"

    async def chat_with_retry(self, **_kwargs: Any) -> LLMResponse:
        return LLMResponse(
            content="Error calling LLM: authentication failed.",
            finish_reason="error",
            error_code="provider_authentication_failed",
        )


def test_agent_extractor_has_no_tools_and_validates_evidence() -> None:
    text = "姓名：张三\n技能：Python"
    provider = FakeProvider(
        {
            "schemaVersion": "candidate_profile_object.v2",
            "objects": [
                {
                    "category": "skill",
                    "objectKey": "skill_profile",
                    "title": "技能画像",
                    "content": "技能：Python",
                    "evidenceTexts": ["技能：Python"],
                    "confidence": 0.95,
                }
            ],
        }
    )
    extractor = CareerProfileFactExtractor(provider)  # type: ignore[arg-type]
    result = extractor.extract(document_id="document-id", text=text)
    assert result[0].value == "技能：Python"
    assert result[0].field_key == "skill_profile"
    assert provider.kwargs["tools"] is None
    assert len(provider.kwargs["messages"]) == 2
    assert "<document>" in provider.kwargs["messages"][1]["content"]


def test_agent_extractor_reports_actionable_provider_authentication_error() -> None:
    extractor = CareerProfileFactExtractor(AuthenticationFailingProvider())  # type: ignore[arg-type]

    with pytest.raises(CareerDomainError) as caught:
        extractor.extract(document_id="document-id", text="技能：Python")

    assert caught.value.code == "fact_extraction_provider_authentication_failed"
    assert "设置 > AI 服务" in caught.value.detail
    assert "API Key" in caught.value.detail


def test_agent_extractor_rejects_hallucinated_evidence() -> None:
    provider = FakeProvider(
        {
            "schemaVersion": "candidate_profile_object.v2",
            "objects": [
                {
                    "category": "award",
                    "objectKey": "award:全国一等奖",
                    "title": "全国一等奖",
                    "content": "获得全国一等奖",
                    "evidenceTexts": ["获得全国一等奖"],
                    "confidence": 0.8,
                }
            ],
        }
    )
    extractor = CareerProfileFactExtractor(provider)  # type: ignore[arg-type]
    with pytest.raises(CareerDomainError) as caught:
        extractor.extract(document_id="document-id", text="技能：Python")
    assert caught.value.code == "fact_evidence_invalid"


def test_agent_extractor_maps_whitespace_variants_to_exact_source_evidence() -> None:
    text = "项 目：求职助手\n技术：P y t h o n、FastAPI\n成果：响应时间降低 30%"
    provider = FakeProvider(
        {
            "schemaVersion": "candidate_profile_object.v2",
            "objects": [
                {
                    "category": "project",
                    "objectKey": "project:求职助手",
                    "title": "求职助手",
                    "content": "求职助手项目",
                    "evidenceTexts": [
                        "项目：求职助手 技术：Python、FastAPI 成果：响应时间降低 30%"
                    ],
                    "confidence": 0.9,
                }
            ],
        }
    )

    facts = CareerProfileFactExtractor(provider).extract(
        document_id="document-id",
        text=text,
    )

    assert facts[0].evidence_texts == (text,)
    assert facts[0].evidence_text == text


def test_agent_extractor_does_not_fuzzy_match_changed_evidence() -> None:
    text = "项目：求职助手\n成果：响应时间降低 30%"
    provider = FakeProvider(
        {
            "schemaVersion": "candidate_profile_object.v2",
            "objects": [
                {
                    "category": "project",
                    "objectKey": "project:求职助手",
                    "title": "求职助手",
                    "content": "求职助手项目",
                    "evidenceTexts": ["项目：求职助手 成果：响应时间降低 40%"],
                    "confidence": 0.9,
                }
            ],
        }
    )

    with pytest.raises(CareerDomainError) as caught:
        CareerProfileFactExtractor(provider).extract(
            document_id="document-id",
            text=text,
        )

    assert caught.value.code == "fact_evidence_invalid"


class FailingExtractor:
    name = "failing_test_extractor"
    schema_version = "candidate_profile_object.v2"

    def extract(self, *, document_id: str, text: str):
        del document_id, text
        raise CareerDomainError("Invalid agent schema", code="fact_extraction_schema_invalid")


class LegacyExtractor:
    name = "local_resume_extractor"
    schema_version = "candidate_fact.v1"

    def extract(self, *, document_id: str, text: str):
        del document_id, text
        return []


class CountingCurrentExtractor:
    name = "career_console_profile_fact_extractor"
    schema_version = "candidate_profile_object.v2"

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, *, document_id: str, text: str):
        del document_id, text
        self.calls += 1
        return []


class FakeRuntime:
    def __init__(self, resolved: Any) -> None:
        self.resolved = resolved

    def resolve(self, task_name: str):
        assert task_name == "fact_extraction"
        return self.resolved


def test_runtime_uses_configured_profile_agent_without_legacy_mode() -> None:
    provider = FakeProvider({"schemaVersion": "candidate_profile_object.v2", "objects": []})
    resolved = type("Resolved", (), {"provider": provider, "model": "configured-model"})()
    extractor = _create_fact_extractor(FakeRuntime(resolved))  # type: ignore[arg-type]
    assert isinstance(extractor, RuntimeConfiguredProfileFactExtractor)
    extractor.extract(document_id="document-id", text="技能：Python")
    assert extractor.provider is provider
    assert extractor.model == "configured-model"


def test_runtime_resolves_current_profile_agent_for_every_import() -> None:
    first_provider = FakeProvider({"schemaVersion": "candidate_profile_object.v2", "objects": []})
    second_provider = FakeProvider({"schemaVersion": "candidate_profile_object.v2", "objects": []})
    resolved = iter((
        type("Resolved", (), {"provider": first_provider, "model": "first-model"})(),
        type("Resolved", (), {"provider": second_provider, "model": "second-model"})(),
    ))
    extractor = RuntimeConfiguredProfileFactExtractor(lambda: next(resolved))

    extractor.extract(document_id="first", text="技能：Python")
    assert extractor.provider is first_provider
    assert extractor.model == "first-model"

    extractor.extract(document_id="second", text="技能：SQL")
    assert extractor.provider is second_provider
    assert extractor.model == "second-model"


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        ("high", 0.9),
        ("中", 0.7),
        ("low confidence", 0.4),
        ("85%", 0.85),
    ],
)
def test_profile_agent_normalizes_bounded_confidence_labels(
    confidence: str,
    expected: float,
) -> None:
    evidence = "技能：Python"
    provider = FakeProvider(
        {
            "schemaVersion": "candidate_profile_object.v2",
            "objects": [
                {
                    "category": "skill",
                    "objectKey": "skill_profile",
                    "title": "技能概况",
                    "content": evidence,
                    "evidenceTexts": [evidence],
                    "confidence": confidence,
                }
            ],
        }
    )

    facts = CareerProfileFactExtractor(provider).extract(
        document_id="document-id",
        text=evidence,
    )

    assert facts[0].confidence == expected


def test_profile_agent_rejects_unknown_confidence_label() -> None:
    evidence = "技能：Python"
    provider = FakeProvider(
        {
            "schemaVersion": "candidate_profile_object.v2",
            "objects": [
                {
                    "category": "skill",
                    "objectKey": "skill_profile",
                    "title": "技能概况",
                    "content": evidence,
                    "evidenceTexts": [evidence],
                    "confidence": "probably",
                }
            ],
        }
    )

    with pytest.raises(CareerDomainError) as caught:
        CareerProfileFactExtractor(provider).extract(
            document_id="document-id",
            text=evidence,
        )

    assert caught.value.code == "fact_extraction_schema_invalid"


def test_unconfigured_profile_agent_fails_with_actionable_error() -> None:
    extractor = _create_fact_extractor(FakeRuntime(None))  # type: ignore[arg-type]
    with pytest.raises(CareerDomainError) as caught:
        extractor.extract(document_id="document-id", text="技能：Python")
    assert caught.value.code == "profile_fact_extraction_unavailable"
    assert "设置 > AI 服务" in caught.value.detail


def test_legacy_schema_document_is_reprocessed_once_by_current_agent(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    upgrade_to_head(settings)
    database = Database(settings)
    gateway = SqlAlchemyProfileGateway(database.session_factory)
    parser = DocumentParser(max_bytes=settings.max_document_bytes)
    blobs = LocalBlobStore(settings.blobs_dir)
    try:
        legacy = ProfileApplicationService(
            gateway=gateway,
            parser=parser,
            blob_store=blobs,
            extractor=LegacyExtractor(),  # type: ignore[arg-type]
        )
        first = legacy.import_text(name="resume", text="技能：Python")
        assert first["duplicate"] is False

        current_extractor = CountingCurrentExtractor()
        current = ProfileApplicationService(
            gateway=gateway,
            parser=parser,
            blob_store=blobs,
            extractor=current_extractor,  # type: ignore[arg-type]
        )
        upgraded = current.import_text(name="resume", text="技能：Python")
        duplicate = current.import_text(name="resume", text="技能：Python")

        assert upgraded["duplicate"] is False
        assert duplicate["duplicate"] is True
        assert current_extractor.calls == 1
        with database.session_factory() as session:
            runs = session.scalars(
                select(AgentRunModel).order_by(AgentRunModel.created_at, AgentRunModel.id)
            ).all()
            assert [run.schema_version for run in runs] == [
                "candidate_fact.v1",
                "candidate_profile_object.v2",
            ]
    finally:
        database.close()


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
