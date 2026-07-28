"""Coordinate workspace connector configuration with operational projections."""

from __future__ import annotations

import shutil
from typing import Any

from career_console.infrastructure.configuration.schema import (
    ConfigurationUpdate,
    ImapConfiguration,
    OpenCliBossConfiguration,
    OpenCliNowcoderConfiguration,
)


class IntegrationConfigurationService:
    """Keep application.json authoritative and SQLite limited to runtime state."""

    def __init__(
        self, *, configuration: Any, connector_service: Any,
        nowcoder_service: Any, mail_service: Any, imap_secret_ref: str,
    ) -> None:
        self.configuration = configuration
        self.connector_service = connector_service
        self.nowcoder_service = nowcoder_service
        self.mail_service = mail_service
        self.imap_secret_ref = imap_secret_ref

    def configure_boss(self, **values: Any) -> dict[str, Any]:
        document, updated = self._copy()
        updated.connectors.opencli.boss = OpenCliBossConfiguration(**{
            key: values[key] for key in OpenCliBossConfiguration.model_fields if key in values
        })
        self._save(document.revision, updated, "更新 OpenCLI BOSS 数据源")
        return self._project_boss(updated.connectors.opencli.boss)

    def get_opencli(self) -> dict[str, Any]:
        document = self.configuration.store.load()
        executable = (
            document.configuration.connectors.opencli.executable if document else None
        )
        return {
            "executable": executable,
            "resolved_executable": self.connector_service.runner.executable or None,
            "installed": self.connector_service.runner.installed,
        }

    def configure_opencli(self, executable: str | None) -> dict[str, Any]:
        document, updated = self._copy()
        normalized = executable.strip() if executable else None
        updated.connectors.opencli.executable = normalized or None
        self._save(document.revision, updated, "更新外部 OpenCLI 可执行文件")
        if normalized:
            self.connector_service.runner.executable = normalized
        else:
            self.connector_service.runner.executable = shutil.which("opencli") or ""
        return self.get_opencli()

    def configure_nowcoder(self, **values: Any) -> dict[str, Any]:
        document, updated = self._copy()
        updated.connectors.opencli.nowcoder = OpenCliNowcoderConfiguration(**{
            key: values[key]
            for key in OpenCliNowcoderConfiguration.model_fields if key in values
        })
        self._save(document.revision, updated, "更新 OpenCLI 牛客数据源")
        return self._project_nowcoder(updated.connectors.opencli.nowcoder)

    def configure_imap(
        self, *, password: str | None = None, **values: Any
    ) -> dict[str, Any]:
        document, updated = self._copy()
        current = document.configuration.connectors.imap
        previous_secret: str | None = None
        secret_created = False
        if password:
            try:
                previous_secret = self.mail_service.secrets.get(self.imap_secret_ref)
            except LookupError:
                secret_created = True
            self.mail_service.secrets.set(self.imap_secret_ref, password)
        elif not current.secret_ref:
            raise ValueError("首次配置必须提供邮箱授权码。")
        values["secret_ref"] = self.imap_secret_ref
        updated.connectors.imap = ImapConfiguration(**values)
        try:
            self._save(document.revision, updated, "更新只读 IMAP 数据源")
        except Exception:
            if secret_created:
                self.mail_service.secrets.delete(self.imap_secret_ref)
            elif previous_secret is not None:
                self.mail_service.secrets.set(self.imap_secret_ref, previous_secret)
            raise
        return self._project_imap(updated.connectors.imap)

    def delete_imap(self) -> dict[str, bool]:
        document, updated = self._copy()
        updated.connectors.imap = ImapConfiguration()
        self._save(document.revision, updated, "删除只读 IMAP 数据源")
        self.mail_service.gateway.delete_account()
        self.mail_service.secrets.delete(self.imap_secret_ref)
        return {"deleted": document.configuration.connectors.imap.secret_ref is not None}

    def reconcile(self) -> dict[str, str]:
        document = self.configuration.store.load()
        if document is None:
            return {}
        failures: dict[str, str] = {}
        config = document.configuration.connectors
        if config.opencli.executable:
            self.connector_service.runner.executable = config.opencli.executable
        self._project_boss(config.opencli.boss)
        self._project_nowcoder(config.opencli.nowcoder)
        if config.imap.secret_ref:
            try:
                self._project_imap(config.imap)
            except LookupError:
                self.mail_service.gateway.record_health(
                    status="unavailable", error_code="imap_credential_missing"
                )
                failures["imap"] = "imap_credential_missing"
        return failures

    def import_operational_configuration(self) -> bool:
        """One-time bridge for installations configured before CC-4."""
        document, updated = self._copy()
        changed = False
        current = document.configuration.connectors
        boss = self.connector_service.get_boss()
        if boss["enabled"] and not current.opencli.boss.enabled:
            updated.connectors.opencli.boss = OpenCliBossConfiguration(**{
                key: boss[key] for key in OpenCliBossConfiguration.model_fields
            })
            changed = True
        nowcoder = self.nowcoder_service.get()
        if nowcoder["enabled"] and not current.opencli.nowcoder.enabled:
            updated.connectors.opencli.nowcoder = OpenCliNowcoderConfiguration(**{
                key: nowcoder[key]
                for key in OpenCliNowcoderConfiguration.model_fields
            })
            changed = True
        mail = self.mail_service.get()
        if mail["configured"] and current.imap.secret_ref is None:
            account = mail["account"]
            try:
                password = self.mail_service.secrets.get(self.imap_secret_ref)
            except LookupError:
                try:
                    password = self.mail_service.secrets.get("imap-account:primary")
                except LookupError:
                    return False
                self.mail_service.secrets.set(self.imap_secret_ref, password)
            updated.connectors.imap = ImapConfiguration(
                enabled=mail["enabled"], secret_ref=self.imap_secret_ref,
                **{
                    key: account[key]
                    for key in ImapConfiguration.model_fields
                    if key not in {"enabled", "secret_ref"}
                },
            )
            changed = True
        if changed:
            self._save(
                document.revision, updated,
                "迁移既有 Connector 配置到 CareerConsole 工作区",
            )
        return changed

    def _project_boss(self, config: OpenCliBossConfiguration) -> dict[str, Any]:
        return self.connector_service.configure(
            **config.model_dump(), schedule_enabled=False,
            schedule_times=["09:00"], timezone="Asia/Shanghai",
        )

    def _project_nowcoder(self, config: OpenCliNowcoderConfiguration) -> dict[str, Any]:
        return self.nowcoder_service.configure(**config.model_dump(exclude={"timezone"}))

    def _project_imap(self, config: ImapConfiguration) -> dict[str, Any]:
        password = self.mail_service.secrets.get(
            config.secret_ref or self.imap_secret_ref
        )
        return self.mail_service.configure(
            password=password, **config.model_dump(exclude={"secret_ref"})
        )

    def _copy(self) -> tuple[Any, Any]:
        document = self.configuration.store.load()
        if document is None:
            raise RuntimeError("Workspace configuration has not been initialized.")
        return document, document.configuration.model_copy(deep=True)

    def _save(self, revision: int, configuration: Any, reason: str) -> dict[str, Any]:
        return self.configuration.update(ConfigurationUpdate(
            expected_revision=revision, reason=reason, configuration=configuration,
        ))
