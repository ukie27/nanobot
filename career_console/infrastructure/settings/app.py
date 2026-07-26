"""Typed settings and local data paths for the Career application."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from career_console.infrastructure.workspace import (
    WorkspaceManager,
    WorkspacePaths,
    default_workspace_path,
)


class CareerSettings(BaseSettings):
    """CareerConsole runtime settings, overridable with ``CAREER_CONSOLE_*`` variables."""

    model_config = SettingsConfigDict(
        env_prefix="CAREER_CONSOLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=default_workspace_path)
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    log_level: str = "INFO"
    auto_migrate: bool = True
    job_lease_seconds: int = Field(default=60, ge=10, le=3600)
    log_retention_days: int = Field(default=14, ge=1, le=365)
    agent_trace_retention_days: int = Field(default=30, ge=1, le=3650)
    max_document_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    fact_extractor_mode: Literal["local", "agent"] = "local"
    mail_intelligence_mode: Literal["disabled", "agent"] = "agent"
    profile_insight_mode: Literal["disabled", "agent"] = "agent"
    job_fit_agent_mode: Literal["disabled", "agent"] = "agent"
    resume_direction_mode: Literal["disabled", "agent"] = "agent"
    material_agent_mode: Literal["disabled", "agent"] = "agent"
    opencli_executable: Path | None = None

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: object) -> Path:
        return Path(str(value)).expanduser().resolve(strict=False)

    @field_validator("opencli_executable", mode="before")
    @classmethod
    def _expand_opencli_executable(cls, value: object) -> Path | None:
        if value in (None, ""):
            return None
        return Path(str(value)).expanduser().resolve(strict=False)

    @property
    def database_path(self) -> Path:
        return self.workspace_paths.database

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def runtime_dir(self) -> Path:
        return self.workspace_paths.runtime

    @property
    def logs_dir(self) -> Path:
        return self.workspace_paths.logs

    @property
    def backups_dir(self) -> Path:
        return self.workspace_paths.backups

    @property
    def blobs_dir(self) -> Path:
        return self.workspace_paths.blobs

    @property
    def exports_dir(self) -> Path:
        return self.workspace_paths.exports

    @property
    def config_dir(self) -> Path:
        return self.workspace_paths.config

    @property
    def secrets_dir(self) -> Path:
        return self.workspace_paths.secrets

    @property
    def integrations_dir(self) -> Path:
        return self.workspace_paths.integrations

    @property
    def workspace_paths(self) -> WorkspacePaths:
        return WorkspacePaths(self.data_dir)

    @property
    def instance_lock_path(self) -> Path:
        return self.runtime_dir / "career.lock"

    @property
    def web_dist_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "interfaces" / "http" / "web_dist"

    def ensure_directories(self) -> None:
        """Create the controlled application directories."""
        WorkspaceManager().ensure(self.data_dir)
