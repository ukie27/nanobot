from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from career_console.domain.profile import ProfileInsightResult
from career_console.infrastructure.database.models import (
    AgentRunModel,
    ProfileInsightProposalModel,
)
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http.app import create_app


class _ProfileInsightAnalyzer:
    name = "test_profile_insight"
    schema_version = "profile_insight.v1"
    prompt_version = "profile_insight.v1-test"
    provider = None
    model = "test"
    last_usage = {"input_tokens": 10, "output_tokens": 5}
    last_retry_count = 0

    def analyze(self, *, context: dict) -> ProfileInsightResult:
        return ProfileInsightResult.model_validate({
            "schemaVersion": "profile_insight.v1",
            "insights": [{
                "insightType": "strength",
                "conclusion": "已确认项目证据支持 Python 技能优势。",
                "evidenceFactIds": [context["confirmedFacts"][0]["id"]],
                "counterEvidenceFactIds": [],
                "confidence": 0.86,
            }],
        })


class _InvalidEvidenceAnalyzer(_ProfileInsightAnalyzer):
    def analyze(self, *, context: dict) -> ProfileInsightResult:
        del context
        return ProfileInsightResult.model_validate({
            "schemaVersion": "profile_insight.v1",
            "insights": [{
                "insightType": "gap",
                "conclusion": "无效引用不应被保存。",
                "evidenceFactIds": ["unknown-fact-id"],
                "counterEvidenceFactIds": [],
                "confidence": 0.5,
            }],
        })


def _confirmed_fact(client: TestClient) -> dict:
    proposed = client.post("/api/v1/facts", json={
        "category": "skill", "field_key": "technical_skill", "value": "Python",
        "source_note": "用户确认的项目证据",
    })
    assert proposed.status_code == 201, proposed.text
    fact = proposed.json()
    confirmed = client.post(f"/api/v1/facts/{fact['id']}/confirm", json={
        "expected_version": fact["version"], "reason": "用户核验",
    })
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def test_preferences_fact_events_digest_and_strategy_are_traceable(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        client.app.state.profile_memory_service.analyzer = _ProfileInsightAnalyzer()
        preference = client.put("/api/v1/profile-memory/preferences/target_roles", json={
            "value": ["后端工程", "AI 应用"], "expected_version": None,
        })
        assert preference.status_code == 200, preference.text
        assert preference.json()["status"] == "confirmed"
        conflict = client.put("/api/v1/profile-memory/preferences/target_roles", json={
            "value": ["数据工程"], "expected_version": 99,
        })
        assert conflict.status_code == 409

        fact = _confirmed_fact(client)
        overview = client.get("/api/v1/profile-memory").json()
        event_types = [item["event_type"] for item in overview["changes"]]
        assert "preference_confirmed" in event_types
        assert "fact_confirm" in event_types
        fact_event = next(item for item in overview["changes"] if item["event_type"] == "fact_confirm")
        assert fact_event["entity_id"] == fact["id"]
        assert "job_fit" in fact_event["impact_scopes"]

        digest = client.post("/api/v1/profile-memory/digests/daily").json()
        repeated = client.post("/api/v1/profile-memory/digests/daily").json()
        assert repeated["id"] == digest["id"]
        assert len(digest["content"]["changes"]) >= 2

        insight = client.post("/api/v1/profile-memory/insights").json()[0]
        assert insight["status"] == "proposed" and fact["id"] in insight["evidence_refs"]
        assert insight["source"] == "career_console_profile_insight"
        assert insight["agent_run_id"]
        strategy = client.post("/api/v1/profile-memory/strategies").json()
        assert strategy["status"] == "proposed"
        assert strategy["content"]["target_directions"] == ["后端工程", "AI 应用"]

        reviews = client.get("/api/v1/runtime/reviews").json()["items"]
        assert {item["entity_type"] for item in reviews} >= {"profile_insight", "strategy_snapshot"}
        resolved = client.post(
            f"/api/v1/profile-memory/strategy_snapshot/{strategy['id']}/resolve",
            json={"expected_version": strategy["version"], "resolution": "confirmed", "reason": "采用本周策略"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "confirmed"
        impact_result = client.post("/api/v1/profile-memory/impacts/run").json()
        assert impact_result["processed"] >= 1
        impact_runs = client.get("/api/v1/profile-memory").json()["impact_runs"]
        assert impact_runs
        assert all(item["status"] == "succeeded" for item in impact_runs)
        changes = client.get("/api/v1/profile-memory").json()["changes"]
        assert changes[0]["event_type"] == "strategy_snapshot_confirmed"


def test_profile_insight_rejects_unknown_fact_reference_and_audits_failure(tmp_path) -> None:
    settings = CareerSettings(
        data_dir=tmp_path, mail_intelligence_mode="disabled", profile_insight_mode="disabled"
    )
    app = create_app(settings)
    with TestClient(app) as client:
        _confirmed_fact(client)
        client.app.state.profile_memory_service.analyzer = _InvalidEvidenceAnalyzer()
        response = client.post("/api/v1/profile-memory/insights")
        assert response.status_code == 409
        with client.app.state.database.session_factory() as session:
            run = session.scalar(select(AgentRunModel).where(
                AgentRunModel.task_type == "profile_insight"
            ))
            assert run is not None
            assert run.status == "failed"
            assert run.error_code == "profile_insight_evidence_invalid"
            assert session.scalar(select(ProfileInsightProposalModel)) is None
