"""Public configuration contracts and field-level activation metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ActivationEffect = Literal["hot_reload", "service_reload", "restart_required"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeneralConfiguration(StrictModel):
    locale: Literal["zh-CN", "en-US"] = "zh-CN"
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    date_format: Literal["yyyy-MM-dd", "yyyy/MM/dd"] = "yyyy-MM-dd"
    open_browser_on_start: bool = True


class AppearanceConfiguration(StrictModel):
    density: Literal["comfortable", "compact"] = "comfortable"
    reduce_motion: bool = False


class RuntimeConfiguration(StrictModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_retention_days: int = Field(default=14, ge=1, le=365)
    agent_trace_retention_days: int = Field(default=30, ge=1, le=3650)
    job_lease_seconds: int = Field(default=60, ge=10, le=3600)
    max_document_mb: int = Field(default=10, ge=1, le=50)


class PrivacyConfiguration(StrictModel):
    diagnostics_metadata_enabled: bool = True
    redact_sensitive_logs: Literal[True] = True
    local_only_network_binding: Literal[True] = True


ProviderType = Literal[
    "custom", "azure_openai", "anthropic", "openai", "openrouter", "deepseek",
    "gemini", "zhipu", "dashscope", "moonshot", "minimax", "mistral",
    "stepfun", "xiaomi_mimo", "aihubmix", "siliconflow", "volcengine",
    "volcengine_coding_plan", "byteplus", "byteplus_coding_plan", "groq",
    "ollama", "vllm", "ovms",
]


class ProviderConfiguration(StrictModel):
    provider_type: ProviderType
    display_name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    api_base: str | None = Field(default=None, max_length=500)
    default_model: str = Field(min_length=1, max_length=200)
    models: list[str] = Field(default_factory=list, max_length=100)
    secret_ref: str | None = Field(default=None, max_length=300)

    @field_validator("models")
    @classmethod
    def _unique_models(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Provider model names must be unique.")
        return normalized


class AgentTaskConfiguration(StrictModel):
    enabled: bool = False
    provider_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    model: str | None = Field(default=None, max_length=200)
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=256, le=65536)
    reasoning_effort: Literal["low", "medium", "high"] | None = None


class AgentTaskMappings(StrictModel):
    fact_extraction: AgentTaskConfiguration = Field(default_factory=AgentTaskConfiguration)
    mail_intelligence: AgentTaskConfiguration = Field(default_factory=AgentTaskConfiguration)
    profile_insight: AgentTaskConfiguration = Field(default_factory=AgentTaskConfiguration)
    job_fit: AgentTaskConfiguration = Field(default_factory=AgentTaskConfiguration)
    daily_job_recommendation: AgentTaskConfiguration = Field(default_factory=AgentTaskConfiguration)
    resume_direction: AgentTaskConfiguration = Field(default_factory=AgentTaskConfiguration)
    resume_drafting: AgentTaskConfiguration = Field(default_factory=lambda: AgentTaskConfiguration(max_tokens=8192))
    material_review: AgentTaskConfiguration = Field(default_factory=lambda: AgentTaskConfiguration(max_tokens=6144))


class AgentConfiguration(StrictModel):
    tasks: AgentTaskMappings = Field(default_factory=AgentTaskMappings)


def _validate_clock_times(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        parts = value.strip().split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("Schedule times must use HH:MM.")
        hour, minute = map(int, parts)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Schedule times must use a valid 24-hour clock.")
        normalized.append(f"{hour:02d}:{minute:02d}")
    if len(set(normalized)) != len(normalized):
        raise ValueError("Schedule times must be unique.")
    return sorted(normalized)


class OpenCliBossConfiguration(StrictModel):
    enabled: bool = False
    profile_alias: str = Field(default="default", min_length=1, max_length=120)
    search_query: str = Field(default="", max_length=200)
    city: str = Field(default="全国", min_length=1, max_length=100)
    result_limit: int = Field(default=15, ge=1, le=50)


class OpenCliNowcoderConfiguration(StrictModel):
    enabled: bool = False
    search_query: str = Field(default="", max_length=200)
    city: str = Field(default="全国", min_length=1, max_length=100)
    result_limit: int = Field(default=500, ge=1, le=1000)
    schedule_enabled: bool = False
    schedule_times: list[str] = Field(default_factory=lambda: ["09:00"], min_length=1, max_length=8)
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"

    @field_validator("schedule_times")
    @classmethod
    def _valid_schedule_times(cls, values: list[str]) -> list[str]:
        return _validate_clock_times(values)


class OpenCliConfiguration(StrictModel):
    executable: str | None = Field(default=None, max_length=1000)
    boss: OpenCliBossConfiguration = Field(default_factory=OpenCliBossConfiguration)
    nowcoder: OpenCliNowcoderConfiguration = Field(default_factory=OpenCliNowcoderConfiguration)


class ImapConfiguration(StrictModel):
    enabled: bool = False
    email_address: str = Field(default="", max_length=320)
    host: str = Field(default="", max_length=255)
    port: int = Field(default=993, ge=1, le=65535)
    username: str = Field(default="", max_length=320)
    folder: Literal["INBOX"] = "INBOX"
    initial_lookback_days: int = Field(default=30, ge=1, le=30)
    poll_interval_minutes: int = Field(default=10, ge=5, le=1440)
    secret_ref: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _enabled_account_is_complete(self) -> "ImapConfiguration":
        if self.enabled and (
            not self.email_address or "@" not in self.email_address
            or not self.host or not self.username
        ):
            raise ValueError("Enabled IMAP requires email, host, and username.")
        return self


class ConnectorConfiguration(StrictModel):
    opencli: OpenCliConfiguration = Field(default_factory=OpenCliConfiguration)
    imap: ImapConfiguration = Field(default_factory=ImapConfiguration)


class QuietHoursConfiguration(StrictModel):
    enabled: bool = False
    start: str = "22:00"
    end: str = "08:00"
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"

    @field_validator("start", "end")
    @classmethod
    def _valid_time(cls, value: str) -> str:
        return _validate_clock_times([value])[0]


class QQChannelConfiguration(StrictModel):
    enabled: bool = False
    app_id: str = Field(default="", max_length=120)
    allow_from: list[str] = Field(default_factory=list, max_length=100)
    notification_targets: list[str] = Field(default_factory=list, max_length=100)
    event_subscriptions: list[Literal[
        "task_reminder", "application_update", "daily_digest", "system_alert"
    ]] = Field(default_factory=lambda: ["task_reminder", "system_alert"])
    message_format: Literal["plain", "markdown"] = "plain"
    outbound_only: Literal[True] = True
    quiet_hours: QuietHoursConfiguration = Field(default_factory=QuietHoursConfiguration)
    secret_ref: str | None = Field(default=None, max_length=300)

    @field_validator("notification_targets")
    @classmethod
    def _valid_notification_targets(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(set(normalized)) != len(normalized):
            raise ValueError("QQ notification targets must be unique.")
        if any(
            not value.startswith(("c2c:", "group:")) or len(value.split(":", 1)[1]) < 3
            for value in normalized
        ):
            raise ValueError("QQ targets must use c2c:<openid> or group:<openid>.")
        return normalized

    @model_validator(mode="after")
    def _enabled_channel_is_complete(self) -> "QQChannelConfiguration":
        if self.enabled and (not self.app_id or not self.notification_targets):
            raise ValueError("Enabled QQ requires app_id and a notification target.")
        return self


class ChannelConfiguration(StrictModel):
    qq: QQChannelConfiguration = Field(default_factory=QQChannelConfiguration)
    send_max_retries: int = Field(default=3, ge=0, le=10)


class SchedulerConfiguration(StrictModel):
    enabled: bool = True
    poll_seconds: int = Field(default=60, ge=10, le=3600)
    reminders_enabled: bool = True
    connector_jobs_enabled: bool = False
    profile_maintenance_enabled: bool = False
    profile_maintenance_time: str = "21:30"
    channel_dispatch_enabled: bool = False

    @field_validator("profile_maintenance_time")
    @classmethod
    def _valid_profile_maintenance_time(cls, value: str) -> str:
        return _validate_clock_times([value])[0]


class CareerConsoleConfiguration(StrictModel):
    general: GeneralConfiguration = Field(default_factory=GeneralConfiguration)
    appearance: AppearanceConfiguration = Field(default_factory=AppearanceConfiguration)
    runtime: RuntimeConfiguration = Field(default_factory=RuntimeConfiguration)
    privacy: PrivacyConfiguration = Field(default_factory=PrivacyConfiguration)
    providers: dict[str, ProviderConfiguration] = Field(default_factory=dict)
    agents: AgentConfiguration = Field(default_factory=AgentConfiguration)
    connectors: ConnectorConfiguration = Field(default_factory=ConnectorConfiguration)
    channels: ChannelConfiguration = Field(default_factory=ChannelConfiguration)
    scheduler: SchedulerConfiguration = Field(default_factory=SchedulerConfiguration)

    @model_validator(mode="after")
    def _validate_provider_references(self) -> "CareerConsoleConfiguration":
        for provider_id, provider in self.providers.items():
            if not provider_id or not provider_id[0].isalpha() or any(
                char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in provider_id
            ):
                raise ValueError(f"Invalid provider ID: {provider_id}")
            expected_suffix = f":provider:{provider_id}:api-key"
            if provider.secret_ref and not provider.secret_ref.endswith(expected_suffix):
                raise ValueError(f"Provider secret_ref does not belong to {provider_id}.")
        for task_name, task in self.agents.tasks:
            if task.enabled and not task.provider_id:
                raise ValueError(f"Enabled agent task {task_name} requires a provider.")
            if task.provider_id:
                provider = self.providers.get(task.provider_id)
                if provider is None:
                    raise ValueError(
                        f"Agent task {task_name} references an unknown provider."
                    )
                if task.enabled and not provider.enabled:
                    raise ValueError(
                        f"Enabled agent task {task_name} requires an enabled provider."
                    )
        imap_ref = self.connectors.imap.secret_ref
        if imap_ref and not imap_ref.endswith(":connector:imap:password"):
            raise ValueError("IMAP secret_ref does not belong to the IMAP connector.")
        qq_ref = self.channels.qq.secret_ref
        if qq_ref and not qq_ref.endswith(":channel:qq:secret"):
            raise ValueError("QQ secret_ref does not belong to the QQ channel.")
        return self


class ConfigurationDocument(StrictModel):
    schema_version: Literal["career-console.configuration.v1"] = (
        "career-console.configuration.v1"
    )
    revision: int = Field(ge=1)
    updated_at: datetime
    configuration: CareerConsoleConfiguration


class ConfigurationUpdate(StrictModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(default="用户从设置页面更新配置", min_length=1, max_length=300)
    configuration: CareerConsoleConfiguration


FIELD_EFFECTS: dict[str, ActivationEffect] = {
    "general.locale": "restart_required",
    "general.timezone": "restart_required",
    "general.date_format": "hot_reload",
    "general.open_browser_on_start": "restart_required",
    "appearance.density": "hot_reload",
    "appearance.reduce_motion": "hot_reload",
    "runtime.log_level": "restart_required",
    "runtime.log_retention_days": "restart_required",
    "runtime.agent_trace_retention_days": "restart_required",
    "runtime.job_lease_seconds": "restart_required",
    "runtime.max_document_mb": "restart_required",
    "privacy.diagnostics_metadata_enabled": "service_reload",
    "privacy.redact_sensitive_logs": "restart_required",
    "privacy.local_only_network_binding": "restart_required",
    "providers": "restart_required",
    "agents": "restart_required",
    "connectors": "service_reload",
    "channels": "service_reload",
    "scheduler": "service_reload",
}
