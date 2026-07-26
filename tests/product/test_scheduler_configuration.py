from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from career_console.infrastructure.scheduling import CareerSchedulerRuntime
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


def _scheduler(**overrides) -> dict:
    return {
        "enabled": True, "poll_seconds": 30, "reminders_enabled": True,
        "connector_jobs_enabled": False, "profile_maintenance_enabled": False,
        "profile_maintenance_time": "21:30", "channel_dispatch_enabled": True,
        **overrides,
    }


def test_scheduler_configuration_controls_execution_and_audits(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        assert client.app.state.scheduler_startup == {
            "schedules_processed": 0,
            "reminders_triggered": 0,
            "outbox_dispatched": 0,
            "leases_recovered": 0,
        }
        revision = client.get("/api/v1/configuration").json()["revision"]
        disabled = client.put("/api/v1/scheduler/configuration", json={
            "expected_revision": revision, "scheduler": _scheduler(enabled=False),
        })
        assert disabled.status_code == 200
        run = client.post("/api/v1/scheduler/run-due", json={})
        assert run.status_code == 200
        assert run.json()["schedules_processed"] == 0
        history = client.get("/api/v1/scheduler/runs").json()
        assert history["items"][0]["status"] == "skipped"
        assert history["items"][0]["error_codes"] == []

        runtime = client.app.state.scheduler_runtime
        runtime.task_service = SimpleNamespace(
            run_due=lambda **_kwargs: {
                "schedules_processed": 2, "reminders_triggered": 1,
                "outbox_dispatched": 1, "leases_recovered": 0,
            },
            gateway=SimpleNamespace(list_notifications=lambda: [
                {"id": "unread", "status": "unread"},
                {"id": "read", "status": "read"},
            ]),
        )
        dispatched = []
        runtime.channels = SimpleNamespace(
            dispatch_notifications=lambda items: (
                dispatched.extend(items)
                or {"sent": 1, "failed": 0, "skipped": 0}
            )
        )
        revision = disabled.json()["configuration_revision"]
        enabled = client.put("/api/v1/scheduler/configuration", json={
            "expected_revision": revision, "scheduler": _scheduler(),
        })
        assert enabled.status_code == 200
        client.post("/api/v1/scheduler/run-due", json={})
        latest = client.get("/api/v1/scheduler/runs").json()["items"][0]
        assert latest["status"] == "succeeded"
        assert latest["counters"]["reminders_triggered"] == 1
        assert latest["counters"]["channel_sent"] == 1
        assert dispatched == [{"id": "unread", "status": "unread"}]


def test_profile_maintenance_uses_china_clock() -> None:
    before = datetime(2026, 7, 26, 13, 29, tzinfo=UTC)
    due = datetime(2026, 7, 26, 13, 30, tzinfo=UTC)
    assert CareerSchedulerRuntime._profile_due("21:30", before) is False
    assert CareerSchedulerRuntime._profile_due("21:30", due) is True


def test_profile_maintenance_runs_only_once_per_china_day(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.scheduler_runtime
        calls = []
        runtime.profile_memory = SimpleNamespace(
            run_due=lambda: calls.append("profile") or {"digest_id": "digest"}
        )
        runtime.profile_impacts = SimpleNamespace(
            enqueue_pending=lambda: None, process_next=lambda: None
        )
        revision = client.get("/api/v1/configuration").json()["revision"]
        response = client.put("/api/v1/scheduler/configuration", json={
            "expected_revision": revision,
            "scheduler": _scheduler(
                reminders_enabled=False,
                profile_maintenance_enabled=True,
                channel_dispatch_enabled=False,
            ),
        })
        assert response.status_code == 200
        now = datetime(2026, 7, 26, 13, 30, tzinfo=UTC)
        runtime.run_once(trigger_type="manual", now=now)
        runtime.run_once(trigger_type="manual", now=now)
        assert calls == ["profile"]
