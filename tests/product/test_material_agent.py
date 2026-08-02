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
    ResumeModel,
    ResumeVersionModel,
    ReviewTaskModel,
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


def _generate_library_resume(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/resumes/import",
        data={"name": "通用后端简历"},
        files={
            "file": (
                "resume.txt",
                "Python 后端工程\n负责稳定交付".encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _generate_application_resume(
    client: TestClient,
    *,
    application: dict,
    job: dict,
    source_resume_version_id: str | None = None,
) -> dict:
    service = client.app.state.material_agent_service
    service.drafter = _Drafter()
    service.reviewer = _Reviewer()
    response = client.post(
        "/api/v1/materials/generate",
        json={
            "application_id": application["id"],
            "job_post_id": job["id"],
            "source_resume_version_id": source_resume_version_id,
            "resume_name": "岗位专属简历",
            "prompt": "突出与该岗位直接相关的后端经验。",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_direct_application_resume_generation_and_copy_to_library(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        job = _job(client)
        library = _generate_library_resume(client)
        application = client.post(
            "/api/v1/applications", json={"job_post_id": job["id"]}
        ).json()

        material = _generate_application_resume(
            client,
            application=application,
            job=job,
            source_resume_version_id=library["current_version"]["id"],
        )
        assert material["status"] == "final"
        assert {item["format"] for item in material["exports"]} == {"pdf", "docx"}

        refreshed = client.get(
            f"/api/v1/applications/{application['id']}"
        ).json()
        assert refreshed["current_status"] == "preparing_materials"
        assert refreshed["active_resume_binding"] is None
        generated_version = material["current_version"]["id"]
        available = next(
            item
            for item in refreshed["available_final_materials"]
            if item["resume_version_id"] == generated_version
        )
        assert available["scope"] == "application"
        assert available["application_id"] == application["id"]

        application_resumes = client.get("/api/v1/resumes/application").json()
        assert application_resumes["total"] == 1
        application_resume = application_resumes["items"][0]
        assert application_resume["scope"] == "application"
        assert application_resume["application_id"] == application["id"]
        assert application_resume["job_title"] == application["job_title"]
        assert application_resume["company"] == application["company"]
        assert application_resume["docx_export"]["format"] == "docx"

        copied = client.post(
            f"/api/v1/resumes/{application_resume['id']}/save-to-library",
            json={"name": "保存后的岗位简历"},
        )
        assert copied.status_code == 201, copied.text
        copied_resume = copied.json()
        assert copied_resume["scope"] == "library"
        assert copied_resume["application_id"] is None
        assert copied_resume["id"] != application_resume["id"]
        assert copied_resume["current_version"]["id"] != generated_version
        assert copied_resume["docx_export"]["format"] == "docx"

        with client.app.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(MaterialAgentProposalModel)
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(ReviewTaskModel)
            ) == 0


def test_application_resume_can_bind_only_owning_application(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _complete_profile(client)
        first_job = _job(client)
        second_job = client.post(
            "/api/v1/job-posts/import-text",
            json={
                "name": "JD2",
                "text": "职位：平台工程师\n公司：另一家公司\n任职要求\n- 必须熟练 Python 和 SQL",
            },
        ).json()
        first_application = client.post(
            "/api/v1/applications", json={"job_post_id": first_job["id"]}
        ).json()
        second_application = client.post(
            "/api/v1/applications", json={"job_post_id": second_job["id"]}
        ).json()
        material = _generate_application_resume(
            client, application=first_application, job=first_job
        )
        version_id = material["current_version"]["id"]

        bound = client.post(
            f"/api/v1/applications/{first_application['id']}/resume-bindings",
            json={
                "expected_version": first_application["version"],
                "command_id": "bind-own-application-resume",
                "resume_version_id": version_id,
                "use_default": False,
                "source": "generated",
            },
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["current_status"] == "ready_to_apply"

        cross_bound = client.post(
            f"/api/v1/applications/{second_application['id']}/resume-bindings",
            json={
                "expected_version": second_application["version"],
                "command_id": "bind-cross-application-resume",
                "resume_version_id": version_id,
                "use_default": False,
                "source": "generated",
            },
        )
        assert cross_bound.status_code == 422, cross_bound.text
        assert cross_bound.json()["code"] == "application_resume_scope_mismatch"

        with client.app.state.database.session_factory() as session:
            resume = session.scalar(
                select(ResumeModel).where(ResumeModel.scope == "application")
            )
            assert resume is not None
            assert resume.application_id == first_application["id"]


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
