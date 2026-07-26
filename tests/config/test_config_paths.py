from pathlib import Path

from career_console.infrastructure.workspace import WorkspacePaths
from career_console.runtime.config.paths import (
    get_bridge_install_dir,
    get_data_dir,
    get_media_dir,
    get_runtime_subdir,
    get_workspace_path,
)


def test_runtime_dirs_follow_config_path(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "instance-a"
    monkeypatch.setattr(
        "career_console.runtime.config.paths.default_workspace_path", lambda: workspace
    )

    assert get_data_dir() == workspace / "runtime"
    assert get_runtime_subdir("cron") == workspace / "runtime" / "cron"


def test_media_dir_supports_channel_namespace(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "instance-b"
    monkeypatch.setattr(
        "career_console.runtime.config.paths.default_workspace_path", lambda: workspace
    )

    assert get_media_dir() == workspace / "runtime" / "media"
    assert get_media_dir("telegram") == workspace / "runtime" / "media" / "telegram"


def test_shared_paths_belong_to_workspace(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        "career_console.runtime.config.paths.default_workspace_path", lambda: workspace
    )
    paths = WorkspacePaths(workspace)
    assert get_bridge_install_dir() == paths.integrations / "whatsapp-bridge"


def test_workspace_path_is_explicitly_resolved(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        "career_console.runtime.config.paths.default_workspace_path", lambda: workspace
    )
    assert get_workspace_path() == workspace / "runtime" / "agent-workspace"
    custom = tmp_path / "custom-workspace"
    assert get_workspace_path(str(custom)) == custom
