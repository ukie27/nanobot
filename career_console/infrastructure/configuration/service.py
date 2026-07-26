"""Configuration orchestration with optimistic concurrency and audit rollback."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Any

from career_console.infrastructure.configuration.audit import ConfigurationAuditStore
from career_console.infrastructure.configuration.schema import (
    FIELD_EFFECTS,
    ActivationEffect,
    CareerConsoleConfiguration,
    ConfigurationDocument,
    ConfigurationUpdate,
)
from career_console.infrastructure.configuration.store import AtomicConfigurationStore


class ConfigurationRevisionConflictError(RuntimeError):
    pass


class ConfigurationService:
    def __init__(
        self, store: AtomicConfigurationStore, audit: ConfigurationAuditStore
    ) -> None:
        self.store = store
        self.audit = audit
        self._lock = RLock()
        self.active_revision = 0

    def initialize(self) -> ConfigurationDocument:
        with self._lock:
            document = self.store.load()
            if document is None:
                document = ConfigurationDocument(
                    revision=1,
                    updated_at=datetime.now(UTC),
                    configuration=CareerConsoleConfiguration(),
                )
                self.store.save(document)
            if not self.audit.has_revision(document.revision):
                self.audit.record(
                    revision=document.revision,
                    previous_revision=0,
                    schema_version=document.schema_version,
                    configuration=document.configuration.model_dump(mode="json"),
                    changed_paths=["*"],
                    activation_effect="restart_required",
                    reason="初始化工作区配置",
                    created_at=document.updated_at,
                )
            self.active_revision = document.revision
            return document

    def status(self) -> dict[str, Any]:
        document = self._required_document()
        return {
            **document.model_dump(mode="json"),
            "active_revision": self.active_revision,
            "activation_status": (
                "active" if document.revision == self.active_revision else "restart_required"
            ),
        }

    def update(self, command: ConfigurationUpdate) -> dict[str, Any]:
        with self._lock:
            previous = self._required_document()
            if previous.revision != command.expected_revision:
                raise ConfigurationRevisionConflictError(
                    f"配置已更新；当前 revision 为 {previous.revision}。"
                )
            old_value = previous.configuration.model_dump(mode="json")
            new_value = command.configuration.model_dump(mode="json")
            changed_paths = _changed_paths(old_value, new_value)
            if not changed_paths:
                return {**self.status(), "changed_paths": [], "activation_effect": None}
            effect = _strongest_effect(changed_paths)
            document = ConfigurationDocument(
                revision=previous.revision + 1,
                updated_at=datetime.now(UTC),
                configuration=command.configuration,
            )
            self.store.save(document)
            try:
                self.audit.record(
                    revision=document.revision,
                    previous_revision=previous.revision,
                    schema_version=document.schema_version,
                    configuration=new_value,
                    changed_paths=changed_paths,
                    activation_effect=effect,
                    reason=command.reason,
                    created_at=document.updated_at,
                )
            except Exception:
                self.store.save(previous)
                raise
            if effect == "hot_reload" and previous.revision == self.active_revision:
                self.active_revision = document.revision
            return {
                **self.status(),
                "changed_paths": changed_paths,
                "activation_effect": effect,
            }

    def _required_document(self) -> ConfigurationDocument:
        document = self.store.load()
        if document is None:
            raise RuntimeError("Workspace configuration has not been initialized.")
        return document


def _changed_paths(old: Any, new: Any, prefix: str = "") -> list[str]:
    if isinstance(old, dict) and isinstance(new, dict):
        paths: list[str] = []
        for key in sorted(old.keys() | new.keys()):
            path = f"{prefix}.{key}" if prefix else key
            paths.extend(_changed_paths(old.get(key), new.get(key), path))
        return paths
    return [] if old == new else [prefix]


def _strongest_effect(paths: list[str]) -> ActivationEffect:
    rank: dict[ActivationEffect, int] = {
        "hot_reload": 0,
        "service_reload": 1,
        "restart_required": 2,
    }
    effects = [FIELD_EFFECTS.get(path, "restart_required") for path in paths]
    return max(effects, key=rank.__getitem__)


def apply_stored_runtime_configuration(settings: Any) -> Any:
    """Apply persisted restart-scoped values before runtime services are constructed."""
    document = AtomicConfigurationStore(
        settings.config_dir / "application.json"
    ).load()
    if document is None:
        return settings
    runtime = document.configuration.runtime
    return settings.model_copy(update={
        "log_level": runtime.log_level,
        "log_retention_days": runtime.log_retention_days,
        "agent_trace_retention_days": runtime.agent_trace_retention_days,
        "job_lease_seconds": runtime.job_lease_seconds,
        "max_document_bytes": runtime.max_document_mb * 1024 * 1024,
    })
