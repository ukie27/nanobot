from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.profile import ProfileInsightResult
from career_console.infrastructure.agents.profile_insight import CareerProfileInsightAnalyzer
from career_console.infrastructure.database.models import (
    AgentRunModel,
    ImprovementItemModel,
    ProfileInsightProposalModel,
)
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http.app import create_app
from career_console.runtime.agent.runner import AgentRunResult


class _ProfileInsightAnalyzer:
    name = "test_profile_insight"
    schema_version = "profile_insight.v3"
    prompt_version = "profile_insight.v3-test"
    provider = None
    model = "test"
    last_usage = {"input_tokens": 10, "output_tokens": 5}
    last_retry_count = 0

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, *, context: dict) -> ProfileInsightResult:
        self.calls += 1
        return ProfileInsightResult.model_validate({
            "schemaVersion": "profile_insight.v3",
            "insights": [{
                "category": "resume",
                "analysis": "已确认项目证据支持 Python 技能，但量化结果不足。",
                "recommendation": "在下一版简历中补充一个可量化的 Python 项目结果。",
                "evidenceFactIds": [context["confirmedFacts"][0]["id"]],
                "evidenceImprovementIds": [],
                "counterEvidenceFactIds": [],
                "confidence": 0.86,
            }],
        })


class _InvalidEvidenceAnalyzer(_ProfileInsightAnalyzer):
    def analyze(self, *, context: dict) -> ProfileInsightResult:
        del context
        return ProfileInsightResult.model_validate({
            "schemaVersion": "profile_insight.v3",
            "insights": [{
                "category": "learning",
                "analysis": "无效引用不应被保存。",
                "recommendation": "忽略这条无效建议。",
                "evidenceFactIds": ["unknown-fact-id"],
                "evidenceImprovementIds": [],
                "counterEvidenceFactIds": [],
                "confidence": 0.5,
            }],
        })


class _ImprovementInsightAnalyzer(_ProfileInsightAnalyzer):
    def analyze(self, *, context: dict) -> ProfileInsightResult:
        self.calls += 1
        return ProfileInsightResult.model_validate({
            "schemaVersion": "profile_insight.v3",
            "insights": [{
                "category": "interview",
                "analysis": "面试复盘反复表明回答结构需要加强。",
                "recommendation": "本周完成两次 STAR 结构模拟回答并记录复盘。",
                "evidenceFactIds": [],
                "evidenceImprovementIds": [
                    context["confirmedInterviewImprovements"][0]["id"]
                ],
                "counterEvidenceFactIds": [],
                "confidence": 0.91,
            }],
        })


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


def _real_analyzer_with_outputs(contents: list[str]) -> CareerProfileInsightAnalyzer:
    analyzer = object.__new__(CareerProfileInsightAnalyzer)
    analyzer.model = "test-model"
    analyzer.runner = _SequentialRunner(contents)
    analyzer.last_usage = {}
    analyzer.last_retry_count = 0
    return analyzer


def _profile_insight_context() -> dict:
    return {
        "schemaVersion": "profile_insight_context.v3",
        "businessTimezone": "Asia/Shanghai",
        "inputRevision": "revision-1",
        "confirmedFacts": [{
            "id": "fact-1",
            "category": "skill",
            "fieldKey": "technical_skill",
            "value": "Python",
        }],
        "confirmedPreferences": [],
        "confirmedInterviewImprovements": [],
        "recentSevenDayAggregates": {},
    }


def _valid_profile_insight_output(
    *,
    evidence_id: str | None = "fact-1",
    improvement_id: str | None = None,
) -> str:
    return json.dumps({
        "schemaVersion": "profile_insight.v3",
        "insights": [{
            "category": "resume",
            "analysis": "已确认事实支持 Python 技能，但项目结果证据不足。",
            "recommendation": "补充一个可量化的 Python 项目结果。",
            "evidenceFactIds": [evidence_id] if evidence_id else [],
            "evidenceImprovementIds": [improvement_id] if improvement_id else [],
            "counterEvidenceFactIds": [],
            "confidence": 0.86,
        }],
    }, ensure_ascii=False)


