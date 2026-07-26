"""Runtime path helpers derived from the active config context."""

from __future__ import annotations

from pathlib import Path

from career_console.infrastructure.workspace.manager import WorkspacePaths, default_workspace_path
from career_console.runtime.utils.helpers import ensure_dir


def get_data_dir(*, create: bool = True) -> Path:
    """Return the instance-level runtime data directory."""
    path = WorkspacePaths(default_workspace_path()).runtime
    return ensure_dir(path) if create else path


def get_runtime_subdir(name: str, *, create: bool = True) -> Path:
    """Return a named runtime subdirectory under the instance data dir."""
    path = get_data_dir(create=create) / name
    return ensure_dir(path) if create else path


def get_media_dir(channel: str | None = None, *, create: bool = True) -> Path:
    """Return the media directory, optionally namespaced per channel."""
    base = get_runtime_subdir("media", create=create)
    path = base / channel if channel else base
    return ensure_dir(path) if create else path


def get_workspace_path(workspace: str | None = None, *, create: bool = True) -> Path:
    """Resolve the agent workspace path and optionally create it."""
    path = (
        Path(workspace).expanduser()
        if workspace
        else WorkspacePaths(default_workspace_path()).runtime / "agent-workspace"
    )
    return ensure_dir(path) if create else path


def get_bridge_install_dir() -> Path:
    """Return the shared WhatsApp bridge installation directory."""
    return WorkspacePaths(default_workspace_path()).integrations / "whatsapp-bridge"
