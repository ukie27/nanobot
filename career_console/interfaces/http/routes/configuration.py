"""Unified non-secret configuration API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import perf_counter
from typing import get_args

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from career_console.infrastructure.agent_runtime.providers import ProviderConfigurationError
from career_console.infrastructure.configuration.schema import (
    FIELD_EFFECTS,
    AgentConfiguration,
    AgentTaskConfiguration,
    CareerConsoleConfiguration,
    ConfigurationUpdate,
    ProviderConfiguration,
    ProviderType,
)
from career_console.infrastructure.configuration.service import ConfigurationRevisionConflictError

router = APIRouter(prefix="/api/v1/configuration", tags=["configuration"])


def _revision_conflict(exc: ConfigurationRevisionConflictError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "configuration_revision_conflict", "message": str(exc)},
    )


def _has_secret(request: Request, secret_ref: str | None) -> bool:
    if not secret_ref:
        return False
    try:
        request.app.state.secret_store.get(secret_ref)
        return True
    except (LookupError, RuntimeError):
        return False


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderUpsertRequest(StrictRequest):
    expected_revision: int = Field(ge=1)
    provider_type: ProviderType
    display_name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    api_base: str | None = Field(default=None, max_length=500)
    default_model: str = Field(min_length=1, max_length=200)
    models: list[str] = Field(default_factory=list, max_length=100)
    api_key: str | None = Field(default=None, min_length=1, max_length=10_000)


class AgentConfigurationUpdateRequest(StrictRequest):
    expected_revision: int = Field(ge=1)
    agents: AgentConfiguration


class ProviderTestRequest(StrictRequest):
    model: str | None = Field(default=None, max_length=200)


@router.get("")
def get_configuration(request: Request) -> dict:
    return request.app.state.configuration_service.status()


@router.put("")
def update_configuration(body: ConfigurationUpdate, request: Request) -> dict:
    try:
        return request.app.state.configuration_service.update(body)
    except ConfigurationRevisionConflictError as exc:
        raise _revision_conflict(exc) from exc


@router.get("/schema")
def configuration_schema() -> dict:
    return {
        "schema_version": "career-console.configuration.v1",
        "json_schema": CareerConsoleConfiguration.model_json_schema(),
        "field_effects": FIELD_EFFECTS,
        "secret_fields_allowed": False,
    }


@router.get("/changes")
def configuration_changes(request: Request, limit: int = Query(50, ge=1, le=200)) -> dict:
    items = request.app.state.configuration_service.audit.list_changes(limit)
    return {"items": items, "total": len(items)}


@router.get("/provider-catalog")
def provider_catalog() -> dict:
    from career_console.runtime.providers.registry import PROVIDERS

    supported = set(get_args(ProviderType))
    items = [
        {
            "type": spec.name, "label": spec.label,
            "default_api_base": spec.default_api_base or None,
            "requires_api_key": not (spec.is_local or spec.is_oauth or spec.is_direct),
            "is_local": spec.is_local,
        }
        for spec in PROVIDERS if spec.name in supported and not spec.is_oauth
    ]
    return {"items": items, "total": len(items)}


@router.get("/providers")
def list_providers(request: Request) -> dict:
    document = request.app.state.configuration_service.store.load()
    if document is None:
        return {"items": [], "total": 0}
    items = []
    for provider_id, provider in document.configuration.providers.items():
        items.append({
            "id": provider_id,
            **provider.model_dump(mode="json"),
            "has_secret": _has_secret(request, provider.secret_ref),
        })
    return {"items": items, "total": len(items)}


@router.put("/providers/{provider_id}")
def upsert_provider(
    provider_id: str, body: ProviderUpsertRequest, request: Request
) -> dict:
    service = request.app.state.configuration_service
    document = service.store.load()
    if document is None:
        raise RuntimeError("Workspace configuration has not been initialized.")
    existing = document.configuration.providers.get(provider_id)
    secret_ref = existing.secret_ref if existing else None
    secret_was_created = False
    previous_secret: str | None = None
    if body.api_key:
        secret_ref = request.app.state.provider_secret_reference(provider_id)
        secret_was_created = existing is None or existing.secret_ref is None
        if not secret_was_created:
            try:
                previous_secret = request.app.state.secret_store.get(secret_ref)
            except LookupError:
                secret_was_created = True
        request.app.state.secret_store.set(secret_ref, body.api_key)
    updated = document.configuration.model_copy(deep=True)
    updated.providers[provider_id] = ProviderConfiguration(
        provider_type=body.provider_type,
        display_name=body.display_name,
        enabled=body.enabled,
        api_base=body.api_base,
        default_model=body.default_model,
        models=body.models,
        secret_ref=secret_ref,
    )
    try:
        result = service.update(ConfigurationUpdate(
            expected_revision=body.expected_revision,
            reason=f"更新 Provider：{provider_id}",
            configuration=updated,
        ))
    except Exception as exc:
        if secret_was_created and secret_ref:
            request.app.state.secret_store.delete(secret_ref)
        elif previous_secret is not None and secret_ref:
            request.app.state.secret_store.set(secret_ref, previous_secret)
        if isinstance(exc, ConfigurationRevisionConflictError):
            raise _revision_conflict(exc) from exc
        raise
    return {
        "provider": {
            "id": provider_id,
            **updated.providers[provider_id].model_dump(mode="json"),
            "has_secret": _has_secret(request, secret_ref),
        },
        "configuration_revision": result["revision"],
        "restart_required": result["activation_status"] == "restart_required",
    }


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str, expected_revision: int, request: Request) -> dict:
    service = request.app.state.configuration_service
    document = service.store.load()
    if document is None or provider_id not in document.configuration.providers:
        raise HTTPException(status_code=404, detail="Provider 不存在。")
    referenced = [
        name for name, task in document.configuration.agents.tasks
        if task.provider_id == provider_id
    ]
    if referenced:
        raise HTTPException(
            status_code=409,
            detail={"code": "provider_in_use", "message": "Provider 仍被 Agent 任务引用。"},
        )
    updated = document.configuration.model_copy(deep=True)
    provider = updated.providers.pop(provider_id)
    try:
        result = service.update(ConfigurationUpdate(
            expected_revision=expected_revision,
            reason=f"删除 Provider：{provider_id}",
            configuration=updated,
        ))
    except ConfigurationRevisionConflictError as exc:
        raise _revision_conflict(exc) from exc
    if provider.secret_ref:
        request.app.state.secret_store.delete(provider.secret_ref)
    return {"deleted": True, "configuration_revision": result["revision"]}


@router.put("/agents")
def update_agents(body: AgentConfigurationUpdateRequest, request: Request) -> dict:
    service = request.app.state.configuration_service
    document = service.store.load()
    if document is None:
        raise RuntimeError("Workspace configuration has not been initialized.")
    updated = document.configuration.model_copy(deep=True)
    updated.agents = body.agents
    try:
        return service.update(ConfigurationUpdate(
            expected_revision=body.expected_revision,
            reason="更新 Agent 任务模型映射",
            configuration=updated,
        ))
    except ConfigurationRevisionConflictError as exc:
        raise _revision_conflict(exc) from exc


@router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: str, body: ProviderTestRequest, request: Request
) -> dict:
    document = request.app.state.configuration_service.store.load()
    provider_config = (
        document.configuration.providers.get(provider_id) if document else None
    )
    if provider_config is None:
        raise HTTPException(status_code=404, detail="Provider 不存在。")
    model = body.model or provider_config.default_model
    started_at = datetime.now(UTC)
    started = perf_counter()
    error_code: str | None = None
    test_status = "passed"
    try:
        provider = request.app.state.agent_runtime.factory.build(
            provider_config,
            AgentTaskConfiguration(model=model, max_tokens=256, temperature=0),
        )
        response = await asyncio.wait_for(provider.chat(
            messages=[{"role": "user", "content": "Reply with OK only."}],
            tools=None, model=model, max_tokens=8, temperature=0,
        ), timeout=30)
        if response.finish_reason == "error":
            test_status, error_code = "failed", "provider_rejected"
    except ProviderConfigurationError:
        test_status, error_code = "failed", "credential_missing"
    except TimeoutError:
        test_status, error_code = "failed", "timeout"
    except Exception:
        test_status, error_code = "failed", "connection_failed"
    return request.app.state.provider_test_audit.record(
        provider_id=provider_id,
        provider_type=provider_config.provider_type,
        model=model,
        status=test_status,
        error_code=error_code,
        duration_ms=max(0, round((perf_counter() - started) * 1000)),
        created_at=started_at,
    )


@router.get("/provider-tests")
def provider_tests(
    request: Request,
    provider_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    items = request.app.state.provider_test_audit.list(provider_id, limit)
    return {"items": items, "total": len(items)}
