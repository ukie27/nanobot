"""Typed settings and local data paths for the Career application."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CareerSettings(BaseSettings):
    """Career runtime settings, overridable with ``NANOBOT_CAREER_*`` variables."""

    model_config = SettingsConfigDict(
        env_prefix="NANOBOT_CAREER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=lambda: Path.home() / ".nanobot" / "career")
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
        return self.data_dir / "career.sqlite3"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def runtime_dir(self) -> Path:
        return self.data_dir / "runtime"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def blobs_dir(self) -> Path:
        return self.data_dir / "blobs"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def instance_lock_path(self) -> Path:
        return self.runtime_dir / "career.lock"

    @property
    def web_dist_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "web_dist"

    def ensure_directories(self) -> None:
        """Create the controlled application directories."""
        for path in (
            self.data_dir,
            self.runtime_dir,
            self.logs_dir,
            self.backups_dir,
            self.blobs_dir,
            self.exports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
