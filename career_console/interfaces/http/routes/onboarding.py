"""First-run onboarding and capability readiness API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


class CompleteOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skipped_steps: list[str] = Field(default_factory=list)


def _status(request: Request) -> dict:
    document = request.app.state.configuration_service.store.load()
    active = request.app.state.workspace_manager.registry.active_workspace()
    settings = request.app.state.settings
    workspace_ready = active == settings.data_dir or not request.app.state.bootstrap_workspace
    profile_gateway = request.app.state.profile_service.gateway
    profile = profile_gateway.get_profile()
    profile_ready = bool(profile_gateway.list_documents()) or any(
        profile["fact_counts"].values()
    )
    return request.app.state.onboarding_service.status(
        configuration=document.configuration,
        workspace_ready=workspace_ready,
        restart_required=active is not None and active != settings.data_dir,
        profile_ready=profile_ready,
    )


@router.get("")
def onboarding_status(request: Request) -> dict:
    return _status(request)


@router.post("/complete")
def complete_onboarding(body: CompleteOnboardingRequest, request: Request) -> dict:
    current = _status(request)
    if not current["workspace_ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "workspace_required",
                "message": "请先创建或导入正式工作区。",
            },
        )
    request.app.state.onboarding_service.complete(skipped_steps=body.skipped_steps)
    result = _status(request)
    result["restart_required"] = True
    return result


@router.post("/reopen")
def reopen_onboarding(request: Request) -> dict:
    request.app.state.onboarding_service.reopen()
    result = _status(request)
    result["restart_required"] = True
    return result
