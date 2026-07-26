"""Safe creation, discovery and activation of CareerConsole workspaces."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="career-console.workspace.v1", alias="schemaVersion")
    workspace_id: str = Field(alias="workspaceId")
    name: str = "CareerConsole"
    product: str = "CareerConsole"
    created_at: datetime = Field(alias="createdAt")
    last_opened_at: datetime = Field(alias="lastOpenedAt")
    portable: bool = False
    paths: dict[str, str]


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / "workspace.json"

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def database(self) -> Path:
        return self.data / "career-console.sqlite3"

    @property
    def secrets(self) -> Path:
        return self.root / "secrets"

    @property
    def blobs(self) -> Path:
        return self.root / "blobs"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def integrations(self) -> Path:
        return self.root / "integrations"

    @property
    def runtime(self) -> Path:
        return self.root / "runtime"

    def directories(self) -> tuple[Path, ...]:
        return (
            self.root, self.config, self.data, self.secrets, self.blobs,
            self.exports, self.backups, self.logs, self.integrations, self.runtime,
        )


class BootstrapRegistry:
    """Minimal machine-local pointer to the active workspace."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or bootstrap_file_path()

    def active_workspace(self) -> Path | None:
        if not self.path.is_file():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("activeWorkspace")
            return Path(value).resolve(strict=False) if value else None
        except (OSError, ValueError, TypeError):
            return None

    def activate(self, root: Path, workspace_id: str) -> None:
        payload = {
            "schemaVersion": "career-console.bootstrap.v1",
            "activeWorkspace": str(root),
            "workspaceId": workspace_id,
            "updatedAt": datetime.now(UTC).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.path, payload)


class WorkspaceManager:
    def __init__(self, registry: BootstrapRegistry | None = None) -> None:
        self.registry = registry or BootstrapRegistry()

    def resolve_active(self, explicit: Path | None = None) -> Path:
        if explicit is not None:
            return explicit.expanduser().resolve(strict=False)
        configured = os.environ.get("CAREER_CONSOLE_WORKSPACE")
        if configured:
            return Path(configured).expanduser().resolve(strict=False)
        active = self.registry.active_workspace()
        return active or default_workspace_path()

    def validate_parent(self, parent: Path) -> dict[str, Any]:
        resolved = parent.expanduser().resolve(strict=False)
        target = (resolved / "CareerConsole").resolve(strict=False)
        error = self._unsafe_parent_error(resolved)
        if error is None and target.exists() and not target.is_dir():
            error = "目标路径已存在且不是目录。"
        if error is None and target.is_dir() and any(target.iterdir()) and not (target / "workspace.json").is_file():
            error = "目标目录非空且不是 CareerConsole 工作区。"
        return {"parent_directory": str(resolved), "workspace_path": str(target),
                "valid": error is None, "error": error}

    def create(self, parent: Path, *, name: str = "CareerConsole", activate: bool = True) -> WorkspaceManifest:
        check = self.validate_parent(parent)
        if not check["valid"]:
            raise ValueError(check["error"])
        paths = WorkspacePaths(Path(check["workspace_path"]))
        for directory in paths.directories():
            directory.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        if paths.manifest.is_file():
            manifest = WorkspaceManifest.model_validate_json(paths.manifest.read_text(encoding="utf-8"))
            manifest.last_opened_at = now
        else:
            manifest = WorkspaceManifest(
                workspaceId=str(uuid4()), name=name.strip()[:120] or "CareerConsole",
                createdAt=now, lastOpenedAt=now,
                paths={name: name for name in (
                    "config", "data", "secrets", "blobs", "exports", "backups",
                    "logs", "integrations", "runtime",
                )},
            )
        _atomic_json(paths.manifest, manifest.model_dump(mode="json", by_alias=True))
        probe = paths.runtime / ".workspace-write-probe"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        if activate:
            self.registry.activate(paths.root, manifest.workspace_id)
        return manifest

    def ensure(self, root: Path, *, activate: bool = False) -> WorkspaceManifest:
        resolved = root.expanduser().resolve(strict=False)
        paths = WorkspacePaths(resolved)
        if paths.manifest.is_file():
            manifest = WorkspaceManifest.model_validate_json(paths.manifest.read_text(encoding="utf-8"))
            for directory in paths.directories():
                directory.mkdir(parents=True, exist_ok=True)
            if activate:
                self.registry.activate(paths.root, manifest.workspace_id)
            return manifest
        parent = resolved.parent
        if resolved.name != "CareerConsole":
            # Explicit test/portable roots keep their exact path.
            for directory in paths.directories():
                directory.mkdir(parents=True, exist_ok=True)
            now = datetime.now(UTC)
            manifest = WorkspaceManifest(
                workspaceId=str(uuid4()), name=resolved.name or "CareerConsole",
                createdAt=now, lastOpenedAt=now,
                paths={name: name for name in (
                    "config", "data", "secrets", "blobs", "exports", "backups",
                    "logs", "integrations", "runtime",
                )},
            )
            _atomic_json(paths.manifest, manifest.model_dump(mode="json", by_alias=True))
            if activate:
                self.registry.activate(paths.root, manifest.workspace_id)
            return manifest
        return self.create(parent, activate=activate)

    @staticmethod
    def _unsafe_parent_error(parent: Path) -> str | None:
        if parent == Path(parent.anchor):
            return "不能直接在磁盘根目录创建工作区。"
        if parent == Path.home().resolve(strict=False):
            return "请选择用户目录下的具体子目录，不能直接使用用户主目录。"
        source_root = Path(__file__).resolve().parents[2]
        if parent == source_root or source_root in parent.parents:
            return "不能在 CareerConsole 源码目录中创建工作区。"
        return None


def bootstrap_file_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "CareerConsole" / "bootstrap.json"


def default_workspace_path() -> Path:
    registry = BootstrapRegistry()
    active = registry.active_workspace()
    if active is not None:
        return active
    return bootstrap_file_path().parent / "workspaces" / "default"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
