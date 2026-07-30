from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from career_console.cli import app as career_console_cli
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


def test_mutating_request_requires_local_browser_session(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/scheduler/run-due",
            json={},
            headers={"X-Test-Skip-Session-Bootstrap": "1"},
        )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_validation_failed"


def test_mutating_request_rejects_wrong_session_token(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        client.cookies.set("career_session", "wrong")
        response = client.post(
            "/api/v1/scheduler/run-due",
            json={},
            headers={
                "X-CSRF-Token": "wrong",
                "X-Test-Skip-Session-Bootstrap": "1",
            },
        )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_validation_failed"


def test_mutating_request_accepts_valid_session_cookie_and_header(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        session = client.get("/api/v1/system/session")
        response = client.post(
            "/api/v1/scheduler/run-due",
            json={},
            headers={
                "X-CSRF-Token": session.json()["csrf_token"],
                "X-Test-Skip-Session-Bootstrap": "1",
            },
        )
    assert response.status_code == 200


def test_disallowed_origin_is_rejected(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/v1/system/status",
            headers={"Origin": "https://example.invalid"},
        )
    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


def test_cli_rejects_non_loopback_bind_address() -> None:
    result = CliRunner().invoke(
        career_console_cli,
        ["serve", "--host", "0.0.0.0"],
    )
    assert result.exit_code != 0
    assert "only supports loopback bind addresses" in result.output
