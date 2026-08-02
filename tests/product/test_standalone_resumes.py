from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from zipfile import is_zipfile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.materials import ResumeDraftResult
from career_console.infrastructure.agents.material_drafting import (
    CareerStandaloneResumeDrafter,
)
from career_console.infrastructure.database.models import (
    AgentRunModel,
    ResumeDefaultModel,
    ResumeModel,
    ResumeVersionModel,
    ReviewTaskModel,
    StandaloneResumeProposalModel,
)
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app
from career_console.runtime.agent.runner import AgentRunResult


class _StandaloneDrafter:
    name = "test_standalone_resume_drafter"
    schema_version = "resume_draft.v2"
    prompt_version = "test"
    skill_version = "test"
    provider = None
    model = "test"
    last_usage = {}
    last_retry_count = 0

    def draft(self, *, context: dict) -> ResumeDraftResult:
        first_fact, second_fact = context["confirmedFacts"][:2]
        return ResumeDraftResult.model_validate(
            {
                "schemaVersion": "resume_draft.v2",
                "title": context["resumeName"],
                "blocks": [
                    {
                        "blockId": "technical-skills",
                        "section": "专业技能",
                        "text": first_fact["value"],
                        "factIds": [first_fact["id"]],
                        "requirementIds": [],
                    },
                    {
                        "blockId": "project-achievement",
                        "section": "项目经历",
                        "text": second_fact["value"],
                        "factIds": [second_fact["id"]],
                        "requirementIds": [],
                    },
                ],
                "rationale": "根据已确认职业事实组织通用简历。",
            }
        )


class _UnknownFactDrafter(_StandaloneDrafter):
    def draft(self, *, context: dict) -> ResumeDraftResult:
        result = super().draft(context=context).model_dump(mode="json", by_alias=True)
        result["blocks"][0]["factIds"] = ["unknown-fact"]
        return ResumeDraftResult.model_validate(result)


class _JobRequirementDrafter(_StandaloneDrafter):
    def draft(self, *, context: dict) -> ResumeDraftResult:
        result = super().draft(context=context).model_dump(mode="json", by_alias=True)
        result["blocks"][0]["requirementIds"] = ["job-requirement"]
        return ResumeDraftResult.model_validate(result)


class _SequentialRunner:
    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.specs = []

    async def run(self, spec) -> AgentRunResult:
        self.specs.append(spec)
        return AgentRunResult(
            final_content=self.contents.pop(0),
            messages=[],
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )


def _real_drafter_with_outputs(contents: list[str]) -> CareerStandaloneResumeDrafter:
    drafter = object.__new__(CareerStandaloneResumeDrafter)
    drafter.model = "test-model"
    drafter.runner = _SequentialRunner(contents)
    drafter.last_usage = {}
    drafter.last_retry_count = 0
    return drafter


def _standalone_context() -> dict:
    return {
        "schemaVersion": "standalone_resume_context.v1",
        "businessTimezone": "Asia/Shanghai",
        "inputRevision": "profile:default:facts:test",
        "resumeName": "后端开发通用简历",
        "userPrompt": "突出后端工程能力。",
        "confirmedFacts": [
            {
                "id": "fact-python",
                "version": 1,
                "category": "skill",
                "fieldKey": "technical_skills",
                "value": "熟练使用 Python、SQL 和 FastAPI",
            },
            {
                "id": "fact-project",
                "version": 1,
                "category": "project",
                "fieldKey": "achievement",
                "value": "负责后端服务开发并完成稳定交付",
            },
        ],
        "factSetHash": "test",
    }


def _valid_adapter_output(
    *,
    fact_id: str = "fact-python",
    requirement_ids: list[str] | None = None,
) -> str:
    values = {
        "fact-python": "熟练使用 Python、SQL 和 FastAPI",
        "fact-project": "负责后端服务开发并完成稳定交付",
    }
    return json.dumps(
        {
            "schemaVersion": "resume_draft.v2",
            "title": "后端开发通用简历",
            "blocks": [
                {
                    "blockId": "technical-skills",
                    "section": "专业技能",
                    "text": values.get(fact_id, "未知事实"),
                    "factIds": [fact_id],
                    "requirementIds": requirement_ids or [],
                }
            ],
            "rationale": "根据已确认职业事实组织通用简历。",
        },
        ensure_ascii=False,
    )


