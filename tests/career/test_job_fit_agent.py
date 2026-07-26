from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from nanobot.career.api import create_app
from nanobot.career.domain.jobs import JobFitAnalysisResult
from nanobot.career.infrastructure.database.models import AgentRunModel, JobFitProposalModel
from nanobot.career.infrastructure.settings import CareerSettings


class _JobFitAnalyzer:
    name = "test_job_fit"
    schema_version = "job_fit_analysis.v2"
    prompt_version = "job_fit_analysis.v2-test"
    provider = None
    model = "test"
    last_usage = {"input_tokens": 50, "output_tokens": 20}
    last_retry_count = 0

    def analyze(self, *, context: dict) -> JobFitAnalysisResult:
        facts_by_category: dict[str, list[str]] = {}
        for fact in context["confirmedFacts"]:
            facts_by_category.setdefault(fact["category"], []).append(fact["id"])
        fallback = context["confirmedFacts"][0]["id"]
        assessments = []
        for requirement in context["requirements"]:
            fact_id = (facts_by_category.get(requirement["category"]) or [fallback])[0]
            assessments.append({
                "requirementId": requirement["id"],
                "interpretation": requirement["description"],
                "decision": "matched",
                "evidenceFactIds": [fact_id],
                "transferableFactIds": [],
                "rationale": "由已确认事实直接支持。",
                "confidence": 0.88,
            })
        return JobFitAnalysisResult.model_validate({
            "schemaVersion": "job_fit_analysis.v2",
            "summary": "技能和学历证据覆盖当前岗位要求。",
            "assessments": assessments,
            "strengths": ["技术栈覆盖"],
            "risks": ["需要准备岗位案例"],
            "materialEffort": "medium",
            "preparationHours": 8,
            "recommendationContext": "建议在用户确认语义证据后进入高优先队列。",
        })


class _InvalidFactAnalyzer(_JobFitAnalyzer):
    def analyze(self, *, context: dict) -> JobFitAnalysisResult:
        output = super().analyze(context=context).model_dump(mode="json", by_alias=True)
        output["assessments"][0]["evidenceFactIds"] = ["unknown-fact"]
        return JobFitAnalysisResult.model_validate(output)


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
        "name": "官网 JD",
        "text": "职位：Python 后端工程师\n公司：示例科技\n任职要求\n- 必须熟练 Python 和 SQL\n- 本科及以上学历",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_job_fit_agent_proposal_review_and_deterministic_promotion(tmp_path: Path) -> None:
    settings = CareerSettings(
        data_dir=tmp_path, mail_intelligence_mode="disabled",
        profile_insight_mode="disabled", job_fit_agent_mode="disabled",
    )
    with TestClient(create_app(settings)) as client:
        _fact(client, "skill", "technical_skills", "Python、SQL")
        _fact(client, "education", "degree", "计算机科学本科学历")
        job = _job(client)
        client.app.state.job_fit_service.analyzer = _JobFitAnalyzer()

        generated = client.post(f"/api/v1/job-posts/{job['id']}/agent-fit-proposals")
        assert generated.status_code == 201, generated.text
        proposal = generated.json()
        assert proposal["status"] == "proposed"
        assert proposal["agent_run_id"] and proposal["review_task_id"]
        assert proposal["formal_analysis_id"] is None
        assert len(client.get(f"/api/v1/job-posts/{job['id']}").json()["analyses"]) == 1

        repeated = client.post(f"/api/v1/job-posts/{job['id']}/agent-fit-proposals")
        assert repeated.json()["id"] == proposal["id"]
        resolved = client.post(
            f"/api/v1/job-posts/agent-fit-proposals/{proposal['id']}/resolve",
            json={"expected_version": proposal["version"], "resolution": "confirmed",
                  "reason": "逐项核验 Agent 证据"},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "confirmed"
        assert resolved.json()["formal_analysis_id"]
        analyses = client.get(f"/api/v1/job-posts/{job['id']}").json()["analyses"]
        assert len(analyses) == 2
        assert analyses[0]["hard_gate_passed"] is True

        stale_candidate = client.post(
            f"/api/v1/job-posts/{job['id']}/agent-fit-proposals"
        ).json()
        preference = client.put("/api/v1/profile-memory/preferences/target_cities", json={
            "value": ["北京"], "expected_version": None,
        })
        assert preference.status_code == 200, preference.text
        stale_resolution = client.post(
            f"/api/v1/job-posts/agent-fit-proposals/{stale_candidate['id']}/resolve",
            json={"expected_version": stale_candidate["version"], "resolution": "confirmed",
                  "reason": "尝试确认过期候选"},
        )
        assert stale_resolution.status_code == 409
        assert "重新运行" in stale_resolution.json()["detail"]


def test_job_fit_agent_rejects_unknown_confirmed_fact_reference(tmp_path: Path) -> None:
    settings = CareerSettings(
        data_dir=tmp_path, mail_intelligence_mode="disabled",
        profile_insight_mode="disabled", job_fit_agent_mode="disabled",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        _fact(client, "skill", "technical_skills", "Python、SQL")
        job = _job(client)
        client.app.state.job_fit_service.analyzer = _InvalidFactAnalyzer()
        response = client.post(f"/api/v1/job-posts/{job['id']}/agent-fit-proposals")
        assert response.status_code == 409
        with client.app.state.database.session_factory() as session:
            run = session.scalar(select(AgentRunModel).where(
                AgentRunModel.task_type == "job_fit_analysis"
            ))
            assert run is not None and run.status == "failed"
            assert run.error_code == "job_fit_fact_reference_invalid"
            assert session.scalar(select(JobFitProposalModel)) is None
