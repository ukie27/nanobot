"""First-run onboarding and capability readiness API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


class CompleteOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skipped_steps: list[str] = Field(default_factory=list)


class UpdateOnboardingStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(min_length=1, max_length=32)


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
    mail = request.app.state.mail_service.get()
    mail_ready = bool(
        mail["configured"]
        and mail["account"]
        and mail["account"]["credential_configured"]
    )
    return request.app.state.onboarding_service.status(
        configuration=document.configuration,
        workspace_ready=workspace_ready,
        restart_required=active is not None and active != settings.data_dir,
        profile_ready=profile_ready,
        mail_ready=mail_ready,
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
    service = request.app.state.onboarding_service
    for step, ready in {
        "workspace": current["workspace_ready"],
        "provider": current["capabilities"]["provider"],
        "profile": current["capabilities"]["profile"],
        "recruitment_sources": current["capabilities"]["opencli"],
        "mail": current["capabilities"]["mail"],
        "channel": current["capabilities"]["channel"],
        "scheduler": current["capabilities"]["scheduler"],
    }.items():
        if ready:
            service.update_step(step, "configured")
    try:
        service.complete(skipped_steps=body.skipped_steps)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "onboarding_incomplete", "message": str(exc)},
        ) from exc
    result = _status(request)
    return result


@router.post("/reopen")
def reopen_onboarding(request: Request) -> dict:
    request.app.state.onboarding_service.reopen()
    result = _status(request)
    result["restart_required"] = True
    return result


@router.put("/steps/{step}")
def update_onboarding_step(
    step: str, body: UpdateOnboardingStepRequest, request: Request
) -> dict:
    try:
        request.app.state.onboarding_service.update_step(step, body.state)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "onboarding_step_invalid", "message": str(exc)},
        ) from exc
    return _status(request)