def test_real_standalone_drafter_repairs_schema_once() -> None:
    drafter = _real_drafter_with_outputs(["{}", _valid_adapter_output()])

    result = asyncio.run(drafter._draft(_standalone_context()))

    assert result.schema_version == "resume_draft.v2"
    assert drafter.last_retry_count == 1
    assert drafter.last_usage == {"prompt_tokens": 20, "completion_tokens": 10}
    assert len(drafter.runner.specs) == 2
    assert drafter.runner.specs[1].session_key.endswith(":schema-repair")


def test_real_standalone_drafter_rejects_unknown_fact_after_repair() -> None:
    drafter = _real_drafter_with_outputs(
        [
            _valid_adapter_output(fact_id="unknown-fact"),
            _valid_adapter_output(fact_id="unknown-fact"),
        ]
    )

    try:
        asyncio.run(drafter._draft(_standalone_context()))
    except CareerDomainError as exc:
        assert exc.code == "standalone_resume_fact_invalid"
    else:
        raise AssertionError("unknown facts must remain rejected after repair")


def test_real_standalone_drafter_rejects_requirements_after_repair() -> None:
    drafter = _real_drafter_with_outputs(
        [
            _valid_adapter_output(requirement_ids=["requirement-1"]),
            _valid_adapter_output(requirement_ids=["requirement-1"]),
        ]
    )

    try:
        asyncio.run(drafter._draft(_standalone_context()))
    except CareerDomainError as exc:
        assert exc.code == "standalone_resume_requirement_invalid"
    else:
        raise AssertionError("job requirement references must remain rejected")


def _settings(path: Path) -> CareerSettings:
    return CareerSettings(
        data_dir=path,
        mail_intelligence_mode="disabled",
        profile_insight_mode="disabled",
        job_fit_agent_mode="disabled",
        resume_direction_mode="disabled",
        material_agent_mode="disabled",
    )