def test_real_profile_insight_analyzer_repairs_schema_once() -> None:
    analyzer = _real_analyzer_with_outputs(["{}", _valid_profile_insight_output()])

    result = asyncio.run(analyzer._analyze(context=_profile_insight_context()))

    assert result.schema_version == "profile_insight.v3"
    assert analyzer.last_retry_count == 1
    assert analyzer.last_usage == {"prompt_tokens": 20, "completion_tokens": 10}
    assert len(analyzer.runner.specs) == 2
    assert analyzer.runner.specs[1].session_key.endswith(":schema-repair")
    system_prompt = analyzer.runner.specs[0].initial_messages[0]["content"]
    assert "automatically published career diagnostic guidance" in system_prompt
    assert "Never ask the user to confirm, approve, adopt, or reject" in system_prompt


def test_real_profile_insight_analyzer_repairs_english_output_once() -> None:
    english_output = json.dumps({
        "schemaVersion": "profile_insight.v3",
        "insights": [{
            "category": "resume",
            "analysis": "The confirmed profile shows Python experience but lacks measurable outcomes.",
            "recommendation": "Add one measurable Python project outcome to the next resume version.",
            "evidenceFactIds": ["fact-1"],
            "evidenceImprovementIds": [],
            "counterEvidenceFactIds": [],
            "confidence": 0.86,
        }],
    })
    analyzer = _real_analyzer_with_outputs([
        english_output,
        _valid_profile_insight_output(),
    ])

    result = asyncio.run(analyzer._analyze(context=_profile_insight_context()))

    assert analyzer.last_retry_count == 1
    assert result.insights[0].analysis.startswith("已确认事实")
    repair_payload = json.loads(
        analyzer.runner.specs[1].initial_messages[1]["content"]
    )
    assert repair_payload["failureCode"] == "profile_insight_language_invalid"
    assert any(
        "Simplified Chinese" in rule
        for rule in repair_payload["repairRules"]
    )


def test_real_profile_insight_analyzer_rejects_unknown_evidence_after_repair() -> None:
    analyzer = _real_analyzer_with_outputs([
        _valid_profile_insight_output(evidence_id="unknown-1"),
        _valid_profile_insight_output(evidence_id="unknown-2"),
    ])

    try:
        asyncio.run(analyzer._analyze(context=_profile_insight_context()))
    except CareerDomainError as exc:
        assert exc.code == "profile_insight_evidence_invalid"
    else:
        raise AssertionError("unknown evidence must remain rejected after schema repair")


