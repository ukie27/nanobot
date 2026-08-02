from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from fastapi.testclient import TestClient

from career_console.domain.recommendations import JobRecommendationResult
from career_console.infrastructure.database.backup import database_revision
from career_console.infrastructure.database.migrations import alembic_config
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


class _RecommendationAnalyzer:
    name = "test_recommendation"
    provider = None
    model = "test"

    def analyze(self, *, context: dict) -> JobRecommendationResult:
        fact_id = context["confirmedFacts"][0]["id"]
        return JobRecommendationResult.model_validate(
            {
                "schemaVersion": "daily_job_recommendation.v1",
                "decision": "recommend",
                "score": 90,
                "priority": "high",
                "summary": "岗位与已确认事实匹配。",
                "matchedDirections": ["Python 后端"],
                "strengths": ["Python"],
                "gaps": [],
                "hardGateFailures": [],
                "preferenceReasons": ["方向匹配"],
                "actionSuggestion": "加入投递计划并准备材料。",
                "assessments": [
                    {
                        "requirementId": item["id"],
                        "decision": "matched",
                        "evidenceFactIds": [fact_id],
                        "transferableFactIds": [],
                        "rationale": "已确认事实支持该要求。",
                    }
                    for item in context["requirements"]
                ],
            }
        )


def _confirmed_fact(client: TestClient) -> None:
    for category, field_key, value in [
        ("skill", "technical_skills", "熟练使用 Python 和 SQL"),
        ("project", "achievement", "负责后端服务开发并完成稳定交付"),
    ]:
        created = client.post(
            "/api/v1/facts",
            json={
                "category": category,
                "field_key": field_key,
                "value": value,
                "source_note": "application test",
            },
        ).json()
        response = client.post(
            f"/api/v1/facts/{created['id']}/confirm",
            json={"expected_version": created["version"], "reason": "verified"},
        )
        assert response.status_code == 200


