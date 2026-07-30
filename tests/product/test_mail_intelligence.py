from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.mail.intelligence import MailIntelligenceResult
from career_console.infrastructure.agents.mail_intelligence import CareerMailIntelligenceAnalyzer
from career_console.infrastructure.database.models import (
    AgentRunModel,
    ApplicationEventModel,
    ApplicationModel,
    CareerTaskModel,
    ReviewTaskModel,
)
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http.app import create_app
from career_console.runtime.agent.runner import AgentRunResult


class FakeAnalyzer:
    name = "fake_mail_agent"
    schema_version = "mail_intelligence.v1"
    prompt_version = "mail_intelligence.v1-test"
    model = "fake-model"
    provider = object()
    last_usage = {"prompt_tokens": 120, "completion_tokens": 80}
    last_retry_count = 0

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, *, message: dict, applications: list[dict]) -> MailIntelligenceResult:
        del applications
        self.calls += 1
        return MailIntelligenceResult.model_validate({
            "schemaVersion": "mail_intelligence.v1",
            "relevance": "recruiting",
            "messageType": "interview_invitation",
            "summary": "测试公司的面试邀请，包含面试和材料截止时间。",
            "company": "测试公司",
            "jobTitle": "Python工程师",
            "applicationReference": None,
            "applicationMatch": {
                "application_id": None, "confidence": 0.2,
                "reason": "没有现有申请可匹配。", "create_record_recommended": True,
            },
            "events": [{
                "event_type": "interview_invited", "status_candidate": "interview",
                "occurred_at": "2026-07-26T10:00:00+08:00", "title": "收到面试邀请",
                "details": "技术面试", "evidence": "面试通知", "confidence": 0.96,
            }],
            "schedules": [{
                "schedule_type": "interview", "scheduled_at": "2026-07-28T14:30:00+08:00",
                "title": "参加技术面试", "instructions": "提前进入会议",
                "evidence": "2026年7月28日 14:30", "confidence": 0.94,
            }],
            "attentionItems": [{
                "category": "preparation", "title": "准备身份证明", "details": "携带身份证",
                "evidence": "携带身份证", "severity": "warning",
            }],
        })


class FailingAnalyzer(FakeAnalyzer):
    def analyze(self, *, message: dict, applications: list[dict]) -> MailIntelligenceResult:
        del message, applications
        raise CareerDomainError("schema invalid", code="mail_intelligence_schema_invalid")


class MatchedAnalyzer(FakeAnalyzer):
    def analyze(self, *, message: dict, applications: list[dict]) -> MailIntelligenceResult:
        result = super().analyze(message=message, applications=applications)
        payload = result.model_dump(by_alias=True)
        payload["applicationMatch"] = {
            "applicationId": applications[0]["id"],
            "confidence": 1.0,
            "reason": "公司和岗位与现有申请完全匹配。",
            "createRecordRecommended": False,
        }
        return MailIntelligenceResult.model_validate(payload)