def test_real_profile_insight_analyzer_rejects_unknown_improvement_after_repair() -> None:
    analyzer = _real_analyzer_with_outputs([
        _valid_profile_insight_output(
            evidence_id=None,
            improvement_id="unknown-improvement-1",
        ),
        _valid_profile_insight_output(
            evidence_id=None,
            improvement_id="unknown-improvement-2",
        ),
    ])

    try:
        asyncio.run(analyzer._analyze(context=_profile_insight_context()))
    except CareerDomainError as exc:
        assert exc.code == "profile_insight_evidence_invalid"
    else:
        raise AssertionError(
            "unknown improvement evidence must remain rejected after schema repair"
        )


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
        analyzer = _ProfileInsightAnalyzer()
        client.app.state.profile_memory_service.analyzer = analyzer
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
        assert "fact_maintained" in event_types
        fact_event = next(
            item for item in overview["changes"] if item["event_type"] == "fact_maintained"
        )
        assert fact_event["entity_id"] == fact["id"]
        assert "job_fit" in fact_event["impact_scopes"]

        digest = client.post("/api/v1/profile-memory/digests/daily").json()
        repeated = client.post("/api/v1/profile-memory/digests/daily").json()
        assert repeated["id"] == digest["id"]
        assert len(digest["content"]["changes"]) >= 2

        insight = client.post("/api/v1/profile-memory/insights").json()[0]
        assert insight["status"] == "active" and fact["id"] in insight["evidence_refs"]
        assert insight["category"] == "resume"
        assert insight["analysis"]
        assert insight["recommendation"]
        assert insight["evidence_fact_ids"] == [fact["id"]]
        assert insight["evidence_improvement_ids"] == []
        assert insight["source"] == "career_console_profile_insight"
        assert insight["agent_run_id"]
        repeated_insight = client.post("/api/v1/profile-memory/insights").json()[0]
        assert repeated_insight["id"] == insight["id"]
        assert analyzer.calls == 1
        updated_preference = client.put(
            "/api/v1/profile-memory/preferences/target_roles",
            json={
                "value": ["后端工程", "AI 应用", "平台工程"],
                "expected_version": preference.json()["version"],
            },
        )
        assert updated_preference.status_code == 200, updated_preference.text
        replacement = client.post("/api/v1/profile-memory/insights").json()[0]
        assert replacement["id"] != insight["id"]
        assert analyzer.calls == 2
        overview_after_reanalysis = client.get("/api/v1/profile-memory").json()
        assert [item["id"] for item in overview_after_reanalysis["insights"]] == [
            replacement["id"]
        ]
        with client.app.state.database.session_factory() as session:
            old_row = session.get(ProfileInsightProposalModel, insight["id"])
            assert old_row is not None and old_row.status == "superseded"
        strategy = client.post("/api/v1/profile-memory/strategies").json()
        assert strategy["status"] == "active"
        assert strategy["content"]["target_directions"] == [
            "后端工程",
            "AI 应用",
            "平台工程",
        ]

        reviews = client.get("/api/v1/runtime/reviews").json()["items"]
        assert not any(
            item["entity_type"] in {"profile_insight", "strategy_snapshot"}
            for item in reviews
        )
        impact_result = client.post("/api/v1/profile-memory/impacts/run").json()
        assert impact_result["processed"] >= 1
        impact_runs = client.get("/api/v1/profile-memory").json()["impact_runs"]
        assert impact_runs
        assert all(item["status"] == "succeeded" for item in impact_runs)


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


