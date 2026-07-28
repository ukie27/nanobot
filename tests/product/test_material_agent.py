from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.materials import (
    MaterialReviewResult,
    ResumeDirectionResult,
    ResumeDraftResult,
)
from career_console.infrastructure.database.models import (
    AgentRunModel,
    FactReferenceModel,
    MaterialAgentProposalModel,
    MaterialDraftModel,
    ResumeVersionModel,
)
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


class _DirectionAnalyzer:
    name = "test_direction"
    schema_version = "resume_direction.v1"
    prompt_version = "test"
    provider = None
    model = "test"
    last_usage = {}
    last_retry_count = 0

    def analyze(self, *, context: dict) -> ResumeDirectionResult:
        requirements = [item["id"] for item in context["requirements"]]
        facts = [item["id"] for item in context["confirmedFacts"]]
        return ResumeDirectionResult.model_validate({
            "schemaVersion": "resume_direction.v1", "directions": [
                {"directionId": "backend", "name": "后端工程", "narrative": "突出工程能力",
                 "focusRequirementIds": requirements, "emphasizeFactIds": facts,
                 "deEmphasizeFactIds": [], "estimatedChangePercent": 30,
                 "expectedPages": 1, "gaps": [], "risks": [], "rationale": "证据充分"},
                {"directionId": "delivery", "name": "交付能力", "narrative": "突出可靠交付",
                 "focusRequirementIds": requirements[:1], "emphasizeFactIds": facts[:1],
                 "deEmphasizeFactIds": facts[1:], "estimatedChangePercent": 40,
                 "expectedPages": 1, "gaps": [], "risks": [], "rationale": "方向不同"},
            ], "comparisonNote": "两个方向分别强调技术与交付。",
        })


class _Drafter:
    name = "test_drafter"
    schema_version = "resume_draft.v2"
    prompt_version = "test"
    provider = None
    model = "test"
    last_usage = {}
    last_retry_count = 0

    def draft(self, *, context: dict) -> ResumeDraftResult:
        first_fact = context["confirmedFacts"][0]
        second_fact = context["confirmedFacts"][1]
        requirement = context["requirements"][0]
        return ResumeDraftResult.model_validate({
            "schemaVersion": "resume_draft.v2", "title": "Python 后端定制简历",
            "blocks": [
                {"blockId": "skill-python", "section": "专业技能",
                 "text": first_fact["value"], "factIds": [first_fact["id"]],
                 "requirementIds": [requirement["id"]]},
                {"blockId": "project-delivery", "section": "项目经历",
                 "text": second_fact["value"], "factIds": [second_fact["id"]],
                 "requirementIds": [requirement["id"]]},
            ],
            "rationale": "按已确认方向突出 Python 证据。",
        })


class _InvalidDrafter(_Drafter):
    def draft(self, *, context: dict) -> ResumeDraftResult:
        result = super().draft(context=context).model_dump(mode="json", by_alias=True)
        result["blocks"][0]["factIds"] = ["unknown-fact"]
        return ResumeDraftResult.model_validate(result)


class _InvalidRequirementDrafter(_Drafter):
    def draft(self, *, context: dict) -> ResumeDraftResult:
        result = super().draft(context=context).model_dump(mode="json", by_alias=True)
        result["blocks"][0]["requirementIds"] = ["unknown-requirement"]
        return ResumeDraftResult.model_validate(result)


class _UnsupportedClaimDrafter(_Drafter):
    def draft(self, *, context: dict) -> ResumeDraftResult:
        result = super().draft(context=context).model_dump(mode="json", by_alias=True)
        result["blocks"][0]["text"] += "，拥有十年大规模系统经验"
        return ResumeDraftResult.model_validate(result)


class _Reviewer:
    name = "test_reviewer"
    schema_version = "material_review.v2"
    prompt_version = "test"
    provider = None
    model = "test"
    last_usage = {}
    last_retry_count = 0

    def review(self, *, context: dict) -> MaterialReviewResult:
        return MaterialReviewResult.model_validate({
            "schemaVersion": "material_review.v2", "verdict": "pass",
            "findings": [{"severity": "info", "code": "fact_supported",
                          "message": "事实引用有效", "blockId": context["draft"]["blocks"][0]["blockId"]}],
            "summary": "事实支持、ATS 和可读性检查通过。",
        })


class _FailingReviewer(_Reviewer):
    def review(self, *, context: dict) -> MaterialReviewResult:
        raise CareerDomainError("review failed", code="review_test_failure")


def _settings(path: Path) -> CareerSettings:
    return CareerSettings(data_dir=path, mail_intelligence_mode="disabled",
                          profile_insight_mode="disabled", job_fit_agent_mode="disabled",
                          resume_direction_mode="disabled", material_agent_mode="disabled")


def _fact(client: TestClient, *, category: str = "skill", key: str = "technical_skills",
          value: str = "Python、SQL、FastAPI") -> dict:
    proposed = client.post("/api/v1/facts", json={"category": category,
                           "field_key": key, "value": value,
                           "source_note": "test"}).json()
    return client.post(f"/api/v1/facts/{proposed['id']}/confirm", json={
        "expected_version": proposed["version"], "reason": "verified"}).json()