class AutoSubmissionAnalyzer(FakeAnalyzer):
    def analyze(self, *, message: dict, applications: list[dict]) -> MailIntelligenceResult:
        del message, applications
        self.calls += 1
        return MailIntelligenceResult.model_validate({
            "schemaVersion": "mail_intelligence.v1",
            "relevance": "recruiting",
            "messageType": "application_received",
            "summary": "测试公司已收到 Python工程师 的申请。",
            "company": "测试公司",
            "jobTitle": "Python工程师",
            "applicationReference": "APP-20260729",
            "applicationMatch": {
                "applicationId": None,
                "confidence": 0.98,
                "reason": "公司、岗位和申请编号明确。",
                "createRecordRecommended": True,
            },
            "events": [{
                "eventType": "application_received",
                "statusCandidate": None,
                "occurredAt": "2026-07-20T10:00:00+08:00",
                "title": "申请已收到",
                "details": "招聘系统确认收到申请。",
                "evidence": "您的申请已成功提交并收到。",
                "confidence": 0.98,
            }],
            "schedules": [],
            "attentionItems": [],
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


def _real_analyzer_with_outputs(contents: list[str]) -> CareerMailIntelligenceAnalyzer:
    analyzer = object.__new__(CareerMailIntelligenceAnalyzer)
    analyzer.model = "test-model"
    analyzer.runner = _SequentialRunner(contents)
    analyzer.last_usage = {}
    analyzer.last_retry_count = 0
    return analyzer


def _valid_real_output(*, evidence: str = "2026年7月30日 14:30（北京时间）") -> str:
    return json.dumps({
        "schemaVersion": "mail_intelligence.v1",
        "relevance": "recruiting",
        "messageType": "interview_invitation",
        "summary": "测试公司的 Python 后端工程师面试邀请。",
        "company": "测试公司",
        "jobTitle": "Python 后端工程师",
        "applicationReference": None,
        "applicationMatch": {
            "applicationId": None,
            "confidence": 0.2,
            "reason": "没有现有申请可匹配。",
            "createRecordRecommended": True,
        },
        "events": [],
        "schedules": [{
            "scheduleType": "interview",
            "scheduledAt": "2026-07-30T14:30:00+08:00",
            "title": "参加技术面试",
            "instructions": "提前进入会议",
            "evidence": evidence,
            "confidence": 0.95,
        }],
        "attentionItems": [],
    }, ensure_ascii=False)


def _real_message() -> dict:
    return {
        "id": "mail-1",
        "sender": "hr@example.com",
        "subject": "测试公司面试邀请",
        "sent_at": datetime(2026, 7, 28, 2, tzinfo=UTC),
        "evidence_excerpt": "技术面试时间：2026年7月30日 14:30（北京时间）。",
        "attachments": [],
    }


def test_real_analyzer_repairs_invalid_schema_once_without_relaxing_contract() -> None:
    analyzer = _real_analyzer_with_outputs(["{}", _valid_real_output()])

    result = asyncio.run(analyzer._analyze(message=_real_message(), applications=[]))

    assert result.schema_version == "mail_intelligence.v1"
    assert analyzer.last_retry_count == 1
    assert analyzer.last_usage == {"prompt_tokens": 20, "completion_tokens": 10}
    assert len(analyzer.runner.specs) == 2
    assert analyzer.runner.specs[1].session_key.endswith(":schema-repair")


def test_real_analyzer_normalizes_matched_application_record_recommendation() -> None:
    output = json.loads(_valid_real_output())
    output["applicationMatch"] = {
        "applicationId": "application-1",
        "confidence": 0.98,
        "reason": "公司和岗位名称一致。",
        "createRecordRecommended": True,
    }
    analyzer = _real_analyzer_with_outputs([json.dumps(output, ensure_ascii=False)])

    result = asyncio.run(analyzer._analyze(
        message=_real_message(),
        applications=[{
            "id": "application-1",
            "company": "测试公司",
            "job_title": "Python 后端工程师",
            "current_status": "submitted",
        }],
    ))

    assert result.application_match.application_id == "application-1"
    assert result.application_match.create_record_recommended is False
    assert analyzer.last_retry_count == 0


def test_real_analyzer_rejects_absent_evidence_after_repair() -> None:
    analyzer = _real_analyzer_with_outputs([
        _valid_real_output(evidence="不存在的证据"),
        _valid_real_output(evidence="仍然不存在的证据"),
    ])

    try:
        asyncio.run(analyzer._analyze(message=_real_message(), applications=[]))
    except CareerDomainError as exc:
        assert exc.code == "mail_intelligence_evidence_invalid"
    else:
        raise AssertionError("invalid evidence must remain rejected after schema repair")


def _message(client: TestClient) -> str:
    gateway = client.app.state.mail_gateway
    gateway.configure(
        enabled=True, email_address="candidate@example.com", host="imap.example.com", port=993,
        username="candidate@example.com", secret_ref="test", folder="INBOX",
        initial_lookback_days=30, poll_interval_minutes=10,
    )
    message, _ = gateway.save_message(
        uid_validity="42", uid=7, message_id="<agent-mail@example.com>",
        sender="hr@example.com", subject="面试通知", sent_at=datetime(2026, 7, 26, 2, tzinfo=UTC),
        classification="recruiting", event_kind="interview",
        extracted={}, evidence_excerpt="面试通知：2026年7月28日 14:30，请携带身份证。",
        body_hash="a" * 64, attachments=[], body_fetched=True,
    )
    return message["id"]


def _unrelated_message(client: TestClient) -> str:
    gateway = client.app.state.mail_gateway
    gateway.configure(
        enabled=True, email_address="candidate@example.com", host="imap.example.com", port=993,
        username="candidate@example.com", secret_ref="test", folder="INBOX",
        initial_lookback_days=30, poll_interval_minutes=10,
    )
    message, _ = gateway.save_message(
        uid_validity="42", uid=8, message_id="<private-mail@example.com>",
        sender="newsletter@example.com", subject="每周资讯",
        sent_at=datetime(2026, 7, 26, 2, tzinfo=UTC),
        classification="unrelated", event_kind="interview",
        extracted={"company": "不应保存"}, evidence_excerpt="不应保存的私人正文",
        body_hash="b" * 64,
        attachments=[{"filename": "private.pdf", "content_type": "application/pdf", "size_bytes": 12}],
        body_fetched=True,
    )
    return message["id"]


def _submission_message(client: TestClient, *, uid: int = 20) -> str:
    gateway = client.app.state.mail_gateway
    gateway.configure(
        enabled=True, email_address="candidate@example.com", host="imap.example.com", port=993,
        username="candidate@example.com", secret_ref="test", folder="INBOX",
        initial_lookback_days=30, poll_interval_minutes=10,
    )
    message, _ = gateway.save_message(
        uid_validity="42", uid=uid, message_id=f"<submission-{uid}@example.com>",
        sender="hr@example.com", subject="测试公司 Python工程师 申请已收到",
        sent_at=datetime(2026, 7, 20, 2, tzinfo=UTC),
        classification="recruiting", event_kind=None, extracted={},
        evidence_excerpt="您的申请已成功提交并收到。申请编号 APP-20260729。",
        body_hash=f"{uid:064d}", attachments=[], body_fetched=True,
    )
    return message["id"]


def _job_and_default_resume(client: TestClient) -> tuple[dict, dict]:
    for category, field_key, value in [
        ("skill", "technical_skills", "熟练使用 Python"),
        ("project", "achievement", "负责后端服务开发并完成稳定交付"),
    ]:
        fact = client.post("/api/v1/facts", json={
            "category": category, "field_key": field_key,
            "value": value, "source_note": "mail lifecycle test",
        }).json()
        confirmed = client.post(f"/api/v1/facts/{fact['id']}/confirm", json={
            "expected_version": fact["version"], "reason": "verified",
        })
        assert confirmed.status_code == 200, confirmed.text
    job_response = client.post("/api/v1/job-posts/import-text", json={
        "name": "公司官网 JD",
        "text": "职位：Python工程师\n公司：测试公司\n地点：上海\n任职要求\n- 熟练 Python",
    })
    assert job_response.status_code == 201, job_response.text
    job = job_response.json()
    material_response = client.post("/api/v1/materials", json={
        "job_post_id": job["id"], "material_type": "resume", "name": "默认简历",
    })
    assert material_response.status_code == 201, material_response.text
    material = material_response.json()
    finalized = client.post(f"/api/v1/materials/{material['id']}/finalize", json={
        "expected_version": material["version"],
    })
    assert finalized.status_code == 200, finalized.text
    material = finalized.json()
    default = client.put("/api/v1/resumes/default", json={
        "resume_id": material["resume_id"], "expected_version": None,
    })
    assert default.status_code == 200, default.text
    return job, material


def test_agent_analysis_persists_multiple_items_reviews_and_is_idempotent(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _message(client)
        analyzer = FakeAnalyzer()
        client.app.state.mail_service.analyzer = analyzer

        first = client.post(f"/api/v1/mail/messages/{message_id}/analyze")
        assert first.status_code == 200
        assert {item["item_type"] for item in first.json()["items"]} == {
            "event", "schedule", "attention", "create_application"
        }
        second = client.post(f"/api/v1/mail/messages/{message_id}/analyze")
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert analyzer.calls == 1

        items_by_type = {item["item_type"]: item for item in first.json()["items"]}
        assert items_by_type["event"]["occurred_at"] == "2026-07-26T02:00:00Z"
        assert items_by_type["schedule"]["scheduled_at"] == "2026-07-28T06:30:00Z"

        with client.app.state.database.session_factory() as session:
            run = session.scalar(select(AgentRunModel).where(AgentRunModel.task_type == "mail_intelligence"))
            reviews = session.scalars(select(ReviewTaskModel).where(
                ReviewTaskModel.task_type == "mail_intelligence_review"
            )).all()
            assert run is not None and run.status == "succeeded" and run.output_count == 4
            assert run.tool_calls_json == "[]" and run.sensitivity == "sensitive"
            assert len(reviews) == 4
            assert all(item.agent_run_id == run.id for item in reviews)

        review_queue = client.get("/api/v1/runtime/reviews").json()
        assert review_queue["total"] == 1
        bundle = review_queue["items"][0]
        assert bundle["entity_type"] == "review_bundle"
        assert bundle["bundle_type"] == "mail_analysis"
        assert bundle["item_count"] == 4
        assert {
            item["entity_subtype"] for item in bundle["items"]
        } == {"event", "schedule", "attention", "create_application"}

        item = first.json()["items"][0]
        resolved = client.post(f"/api/v1/mail/intelligence-items/{item['id']}/resolve", json={
            "expected_version": item["version"], "resolution": "confirmed", "reason": "已核对",
        })
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "confirmed"

        refreshed_bundle = client.get(
            f"/api/v1/runtime/reviews/{bundle['id']}"
        ).json()
        assert refreshed_bundle["status"] == "open"
        assert refreshed_bundle["item_count"] == 4


def test_high_confidence_submission_mail_auto_backfills_exact_snapshot(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        job, material = _job_and_default_resume(client)
        message_id = _submission_message(client)
        analyzer = AutoSubmissionAnalyzer()
        client.app.state.mail_service.analyzer = analyzer

        response = client.post(f"/api/v1/mail/messages/{message_id}/analyze")

        assert response.status_code == 200, response.text
        analysis = response.json()
        application_id = analysis["application_match"]["application_id"]
        assert analysis["job_post_id"] == job["id"]
        application = client.get(f"/api/v1/applications/{application_id}").json()
        assert application["current_status"] == "submitted"
        assert application["active_resume_binding"]["source"] == "mail_default"
        assert application["active_resume_binding"]["status"] == "locked"
        assert application["material_snapshots"][0]["resume_version_id"] == (
            material["current_version"]["id"]
        )
        submitted = next(
            item for item in application["events"]
            if item["event_type"] == "application_submitted"
        )
        assert submitted["source"] == "imap_policy"
        assert submitted["occurred_at"] == "2026-07-20T02:00:00Z"
        assert any(
            item["task_type"] == "mail_application_backfill"
            and item["application_id"] == application_id
            for item in client.app.state.task_gateway.list_tasks()
        )
        assert {
            item["status"] for item in analysis["items"]
            if item["item_type"] in {"event", "create_application"}
        } == {"confirmed"}

        repeated = client.post(f"/api/v1/mail/messages/{message_id}/analyze")
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["application_match"]["application_id"] == application_id
        assert analyzer.calls == 1
        assert len(client.get("/api/v1/applications").json()["items"]) == 1


def test_submission_mail_without_default_resume_stays_in_review(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        fact = client.post("/api/v1/facts", json={
            "category": "skill", "field_key": "technical_skills",
            "value": "熟练使用 Python", "source_note": "mail lifecycle test",
        }).json()
        client.post(f"/api/v1/facts/{fact['id']}/confirm", json={
            "expected_version": fact["version"], "reason": "verified",
        })
        client.post("/api/v1/job-posts/import-text", json={
            "name": "公司官网 JD",
            "text": "职位：Python工程师\n公司：测试公司\n地点：上海\n任职要求\n- 熟练 Python",
        })
        message_id = _submission_message(client)
        client.app.state.mail_service.analyzer = AutoSubmissionAnalyzer()

        analysis = client.post(f"/api/v1/mail/messages/{message_id}/analyze").json()

        assert analysis["application_match"]["application_id"] is None
        assert client.get("/api/v1/applications").json()["total"] == 0
        assert any(item["status"] == "pending" for item in analysis["items"])
        assert client.get("/api/v1/runtime/reviews").json()["total"] == 1


def test_submission_mail_with_ambiguous_or_existing_job_stays_in_review(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        job, _ = _job_and_default_resume(client)
        client.post("/api/v1/job-posts/import-text", json={
            "name": "另一地区 JD",
            "text": "职位：Python工程师\n公司：测试公司\n地点：北京\n任职要求\n- 熟练 Python",
        })
        ambiguous_id = _submission_message(client, uid=21)
        client.app.state.mail_service.analyzer = AutoSubmissionAnalyzer()
        ambiguous = client.post(
            f"/api/v1/mail/messages/{ambiguous_id}/analyze"
        ).json()
        assert ambiguous["application_match"]["application_id"] is None
        assert client.get("/api/v1/applications").json()["total"] == 0

        second_settings = CareerSettings(
            data_dir=tmp_path / "existing", mail_intelligence_mode="disabled"
        )
    with TestClient(create_app(second_settings)) as client:
        job, _ = _job_and_default_resume(client)
        existing = client.post(
            "/api/v1/applications", json={"job_post_id": job["id"]}
        ).json()
        message_id = _submission_message(client, uid=22)
        client.app.state.mail_service.analyzer = AutoSubmissionAnalyzer()
        analysis = client.post(f"/api/v1/mail/messages/{message_id}/analyze").json()
        assert analysis["application_match"]["application_id"] is None
        applications = client.get("/api/v1/applications").json()["items"]
        assert [item["id"] for item in applications] == [existing["id"]]
        assert applications[0]["current_status"] == "preparing_materials"


def test_mail_bundle_can_be_rejected_as_one_user_decision(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _message(client)
        client.app.state.mail_service.analyzer = FakeAnalyzer()
        client.post(f"/api/v1/mail/messages/{message_id}/analyze")
        bundle = client.get("/api/v1/runtime/reviews").json()["items"][0]

        response = client.post(
            f"/api/v1/runtime/reviews/{bundle['id']}/resolve",
            json={
                "expected_version": bundle["version"],
                "resolution": "rejected",
                "reason": "该邮件与我的求职申请无关",
            },
        )

        assert response.status_code == 200, response.text
        resolved = response.json()
        assert resolved["status"] == "resolved"
        assert resolved["resolution"] == "rejected"
        assert all(item["status"] == "resolved" for item in resolved["items"])
        assert all(item["resolution"] == "rejected" for item in resolved["items"])


def test_mail_bundle_confirmation_requires_application_link_first(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _message(client)
        client.app.state.mail_service.analyzer = FakeAnalyzer()
        client.post(f"/api/v1/mail/messages/{message_id}/analyze")
        bundle = client.get("/api/v1/runtime/reviews").json()["items"][0]

        response = client.post(
            f"/api/v1/runtime/reviews/{bundle['id']}/resolve",
            json={
                "expected_version": bundle["version"],
                "resolution": "confirmed",
                "reason": "确认邮件中的全部事项",
            },
        )

        assert response.status_code == 409
        assert "建立或关联申请" in response.json()["detail"]
        still_open = client.get(
            f"/api/v1/runtime/reviews/{bundle['id']}"
        ).json()
        assert still_open["status"] == "open"


def test_matched_mail_bundle_confirmation_creates_event_and_tasks(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _message(client)
        jd = """职位：Python工程师
公司：测试公司
地点：上海
任职要求
- 熟练 Python
"""
        job = client.post(
            "/api/v1/job-posts/import-text",
            json={"name": "公司官网 JD", "text": jd},
        ).json()
        application = client.post(
            "/api/v1/applications", json={"job_post_id": job["id"]}
        ).json()
        with client.app.state.database.session_factory() as session:
            row = session.get(ApplicationModel, application["id"])
            row.current_status = "submitted"
            session.commit()

        client.app.state.mail_service.analyzer = MatchedAnalyzer()
        client.post(f"/api/v1/mail/messages/{message_id}/analyze")
        bundle = client.get("/api/v1/runtime/reviews").json()["items"][0]

        response = client.post(
            f"/api/v1/runtime/reviews/{bundle['id']}/resolve",
            json={
                "expected_version": bundle["version"],
                "resolution": "confirmed",
                "reason": "已核对邮件原文和时间",
            },
        )

        assert response.status_code == 200, response.text
        resolved = response.json()
        assert resolved["status"] == "resolved"
        assert resolved["resolution"] == "confirmed"
        task_views = [
            item
            for item in client.app.state.task_gateway.list_tasks()
            if item["application_id"] == application["id"]
            and item["title"] in {"参加技术面试", "准备身份证明"}
        ]
        with client.app.state.database.session_factory() as session:
            events = session.scalars(
                select(ApplicationEventModel).where(
                    ApplicationEventModel.application_id == application["id"],
                    ApplicationEventModel.idempotency_key.like(
                        "mail-intelligence:%"
                    ),
                )
            ).all()
        assert len(events) == 1
        assert len(task_views) == 2
        due_by_title = {task["title"]: task["due_at"] for task in task_views}
        china = ZoneInfo("Asia/Shanghai")
        attention_due = due_by_title["准备身份证明"].astimezone(china)
        assert attention_due.hour == 10 and attention_due.minute == 0
        assert attention_due.date() == (
            datetime.now(china).date() + timedelta(days=1)
        )


def test_invalid_agent_output_creates_retryable_failed_run_only(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _message(client)
        client.app.state.mail_service.analyzer = FailingAnalyzer()
        response = client.post(f"/api/v1/mail/messages/{message_id}/analyze")
        assert response.status_code == 409
        assert "schema invalid" in response.json()["detail"]
        assert client.get("/api/v1/mail/messages").json()["items"][0]["intelligence"] is None
        with client.app.state.database.session_factory() as session:
            run = session.scalar(select(AgentRunModel).where(AgentRunModel.task_type == "mail_intelligence"))
            assert run is not None and run.status == "failed"
            assert run.error_code == "mail_intelligence_schema_invalid"


def test_persistent_worker_processes_queued_mail_analysis(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _message(client)
        service = client.app.state.mail_service
        service.analyzer = FakeAnalyzer()
        message = client.app.state.mail_gateway.get_message(message_id)

        assert service._queue_analysis(message) is True
        queued = [job for job in client.app.state.jobs.list_jobs() if job.job_type == service.ANALYSIS_JOB_TYPE]
        assert len(queued) == 1 and queued[0].status == "pending"
        assert service.process_next_analysis_job(worker_id="test-mail-worker") is True

        completed = client.app.state.jobs.list_jobs()[0]
        assert completed.status == "succeeded"
        analyzed = client.app.state.mail_gateway.get_message(message_id)["intelligence"]
        assert analyzed is not None and len(analyzed["items"]) == 4


def test_unrelated_mail_is_minimized_and_cannot_enter_agent_analysis(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _unrelated_message(client)
        analyzer = FakeAnalyzer()
        service = client.app.state.mail_service
        service.analyzer = analyzer
        message = client.app.state.mail_gateway.get_message(message_id)

        assert message["classification"] == "unrelated"
        assert message["event_kind"] is None
        assert message["extracted"] == {}
        assert message["evidence_excerpt"] is None
        assert message["body_hash"] is None
        assert message["attachments"] == []
        assert message["body_fetched"] is False
        assert service._queue_analysis(message) is False
        assert not client.app.state.jobs.list_jobs()

        response = client.post(f"/api/v1/mail/messages/{message_id}/analyze")
        assert response.status_code == 409
        assert response.json()["code"] == "mail_intelligence_unrelated"
        assert analyzer.calls == 0


def test_unmatched_mail_links_real_job_then_application_evidence(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _message(client)
        client.app.state.mail_service.analyzer = FakeAnalyzer()
        analysis = client.post(f"/api/v1/mail/messages/{message_id}/analyze").json()
        jd = """职位：Python工程师
公司：测试公司
地点：上海
任职要求
- 熟练 Python
"""
        imported = client.post("/api/v1/job-posts/import-text", json={
            "name": "公司官网 JD", "text": jd, "mail_analysis_id": analysis["id"],
        })
        assert imported.status_code == 201, imported.text
        job = imported.json()
        linked_message = client.get("/api/v1/mail/messages").json()["items"][0]
        assert linked_message["intelligence"]["job_post_id"] == job["id"]

        created = client.post("/api/v1/applications", json={"job_post_id": job["id"]})
        assert created.status_code == 201, created.text
        application = created.json()
        assert len(application["mail_evidence"]) == 1
        assert application["mail_evidence"][0]["analysis_id"] == analysis["id"]
        assert application["mail_evidence"][0]["subject"] == "面试通知"
        refreshed = client.get("/api/v1/mail/messages").json()["items"][0]["intelligence"]
        assert refreshed["application_match"]["application_id"] == application["id"]
        assert refreshed["application_match"]["create_record_recommended"] is False
        create_item = next(
            item for item in refreshed["items"] if item["item_type"] == "create_application"
        )
        assert create_item["status"] == "confirmed"
        open_reviews = client.get("/api/v1/runtime/reviews").json()["items"]
        assert all(item["entity_id"] != create_item["id"] for item in open_reviews)


def test_mail_resolution_retry_does_not_duplicate_event_or_task(tmp_path) -> None:
    settings = CareerSettings(data_dir=tmp_path, mail_intelligence_mode="disabled")
    with TestClient(create_app(settings)) as client:
        message_id = _message(client)
        jd = """职位：Python工程师
公司：测试公司
地点：上海
任职要求
- 熟练 Python
"""
        job = client.post(
            "/api/v1/job-posts/import-text",
            json={"name": "公司官网 JD", "text": jd},
        ).json()
        application = client.post(
            "/api/v1/applications", json={"job_post_id": job["id"]}
        ).json()
        with client.app.state.database.session_factory() as session:
            row = session.get(ApplicationModel, application["id"])
            row.current_status = "submitted"
            session.commit()

        client.app.state.mail_service.analyzer = MatchedAnalyzer()
        intelligence = client.post(
            f"/api/v1/mail/messages/{message_id}/analyze"
        ).json()
        items = {item["item_type"]: item for item in intelligence["items"]}
        service = client.app.state.mail_service
        original_resolve = service.gateway.resolve_intelligence_item
        failures = 0

        def fail_after_side_effect(*args, **kwargs):
            nonlocal failures
            failures += 1
            if failures in {1, 3}:
                raise RuntimeError("simulated review persistence failure")
            return original_resolve(*args, **kwargs)

        service.gateway.resolve_intelligence_item = fail_after_side_effect
        event = items["event"]
        with pytest.raises(RuntimeError):
            service.resolve_intelligence_item(
                item_id=event["id"], expected_version=event["version"],
                resolution="confirmed", reason="已核对",
            )
        resolved_event = service.resolve_intelligence_item(
            item_id=event["id"], expected_version=event["version"],
            resolution="confirmed", reason="已核对",
        )
        assert resolved_event["status"] == "confirmed"

        schedule = items["schedule"]
        with pytest.raises(RuntimeError):
            service.resolve_intelligence_item(
                item_id=schedule["id"], expected_version=schedule["version"],
                resolution="confirmed", reason="已核对",
            )
        resolved_schedule = service.resolve_intelligence_item(
            item_id=schedule["id"], expected_version=schedule["version"],
            resolution="confirmed", reason="已核对",
        )
        assert resolved_schedule["status"] == "confirmed"

        with client.app.state.database.session_factory() as session:
            event_count = session.scalar(
                select(func.count()).select_from(ApplicationEventModel).where(
                    ApplicationEventModel.application_id == application["id"],
                    ApplicationEventModel.idempotency_key
                    == f"mail-intelligence:{event['id']}",
                )
            )
            task_count = session.scalar(
                select(func.count()).select_from(CareerTaskModel).where(
                    CareerTaskModel.source_key == f"mail-intelligence:{schedule['id']}"
                )
            )
            assert event_count == 1
            assert task_count == 1