def test_confirmed_interview_improvements_enter_context_and_persist_typed_evidence(
    tmp_path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        job = client.post("/api/v1/job-posts/import-text", json={
            "name": "面试改进测试 JD",
            "text": "职位：Python 后端工程师\n公司：示例科技\n任职要求\n- 熟练 Python",
        }).json()
        application = client.post(
            "/api/v1/applications", json={"job_post_id": job["id"]}
        ).json()
        interview = client.post("/api/v1/interviews", json={
            "application_id": application["id"],
            "round_type": "technical",
            "scheduled_at": "2026-07-31T13:30:00Z",
            "timezone": "Asia/Shanghai",
        }).json()
        record = client.post(f"/api/v1/interviews/{interview['id']}/record", json={
            "occurred_at": "2026-07-31T14:30:00Z",
            "overall_summary": "回答内容基本正确，但结构松散。",
            "self_rating": 3,
            "result": "pending",
            "questions": [{
                "question_text": "介绍一次复杂故障排查经历",
                "answer_summary": "直接描述了处理过程，没有交代背景和结果。",
                "self_rating": 2,
            }],
        })
        assert record.status_code == 201, record.text
        pending_feedback = client.get("/api/v1/interview-feedback").json()["items"]
        assert pending_feedback

        gateway = client.app.state.profile_memory_service.gateway
        before_confirmation = gateway.profile_insight_context()
        assert before_confirmation["confirmedInterviewImprovements"] == []

        for feedback in pending_feedback:
            resolved = client.post(
                f"/api/v1/interview-feedback/{feedback['id']}/resolve",
                json={
                    "expected_version": feedback["version"],
                    "resolution": "confirmed",
                    "reason": "用户确认该面试改进项",
                },
            )
            assert resolved.status_code == 200, resolved.text

        confirmed_context = gateway.profile_insight_context()
        assert confirmed_context["schemaVersion"] == "profile_insight_context.v3"
        assert confirmed_context["confirmedInterviewImprovements"]
        improvement = confirmed_context["confirmedInterviewImprovements"][0]
        assert improvement["occurrenceCount"] >= 1
        assert confirmed_context["inputRevision"] != before_confirmation["inputRevision"]

        client.app.state.profile_memory_service.analyzer = _ImprovementInsightAnalyzer()
        insight = client.post("/api/v1/profile-memory/insights").json()[0]
        assert insight["recommendation"] == (
            "本周完成两次 STAR 结构模拟回答并记录复盘。"
        )
        assert insight["evidence_fact_ids"] == []
        assert insight["evidence_improvement_ids"] == [improvement["id"]]
        assert insight["evidence_refs"] == [improvement["id"]]

        with client.app.state.database.session_factory() as session:
            row = session.get(ImprovementItemModel, improvement["id"])
            assert row is not None
            row.occurrence_count += 1
            row.updated_at = datetime.now(UTC)
            session.commit()
        updated_context = gateway.profile_insight_context()
        assert updated_context["inputRevision"] != confirmed_context["inputRevision"]


def test_daily_profile_maintenance_runs_agent_once_and_reuses_same_input(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        analyzer = _ProfileInsightAnalyzer()
        service = client.app.state.profile_memory_service
        service.analyzer = analyzer
        now = datetime(2026, 7, 29, 13, 30, tzinfo=UTC)

        first = service.run_due(now=now)
        second = service.run_due(now=now)

        assert first["business_timezone"] == "Asia/Shanghai"
        assert first["business_date"] == "2026-07-29"
        assert first["profile_digest_generated"] == 1
        assert first["profile_insights_created"] == 1
        assert second["profile_insights_reused"] == 1
        assert second["insight_ids"] == first["insight_ids"]
        assert analyzer.calls == 1


def test_profile_insights_regenerate_when_prompt_version_changes(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        service = client.app.state.profile_memory_service
        first_analyzer = _ProfileInsightAnalyzer()
        service.analyzer = first_analyzer

        first = service.generate_insights()

        second_analyzer = _ProfileInsightAnalyzer()
        second_analyzer.prompt_version = "profile_insight.v4-test"
        service.analyzer = second_analyzer
        second = service.generate_insights()

        assert first_analyzer.calls == 1
        assert second_analyzer.calls == 1
        assert [item["id"] for item in second] != [item["id"] for item in first]
        with client.app.state.database.session_factory() as session:
            rows = session.scalars(
                select(ProfileInsightProposalModel).order_by(
                    ProfileInsightProposalModel.created_at
                )
            ).all()
            assert [row.status for row in rows] == ["superseded", "active"]


def test_scheduler_executes_complete_profile_maintenance_workflow(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        analyzer = _ProfileInsightAnalyzer()
        client.app.state.profile_memory_service.analyzer = analyzer
        configuration = client.get("/api/v1/configuration").json()
        scheduler = {
            **configuration["configuration"]["scheduler"],
            "enabled": True,
            "reminders_enabled": False,
            "connector_jobs_enabled": False,
            "profile_maintenance_enabled": True,
            "profile_maintenance_time": "21:30",
            "profile_maintenance_interval_days": 3,
            "channel_dispatch_enabled": False,
        }
        configured = client.put("/api/v1/scheduler/configuration", json={
            "expected_revision": configuration["revision"],
            "scheduler": scheduler,
        })
        assert configured.status_code == 200, configured.text

        now = datetime(2026, 7, 29, 13, 30, tzinfo=UTC)
        run = client.app.state.scheduler_runtime.run_once(trigger_type="manual", now=now)
        repeated = client.app.state.scheduler_runtime.run_once(trigger_type="manual", now=now)

        assert run["counters"]["profile_digest_generated"] == 1
        assert run["counters"]["profile_insights_created"] == 1
        assert run["counters"]["profile_insight_failed"] == 0
        assert repeated["counters"]["profile_jobs_processed"] == 0
        assert analyzer.calls == 1
