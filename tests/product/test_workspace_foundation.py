from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from career_console.cli import app as career_console_cli
from career_console.infrastructure.settings import CareerSettings
from career_console.infrastructure.workspace import (
    BootstrapRegistry,
    WorkspaceManager,
    WorkspacePaths,
)
from career_console.interfaces.http import create_app


def test_workspace_creation_activation_and_layout(tmp_path: Path) -> None:
    registry = BootstrapRegistry(tmp_path / "machine" / "bootstrap.json")
    manager = WorkspaceManager(registry)
    parent = tmp_path / "包含 空格的工作区父目录"
    check = manager.validate_parent(parent)
    assert check == {
        "parent_directory": str(parent.resolve()),
        "workspace_path": str((parent / "CareerConsole").resolve()),
        "valid": True,
        "error": None,
    }
    manifest = manager.create(parent, name="我的求职工作区", activate=True)
    root = (parent / "CareerConsole").resolve()
    paths = WorkspacePaths(root)
    assert manager.resolve_active() == root
    assert manifest.name == "我的求职工作区"
    assert all(path.is_dir() for path in paths.directories())
    payload = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert payload["product"] == "CareerConsole"
    assert payload["workspaceId"] == manifest.workspace_id
    assert json.loads(registry.path.read_text(encoding="utf-8"))["activeWorkspace"] == str(root)


def test_workspace_rejects_unsafe_or_non_workspace_targets(tmp_path: Path) -> None:
    manager = WorkspaceManager(BootstrapRegistry(tmp_path / "bootstrap.json"))
    nonempty_parent = tmp_path / "parent"
    target = nonempty_parent / "CareerConsole"
    target.mkdir(parents=True)
    (target / "foreign.txt").write_text("not a workspace", encoding="utf-8")
    check = manager.validate_parent(nonempty_parent)
    assert check["valid"] is False
    assert "非空" in check["error"]
    assert manager.validate_parent(Path(Path.cwd().anchor))["valid"] is False


def test_workspace_api_rejects_invalid_target_as_validation_error(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "current")
    app = create_app(settings)
    with TestClient(app) as client:
        client.app.state.workspace_manager = WorkspaceManager(
            BootstrapRegistry(tmp_path / "machine" / "bootstrap.json")
        )
        response = client.post(
            "/api/v1/workspace",
            json={"parent_directory": Path.cwd().anchor, "name": "CareerConsole"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "workspace_invalid"


def test_settings_and_workspace_api_use_workspace_owned_paths(tmp_path: Path) -> None:
    current_root = tmp_path / "current"
    settings = CareerSettings(
        data_dir=current_root, mail_intelligence_mode="disabled",
        profile_insight_mode="disabled", job_fit_agent_mode="disabled",
        resume_direction_mode="disabled", material_agent_mode="disabled",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        registry = BootstrapRegistry(tmp_path / "machine" / "bootstrap.json")
        client.app.state.workspace_manager = WorkspaceManager(registry)
        status = client.get("/api/v1/workspace")
        assert status.status_code == 200
        assert status.json()["workspace_path"] == str(current_root.resolve())
        assert status.json()["paths"]["database"] == str(
            current_root.resolve() / "data" / "career-console.sqlite3"
        )
        parent = tmp_path / "selected"
        validation = client.post(
            "/api/v1/workspace/validate", json={"parent_directory": str(parent)}
        )
        assert validation.status_code == 200
        assert validation.json()["valid"] is True
        created = client.post("/api/v1/workspace", json={
            "parent_directory": str(parent), "name": "正式工作区",
        })
        assert created.status_code == 201, created.text
        assert created.json()["restart_required"] is True
        assert registry.active_workspace() is None
        assert registry.pending_workspace() == (parent / "CareerConsole").resolve()


def test_restart_callback_failure_restores_active_and_keeps_pending(
    tmp_path: Path,
) -> None:
    current = tmp_path / "current"
    candidate_parent = tmp_path / "candidate"
    registry = BootstrapRegistry(tmp_path / "machine" / "bootstrap.json")
    manager = WorkspaceManager(registry)
    current_manifest = manager.ensure(current)
    registry.activate(current, current_manifest.workspace_id)
    candidate = manager.create(candidate_parent, activate=False)
    candidate_root = candidate_parent / "CareerConsole"
    registry.stage_pending(candidate_root, candidate.workspace_id)

    settings = CareerSettings(data_dir=current)
    app = create_app(settings)
    with TestClient(app) as client:
        client.app.state.workspace_manager = manager

        def failed_restart() -> None:
            raise OSError("simulated exec failure")

        client.app.state.restart_callback = failed_restart
        response = client.post("/api/v1/system/restart")
        assert response.status_code == 202
        import time

        time.sleep(0.5)
        assert registry.active_workspace() == current.resolve()
        assert registry.pending_workspace() == candidate_root.resolve()
        assert "simulated exec failure" in (registry.last_switch_error() or "")


def test_workspace_api_uses_replaceable_native_directory_picker(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path / "current")
    with TestClient(create_app(settings)) as client:
        selected = tmp_path / "用户选择的父目录"

        class Picker:
            def pick(self, *, initial_directory: Path | None = None) -> Path:
                assert initial_directory == tmp_path
                return selected

        client.app.state.directory_picker = Picker()
        response = client.post(
            "/api/v1/workspace/pick-directory",
            json={"initial_directory": str(tmp_path)},
        )
        assert response.status_code == 200
        assert response.json() == {
            "cancelled": False,
            "parent_directory": str(selected),
        }

        client.app.state.directory_picker = type(
            "CancelledPicker", (), {"pick": lambda self, **_kwargs: None}
        )()
        cancelled = client.post(
            "/api/v1/workspace/pick-directory", json={"initial_directory": None}
        )
        assert cancelled.json() == {"cancelled": True, "parent_directory": None}


def test_career_settings_creates_workspace_subdirectories(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "portable")
    settings.ensure_directories()
    assert settings.database_path == (tmp_path / "portable" / "data" / "career-console.sqlite3").resolve()
    assert settings.config_dir.is_dir()
    assert settings.secrets_dir.is_dir()
    assert settings.integrations_dir.is_dir()
    assert (settings.data_dir / "workspace.json").is_file()


def test_cli_explicit_workspace_does_not_replace_activation(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    runner = CliRunner()
    parent = tmp_path / "selected"
    created = runner.invoke(career_console_cli, ["workspace", "create", str(parent)])
    assert created.exit_code == 0, created.output
    active = (parent / "CareerConsole").resolve()

    portable = tmp_path / "one-off-portable"
    status_result = runner.invoke(
        career_console_cli, ["status", "--workspace", str(portable)]
    )
    assert status_result.exit_code == 0, status_result.output
    assert BootstrapRegistry().active_workspace() == active


def test_cli_workspace_error_is_concise(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    result = CliRunner().invoke(
        career_console_cli, ["workspace", "create", Path.cwd().anchor]
    )
    assert result.exit_code == 2
    assert "Workspace could not be created" in result.output
    assert "Traceback" not in result.output


def test_start_command_rejects_non_loopback_host() -> None:
    result = CliRunner().invoke(
        career_console_cli, ["start", "--host", "0.0.0.0"]
    )
    assert result.exit_code == 2
    assert "only supports loopback bind addresses" in result.output
