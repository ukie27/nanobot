from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from career_console.domain.materials import ResumeDirectionResult
from career_console.infrastructure.database.models import (
    AgentRunModel,
    ResumeDirectionProposalModel,
)
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


class _DirectionAnalyzer:
    name = "test_resume_direction"
    schema_version = "resume_direction.v1"
    prompt_version = "resume_direction.v1-test"
    provider = None
    model = "test"
    last_usage = {"input_tokens": 40, "output_tokens": 30}
    last_retry_count = 0

    def analyze(self, *, context: dict) -> ResumeDirectionResult:
        requirements = [item["id"] for item in context["requirements"]]
        facts = [item["id"] for item in context["confirmedFacts"]]
        return ResumeDirectionResult.model_validate({
            "schemaVersion": "resume_direction.v1",
            "directions": [
                {
                    "directionId": "engineering_delivery", "name": "工程交付方向",
                    "narrative": "突出后端工程、可靠交付和性能优化。",
                    "focusRequirementIds": requirements,
                    "emphasizeFactIds": facts,
                    "deEmphasizeFactIds": [], "estimatedChangePercent": 35,
                    "expectedPages": 1.5, "gaps": [], "risks": ["需要压缩次要经历"],
                    "rationale": "与岗位的工程要求覆盖一致。",
                },
                {
                    "directionId": "data_ai", "name": "数据与 AI 应用方向",
                    "narrative": "突出数据处理和 AI 应用能力，并保留工程基础。",
                    "focusRequirementIds": [requirements[0]],
                    "emphasizeFactIds": [facts[0]],
                    "deEmphasizeFactIds": facts[1:], "estimatedChangePercent": 50,
                    "expectedPages": 1.0, "gaps": ["AI 项目证据有限"], "risks": [],
                    "rationale": "适合作为差异化方向，但证据覆盖更窄。",
                },
            ],
            "comparisonNote": "工程方向覆盖更完整，数据与 AI 方向差异化更强。",
        })


class _InvalidDirectionAnalyzer(_DirectionAnalyzer):
    def analyze(self, *, context: dict) -> ResumeDirectionResult:
        output = super().analyze(context=context).model_dump(mode="json", by_alias=True)
        output["directions"][0]["emphasizeFactIds"] = ["unknown-fact"]
        return ResumeDirectionResult.model_validate(output)


def _fact(client: TestClient, category: str, key: str, value: str) -> dict:
    proposed = client.post("/api/v1/facts", json={
        "category": category, "field_key": key, "value": value, "source_note": "test",
    }).json()
    response = client.post(f"/api/v1/facts/{proposed['id']}/confirm", json={
        "expected_version": proposed["version"], "reason": "verified",
    })
    assert response.status_code == 200, response.text
    return response.json()


def _job(client: TestClient) -> dict:
    response = client.post("/api/v1/job-posts/import-text", json={
        "name": "JD", "text": (
            "职位：Python 后端工程师\n公司：示例科技\n任职要求\n"
            "- 必须熟练 Python 和 SQL\n- 本科及以上学历"
        ),
    })
    assert response.status_code == 201, response.text
    return response.json()


def _settings(tmp_path: Path) -> CareerSettings:
    return CareerSettings(
        data_dir=tmp_path, mail_intelligence_mode="disabled",
        profile_insight_mode="disabled", job_fit_agent_mode="disabled",
        resume_direction_mode="disabled",
    )


def test_resume_direction_proposal_selection_and_stale_guard(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        _fact(client, "skill", "technical_skills", "Python、SQL、FastAPI")
        _fact(client, "education", "degree", "计算机科学本科学历")
        job = _job(client)
        client.app.state.resume_direction_service.analyzer = _DirectionAnalyzer()

        generated = client.post(f"/api/v1/job-posts/{job['id']}/resume-directions")
        assert generated.status_code == 201, generated.text
        proposal = generated.json()
        assert proposal["status"] == "proposed"
        assert len(proposal["content"]["directions"]) == 2
        assert proposal["agent_run_id"] and proposal["review_task_id"]

        resolved = client.post(
            f"/api/v1/job-posts/resume-directions/{proposal['id']}/resolve",
            json={
                "expected_version": proposal["version"], "resolution": "confirmed",
                "selected_direction_ids": ["engineering_delivery", "data_ai"],
                "reason": "组合工程交付与 AI 应用方向",
            },
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["selection_id"]
        overview = client.get(f"/api/v1/job-posts/{job['id']}/resume-directions").json()
        assert overview["selections"][0]["status"] == "active"
        assert overview["selections"][0]["selected_direction_ids"] == [
            "engineering_delivery", "data_ai"
        ]

        stale = client.post(f"/api/v1/job-posts/{job['id']}/resume-directions").json()
        client.put("/api/v1/profile-memory/preferences/target_roles", json={
            "value": ["AI 应用"], "expected_version": None,
        })
        conflict = client.post(
            f"/api/v1/job-posts/resume-directions/{stale['id']}/resolve",
            json={
                "expected_version": stale["version"], "resolution": "confirmed",
                "selected_direction_ids": ["data_ai"], "reason": "确认",
            },
        )
        assert conflict.status_code == 409
        assert "重新生成" in conflict.json()["detail"]


def test_resume_direction_invalid_fact_reference_writes_failed_run_only(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        _fact(client, "skill", "technical_skills", "Python、SQL")
        job = _job(client)
        client.app.state.resume_direction_service.analyzer = _InvalidDirectionAnalyzer()
        response = client.post(f"/api/v1/job-posts/{job['id']}/resume-directions")
        assert response.status_code == 409
        with client.app.state.database.session_factory() as session:
            run = session.scalar(select(AgentRunModel).where(
                AgentRunModel.task_type == "resume_direction"
            ))
            assert run is not None and run.status == "failed"
            assert run.error_code == "resume_direction_fact_invalid"
            assert session.scalar(select(ResumeDirectionProposalModel)) is None
