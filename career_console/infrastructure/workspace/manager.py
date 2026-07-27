"""Safe creation, discovery and activation of CareerConsole workspaces."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
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
        return self._workspace_value("activeWorkspace")

    def pending_workspace(self) -> Path | None:
        return self._workspace_value("pendingWorkspace")

    def last_switch_error(self) -> str | None:
        value = self._load().get("lastSwitchError")
        return str(value) if value else None

    def activate(self, root: Path, workspace_id: str) -> None:
        payload = self._load()
        payload.update({
            "schemaVersion": "career-console.bootstrap.v1",
            "activeWorkspace": str(root),
            "workspaceId": workspace_id,
            "updatedAt": datetime.now(UTC).isoformat(),
        })
        payload.pop("pendingWorkspace", None)
        payload.pop("pendingWorkspaceId", None)
        payload.pop("lastSwitchError", None)
        self._save(payload)

    def stage_pending(self, root: Path, workspace_id: str) -> None:
        payload = self._load()
        payload.update({
            "schemaVersion": "career-console.bootstrap.v1",
            "pendingWorkspace": str(root),
            "pendingWorkspaceId": workspace_id,
            "updatedAt": datetime.now(UTC).isoformat(),
        })
        payload.pop("lastSwitchError", None)
        self._save(payload)

    def cancel_pending(self) -> None:
        payload = self._load()
        payload.pop("pendingWorkspace", None)
        payload.pop("pendingWorkspaceId", None)
        payload.pop("lastSwitchError", None)
        self._save(payload)

    def commit_pending(self) -> dict[str, str | None] | None:
        payload = self._load()
        pending = payload.get("pendingWorkspace")
        if not pending:
            return None
        snapshot = {
            "previous_workspace": (
                str(payload["activeWorkspace"])
                if payload.get("activeWorkspace")
                else None
            ),
            "previous_workspace_id": (
                str(payload["workspaceId"])
                if payload.get("workspaceId")
                else None
            ),
            "pending_workspace": str(pending),
            "pending_workspace_id": (
                str(payload["pendingWorkspaceId"])
                if payload.get("pendingWorkspaceId")
                else None
            ),
        }
        payload["activeWorkspace"] = pending
        if payload.get("pendingWorkspaceId"):
            payload["workspaceId"] = payload["pendingWorkspaceId"]
        payload["switchRollback"] = snapshot
        payload.pop("pendingWorkspace", None)
        payload.pop("pendingWorkspaceId", None)
        payload.pop("lastSwitchError", None)
        payload["updatedAt"] = datetime.now(UTC).isoformat()
        self._save(payload)
        return snapshot

    def rollback_committed_switch(
        self, snapshot: dict[str, str | None], message: str
    ) -> None:
        """Restore the old active workspace and keep the candidate pending."""
        payload = self._load()
        previous = snapshot.get("previous_workspace")
        previous_id = snapshot.get("previous_workspace_id")
        pending = snapshot.get("pending_workspace")
        pending_id = snapshot.get("pending_workspace_id")
        if previous:
            payload["activeWorkspace"] = previous
        else:
            payload.pop("activeWorkspace", None)
        if previous_id:
            payload["workspaceId"] = previous_id
        else:
            payload.pop("workspaceId", None)
        if pending:
            payload["pendingWorkspace"] = pending
        if pending_id:
            payload["pendingWorkspaceId"] = pending_id
        payload.pop("switchRollback", None)
        payload["lastSwitchError"] = message[:1000]
        payload["updatedAt"] = datetime.now(UTC).isoformat()
        self._save(payload)

    def finalize_committed_switch(self, active_root: Path) -> None:
        """Clear rollback metadata after a restarted process opens the target."""
        payload = self._load()
        rollback = payload.get("switchRollback")
        if not isinstance(rollback, dict):
            return
        active = payload.get("activeWorkspace")
        if active and Path(str(active)).resolve(strict=False) == active_root.resolve(
            strict=False
        ):
            payload.pop("switchRollback", None)
            payload.pop("lastSwitchError", None)
            payload["updatedAt"] = datetime.now(UTC).isoformat()
            self._save(payload)

    def record_switch_error(self, message: str) -> None:
        payload = self._load()
        payload["lastSwitchError"] = message[:1000]
        payload["updatedAt"] = datetime.now(UTC).isoformat()
        self._save(payload)

    def _workspace_value(self, key: str) -> Path | None:
        value = self._load().get(key)
        return Path(str(value)).resolve(strict=False) if value else None

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self, payload: dict[str, Any]) -> None:
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
        if error is None:
            try:
                self._probe_parent(resolved)
                if target.is_dir():
                    self.preflight(target)
            except (OSError, ValueError, sqlite3.Error) as exc:
                error = str(exc)
        return {"parent_directory": str(resolved), "workspace_path": str(target),
                "valid": error is None, "error": error}

    def preflight(self, root: Path) -> dict[str, Any]:
        resolved = root.expanduser().resolve(strict=False)
        paths = WorkspacePaths(resolved)
        if not paths.manifest.is_file():
            raise ValueError("候选目录缺少 workspace.json。")
        manifest = WorkspaceManifest.model_validate_json(
            paths.manifest.read_text(encoding="utf-8")
        )
        for directory in paths.directories():
            if not directory.is_dir():
                raise ValueError(f"工作区目录缺失：{directory.name}")
            self._probe_directory(directory)
        if paths.database.is_file():
            with sqlite3.connect(
                f"file:{paths.database.as_posix()}?mode=ro", uri=True
            ) as connection:
                result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise ValueError("工作区数据库未通过 SQLite quick_check。")
        free_bytes = shutil.disk_usage(resolved).free
        if free_bytes < 100 * 1024 * 1024:
            raise ValueError("工作区所在磁盘可用空间不足 100 MiB。")
        return {
            "workspace_path": str(resolved),
            "workspace_id": manifest.workspace_id,
            "valid": True,
            "database": "ok" if paths.database.is_file() else "not_created",
            "free_bytes": free_bytes,
        }

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

    @staticmethod
    def _probe_parent(parent: Path) -> None:
        parent.mkdir(parents=True, exist_ok=True)
        probe_directory = Path(tempfile.mkdtemp(prefix=".career-console-probe-", dir=parent))
        try:
            WorkspaceManager._probe_directory(probe_directory)
        finally:
            probe_directory.rmdir()

    @staticmethod
    def _probe_directory(directory: Path) -> None:
        source = directory / f".write-probe-{uuid4().hex}"
        destination = directory / f".write-probe-renamed-{uuid4().hex}"
        try:
            with source.open("w", encoding="ascii", newline="\n") as handle:
                handle.write("ok\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(source, destination)
        finally:
            source.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)


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