def _job(
    client: TestClient,
    *,
    title: str = "Python 后端工程师",
    company: str = "示例科技",
) -> dict:
    response = client.post(
        "/api/v1/job-posts/import-text",
        json={
            "name": "application JD",
            "text": f"职位：{title}\n公司：{company}\n任职要求\n- 熟练 Python 和 SQL",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _final_material(
    client: TestClient,
    job_id: str,
    *,
    name: str = "申请快照简历",
    resume_id: str | None = None,
) -> dict:
    generated = client.post(
        "/api/v1/materials",
        json={
            "job_post_id": job_id,
            "material_type": "resume",
            "name": name,
            **({"resume_id": resume_id} if resume_id else {}),
        },
    )
    assert generated.status_code == 201, generated.text
    material = generated.json()
    finalized = client.post(
        f"/api/v1/materials/{material['id']}/finalize",
        json={"expected_version": material["version"]},
    )
    assert finalized.status_code == 200, finalized.text
    return finalized.json()


def test_application_event_stream_material_snapshot_and_idempotency(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        job = _job(client)
        material = _final_material(client, job["id"])

        created = client.post("/api/v1/applications", json={"job_post_id": job["id"]})
        assert created.status_code == 201, created.text
        application = created.json()
        assert application["current_status"] == "preparing_materials"
        duplicate = client.post("/api/v1/applications", json={"job_post_id": job["id"]})
        assert duplicate.json()["id"] == application["id"]

        unbound = client.post(
            f"/api/v1/applications/{application['id']}/submit",
            json={
                "expected_version": application["version"],
                "resume_version_id": material["current_version"]["id"],
                "command_id": "unbound-submit",
            },
        )
        assert unbound.status_code == 422
        assert unbound.json()["code"] == "invalid_application_transition"

        direct_ready = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "expected_version": application["version"],
                "target_status": "ready_to_apply",
                "command_id": "direct-ready",
            },
        )
        assert direct_ready.status_code == 422
        assert direct_ready.json()["code"] == "application_resume_binding_required"

        bound = client.post(
            f"/api/v1/applications/{application['id']}/resume-bindings",
            json={
                "expected_version": application["version"],
                "command_id": "bind-resume",
                "resume_version_id": material["current_version"]["id"],
                "use_default": False,
                "source": "user",
                "reason": "使用已定稿岗位简历",
            },
        )
        assert bound.status_code == 200, bound.text
        application = bound.json()
        assert application["current_status"] == "ready_to_apply"
        assert application["active_resume_binding"]["resume_version_id"] == (
            material["current_version"]["id"]
        )

        direct_submit = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "expected_version": application["version"],
                "target_status": "submitted",
                "command_id": "direct-submit",
            },
        )
        assert direct_submit.status_code == 422
        assert direct_submit.json()["code"] == (
            "application_submission_confirmation_required"
        )

        mismatch = client.post(
            f"/api/v1/applications/{application['id']}/submit",
            json={
                "expected_version": application["version"],
                "resume_version_id": "00000000-0000-0000-0000-000000000000",
                "command_id": "wrong-resume",
            },
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["code"] == "application_resume_confirmation_mismatch"

        submitted_at = datetime.now(UTC) - timedelta(days=1)
        payload = {
            "expected_version": application["version"],
            "resume_version_id": material["current_version"]["id"],
            "occurred_at": submitted_at.isoformat(),
            "note": "官网提交",
            "command_id": "submit-command",
        }
        submitted = client.post(f"/api/v1/applications/{application['id']}/submit", json=payload)
        assert submitted.status_code == 200, submitted.text
        application = submitted.json()
        assert application["current_status"] == "submitted"
        assert application["material_count"] == 1
        assert application["active_resume_binding"]["status"] == "locked"
        snapshot = application["material_snapshots"][0]
        assert snapshot["resume_version_id"] == material["current_version"]["id"]
        assert snapshot["content_hash"] == material["current_version"]["content_hash"]
        assert snapshot["rendered_text"] == material["current_version"]["rendered_text"]
        assert snapshot["export_sha256"] == material["export"]["sha256"]

        locked = client.post(
            f"/api/v1/applications/{application['id']}/resume-bindings",
            json={
                "expected_version": application["version"],
                "command_id": "replace-after-submit",
                "resume_version_id": material["current_version"]["id"],
                "use_default": False,
                "source": "user",
            },
        )
        assert locked.status_code == 422
        assert locked.json()["code"] == "application_resume_binding_locked"

        repeated = client.post(f"/api/v1/applications/{application['id']}/submit", json=payload)
        assert repeated.status_code == 200
        assert repeated.json()["version"] == application["version"]
        assert len(repeated.json()["material_snapshots"]) == 1

        confirmed = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "expected_version": application["version"],
                "target_status": "application_confirmed",
                "note": "收到网申确认",
                "command_id": "confirmation-command",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        application = confirmed.json()

        illegal = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "expected_version": application["version"],
                "target_status": "submitted",
                "command_id": "illegal-command",
            },
        )
        assert illegal.status_code == 422
        assert illegal.json()["code"] == (
            "application_submission_confirmation_required"
        )

        written = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "expected_version": application["version"],
                "target_status": "written_test",
                "occurred_at": datetime.now(UTC).isoformat(),
                "note": "线上笔试",
                "command_id": "written-command",
            },
        ).json()
        interviewed = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "expected_version": written["version"],
                "target_status": "interview",
                "occurred_at": datetime.now(UTC).isoformat(),
                "note": "技术一面",
                "command_id": "interview-command",
            },
        ).json()
        interview_event = next(
            item for item in interviewed["events"] if item["event_type"] == "interview_scheduled"
        )
        corrected_time = datetime.now(UTC) + timedelta(days=2)
        corrected = client.post(
            f"/api/v1/applications/{application['id']}/events/{interview_event['id']}/corrections",
            json={
                "expected_version": interviewed["version"],
                "occurred_at": corrected_time.isoformat(),
                "note": "更正为周五技术一面",
                "command_id": "correction-command",
            },
        )
        assert corrected.status_code == 200, corrected.text
        application = corrected.json()
        assert application["current_status"] == "interview"
        original = next(
            item for item in application["events"] if item["id"] == interview_event["id"]
        )
        correction = next(
            item for item in application["events"] if item["event_type"] == "event_corrected"
        )
        assert original["superseded"] is True
        assert correction["supersedes_event_id"] == original["id"]
        derived_tasks = client.get("/api/v1/tasks").json()["items"]
        interview_task = next(
            item for item in derived_tasks if item["source_event_id"] == interview_event["id"]
        )
        assert interview_task["task_type"] == "interview"
        assert interview_task["notes"] == "更正为周五技术一面"
        assert datetime.fromisoformat(interview_task["due_at"]) == corrected_time

        newer_material = _final_material(
            client,
            job["id"],
            name=material["name"],
            resume_id=material["resume_id"],
        )
        assert newer_material["current_version"]["id"] != snapshot["resume_version_id"]
        interview = client.post(
            "/api/v1/interviews",
            json={
                "application_id": application["id"],
                "round_type": "technical",
                "scheduled_at": corrected_time.isoformat(),
                "timezone": "Asia/Shanghai",
            },
        )
        assert interview.status_code == 201, interview.text
        preparation = client.post(
            f"/api/v1/interviews/{interview.json()['id']}/preparation"
        )
        assert preparation.status_code == 201, preparation.text
        pack = preparation.json()
        assert pack["material_snapshot_ids"] == [snapshot["id"]]
        assert pack["content"]["submitted_materials"][0]["content_hash"] == (
            snapshot["content_hash"]
        )

        stale = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "expected_version": interviewed["version"],
                "target_status": "offer",
                "command_id": "stale-command",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "version_conflict"


