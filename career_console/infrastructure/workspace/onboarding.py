"""Workspace-owned onboarding state and capability readiness."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ONBOARDING_VERSION = 1
OPTIONAL_STEPS = frozenset({"provider", "profile", "mail", "opencli", "channel"})


class OnboardingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(
        default="career-console.onboarding.v1", alias="schemaVersion"
    )
    onboarding_version: int = Field(default=ONBOARDING_VERSION, alias="onboardingVersion")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    skipped_steps: list[str] = Field(default_factory=list, alias="skippedSteps")


class OnboardingService:
    """Persist setup completion separately from ordinary mutable settings."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> OnboardingRecord:
        if not self.path.is_file():
            return OnboardingRecord()
        try:
            return OnboardingRecord.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return OnboardingRecord()

    def is_complete(self) -> bool:
        record = self.load()
        return (
            record.completed_at is not None
            and record.onboarding_version >= ONBOARDING_VERSION
        )

    def status(
        self,
        *,
        configuration: Any,
        workspace_ready: bool,
        restart_required: bool,
        profile_ready: bool = False,
    ) -> dict[str, Any]:
        record = self.load()
        capabilities = {
            "workspace": workspace_ready,
            "provider": any(item.enabled for item in configuration.providers.values()),
            "profile": profile_ready,
            "mail": configuration.connectors.imap.enabled,
            "opencli": configuration.connectors.opencli.nowcoder.enabled,
            "channel": configuration.channels.qq.enabled,
            "scheduler": configuration.scheduler.enabled,
        }
        complete = self.is_complete()
        return {
            "schema_version": record.schema_version,
            "onboarding_version": record.onboarding_version,
            "required_version": ONBOARDING_VERSION,
            "completed": complete,
            "completed_at": record.completed_at,
            "skipped_steps": record.skipped_steps,
            "workspace_ready": workspace_ready,
            "restart_required": restart_required,
            "runtime_mode": "product" if complete else "bootstrap",
            "capabilities": capabilities,
        }

    def complete(self, *, skipped_steps: list[str]) -> OnboardingRecord:
        invalid = sorted(set(skipped_steps) - OPTIONAL_STEPS)
        if invalid:
            raise ValueError(f"Unknown optional onboarding steps: {', '.join(invalid)}")
        record = OnboardingRecord(
            completedAt=datetime.now(UTC),
            skippedSteps=sorted(set(skipped_steps)),
        )
        self._save(record)
        return record

    def reopen(self) -> OnboardingRecord:
        record = OnboardingRecord()
        self._save(record)
        return record

    def _save(self, record: OnboardingRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}-", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    record.model_dump(mode="json", by_alias=True),
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
