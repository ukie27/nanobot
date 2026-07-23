from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from nanobot.career.api import create_app
from nanobot.career.infrastructure.database import Database
from nanobot.career.infrastructure.database.migrations import (
    current_revision,
    head_revision,
    upgrade_to_head,
)
from nanobot.career.infrastructure.database.models import BackgroundJobModel
from nanobot.career.infrastructure.jobs import BackgroundJobService
from nanobot.career.infrastructure.logging import redact
from nanobot.career.infrastructure.runtime import CareerInstanceLock
from nanobot.career.infrastructure.runtime.instance_lock import InstanceAlreadyRunningError
from nanobot.career.infrastructure.settings import CareerSettings


def settings_at(path: Path) -> CareerSettings:
    return CareerSettings(data_dir=path)


def test_empty_unicode_data_directory_migrates_to_head(tmp_path: Path) -> None:
    settings = settings_at(tmp_path / "中文 数据目录")
    upgrade_to_head(settings)
    database = Database(settings)
    try:
        assert settings.database_path.is_file()
        assert current_revision(database) == head_revision(settings)
        pragmas = database.pragmas()
        assert str(pragmas["journal_mode"]).lower() == "wal"
        assert pragmas["foreign_keys"] == 1
        assert pragmas["busy_timeout"] == 5000
        assert pragmas["synchronous"] == 1
    finally:
        database.close()


def test_health_status_and_empty_jobs_api(tmp_path: Path) -> None:
    settings = settings_at(tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready", headers={"X-Correlation-ID": "acceptance-test"})
        status = client.get("/api/v1/system/status")
        jobs = client.get("/api/v1/jobs")
        missing = client.get("/api/v1/does-not-exist")

    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert ready.status_code == 200
    assert ready.headers["X-Correlation-ID"] == "acceptance-test"
    assert ready.json()["revision"] == head_revision(settings)
    assert status.json()["health"] == "ready"
    assert status.json()["paths"]["data_dir"] == str(settings.data_dir)
    assert jobs.json() == {"items": [], "total": 0}
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
    assert missing.json()["code"] == "http_error"


def test_sensitive_log_values_are_redacted() -> None:
    output = redact("api_key=super-secret email=person@example.com token: abc123")
    assert "super-secret" not in output
    assert "person@example.com" not in output
    assert "abc123" not in output
    assert output.count("[REDACTED]") == 2


def test_instance_lock_rejects_second_server(tmp_path: Path) -> None:
    first = CareerInstanceLock(tmp_path / "runtime" / "career.lock")
    second = CareerInstanceLock(tmp_path / "runtime" / "career.lock")
    first.acquire()
    try:
        with pytest.raises(InstanceAlreadyRunningError):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_expired_job_lease_is_recovered(tmp_path: Path) -> None:
    settings = settings_at(tmp_path / "career")
    upgrade_to_head(settings)
    database = Database(settings)
    now = datetime.now(UTC)
    try:
        with database.session_factory() as session:
            session.add(
                BackgroundJobModel(
                    id="00000000-0000-0000-0000-000000000001",
                    job_type="test.only",
                    payload_json="{}",
                    status="running",
                    priority=0,
                    run_after=now - timedelta(minutes=2),
                    attempt_count=1,
                    max_attempts=3,
                    lease_owner="dead-worker",
                    lease_expires_at=now - timedelta(minutes=1),
                    created_at=now - timedelta(minutes=3),
                )
            )
            session.commit()

        service = BackgroundJobService(database.session_factory)
        assert service.recover_expired_leases(now=now) == 1
        with database.session_factory() as session:
            job = session.scalar(select(BackgroundJobModel))
            assert job is not None
            assert job.status == "pending"
            assert job.lease_owner is None
            assert job.last_error_code == "lease_expired"
    finally:
        database.close()


def test_job_enqueue_is_idempotent(tmp_path: Path) -> None:
    settings = settings_at(tmp_path / "career")
    upgrade_to_head(settings)
    database = Database(settings)
    try:
        service = BackgroundJobService(database.session_factory)
        first = service.enqueue("test.only", {"text": "中文"}, idempotency_key="same")
        second = service.enqueue("test.only", {"text": "ignored"}, idempotency_key="same")
        assert first == second
        assert len(service.list_jobs()) == 1
    finally:
        database.close()