def _job(client: TestClient) -> dict:
    response = client.post("/api/v1/job-posts/import-text", json={
        "name": "JD", "text": "职位：Python 后端工程师\n公司：示例科技\n任职要求\n- 必须熟练 Python 和 SQL"})
    assert response.status_code == 201, response.text
    return response.json()


def _complete_profile(client: TestClient) -> tuple[dict, dict]:
    return (
        _fact(client),
        _fact(
            client,
            category="project",
            key="achievement",
            value="负责后端服务开发并完成稳定交付",
        ),
    )


def _select_direction(client: TestClient, job_id: str) -> None:
    client.app.state.resume_direction_service.analyzer = _DirectionAnalyzer()
    proposal = client.post(f"/api/v1/job-posts/{job_id}/resume-directions").json()
    response = client.post(f"/api/v1/job-posts/resume-directions/{proposal['id']}/resolve", json={
        "expected_version": proposal["version"], "resolution": "confirmed",
        "selected_direction_ids": ["backend"], "reason": "test"})
    assert response.status_code == 200, response.text


def test_material_agent_requires_active_direction(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        job = _job(client)
        client.app.state.material_agent_service.drafter = _Drafter()
        client.app.state.material_agent_service.reviewer = _Reviewer()
        response = client.post("/api/v1/materials/agent-proposals", json={"job_post_id": job["id"]})
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "active_resume_direction_required"


def test_material_agent_confirmation_promotes_fact_bound_version(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        fact, _ = _complete_profile(client)
        job = _job(client)
        _select_direction(client, job["id"])
        service = client.app.state.material_agent_service
        service.drafter = _Drafter()
        service.reviewer = _Reviewer()
        generated = client.post("/api/v1/materials/agent-proposals", json={
            "job_post_id": job["id"], "resume_name": "Agent 定制简历"})
        assert generated.status_code == 201, generated.text
        proposal = generated.json()
        with client.app.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(MaterialDraftModel)) == 0
        resolved = client.post(f"/api/v1/materials/agent-proposals/{proposal['id']}/resolve", json={
            "expected_version": proposal["version"], "resolution": "confirmed", "reason": "确认草稿"})
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["material_draft_id"]
        material = client.get(f"/api/v1/materials/{resolved.json()['material_draft_id']}").json()
        assert material["status"] == "reviewed"
        referenced_fact_ids = {
            snapshot["fact_id"]
            for block in material["current_version"]["blocks"]
            for snapshot in block["fact_snapshots"]
        }
        assert fact["id"] in referenced_fact_ids
        with client.app.state.database.session_factory() as session:
            version = session.scalar(select(ResumeVersionModel))
            assert version.version_number == 1 and version.parent_version_id is None
            assert session.scalar(select(func.count()).select_from(FactReferenceModel)) == 2


def test_material_agent_rejects_stale_direction_selection(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        job = _job(client)
        _select_direction(client, job["id"])
        _fact(client, key="delivery_skills", value="持续集成与可靠交付")
        client.app.state.material_agent_service.drafter = _Drafter()
        client.app.state.material_agent_service.reviewer = _Reviewer()
        response = client.post("/api/v1/materials/agent-proposals", json={"job_post_id": job["id"]})
        assert response.status_code == 409, response.text


def test_invalid_draft_and_reviewer_failure_leave_audit_only(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        job = _job(client)
        _select_direction(client, job["id"])
        service = client.app.state.material_agent_service
        service.drafter = _InvalidDrafter()
        service.reviewer = _Reviewer()
        invalid = client.post("/api/v1/materials/agent-proposals", json={"job_post_id": job["id"]})
        assert invalid.status_code == 422, invalid.text
        service.drafter = _InvalidRequirementDrafter()
        invalid_requirement = client.post(
            "/api/v1/materials/agent-proposals", json={"job_post_id": job["id"]}
        )
        assert invalid_requirement.status_code == 422, invalid_requirement.text
        service.drafter = _UnsupportedClaimDrafter()
        unsupported = client.post(
            "/api/v1/materials/agent-proposals", json={"job_post_id": job["id"]}
        )
        assert unsupported.status_code == 422, unsupported.text
        service.drafter = _Drafter()
        service.reviewer = _FailingReviewer()
        failed = client.post("/api/v1/materials/agent-proposals", json={"job_post_id": job["id"]})
        assert failed.status_code == 422
        with client.app.state.database.session_factory() as session:
            assert session.scalar(select(MaterialAgentProposalModel)) is None
            runs = session.scalars(select(AgentRunModel).where(
                AgentRunModel.task_type.in_(["resume_draft", "material_review"])
            )).all()
            assert any(run.error_code == "resume_draft_fact_invalid" for run in runs)
            assert any(run.error_code == "resume_draft_requirement_invalid" for run in runs)
            assert any(run.error_code == "unsupported_claim" for run in runs)
            assert any(run.status == "succeeded" and run.task_type == "resume_draft" for run in runs)
            assert any(run.error_code == "review_test_failure" for run in runs)
