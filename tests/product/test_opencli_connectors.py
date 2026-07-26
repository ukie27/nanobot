from __future__ import annotations

import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import select

from career_console.domain.connectors import ConnectorError
from career_console.infrastructure.connectors import OpenCliError, OpenCliProcessRunner
from career_console.infrastructure.database import Database
from career_console.infrastructure.database.backup import database_revision
from career_console.infrastructure.database.connector_gateway import (
    SqlAlchemyConnectorGateway,
)
from career_console.infrastructure.database.migrations import alembic_config
from career_console.infrastructure.database.models import SourceEventModel
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


class FakeOpenCliRunner:
    def __init__(self) -> None:
        self.description = "负责 Python、FastAPI 服务开发。"
        self.evaluation = "公开校招项目"
        self.nowcoder_application_url = "https://example.com/apply"
        self.invalid = False
        self.calls: list[str] = []
        self.collected_at = (
            datetime.now(ZoneInfo("Asia/Shanghai")).astimezone(UTC).isoformat()
        )

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

    def nowcoder_schedule(
        self, *, lookback_days: int, limit: int, query: str = ""
    ) -> list[dict]:
        self.calls.append(f"nowcoder:{lookback_days}:{limit}:{query}")
        collected = self.collected_at
        if self.invalid:
            return [{"id": "broken", "source_url": ""}]
        return [
            {
                "id": "895:1210:1784390400000",
                "company_id": "895",
                "company": "网易游戏雷火",
                "batch": "27届秋招",
                "cities": "杭州",
                "careers": "后端开发,测试",
                "industries": "游戏",
                "evaluation": self.evaluation,
                "collected_label": "今日收录",
                "collected_at": collected,
                "updated_at": collected,
                "application_starts_at": collected,
                "application_ends_at": collected,
                "source_url": "https://www.nowcoder.com/enterprise/895?pageSource=5014",
                "announcement_url": "https://example.com/announcement",
                "application_url": self.nowcoder_application_url,
            }
        ]


def _client(tmp_path: Path) -> tuple[TestClient, FakeOpenCliRunner]:
    client = TestClient(create_app(CareerSettings(data_dir=tmp_path / "career")))
    client.__enter__()
    runner = FakeOpenCliRunner()
    client.app.state.connector_service.runner = runner
    client.app.state.nowcoder_connector_service.runner = runner
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


def test_automatic_discovery_is_nowcoder_today_only(tmp_path: Path, monkeypatch) -> None:
    client, runner = _client(tmp_path)
    try:
        _enable(client)
        boss = client.get("/api/v1/connectors/boss").json()
        assert boss["schedule_enabled"] is False
        assert boss["next_scan_at"] is None

        calls_before_boss_run = list(runner.calls)
        assert client.app.state.connector_service.run_due() is None
        assert runner.calls == calls_before_boss_run

        saved = client.put(
            "/api/v1/connectors/nowcoder",
            json={
                "enabled": True,
                "search_query": "",
                "city": "全国",
                "result_limit": 500,
                "schedule_enabled": True,
                "schedule_times": ["09:00"],
            },
        )
        assert saved.status_code == 200, saved.text
        service = client.app.state.nowcoder_connector_service
        monkeypatch.setattr(service.gateway, "due", lambda *, connector_id: True)

        run = service.run_due()
        assert run is not None
        assert run["trigger_type"] == "schedule"
        assert runner.calls[-1] == "nowcoder:0:500:"
    finally:
        client.__exit__(None, None, None)


