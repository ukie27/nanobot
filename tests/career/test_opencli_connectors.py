from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient

from nanobot.career.api import create_app
from nanobot.career.domain.connectors import ConnectorError
from nanobot.career.infrastructure.connectors import OpenCliError, OpenCliProcessRunner
from nanobot.career.infrastructure.database import Database
from nanobot.career.infrastructure.database.backup import database_revision
from nanobot.career.infrastructure.database.connector_gateway import SqlAlchemyConnectorGateway
from nanobot.career.infrastructure.database.migrations import alembic_config
from nanobot.career.infrastructure.settings import CareerSettings


class FakeOpenCliRunner:
    def __init__(self) -> None:
        self.description = "负责 Python、FastAPI 服务开发。"
        self.invalid = False
        self.calls: list[str] = []

    def version(self) -> str:
        return "1.8.6"

    def boss_status(self, *, profile: str) -> dict:
        self.calls.append(f"status:{profile}")
        return {"logged_in": True, "site": "boss", "user_type": "geek"}

    def boss_login(self, *, profile: str, timeout: int = 300) -> dict:
        self.calls.append(f"login:{profile}:{timeout}")
        return {"status": "login_complete", "logged_in": True}

    def boss_search(self, *, profile: str, query: str, city: str, limit: int) -> list[dict]:
        self.calls.append(f"search:{profile}:{query}:{city}:{limit}")
        if self.invalid:
            return [{"name": "broken", "url": ""}]
        return [
            {
                "name": "Python 后端工程师",
                "company": "示例科技",
                "area": "上海",
                "security_id": "security-1",
                "url": "https://www.zhipin.com/job_detail/job-1.html",
            }
        ]

    def boss_detail(self, *, profile: str, security_id: str) -> dict:
        self.calls.append(f"detail:{profile}:{security_id}")
        return {
            "name": "Python 后端工程师",
            "company": "示例科技",
            "city": "上海",
            "district": "浦东新区",
            "salary": "20-30K",
            "experience": "3-5年",
            "degree": "本科",
            "skills": "Python,FastAPI,SQL",
            "description": self.description,
            "url": "https://www.zhipin.com/job_detail/job-1.html",
        }


def _client(tmp_path: Path) -> tuple[TestClient, FakeOpenCliRunner]:
    client = TestClient(create_app(CareerSettings(data_dir=tmp_path / "career")))
    client.__enter__()
    runner = FakeOpenCliRunner()
    client.app.state.connector_service.runner = runner
    return client, runner


def _enable(client: TestClient) -> None:
    response = client.put(
        "/api/v1/connectors/boss",
        json={
            "enabled": True,
            "profile_alias": "career",
            "search_query": "Python",
            "city": "上海",
            "result_limit": 10,
            "schedule_enabled": True,
            "schedule_times": ["09:00", "18:00"],
            "timezone": "Asia/Shanghai",
        },
    )
    assert response.status_code == 200, response.text


def test_boss_health_login_scan_idempotency_and_versioning(tmp_path: Path) -> None:
    client, runner = _client(tmp_path)
    try:
        _enable(client)
        health = client.post("/api/v1/connectors/boss/health", json={})
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"
        assert health.json()["opencli_version"] == "1.8.6"
        assert client.post("/api/v1/connectors/boss/login", json={"timeout": 60}).status_code == 200

        first = client.post("/api/v1/connectors/boss/scan", json={})
        assert first.status_code == 200, first.text
        assert first.json()["created_count"] == 1
        second = client.post("/api/v1/connectors/boss/scan", json={})
        assert second.json()["duplicate_count"] == 1
        runner.description = "负责 Python、FastAPI、PostgreSQL 与 Redis 服务开发。"
        third = client.post("/api/v1/connectors/boss/scan", json={})
        assert third.json()["updated_count"] == 1

        jobs = client.get("/api/v1/job-posts").json()["items"]
        assert len(jobs) == 1
        detail = client.get(f"/api/v1/job-posts/{jobs[0]['id']}").json()
        assert detail["version"] == 2
        assert detail["sources"][0]["source_type"] == "opencli_boss"
        assert any(call.startswith("search:career:Python:上海:10") for call in runner.calls)
    finally:
        client.__exit__(None, None, None)


def test_invalid_schema_is_quarantined_and_does_not_pollute_job_pool(tmp_path: Path) -> None:
    client, runner = _client(tmp_path)
    try:
        _enable(client)
        runner.invalid = True
        response = client.post("/api/v1/connectors/boss/scan", json={})
        assert response.status_code == 200
        assert response.json()["status"] == "partial"
        assert response.json()["quarantined_count"] == 1
        assert client.get("/api/v1/job-posts").json()["total"] == 0
        connector = client.get("/api/v1/connectors/boss").json()
        assert connector["quarantine"][0]["error_code"] == "schema_invalid"
    finally:
        client.__exit__(None, None, None)


def test_profile_concurrency_lock(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    settings.ensure_directories()
    command.upgrade(alembic_config(settings), "head")
    database = Database(settings)
    try:
        gateway = SqlAlchemyConnectorGateway(database.session_factory)
        gateway.start_run(trigger_type="manual")
        with pytest.raises(RuntimeError, match="已有扫描"):
            gateway.start_run(trigger_type="manual")
    finally:
        database.close()


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (2, "invalid_argument"),
        (69, "bridge_unavailable"),
        (75, "temporary_timeout"),
        (77, "requires_login"),
        (78, "bridge_unavailable"),
        (1, "execution_failed"),
    ],
)
def test_opencli_exit_code_mapping(
    monkeypatch: pytest.MonkeyPatch, exit_code: int, expected: str
) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], exit_code, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = OpenCliProcessRunner("opencli.exe")
    with pytest.raises(OpenCliError) as caught:
        runner.boss_status(profile="career")
    assert caught.value.code == expected


def test_opencli_argv_and_write_command_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured.update({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, '[{"logged_in":true}]', "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = OpenCliProcessRunner("opencli.exe")
    runner.boss_status(profile="career")
    assert captured["argv"] == [
        "opencli.exe",
        "--profile",
        "career",
        "boss",
        "whoami",
        "-f",
        "json",
    ]
    assert captured["shell"] is False
    with pytest.raises(OpenCliError) as caught:
        runner._run("career", "send", [])
    assert caught.value.code == ConnectorError.COMMAND_DENIED


def test_upgrade_from_part5_creates_backup_and_connector_schema(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    settings.ensure_directories()
    command.upgrade(alembic_config(settings), "20260724_0006")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/connectors/boss").status_code == 200
    assert database_revision(settings.database_path) == "20260724_0010"
    assert list(settings.backups_dir.glob("*pre-202607240010.sqlite3"))
    with sqlite3.connect(settings.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"connector_configs", "sync_runs", "source_events", "sync_cursors"} <= tables