def test_finalizing_material_requires_explicit_binding_to_become_ready(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        job = _job(client)
        created = client.post("/api/v1/applications", json={"job_post_id": job["id"]})
        assert created.status_code == 201, created.text
        assert created.json()["current_status"] == "preparing_materials"

        material = _final_material(client, job["id"])
        refreshed = client.get(f"/api/v1/applications/{created.json()['id']}")

        assert refreshed.status_code == 200, refreshed.text
        application = refreshed.json()
        assert application["current_status"] == "preparing_materials"
        assert application["version"] == 1
        assert application["available_final_materials"][0]["id"] == material["id"]
        assert application["active_resume_binding"] is None

        bound = client.post(
            f"/api/v1/applications/{application['id']}/resume-bindings",
            json={
                "expected_version": application["version"],
                "command_id": "bind-after-finalize",
                "resume_version_id": material["current_version"]["id"],
                "use_default": False,
                "source": "user",
            },
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["current_status"] == "ready_to_apply"
        assert bound.json()["events"][-1]["to_status"] == "ready_to_apply"


def test_recommendation_acceptance_creates_preparing_application_once(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        job = _job(client)
        service = client.app.state.recommendation_service
        service.analyzer = _RecommendationAnalyzer()
        recommendation = service.analyze(job["id"])

        accepted = client.post(
            f"/api/v1/job-recommendations/{recommendation['id']}/accept",
            json={
                "expected_version": recommendation["version"],
                "command_id": "accept-recommendation",
            },
        )
        assert accepted.status_code == 200, accepted.text
        result = accepted.json()
        assert result["status"] == "accepted"
        application = client.get(
            f"/api/v1/applications/{result['application_id']}"
        ).json()
        assert application["current_status"] == "preparing_materials"
        assert application["material_snapshots"] == []
        assert all(
            item["event_type"] != "application_submitted"
            for item in application["events"]
        )

        repeated = client.post(
            f"/api/v1/job-recommendations/{recommendation['id']}/accept",
            json={
                "expected_version": recommendation["version"],
                "command_id": "accept-recommendation-retry",
            },
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["application_id"] == application["id"]
        same_job = [
            item
            for item in client.get("/api/v1/applications").json()["items"]
            if item["job_post_id"] == job["id"]
        ]
        assert len(same_job) == 1


def test_resume_binding_history_default_stability_and_cross_application_reuse(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        first_job = _job(client)
        second_job = _job(
            client,
            title="数据平台工程师",
            company="示例云计算",
        )
        first_resume = _final_material(
            client,
            first_job["id"],
            name="通用后端简历",
        )
        second_resume = _final_material(
            client,
            first_job["id"],
            name="平台工程简历",
        )
        default = client.put(
            "/api/v1/resumes/default",
            json={"resume_id": first_resume["resume_id"], "expected_version": None},
        )
        assert default.status_code == 200, default.text

        first_application = client.post(
            "/api/v1/applications", json={"job_post_id": first_job["id"]}
        ).json()
        first_application = client.post(
            f"/api/v1/applications/{first_application['id']}/resume-bindings",
            json={
                "expected_version": first_application["version"],
                "command_id": "bind-current-default",
                "resume_version_id": None,
                "use_default": True,
                "source": "user",
            },
        ).json()
        first_version_id = first_resume["current_version"]["id"]
        assert first_application["active_resume_binding"]["resume_version_id"] == (
            first_version_id
        )

        changed_default = client.put(
            "/api/v1/resumes/default",
            json={
                "resume_id": second_resume["resume_id"],
                "expected_version": default.json()["default_version"],
            },
        )
        assert changed_default.status_code == 200, changed_default.text
        unchanged = client.get(
            f"/api/v1/applications/{first_application['id']}"
        ).json()
        assert unchanged["active_resume_binding"]["resume_version_id"] == first_version_id

        replaced = client.post(
            f"/api/v1/applications/{unchanged['id']}/resume-bindings",
            json={
                "expected_version": unchanged["version"],
                "command_id": "replace-before-submit",
                "resume_version_id": second_resume["current_version"]["id"],
                "use_default": False,
                "source": "user",
                "reason": "更贴合平台岗位",
            },
        )
        assert replaced.status_code == 200, replaced.text
        bindings = replaced.json()["resume_bindings"]
        assert [item["status"] for item in bindings] == ["replaced", "active"]
        assert bindings[0]["replaced_by_binding_id"] == bindings[1]["id"]

        second_application = client.post(
            "/api/v1/applications", json={"job_post_id": second_job["id"]}
        ).json()
        reused = client.post(
            f"/api/v1/applications/{second_application['id']}/resume-bindings",
            json={
                "expected_version": second_application["version"],
                "command_id": "reuse-first-version",
                "resume_version_id": first_version_id,
                "use_default": False,
                "source": "user",
            },
        )
        assert reused.status_code == 200, reused.text
        assert reused.json()["active_resume_binding"]["resume_version_id"] == (
            first_version_id
        )


def test_event_proposal_review_audit_and_archive(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        job = _job(client)
        material = _final_material(client, job["id"])
        application = client.post("/api/v1/applications", json={"job_post_id": job["id"]}).json()
        application = client.post(
            f"/api/v1/applications/{application['id']}/resume-bindings",
            json={
                "expected_version": application["version"],
                "command_id": "bind",
                "resume_version_id": material["current_version"]["id"],
                "use_default": False,
                "source": "user",
            },
        ).json()
        application = client.post(
            f"/api/v1/applications/{application['id']}/submit",
            json={
                "expected_version": application["version"],
                "resume_version_id": material["current_version"]["id"],
                "command_id": "submit",
            },
        ).json()

        proposal = client.post(
            f"/api/v1/applications/{application['id']}/event-proposals",
            json={
                "proposed_status": "interview",
                "note": "Connector 候选：面试邀请",
                "source": "test_connector",
                "source_ref": "message-redacted-1",
            },
        )
        assert proposal.status_code == 201, proposal.text
        proposed = proposal.json()
        assert proposed["task_status"] == "open"
        duplicate_proposal = client.post(
            f"/api/v1/applications/{application['id']}/event-proposals",
            json={
                "proposed_status": "interview",
                "note": "Connector 重试不应重复创建",
                "source": "test_connector",
                "source_ref": "message-redacted-1",
            },
        )
        assert duplicate_proposal.status_code == 201
        assert duplicate_proposal.json()["id"] == proposed["id"]
        tasks = client.get("/api/v1/application-review-tasks").json()
        assert tasks["total"] == 1
        unified_review = client.get("/api/v1/runtime/reviews").json()["items"][0]
        assert unified_review["target_url"] == (
            f"/applications/{application['id']}?review={proposed['id']}"
        )

        resolved = client.post(
            f"/api/v1/application-event-proposals/{proposed['id']}/resolve",
            json={
                "expected_version": proposed["version"],
                "application_expected_version": application["version"],
                "resolution": "confirmed",
                "reason": "已核对邀请内容",
                "command_id": "confirm-proposal",
            },
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["resolution"] == "confirmed"
        assert resolved.json()["resolved_by"] == "user"
        application = client.get(f"/api/v1/applications/{application['id']}").json()
        assert application["current_status"] == "interview"
        assert any(item["proposal_id"] == proposed["id"] for item in application["events"])

        rejected_proposal = client.post(
            f"/api/v1/applications/{application['id']}/event-proposals",
            json={"proposed_status": "offer", "note": "误判的 Offer 候选"},
        ).json()
        rejected = client.post(
            f"/api/v1/application-event-proposals/{rejected_proposal['id']}/resolve",
            json={
                "expected_version": rejected_proposal["version"],
                "application_expected_version": application["version"],
                "resolution": "rejected",
                "reason": "实际只是流程通知",
                "command_id": "reject-proposal",
            },
        )
        assert rejected.status_code == 200
        assert rejected.json()["resolution"] == "rejected"
        unchanged = client.get(f"/api/v1/applications/{application['id']}").json()
        assert unchanged["current_status"] == "interview"

        archive = client.post(
            f"/api/v1/applications/{application['id']}/archive",
            json={
                "expected_version": application["version"],
                "note": "流程结束",
                "command_id": "archive",
            },
        )
        assert archive.status_code == 200, archive.text
        assert archive.json()["current_status"] == "archived"
        assert archive.json()["archived_at"] is not None
        later = client.post("/api/v1/applications", json={"job_post_id": job["id"]})
        assert later.status_code == 201, later.text
        assert later.json()["id"] != application["id"]
        assert later.json()["current_status"] == "preparing_materials"


def test_upgrade_from_part3_creates_backup_and_application_schema(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    settings.ensure_directories()
    command.upgrade(alembic_config(settings), "20260723_0004")
    assert database_revision(settings.database_path) == "20260723_0004"

    with TestClient(create_app(settings)) as client:
        doctor = client.get("/api/v1/system/status")
        assert doctor.status_code == 200
        assert doctor.json()["database_revision"] == "20260801_0034"

    assert list(settings.backups_dir.glob("*pre-202608010034.sqlite3"))
    with sqlite3.connect(settings.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        review_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(review_tasks)").fetchall()
        }
    assert {
        "applications",
        "application_events",
        "application_material_snapshots",
        "application_event_proposals",
        "application_resume_bindings",
        "resume_defaults",
    } <= tables
    assert {"resolution", "resolution_reason", "resolved_by"} <= review_columns


def test_application_resume_lifecycle_migration_round_trip(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    settings.ensure_directories()
    config = alembic_config(settings)

    command.upgrade(config, "20260729_0031")
    assert database_revision(settings.database_path) == "20260729_0031"

    command.downgrade(config, "20260728_0030")
    assert database_revision(settings.database_path) == "20260728_0030"
    with sqlite3.connect(settings.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "application_resume_bindings" not in tables
    assert "resume_defaults" not in tables

    command.upgrade(config, "20260729_0031")
    assert database_revision(settings.database_path) == "20260729_0031"
    with sqlite3.connect(settings.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"application_resume_bindings", "resume_defaults"} <= tables
