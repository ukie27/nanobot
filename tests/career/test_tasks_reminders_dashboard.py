from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from fastapi.testclient import TestClient

from nanobot.career.api import create_app
from nanobot.career.domain.common.errors import CareerDomainError
from nanobot.career.domain.tasks import next_schedule_run, normalize_due
from nanobot.career.infrastructure.database import Database
from nanobot.career.infrastructure.database.backup import database_revision
from nanobot.career.infrastructure.database.migrations import alembic_config, upgrade_to_head
from nanobot.career.infrastructure.jobs import BackgroundJobService
from nanobot.career.infrastructure.settings import CareerSettings


def _create_task(
    client: TestClient,
    *,
    title: str = "准备技术面试",
    task_type: str = "interview",
    due_at: datetime | None = None,
) -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={
            "title": title,
            "task_type": task_type,
            "due_at": (due_at or datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "timezone": "Asia/Shanghai",
            "notes": "真实任务",
            "priority": 10,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_timezone_and_daily_cron_rules_cover_dst() -> None:
    with pytest.raises(CareerDomainError) as exc:
        normalize_due(datetime(2026, 3, 8, 2, 30), "America/New_York")
    assert exc.value.code == "nonexistent_local_time"

    normalized = normalize_due(datetime(2026, 7, 24, 10, 0), "Asia/Shanghai")
    assert normalized == datetime(2026, 7, 24, 2, 0, tzinfo=UTC)
    next_run = next_schedule_run(
        "cron",
        datetime(2026, 11, 1, 5, 0, tzinfo=UTC),
        cron_expression="30 9 * * *",
        timezone="America/New_York",
    )
    assert next_run is not None
    assert next_run.astimezone(ZoneInfo("America/New_York")).hour == 9


def test_task_reminder_outbox_notification_and_lifecycle(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        due_at = datetime.now(UTC) + timedelta(hours=2)
        task = _create_task(client, due_at=due_at)
        reminder = client.post(f"/api/v1/tasks/{task['id']}/reminders", json={"offset_minutes": 60})
        assert reminder.status_code == 201, reminder.text
        reminder_data = reminder.json()
        duplicate = client.post(
            f"/api/v1/tasks/{task['id']}/reminders", json={"offset_minutes": 60}
        )
        assert duplicate.json()["id"] == reminder_data["id"]

        trigger_at = datetime.fromisoformat(reminder_data["scheduled_for"]) + timedelta(seconds=1)
        first_run = client.post("/api/v1/scheduler/run-due", json={"now": trigger_at.isoformat()})
        assert first_run.status_code == 200, first_run.text
        assert first_run.json()["reminders_triggered"] == 1
        second_run = client.post("/api/v1/scheduler/run-due", json={"now": trigger_at.isoformat()})
        assert second_run.json()["reminders_triggered"] == 0

        notifications = client.get("/api/v1/notifications").json()
        assert notifications["total"] == 1
        notification = notifications["items"][0]
        assert notification["reminder_id"] == reminder_data["id"]
        read = client.post(f"/api/v1/notifications/{notification['id']}/read")
        assert read.json()["status"] == "read"

        completed = client.post(
            f"/api/v1/tasks/{task['id']}/complete",
            json={"expected_version": task["version"]},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        stale = client.post(
            f"/api/v1/tasks/{task['id']}/cancel",
            json={"expected_version": task["version"]},
        )
        assert stale.status_code in {409, 422}


def test_postpone_cancel_conflicts_dashboard_and_lightweight_sse(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        base = datetime.now(UTC) + timedelta(hours=4)
        first = _create_task(client, title="技术一面", task_type="interview", due_at=base)
        second = _create_task(
            client, title="线上笔试", task_type="written_test", due_at=base + timedelta(minutes=20)
        )
        reminder = client.post(
            f"/api/v1/tasks/{first['id']}/reminders", json={"offset_minutes": 1440}
        ).json()
        new_due = base + timedelta(days=1)
        postponed = client.post(
            f"/api/v1/tasks/{first['id']}/postpone",
            json={
                "expected_version": first["version"],
                "due_at": new_due.isoformat(),
                "timezone": "Asia/Shanghai",
            },
        )
        assert postponed.status_code == 200, postponed.text
        assert postponed.json()["version"] == first["version"] + 1
        new_reminder = next(
            item for item in postponed.json()["reminders"] if item["id"] == reminder["id"]
        )
        assert datetime.fromisoformat(new_reminder["scheduled_for"]) > datetime.fromisoformat(
            reminder["scheduled_for"]
        )

        second_due = base + timedelta(minutes=25)
        third = _create_task(client, title="HR 面试", task_type="interview", due_at=second_due)
        dashboard = client.get("/api/v1/dashboard").json()
        assert dashboard["conflict_count"] >= 1
        task_list = client.get("/api/v1/tasks").json()["items"]
        second_view = next(item for item in task_list if item["id"] == second["id"])
        assert third["id"] in second_view["conflict_ids"]
        assert datetime.fromisoformat(third["due_at"]) == second_due

        cancelled = client.post(
            f"/api/v1/tasks/{second['id']}/cancel",
            json={"expected_version": second["version"]},
        )
        assert cancelled.json()["status"] == "cancelled"

        stream = client.get("/api/v1/events/stream")
        assert stream.status_code == 200
        assert "dashboard.changed" in stream.text
        assert "技术一面" not in stream.text
        assert "aggregate_id" in stream.text


def test_background_job_claim_backoff_retry_and_cancel(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    upgrade_to_head(settings)
    database = Database(settings)
    now = datetime.now(UTC)
    try:
        service = BackgroundJobService(database.session_factory)
        job_id = service.enqueue("test.reliable", max_attempts=2)
        claimed = service.claim_next("worker-1", lease_seconds=30, now=now)
        assert claimed is not None and claimed.id == job_id and claimed.attempt_count == 1
        service.fail(job_id, "worker-1", error_code="temporary", now=now)
        assert service.claim_next("worker-1", now=now) is None
        claimed = service.claim_next("worker-1", now=now + timedelta(seconds=3))
        assert claimed is not None and claimed.attempt_count == 2
        service.fail(job_id, "worker-1", error_code="again", now=now + timedelta(seconds=3))
        failed = service.list_jobs()[0]
        assert failed.status == "failed"
        assert service.retry(job_id).status == "pending"
        assert service.cancel(job_id).status == "cancelled"
    finally:
        database.close()


def test_upgrade_from_part4_creates_backup_and_scheduler_schema(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    settings.ensure_directories()
    command.upgrade(alembic_config(settings), "20260724_0005")
    assert database_revision(settings.database_path) == "20260724_0005"
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
    assert database_revision(settings.database_path) == "20260726_0021"
    assert list(settings.backups_dir.glob("*pre-202607260021.sqlite3"))
    with sqlite3.connect(settings.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"career_tasks", "reminders", "schedules", "outbox_events", "notifications"} <= tables
