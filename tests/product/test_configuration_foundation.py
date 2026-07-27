from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from career_console.infrastructure.configuration import (
    CareerConsoleConfiguration,
    apply_stored_runtime_configuration,
)
from career_console.infrastructure.database.models import (
    ConfigurationChangeModel,
    ConfigurationSnapshotModel,
)
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app
from career_console.interfaces.http.routes.configuration import run_configuration_check


def _configuration() -> dict:
    return CareerConsoleConfiguration().model_dump(mode="json")


def test_configuration_initializes_workspace_file_and_audit(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/configuration")
        assert response.status_code == 200
        body = response.json()
        assert body["revision"] == 1
        assert body["active_revision"] == 1
        assert body["activation_status"] == "active"
        assert body["configuration"] == _configuration()
        schema = client.get("/api/v1/configuration/schema").json()
        assert schema["secret_fields_allowed"] is False
        assert schema["field_effects"]["runtime.log_level"] == "restart_required"

        payload = json.loads(
            (settings.config_dir / "application.json").read_text(encoding="utf-8")
        )
        assert payload["schema_version"] == "career-console.configuration.v1"
        serialized = json.dumps(payload).lower()
        assert "api_key" not in serialized
        assert "password" not in serialized
        assert "app-password" not in serialized
        with app.state.database.session_factory() as session:
            assert len(session.scalars(select(ConfigurationSnapshotModel)).all()) == 1
            assert len(session.scalars(select(ConfigurationChangeModel)).all()) == 1


def test_configuration_update_is_versioned_audited_and_requires_restart(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    app = create_app(settings)
    with TestClient(app) as client:
        configuration = _configuration()
        configuration["runtime"]["log_level"] = "DEBUG"
        response = client.put("/api/v1/configuration", json={
            "expected_revision": 1,
            "reason": "调试本地运行问题",
            "configuration": configuration,
        })
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["revision"] == 2
        assert body["active_revision"] == 1
        assert body["activation_status"] == "restart_required"
        assert body["changed_paths"] == ["runtime.log_level"]
        assert body["activation_effect"] == "restart_required"
        changes = client.get("/api/v1/configuration/changes").json()["items"]
        assert changes[0]["previous_revision"] == 1
        assert changes[0]["new_revision"] == 2
        assert changes[0]["reason"] == "调试本地运行问题"

        conflict = client.put("/api/v1/configuration", json={
            "expected_revision": 1,
            "reason": "过期页面提交",
            "configuration": configuration,
        })
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "configuration_revision_conflict"


def test_configuration_rejects_unknown_and_unsafe_fields(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        configuration = _configuration()
        configuration["api_key"] = "must-not-be-accepted"
        invalid = client.put("/api/v1/configuration", json={
            "expected_revision": 1,
            "reason": "unknown field",
            "configuration": configuration,
        })
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "validation_error"

        configuration = _configuration()
        configuration["privacy"]["redact_sensitive_logs"] = False
        unsafe = client.put("/api/v1/configuration", json={
            "expected_revision": 1,
            "reason": "disable redaction",
            "configuration": configuration,
        })
        assert unsafe.status_code == 422


def test_runtime_configuration_applies_after_restart_and_appearance_hot_reloads(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        configuration = _configuration()
        configuration["appearance"]["density"] = "compact"
        hot = client.put("/api/v1/configuration", json={
            "expected_revision": 1,
            "reason": "使用紧凑布局",
            "configuration": configuration,
        })
        assert hot.status_code == 200
        assert hot.json()["activation_effect"] == "hot_reload"
        assert hot.json()["activation_status"] == "active"

        configuration["runtime"]["max_document_mb"] = 20
        restart = client.put("/api/v1/configuration", json={
            "expected_revision": 2,
            "reason": "扩大文档上限",
            "configuration": configuration,
        })
        assert restart.status_code == 200
        assert restart.json()["activation_status"] == "restart_required"

    effective = apply_stored_runtime_configuration(settings)
    assert effective.max_document_bytes == 20 * 1024 * 1024


def test_privacy_configuration_check_passes_with_safe_defaults(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/configuration/checks/privacy", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capability"] == "privacy"
    assert body["status"] == "passed"


def test_privacy_configuration_check_reports_disabled_guard(tmp_path: Path) -> None:
    unsafe_configuration = SimpleNamespace(
        privacy=SimpleNamespace(
            redact_sensitive_logs=False,
            local_only_network_binding=False,
            diagnostics_metadata_enabled=False,
        )
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                configuration_service=SimpleNamespace(
                    store=SimpleNamespace(
                        load=lambda: SimpleNamespace(configuration=unsafe_configuration)
                    )
                )
            )
        )
    )

    body = run_configuration_check("privacy", request)
    assert body["capability"] == "privacy"
    assert body["status"] == "failed"
    assert body["error_code"] == "privacy_guard_disabled"
