from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from career_console.domain.common.errors import CareerDomainError
from career_console.domain.mail.intelligence import MailIntelligenceResult
from career_console.infrastructure.database.models import AgentRunModel, ReviewTaskModel
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http.app import create_app


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

        with client.app.state.database.session_factory() as session:
            run = session.scalar(select(AgentRunModel).where(AgentRunModel.task_type == "mail_intelligence"))
            reviews = session.scalars(select(ReviewTaskModel).where(
                ReviewTaskModel.task_type == "mail_intelligence_review"
            )).all()
            assert run is not None and run.status == "succeeded" and run.output_count == 4
            assert run.tool_calls_json == "[]" and run.sensitivity == "sensitive"
            assert len(reviews) == 4
            assert all(item.agent_run_id == run.id for item in reviews)

        item = first.json()["items"][0]
        resolved = client.post(f"/api/v1/mail/intelligence-items/{item['id']}/resolve", json={
            "expected_version": item["version"], "resolution": "confirmed", "reason": "已核对",
        })
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "confirmed"


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
