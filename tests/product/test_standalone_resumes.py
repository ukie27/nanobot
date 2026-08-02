from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path

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
    FactReferenceModel,
    FactSnapshotModel,
    ResumeModel,
    ResumeVersionModel,
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
        "/api/v1/resumes/agent-proposals",
        json={
            "name": "后端开发通用简历",
            "prompt": "突出后端工程能力，保持事实准确并控制在两页内。",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_generation_requires_confirmed_facts(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        client.app.state.standalone_resume_service.drafter = _StandaloneDrafter()
        response = client.post(
            "/api/v1/resumes/agent-proposals",
            json={"name": "通用简历", "prompt": "突出后端经历"},
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "confirmed_facts_required"


def test_generation_creates_candidate_without_formal_resume(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        proposal = _generate(client)

        assert proposal["status"] == "proposed"
        assert proposal["resume_id"] is None
        assert proposal["review_task_id"]
        assert all(
            not block["requirementIds"] for block in proposal["content"]["blocks"]
        )
        with client.app.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(StandaloneResumeProposalModel)
            ) == 1
            assert session.scalar(select(func.count()).select_from(ResumeModel)) == 0
            assert session.scalar(
                select(func.count()).select_from(ResumeVersionModel)
            ) == 0


def test_invalid_agent_references_leave_failure_audit_only(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        service = client.app.state.standalone_resume_service

        service.drafter = _UnknownFactDrafter()
        unknown_fact = client.post(
            "/api/v1/resumes/agent-proposals",
            json={"name": "非法事实简历", "prompt": "生成简历"},
        )
        assert unknown_fact.status_code == 422, unknown_fact.text
        assert unknown_fact.json()["code"] == "standalone_resume_fact_invalid"

        service.drafter = _JobRequirementDrafter()
        job_requirement = client.post(
            "/api/v1/resumes/agent-proposals",
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


def test_profile_change_blocks_candidate_confirmation(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        first_fact, _ = _complete_profile(client)
        proposal = _generate(client)
        changed = client.post(
            f"/api/v1/facts/{first_fact['id']}/edit",
            json={
                "expected_version": first_fact["version"],
                "value": "熟练使用 Python 和 SQL",
                "reason": "修正技能范围",
            },
        )
        assert changed.status_code == 200, changed.text

        resolved = client.post(
            f"/api/v1/resumes/agent-proposals/{proposal['id']}/resolve",
            json={
                "expected_version": proposal["version"],
                "resolution": "confirmed",
                "reason": "确认创建",
            },
        )
        assert resolved.status_code == 409, resolved.text
        with client.app.state.database.session_factory() as session:
            assert session.scalar(select(ResumeModel)) is None


def test_confirmation_creates_fact_bound_resume_version(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        facts = _complete_profile(client)
        proposal = _generate(client)
        resolved = client.post(
            f"/api/v1/resumes/agent-proposals/{proposal['id']}/resolve",
            json={
                "expected_version": proposal["version"],
                "resolution": "confirmed",
                "reason": "内容和依据已核对",
            },
        )
        assert resolved.status_code == 200, resolved.text
        result = resolved.json()
        assert result["status"] == "confirmed"
        assert result["resume_id"]
        assert result["resume_version_id"]

        detail = client.get(f"/api/v1/resumes/{result['resume_id']}")
        assert detail.status_code == 200, detail.text
        resume = detail.json()
        assert resume["series_type"] == "base"
        assert resume["current_version"]["version_scope"] == "base"
        assert resume["current_version"]["version_number"] == 1
        assert resume["current_version"]["status"] == "reviewed"
        evidence_ids = {
            snapshot["fact_id"]
            for block in resume["current_version"]["blocks"]
            for snapshot in block["fact_snapshots"]
        }
        assert evidence_ids == {fact["id"] for fact in facts}

        with client.app.state.database.session_factory() as session:
            version = session.get(
                ResumeVersionModel, result["resume_version_id"]
            )
            assert version is not None
            assert version.parent_version_id is None
            assert session.scalar(
                select(func.count()).select_from(FactSnapshotModel)
            ) == 2
            assert session.scalar(
                select(func.count()).select_from(FactReferenceModel)
            ) == 2


def test_resume_edit_review_repair_finalize_and_export(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        proposal = _generate(client)
        confirmed = client.post(
            f"/api/v1/resumes/agent-proposals/{proposal['id']}/resolve",
            json={
                "expected_version": proposal["version"],
                "resolution": "confirmed",
                "reason": "确认创建",
            },
        ).json()
        resume = client.get(f"/api/v1/resumes/{confirmed['resume_id']}").json()

        edited = client.post(
            f"/api/v1/resumes/{resume['id']}/versions",
            json={
                "expected_version_id": resume["current_version"]["id"],
                "blocks": [
                    {
                        "id": block["id"],
                        "text": (
                            f"核心能力：{block['text']}"
                            if index == 0
                            else block["text"]
                        ),
                    }
                    for index, block in enumerate(resume["current_version"]["blocks"])
                ],
            },
        )
        assert edited.status_code == 201, edited.text
        resume = edited.json()
        assert resume["current_version"]["version_number"] == 2
        assert resume["current_version"]["parent_version_id"]
        assert resume["current_version"]["status"] == "reviewed"

        invented = client.post(
            f"/api/v1/resumes/{resume['id']}/versions",
            json={
                "expected_version_id": resume["current_version"]["id"],
                "blocks": [
                    {
                        "id": block["id"],
                        "text": (
                            f"曾担任首席架构师，{block['text']}"
                            if index == 0
                            else block["text"]
                        ),
                    }
                    for index, block in enumerate(resume["current_version"]["blocks"])
                ],
            },
        )
        assert invented.status_code == 201, invented.text
        resume = invented.json()
        assert resume["current_version"]["status"] == "draft"
        assert any(
            finding["code"] == "unsupported_claim"
            for finding in resume["review"]["findings"]
        )

        repaired = client.post(
            f"/api/v1/resumes/{resume['id']}/versions",
            json={
                "expected_version_id": resume["current_version"]["id"],
                "blocks": [
                    {
                        "id": block["id"],
                        "text": block["fact_snapshots"][0]["value"],
                    }
                    for block in resume["current_version"]["blocks"]
                ],
            },
        )
        assert repaired.status_code == 201, repaired.text
        resume = repaired.json()
        assert resume["current_version"]["status"] == "reviewed"

        reviewed = client.post(f"/api/v1/resumes/{resume['id']}/reviews")
        assert reviewed.status_code == 201, reviewed.text
        resume = reviewed.json()
        assert resume["review"]["error_count"] == 0

        finalized = client.post(
            f"/api/v1/resumes/{resume['id']}/finalize",
            json={"expected_version_id": resume["current_version"]["id"]},
        )
        assert finalized.status_code == 200, finalized.text
        resume = finalized.json()
        assert resume["current_version"]["status"] == "final"
        assert resume["export"]["text_layer_ok"] is True
        assert resume["export"]["render_ok"] is True

        pdf_response = client.get(resume["export"]["download_url"])
        assert pdf_response.status_code == 200
        assert pdf_response.content.startswith(b"%PDF-")
        pdf = PdfReader(BytesIO(pdf_response.content))
        extracted = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert "Python" in extracted
