"""Health and operational status routes."""

import asyncio
import os
import sys
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, Response, status

from career_console import __version__
from career_console.infrastructure.database.migrations import (
    current_revision,
    head_revision,
)
from career_console.interfaces.http.schemas import (
    HealthResponse,
    ReadyResponse,
    SystemPathsResponse,
    SystemStatusResponse,
)

router = APIRouter(tags=["system"])


def restart_current_process() -> None:
    """Replace the current process while preserving the original CLI arguments."""
    os.execv(
        sys.executable,
        [sys.executable, "-m", "career_console", *sys.argv[1:]],
    )


async def _delayed_restart(callback: Callable[[], None]) -> None:
    await asyncio.sleep(0.35)
    callback()


@router.get("/api/v1/system/session")
def local_session(request: Request, response: Response) -> dict[str, str]:
    token = request.app.state.browser_session_token
    response.set_cookie(
        "career_session",
        token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=8 * 60 * 60,
        path="/",
    )
    return {"csrf_token": token}


@router.post("/api/v1/system/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart(request: Request) -> dict[str, str]:
    asyncio.create_task(_delayed_restart(request.app.state.restart_callback))
    return {"status": "restarting"}


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
