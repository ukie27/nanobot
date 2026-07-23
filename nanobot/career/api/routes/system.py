"""Health and operational status routes."""

from fastapi import APIRouter, HTTPException, Request

from nanobot import __version__
from nanobot.career.api.schemas import (
    HealthResponse,
    ReadyResponse,
    SystemPathsResponse,
    SystemStatusResponse,
)
from nanobot.career.infrastructure.database.migrations import current_revision, head_revision

router = APIRouter(tags=["system"])


@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="live")


@router.get("/health/ready", response_model=ReadyResponse)
def ready(request: Request) -> ReadyResponse:
    database = request.app.state.database
    settings = request.app.state.settings
    healthy, detail = database.ready()
    current = current_revision(database) if healthy else None
    expected = head_revision(settings)
    if not healthy or current != expected:
        raise HTTPException(status_code=503, detail=f"Database is not ready: {detail}")
    return ReadyResponse(
        status="ready",
        database="ok",
        revision=current,
        expected_revision=expected,
    )


@router.get("/api/v1/system/status", response_model=SystemStatusResponse)
def status(request: Request) -> SystemStatusResponse:
    database = request.app.state.database
    settings = request.app.state.settings
    healthy, _detail = database.ready()
    current = current_revision(database) if healthy else None
    expected = head_revision(settings)
    return SystemStatusResponse(
        version=__version__,
        health="ready" if healthy and current == expected else "not_ready",
        database="ok" if healthy else "error",
        database_revision=current,
        expected_revision=expected,
        recovered_jobs_at_startup=request.app.state.recovered_jobs,
        paths=SystemPathsResponse(
            data_dir=str(settings.data_dir),
            database=str(settings.database_path),
            logs=str(settings.logs_dir),
            backups=str(settings.backups_dir),
        ),
    )
