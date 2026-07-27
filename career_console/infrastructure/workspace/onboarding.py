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
ONBOARDING_STEPS = (
    "workspace", "provider", "profile", "recruitment_sources",
    "mail", "channel", "scheduler",
)
STEP_STATES = frozenset({
    "not_started", "in_progress", "configured", "skipped", "failed_validation",
})
OPTIONAL_STEPS = frozenset(set(ONBOARDING_STEPS) - {"workspace"})


class OnboardingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(
        default="career-console.onboarding.v1", alias="schemaVersion"
    )
    onboarding_version: int = Field(default=ONBOARDING_VERSION, alias="onboardingVersion")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    skipped_steps: list[str] = Field(default_factory=list, alias="skippedSteps")
    step_states: dict[str, str] = Field(default_factory=dict, alias="stepStates")


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
        mail_ready: bool | None = None,
    ) -> dict[str, Any]:
        record = self.load()
        imap = configuration.connectors.imap
        resolved_mail_ready = mail_ready if mail_ready is not None else bool(
            imap.secret_ref and imap.email_address and imap.host and imap.username
        )
        capabilities = {
            "workspace": workspace_ready,
            "provider": any(item.enabled for item in configuration.providers.values()),
            "profile": profile_ready,
            "mail": resolved_mail_ready,
            "opencli": configuration.connectors.opencli.nowcoder.enabled,
            "channel": configuration.channels.qq.enabled,
            "scheduler": configuration.scheduler.enabled,
        }
        complete = self.is_complete()
        detected = {
            "workspace": workspace_ready,
            "provider": capabilities["provider"],
            "profile": capabilities["profile"],
            "recruitment_sources": capabilities["opencli"],
            "mail": capabilities["mail"],
            "channel": capabilities["channel"],
            "scheduler": capabilities["scheduler"],
        }
        step_states = {
            step: record.step_states.get(
                step,
                "configured" if detected[step]
                else "skipped" if step in record.skipped_steps
                else "not_started",
            )
            for step in ONBOARDING_STEPS
        }
        return {
            "schema_version": record.schema_version,
            "onboarding_version": record.onboarding_version,
            "required_version": ONBOARDING_VERSION,
            "completed": complete,
            "completed_at": record.completed_at,
            "skipped_steps": record.skipped_steps,
            "step_states": step_states,
            "workspace_ready": workspace_ready,
            "restart_required": restart_required,
            "runtime_mode": "product" if complete else "bootstrap",
            "capabilities": capabilities,
        }

    def complete(self, *, skipped_steps: list[str]) -> OnboardingRecord:
        invalid = sorted(set(skipped_steps) - OPTIONAL_STEPS)
        if invalid:
            raise ValueError(f"Unknown optional onboarding steps: {', '.join(invalid)}")
        current = self.load()
        states = dict(current.step_states)
        for step in skipped_steps:
            states[step] = "skipped"
        incomplete = [
            step for step in ONBOARDING_STEPS
            if states.get(step) not in {"configured", "skipped"}
        ]
        if incomplete:
            raise ValueError(
                "Onboarding steps require a decision: " + ", ".join(incomplete)
            )
        if states.get("workspace") != "configured":
            raise ValueError("Workspace onboarding step must be configured.")
        record = OnboardingRecord(
            completedAt=datetime.now(UTC),
            skippedSteps=sorted(
                step for step, state in states.items() if state == "skipped"
            ),
            stepStates=states,
        )
        self._save(record)
        return record

    def reopen(self) -> OnboardingRecord:
        current = self.load()
        record = OnboardingRecord(stepStates=current.step_states)
        self._save(record)
        return record

    def update_step(self, step: str, state: str) -> OnboardingRecord:
        if step not in ONBOARDING_STEPS:
            raise ValueError(f"Unknown onboarding step: {step}")
        if state not in STEP_STATES:
            raise ValueError(f"Unknown onboarding state: {state}")
        if step == "workspace" and state == "skipped":
            raise ValueError("Workspace onboarding step cannot be skipped.")
        current = self.load()
        states = dict(current.step_states)
        states[step] = state
        record = current.model_copy(update={
            "completed_at": None,
            "step_states": states,
            "skipped_steps": sorted(
                name for name, value in states.items() if value == "skipped"
            ),
        })
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
