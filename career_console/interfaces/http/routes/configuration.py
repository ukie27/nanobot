"""Unified non-secret configuration API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
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


CONFIGURATION_CHECKS = (
    "workspace", "general", "appearance", "privacy", "runtime", "agent_routing",
    "opencli", "nowcoder", "boss", "mail", "qq", "scheduler",
    "portable_export", "portable_import",
)


def _check_result(
    capability: str, check_status: str, summary: str,
    *, details: list[str] | None = None, error_code: str | None = None,
) -> dict:
    return {
        "capability": capability,
        "status": check_status,
        "checked_at": datetime.now(UTC),
        "summary": summary,
        "details": details or [],
        "error_code": error_code,
    }


@router.get("/checks")
def configuration_checks() -> dict:
    return {
        "items": [
            {"capability": capability, "testable": True}
            for capability in CONFIGURATION_CHECKS
        ],
        "total": len(CONFIGURATION_CHECKS),
    }


@router.post("/checks/{capability}")
def run_configuration_check(capability: str, request: Request) -> dict:
    if capability not in CONFIGURATION_CHECKS:
        raise HTTPException(status_code=404, detail="未知配置检查项。")
    try:
        document = request.app.state.configuration_service.store.load()
        config = document.configuration
        if capability == "workspace":
            details = request.app.state.workspace_manager.preflight(
                request.app.state.settings.data_dir
            )
            return _check_result(
                capability, "passed", "工作区目录、写入和数据库检查通过。",
                details=[
                    f"database={details['database']}",
                    f"free_bytes={details['free_bytes']}",
                ],
            )
        if capability == "general":
            from zoneinfo import ZoneInfo

            ZoneInfo(config.general.timezone)
            return _check_result(
                capability, "passed", "语言、时区和日期格式有效。",
                details=[config.general.locale, config.general.timezone],
            )
        if capability == "appearance":
            return _check_result(
                capability, "passed", "界面密度和动效偏好有效。",
                details=[
                    f"density={config.appearance.density}",
                    f"reduce_motion={config.appearance.reduce_motion}",
                ],
            )
        if capability == "privacy":
            if not (
                config.privacy.redact_sensitive_logs
                and config.privacy.local_only_network_binding
            ):
                return _check_result(
                    capability,
                    "failed",
                    "敏感日志脱敏和仅本机访问必须保持开启。",
                    error_code="privacy_guard_disabled",
                )
            return _check_result(
                capability,
                "passed",
                "本地数据保护设置有效。",
                details=[
                    f"diagnostics_metadata={config.privacy.diagnostics_metadata_enabled}",
                    "sensitive_logs=redacted",
                    "network_binding=local_only",
                ],
            )
        if capability == "runtime":
            paths = (
                request.app.state.settings.logs_dir,
                request.app.state.settings.runtime_dir,
            )
            for path in paths:
                Path(path).mkdir(parents=True, exist_ok=True)
            return _check_result(
                capability, "passed", "运行目录和资源限制有效。",
                details=[f"log_level={config.runtime.log_level}"],
            )
        if capability == "agent_routing":
            enabled = [
                (name, task)
                for name, task in config.agents.tasks if task.enabled
            ]
            if not enabled:
                return _check_result(
                    capability, "blocked", "尚未启用任何 Agent 任务。",
                    error_code="agent_tasks_disabled",
                )
            missing = []
            for name, task in enabled:
                provider = config.providers.get(task.provider_id or "")
                if (
                    provider is None or not provider.enabled
                    or (
                        provider.secret_ref
                        and not _has_secret(request, provider.secret_ref)
                    )
                ):
                    missing.append(name)
            if missing:
                return _check_result(
                    capability, "failed", "部分 Agent 任务缺少可用 Provider 或凭据。",
                    details=missing, error_code="agent_provider_unavailable",
                )
            return _check_result(
                capability, "passed", f"{len(enabled)} 个 Agent 任务映射有效。"
            )
        if capability == "opencli":
            runner = request.app.state.connector_service.runner
            if not runner.installed:
                return _check_result(
                    capability, "failed", "未找到 OpenCLI 可执行文件。",
                    error_code="opencli_not_installed",
                )
            version = runner.version()
            return _check_result(
                capability, "passed", "OpenCLI 可执行且版本查询成功。",
                details=[str(version)],
            )
        if capability in {"nowcoder", "boss"}:
            service = (
                request.app.state.nowcoder_connector_service
                if capability == "nowcoder"
                else request.app.state.connector_service
            )
            health = service.health()
            state = str(health.get("status", health.get("health", "unknown")))
            passed = state in {"healthy", "ready", "passed", "ok"}
            source_name = "牛客" if capability == "nowcoder" else "BOSS"
            source_error = health.get("error_code")
            if passed:
                summary = f"{source_name}来源可用。"
            elif source_error == "opencli_not_installed":
                summary = (
                    "未检测到 OpenCLI。请先在“设置 → 数据来源”中"
                    "配置 OpenCLI 可执行文件。"
                )
            elif source_error == "requires_login":
                summary = f"{source_name}尚未登录，请先打开登录页面完成登录。"
            else:
                summary = f"{source_name}来源暂不可用，请检查数据来源设置。"
            return _check_result(
                capability, "passed" if passed else "failed",
                summary,
                error_code=None if passed else str(
                    source_error or f"{capability}_unavailable"
                ),
            )
        if capability == "mail":
            result = request.app.state.mail_service.test_connection()
            return _check_result(
                capability, "passed", "邮箱只读连接正常。",
                details=[
                    f"read_only={result.get('read_only', True)}",
                    f"uid_validity={result.get('uid_validity', 'unknown')}",
                ],
            )
        if capability == "qq":
            result = request.app.state.channel_configuration.test_qq()
            return _check_result(
                capability, "passed", "QQ 通知测试消息发送成功。",
                details=[f"status={result.get('status', 'passed')}"],
            )
        if capability == "scheduler":
            enabled_jobs = [
                name for name in (
                    "reminders", "connector_jobs", "profile_maintenance",
                    "channel_dispatch",
                )
                if getattr(config.scheduler, f"{name}_enabled")
            ]
            return _check_result(
                capability, "passed", "调度配置自检通过，未执行任何业务任务。",
                details=[
                    f"enabled={config.scheduler.enabled}",
                    f"jobs={','.join(enabled_jobs) or 'none'}",
                ],
            )
        if capability == "portable_export":
            request.app.state.workspace_manager.preflight(
                request.app.state.settings.data_dir
            )
            required = (
                request.app.state.settings.database_path,
                request.app.state.settings.config_dir / "application.json",
            )
            missing = [str(path) for path in required if not path.is_file()]
            if missing:
                return _check_result(
                    capability, "failed", "便携导出缺少必要文件。",
                    details=missing, error_code="portable_export_incomplete",
                )
            return _check_result(
                capability, "passed", "便携导出前置条件满足。"
            )
        return _check_result(
            capability, "passed",
            "便携导入入口可用；具体归档会在上传后执行格式、哈希和数据库校验。",
        )
    except (LookupError, OSError, RuntimeError, ValueError) as exc:
        return _check_result(
            capability, "failed", str(exc),
            error_code=f"{capability}_check_failed",
        )


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
