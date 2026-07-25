from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from fastapi.testclient import TestClient

from nanobot.career.api import create_app
from nanobot.career.infrastructure.database.backup import database_revision
from nanobot.career.infrastructure.database.migrations import alembic_config
from nanobot.career.infrastructure.settings import CareerSettings


def _confirmed_fact(client: TestClient) -> None:
    created = client.post(
        "/api/v1/facts",
        json={
            "category": "skill",
            "field_key": "technical_skills",
            "value": "熟练使用 Python 和 SQL",
            "source_note": "application test",
        },
    ).json()
    response = client.post(
        f"/api/v1/facts/{created['id']}/confirm",
        json={"expected_version": created["version"], "reason": "verified"},
    )
    assert response.status_code == 200


def _job(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/job-posts/import-text",
        json={
            "name": "application JD",
            "text": "职位：Python 后端工程师\n公司：示例科技\n任职要求\n- 熟练 Python 和 SQL",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _final_material(client: TestClient, job_id: str) -> dict:
    generated = client.post(
        "/api/v1/materials",
        json={"job_post_id": job_id, "material_type": "resume", "name": "申请快照简历"},
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
        assert application["current_status"] == "ready_to_apply"
        duplicate = client.post("/api/v1/applications", json={"job_post_id": job["id"]})
        assert duplicate.json()["id"] == application["id"]

        submitted_at = datetime.now(UTC) - timedelta(days=1)
        payload = {
            "expected_version": application["version"],
            "material_ids": [material["id"]],
            "occurred_at": submitted_at.isoformat(),
            "note": "官网提交",
            "command_id": "submit-command",
        }
        submitted = client.post(f"/api/v1/applications/{application['id']}/submit", json=payload)
        assert submitted.status_code == 200, submitted.text
        application = submitted.json()
        assert application["current_status"] == "submitted"
        assert application["material_count"] == 1
        snapshot = application["material_snapshots"][0]
        assert snapshot["content_hash"] == material["current_version"]["content_hash"]
        assert snapshot["rendered_text"] == material["current_version"]["rendered_text"]
        assert snapshot["export_sha256"] == material["export"]["sha256"]

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
        assert illegal.json()["code"] == "invalid_application_transition"

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


def test_event_proposal_review_audit_and_archive(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client)
        job = _job(client)
        material = _final_material(client, job["id"])
        application = client.post("/api/v1/applications", json={"job_post_id": job["id"]}).json()
        application = client.post(
            f"/api/v1/applications/{application['id']}/submit",
            json={
                "expected_version": application["version"],
                "material_ids": [material["id"]],
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


def test_upgrade_from_part3_creates_backup_and_application_schema(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    settings.ensure_directories()
    command.upgrade(alembic_config(settings), "20260723_0004")
    assert database_revision(settings.database_path) == "20260723_0004"

    with TestClient(create_app(settings)) as client:
        doctor = client.get("/api/v1/system/status")
        assert doctor.status_code == 200
        assert doctor.json()["database_revision"] == "20260724_0010"

    assert list(settings.backups_dir.glob("*pre-202607240010.sqlite3"))
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
    } <= tables
    assert {"resolution", "resolution_reason", "resolved_by"} <= review_columns