def _fact(
    client: TestClient,
    *,
    category: str,
    key: str,
    value: str,
) -> dict:
    proposed = client.post(
        "/api/v1/facts",
        json={
            "category": category,
            "field_key": key,
            "value": value,
            "source_note": "standalone resume test",
        },
    )
    assert proposed.status_code == 201, proposed.text
    fact = proposed.json()
    confirmed = client.post(
        f"/api/v1/facts/{fact['id']}/confirm",
        json={"expected_version": fact["version"], "reason": "verified"},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def _complete_profile(client: TestClient) -> tuple[dict, dict]:
    return (
        _fact(
            client,
            category="skill",
            key="technical_skills",
            value="熟练使用 Python、SQL 和 FastAPI",
        ),
        _fact(
            client,
            category="project",
            key="achievement",
            value="负责后端服务开发并完成稳定交付",
        ),
    )


def _generate(client: TestClient) -> dict:
    client.app.state.standalone_resume_service.drafter = _StandaloneDrafter()
    response = client.post(
        "/api/v1/resumes/generate",
        json={
            "name": "后端开发通用简历",
            "prompt": "突出后端工程能力，保持事实准确并控制在两页内。",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_generation_requires_profile_facts(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        client.app.state.standalone_resume_service.drafter = _StandaloneDrafter()
        response = client.post(
            "/api/v1/resumes/generate",
            json={"name": "通用简历", "prompt": "突出后端经历"},
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "confirmed_facts_required"


def test_generation_publishes_library_resume_with_pdf_and_docx(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        facts = _complete_profile(client)
        resume = _generate(client)

        assert resume["scope"] == "library"
        assert resume["application_id"] is None
        assert resume["current_version"]["status"] == "final"
        assert {item["format"] for item in resume["exports"]} == {"pdf", "docx"}
        assert resume["docx_export"]["format"] == "docx"
        evidence_ids = {
            snapshot["fact_id"]
            for block in resume["current_version"]["blocks"]
            for snapshot in block["fact_snapshots"]
        }
        assert evidence_ids == {fact["id"] for fact in facts}

        docx = client.get(resume["docx_export"]["download_url"])
        assert docx.status_code == 200
        assert docx.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert is_zipfile(BytesIO(docx.content))

        with client.app.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(StandaloneResumeProposalModel)
            ) == 0
            assert session.scalar(select(func.count()).select_from(ReviewTaskModel)) == 0
            assert session.scalar(select(func.count()).select_from(ResumeModel)) == 1
            assert session.scalar(
                select(func.count()).select_from(ResumeVersionModel)
            ) == 1


def test_invalid_agent_references_leave_failure_audit_only(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        service = client.app.state.standalone_resume_service

        service.drafter = _UnknownFactDrafter()
        unknown_fact = client.post(
            "/api/v1/resumes/generate",
            json={"name": "非法事实简历", "prompt": "生成简历"},
        )
        assert unknown_fact.status_code == 422, unknown_fact.text
        assert unknown_fact.json()["code"] == "standalone_resume_fact_invalid"

        service.drafter = _JobRequirementDrafter()
        job_requirement = client.post(
            "/api/v1/resumes/generate",
            json={"name": "混入岗位要求的简历", "prompt": "生成简历"},
        )
        assert job_requirement.status_code == 422, job_requirement.text
        assert (
            job_requirement.json()["code"]
            == "standalone_resume_requirement_invalid"
        )

        with client.app.state.database.session_factory() as session:
            assert session.scalar(select(StandaloneResumeProposalModel)) is None
            assert session.scalar(select(ResumeModel)) is None
            runs = session.scalars(
                select(AgentRunModel).where(
                    AgentRunModel.task_type == "standalone_resume_draft"
                )
            ).all()
            assert {run.error_code for run in runs} == {
                "standalone_resume_fact_invalid",
                "standalone_resume_requirement_invalid",
            }


def test_import_publishes_resume_and_default_archive_lifecycle(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        imported = client.post(
            "/api/v1/resumes/import",
            data={"name": "导入的通用简历"},
            files={
                "file": (
                    "resume.txt",
                    "技能\nPython、SQL\n项目经历\n负责后端服务交付".encode(),
                    "text/plain",
                )
            },
        )
        assert imported.status_code == 201, imported.text
        resume = imported.json()
        assert resume["scope"] == "library"
        assert resume["source_file_name"] == "resume.txt"
        assert resume["current_version"]["status"] == "final"
        assert resume["docx_export"]["format"] == "docx"

        made_default = client.put(
            "/api/v1/resumes/default",
            json={"resume_id": resume["id"], "expected_version": None},
        )
        assert made_default.status_code == 200, made_default.text
        assert made_default.json()["is_default"] is True

        archived = client.delete(f"/api/v1/resumes/{resume['id']}")
        assert archived.status_code == 204, archived.text
        assert client.get("/api/v1/resumes").json()["items"] == []
        assert client.get("/api/v1/resumes/default").json() is None
        with client.app.state.database.session_factory() as session:
            stored = session.get(ResumeModel, resume["id"])
            assert stored is not None and stored.retired_at is not None
            assert session.scalar(select(ResumeDefaultModel)) is None


def test_export_failure_keeps_agent_audit_and_removes_provisional_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        service = client.app.state.standalone_resume_service
        service.drafter = _StandaloneDrafter()

        def fail_finalize(*args, **kwargs):
            raise RuntimeError("export failed")

        monkeypatch.setattr(service.gateway._publisher, "finalize_resume", fail_finalize)
        with pytest.raises(RuntimeError, match="export failed"):
            client.post(
                "/api/v1/resumes/generate",
                json={"name": "导出失败简历", "prompt": "突出后端能力"},
            )
        with client.app.state.database.session_factory() as session:
            assert session.scalar(select(ResumeModel)) is None
            run = session.scalar(
                select(AgentRunModel).where(
                    AgentRunModel.task_type == "standalone_resume_draft"
                )
            )
            assert run is not None and run.status == "succeeded"


def test_generated_resume_keeps_pdf_preview_compatibility(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        resume = _generate(client)
        assert resume["current_version"]["status"] == "final"
        assert resume["export"]["text_layer_ok"] is True
        assert resume["export"]["render_ok"] is True
        assert resume["export"]["format"] == "pdf"

        pdf_response = client.get(resume["export"]["download_url"])
        assert pdf_response.status_code == 200
        assert pdf_response.content.startswith(b"%PDF-")
        pdf = PdfReader(BytesIO(pdf_response.content))
        extracted = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert "Python" in extracted
