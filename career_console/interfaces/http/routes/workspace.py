"""CareerConsole workspace onboarding and selection API."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from career_console.infrastructure.workspace import (
    DirectoryPickerUnavailableError,
    NativeDirectoryPicker,
    PortableWorkspaceError,
    PortableWorkspaceService,
    WorkspaceManager,
    WorkspacePaths,
)

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


class ValidateWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_directory: str = Field(min_length=1, max_length=2_000)


class CreateWorkspaceRequest(ValidateWorkspaceRequest):
    name: str = Field(default="CareerConsole", min_length=1, max_length=120)


class PickDirectoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_directory: str | None = Field(default=None, max_length=2_000)


class PortableExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_secrets: bool = False
    passphrase: str | None = Field(default=None, max_length=1_000)


@router.get("")
def workspace_status(request: Request) -> dict:
    settings = request.app.state.settings
    manager: WorkspaceManager = request.app.state.workspace_manager
    paths = WorkspacePaths(settings.data_dir)
    manifest = (
        json.loads(paths.manifest.read_text(encoding="utf-8"))
        if paths.manifest.is_file()
        else None
    )
    active = manager.registry.active_workspace()
    pending = manager.registry.pending_workspace()
    return {
        "product": "CareerConsole",
        "workspace_path": str(paths.root),
        "manifest": manifest,
        "active_workspace_path": str(active) if active else None,
        "pending_workspace_path": str(pending) if pending else None,
        "last_switch_error": manager.registry.last_switch_error(),
        "onboarding_required": active is None,
        "restart_required": pending is not None or (
            active is not None and active != paths.root
        ),
        "paths": {
            "config": str(paths.config), "data": str(paths.data),
            "database": str(paths.database), "secrets": str(paths.secrets),
            "blobs": str(paths.blobs), "exports": str(paths.exports),
            "backups": str(paths.backups), "logs": str(paths.logs),
            "integrations": str(paths.integrations), "runtime": str(paths.runtime),
        },
    }


@router.post("/validate")
def validate_workspace(body: ValidateWorkspaceRequest, request: Request) -> dict:
    manager: WorkspaceManager = request.app.state.workspace_manager
    return manager.validate_parent(Path(body.parent_directory))


@router.post("/pick-directory")
def pick_directory(body: PickDirectoryRequest, request: Request) -> dict:
    picker: NativeDirectoryPicker = request.app.state.directory_picker
    initial = (
        Path(body.initial_directory)
        if body.initial_directory
        else request.app.state.settings.data_dir.parent
    )
    try:
        selected = picker.pick(initial_directory=initial)
    except DirectoryPickerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"code": "directory_picker_unavailable", "message": str(exc)},
        ) from exc
    return {
        "cancelled": selected is None,
        "parent_directory": str(selected) if selected is not None else None,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(body: CreateWorkspaceRequest, request: Request) -> dict:
    manager: WorkspaceManager = request.app.state.workspace_manager
    try:
        manifest = manager.create(
            Path(body.parent_directory), name=body.name, activate=False
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "workspace_invalid", "message": str(exc)},
        ) from exc
    root = Path(body.parent_directory).expanduser().resolve(strict=False) / "CareerConsole"
    manager.registry.stage_pending(root, manifest.workspace_id)
    return {
        "workspace_path": str(root),
        "manifest": manifest.model_dump(mode="json", by_alias=True),
        "restart_required": root.resolve() != request.app.state.settings.data_dir,
    }


@router.delete("/pending")
def cancel_pending_workspace(request: Request) -> dict:
    manager: WorkspaceManager = request.app.state.workspace_manager
    manager.registry.cancel_pending()
    return {"cancelled": True}


@router.post("/portable-export")
def portable_export(body: PortableExportRequest, request: Request) -> dict:
    service: PortableWorkspaceService = request.app.state.portable_workspace
    try:
        return service.export(
            include_secrets=body.include_secrets, passphrase=body.passphrase,
        )
    except (OSError, PortableWorkspaceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "workspace_export_failed", "message": str(exc)},
        ) from exc


@router.get("/portable-exports/{filename}", response_class=FileResponse)
def download_portable_export(filename: str, request: Request) -> FileResponse:
    service: PortableWorkspaceService = request.app.state.portable_workspace
    try:
        path = service.resolve_export(filename)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    return FileResponse(
        path, media_type="application/zip", filename=filename,
    )


@router.post("/portable-import")
async def portable_import(
    request: Request,
    parent_directory: str = Form(min_length=1, max_length=2_000),
    file: UploadFile = File(...),
    passphrase: str | None = Form(default=None, max_length=1_000),
) -> dict:
    service: PortableWorkspaceService = request.app.state.portable_workspace
    runtime = request.app.state.settings.runtime_dir
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="portable-upload-", suffix=".ccworkspace", dir=runtime,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    size = 0
    try:
        with temporary.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 2 * 1024 * 1024 * 1024:
                    raise PortableWorkspaceError("工作区归档超过 2 GiB 限制。")
                handle.write(chunk)
        return service.import_archive(
            archive_path=temporary,
            parent=Path(parent_directory),
            passphrase=passphrase,
        )
    except (OSError, PortableWorkspaceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "workspace_import_failed", "message": str(exc)},
        ) from exc
    finally:
        await file.close()
        temporary.unlink(missing_ok=True)