def test_nowcoder_today_scan_and_manual_lookback_are_separate(tmp_path: Path) -> None:
    client, runner = _client(tmp_path)
    try:
        saved = client.put(
            "/api/v1/connectors/nowcoder",
            json={
                "enabled": True,
                "search_query": "",
                "city": "全国",
                "result_limit": 500,
                "schedule_enabled": True,
                "schedule_times": ["09:00"],
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["timezone"] == "Asia/Shanghai"

        health = client.post("/api/v1/connectors/nowcoder/health", json={})
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        today = client.post(
            "/api/v1/connectors/nowcoder/scan", json={"lookback_days": 0}
        )
        assert today.status_code == 200, today.text
        assert today.json()["created_count"] == 1

        duplicate = client.post(
            "/api/v1/connectors/nowcoder/scan", json={"lookback_days": 0}
        )
        assert duplicate.json()["duplicate_count"] == 1

        runner.evaluation = "公开校招项目，新增技术岗位方向"
        changed = client.post(
            "/api/v1/connectors/nowcoder/scan", json={"lookback_days": 0}
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["updated_count"] == 1

        history = client.post(
            "/api/v1/connectors/nowcoder/scan", json={"lookback_days": 30}
        )
        assert history.status_code == 200, history.text
        assert any(call == "nowcoder:30:500:" for call in runner.calls)

        invalid = client.post(
            "/api/v1/connectors/nowcoder/scan", json={"lookback_days": 31}
        )
        assert invalid.status_code == 422

        with pytest.raises(ValueError, match="自动同步只能"):
            client.app.state.nowcoder_connector_service.scan(
                lookback_days=30, trigger_type="schedule"
            )

        assert client.get("/api/v1/job-posts").json()["total"] == 0
        opportunities = client.get("/api/v1/opportunities").json()
        assert opportunities["total"] == 1
        opportunity = opportunities["items"][0]
        assert opportunity["company"] == "网易游戏雷火"
        assert opportunity["batch"] == "27届秋招"
        assert opportunity["triage_status"] == "new"
        assert opportunity["version"] == 2
        assert opportunity["sources"][0]["external_id"] == "895:1210:1784390400000"

        detail = client.get(f"/api/v1/opportunities/{opportunity['id']}").json()
        assert [item["version_number"] for item in detail["versions"]] == [2, 1]
        followed = client.post(
            f"/api/v1/opportunities/{opportunity['id']}/triage",
            json={"triage_status": "following", "expected_version": 2},
        )
        assert followed.status_code == 200, followed.text
        assert followed.json()["triage_status"] == "following"
        assert followed.json()["version"] == 3
        conflict = client.post(
            f"/api/v1/opportunities/{opportunity['id']}/triage",
            json={"triage_status": "ignored", "expected_version": 2},
        )
        assert conflict.status_code == 409
        assert client.get(
            "/api/v1/opportunities", params={"triage_status": "following"}
        ).json()["total"] == 1
        assert client.get(
            "/api/v1/opportunities", params={"triage_status": "ignored"}
        ).json()["total"] == 0

        with client.app.state.database.session_factory() as session:
            events = session.scalars(select(SourceEventModel)).all()
            assert len(events) == 2
            assert all(event.opportunity_id == opportunity["id"] for event in events)
            assert all(event.job_post_id is None for event in events)

        today_items = client.get(
            "/api/v1/opportunities", params={"today": "true"}
        ).json()
        assert today_items["total"] == 1
        imported = client.post(
            "/api/v1/job-posts/import-text",
            json={
                "name": "网易官网 JD",
                "text": (
                    "职位：Python 后端工程师\n公司：网易游戏雷火\n地点：杭州\n"
                    "任职要求\n- 必须熟练 Python 和 SQL\n- 本科及以上学历"
                ),
                "opportunity_id": opportunity["id"],
            },
        )
        assert imported.status_code == 201, imported.text
        job = imported.json()
        assert job["opportunity_ids"] == [opportunity["id"]]
        duplicate_job = client.post(
            "/api/v1/job-posts/import-text",
            json={
                "name": "网易官网 JD 重复导入",
                "text": (
                    "职位：Python 后端工程师\n公司：网易游戏雷火\n地点：杭州\n"
                    "任职要求\n- 必须熟练 Python 和 SQL\n- 本科及以上学历"
                ),
                "opportunity_id": opportunity["id"],
            },
        )
        assert duplicate_job.status_code == 201, duplicate_job.text
        assert duplicate_job.json()["duplicate"] is True
        linked = client.get(f"/api/v1/opportunities/{opportunity['id']}").json()
        assert len(linked["linked_jobs"]) == 1
        assert linked["linked_jobs"][0]["id"] == job["id"]
        assert linked["linked_jobs"][0]["title"] == "Python 后端工程师"

        application = client.post(
            "/api/v1/applications", json={"job_post_id": job["id"]}
        )
        assert application.status_code == 201, application.text
        assert application.json()["job_post_id"] == job["id"]
        connector = client.get("/api/v1/connectors/nowcoder").json()
        assert connector["automatic_scope"] == "today"
        assert connector["manual_lookback_options"] == [0, 7, 14, 30]
    finally:
        client.__exit__(None, None, None)


def test_nowcoder_quarantines_unsafe_application_url(tmp_path: Path) -> None:
    client, runner = _client(tmp_path)
    try:
        saved = client.put(
            "/api/v1/connectors/nowcoder",
            json={
                "enabled": True,
                "search_query": "",
                "city": "全国",
                "result_limit": 500,
                "schedule_enabled": False,
                "schedule_times": ["09:00"],
            },
        )
        assert saved.status_code == 200, saved.text
        runner.nowcoder_application_url = "javascript:alert(1)"

        response = client.post(
            "/api/v1/connectors/nowcoder/scan", json={"lookback_days": 0}
        )
        assert response.status_code == 200, response.text
        assert response.json()["quarantined_count"] == 1
        assert client.get("/api/v1/opportunities").json()["total"] == 0
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


def test_windows_cmd_shim_prefers_powershell_to_avoid_cmd_metacharacters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command_path = tmp_path / "opencli.cmd"
    powershell_path = tmp_path / "opencli.ps1"
    command_path.write_text("", encoding="ascii")
    powershell_path.write_text("", encoding="ascii")

    def fake_which(name: str) -> str | None:
        return "C:/Program Files/PowerShell/7/pwsh.exe" if name == "pwsh.exe" else None

    monkeypatch.setattr("career_console.infrastructure.connectors.opencli.shutil.which", fake_which)
    prefix = OpenCliProcessRunner(command_path)._command_prefix()
    assert prefix[-2:] == ["-File", str(powershell_path)]
    assert "/c" not in prefix


def test_upgrade_from_part5_creates_backup_and_connector_schema(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    settings.ensure_directories()
    command.upgrade(alembic_config(settings), "20260724_0006")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/connectors/boss").status_code == 200
    assert database_revision(settings.database_path) == "20260726_0026"
    assert list(settings.backups_dir.glob("*pre-202607260026.sqlite3"))
    with sqlite3.connect(settings.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {
        "connector_configs",
        "sync_runs",
        "source_events",
        "sync_cursors",
        "recruitment_opportunities",
        "opportunity_sources",
        "opportunity_versions",
        "opportunity_job_links",
    } <= tables
