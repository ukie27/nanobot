from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from career_console.infrastructure.secrets import InMemorySecretStore
from career_console.infrastructure.settings import CareerSettings
from career_console.infrastructure.workspace import OnboardingService
from career_console.interfaces.http import create_app

OPTIONAL_ONBOARDING_STEPS = (
    "provider",
    "profile",
    "recruitment_sources",
    "mail",
    "channel",
    "scheduler",
)


def complete_onboarding_service(service: OnboardingService) -> None:
    service.update_step("workspace", "configured")
    for step in OPTIONAL_ONBOARDING_STEPS:
        service.update_step(step, "skipped")
    service.complete(skipped_steps=list(OPTIONAL_ONBOARDING_STEPS))


def test_onboarding_service_persists_validated_completion(tmp_path: Path) -> None:
    path = tmp_path / "config" / "onboarding.json"
    service = OnboardingService(path)

    assert service.is_complete() is False
    service.update_step("workspace", "configured")
    service.update_step("provider", "configured")
    for step in ("profile", "recruitment_sources", "mail", "channel", "scheduler"):
        service.update_step(step, "skipped")
    record = service.complete(skipped_steps=["mail", "profile", "mail"])

    assert service.is_complete() is True
    assert record.skipped_steps == [
        "channel",
        "mail",
        "profile",
        "recruitment_sources",
        "scheduler",
    ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == "career-console.onboarding.v1"
    assert payload["completedAt"] is not None
    assert payload["skippedSteps"] == [
        "channel",
        "mail",
        "profile",
        "recruitment_sources",
        "scheduler",
    ]

    try:
        service.complete(skipped_steps=["unknown"])
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown onboarding steps must be rejected")


def test_onboarding_api_transitions_between_bootstrap_and_product(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        initial = client.get("/api/v1/onboarding")
        assert initial.status_code == 200
        assert initial.json()["runtime_mode"] == "bootstrap"
        assert initial.json()["completed"] is False
        assert initial.json()["workspace_ready"] is True

        for step in OPTIONAL_ONBOARDING_STEPS:
            response = client.put(
                f"/api/v1/onboarding/steps/{step}",
                json={"state": "skipped"},
            )
            assert response.status_code == 200, response.text

        completed = client.post(
            "/api/v1/onboarding/complete",
            json={"skipped_steps": list(OPTIONAL_ONBOARDING_STEPS)},
        )
        assert completed.status_code == 200
        assert completed.json()["runtime_mode"] == "product"
        assert completed.json()["skipped_steps"] == sorted(OPTIONAL_ONBOARDING_STEPS)
        assert completed.json()["restart_required"] is True

        reopened = client.post("/api/v1/onboarding/reopen", json={})
        assert reopened.status_code == 200
        assert reopened.json()["runtime_mode"] == "bootstrap"
        assert reopened.json()["completed"] is False


def test_mail_capability_means_configured_not_polling_enabled(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        secrets = InMemorySecretStore()
        client.app.state.secret_store = secrets
        client.app.state.mail_service.secrets = secrets

        configured = client.put(
            "/api/v1/mail/account",
            json={
                "enabled": False,
                "email_address": "candidate@example.com",
                "host": "imap.example.com",
                "port": 993,
                "username": "candidate@example.com",
                "password": "app-password",
                "folder": "INBOX",
                "initial_lookback_days": 30,
                "poll_interval_minutes": 10,
            },
        )

        assert configured.status_code == 200, configured.text
        assert configured.json()["configured"] is True
        assert configured.json()["enabled"] is False
        status = client.get("/api/v1/onboarding").json()
        assert status["capabilities"]["mail"] is True


def test_bootstrap_workspace_must_be_replaced_before_completion(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path / "bootstrap" / "workspaces" / "default")
    with TestClient(create_app(settings)) as client:
        client.app.state.bootstrap_workspace = True
        response = client.post(
            "/api/v1/onboarding/complete", json={"skipped_steps": []}
        )
        assert response.status_code == 409
        assert "workspace_required" in response.text


def test_restart_endpoint_uses_replaceable_callback(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    called: list[str] = []
    with TestClient(create_app(settings)) as client:
        client.app.state.restart_callback = lambda: called.append("restart")
        response = client.post("/api/v1/system/restart", json={})
        assert response.status_code == 202
        deadline = time.monotonic() + 1
        while not called and time.monotonic() < deadline:
            time.sleep(0.01)
    assert called == ["restart"]


def test_scheduler_loop_is_gated_by_onboarding(
    tmp_path: Path, monkeypatch,
) -> None:
    calls: list[str] = []

    async def fake_scheduler_loop(_runtime, stop: asyncio.Event) -> None:
        calls.append("started")
        await stop.wait()

    monkeypatch.setattr(
        "career_console.interfaces.http.app._scheduler_loop", fake_scheduler_loop
    )

    bootstrap_settings = CareerSettings(data_dir=tmp_path / "bootstrap")
    with TestClient(create_app(bootstrap_settings)) as client:
        assert client.app.state.scheduler_startup == {
            "schedules_processed": 0,
            "reminders_triggered": 0,
            "outbox_dispatched": 0,
            "leases_recovered": 0,
        }
        assert calls == []

    product_settings = CareerSettings(data_dir=tmp_path / "product")
    product_settings.ensure_directories()
    complete_onboarding_service(
        OnboardingService(product_settings.config_dir / "onboarding.json")
    )
    with TestClient(create_app(product_settings)):
        assert calls == ["started"]
