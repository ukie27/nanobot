from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


class MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, reference: str, value: str) -> None:
        self.values[reference] = value

    def get(self, reference: str) -> str:
        if reference not in self.values:
            raise LookupError(reference)
        return self.values[reference]

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


class FakeQQSender:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send(self, **values) -> None:
        self.calls.append(values)


class FailingQQSender:
    def send(self, **_values) -> None:
        raise RuntimeError("secret-bearing provider failure")


def _payload(revision: int, secret: str | None = "qq-secret-value") -> dict:
    return {
        "expected_revision": revision, "enabled": True,
        "app_id": "102000000", "secret": secret, "allow_from": [],
        "notification_targets": ["c2c:user-open-id"],
        "event_subscriptions": ["task_reminder", "system_alert"],
        "message_format": "plain", "outbound_only": True,
        "quiet_hours": {
            "enabled": True, "start": "22:00", "end": "08:00",
            "timezone": "Asia/Shanghai",
        },
    }


def test_qq_secret_test_delivery_and_audit_are_sanitized(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        service = client.app.state.channel_configuration
        service.secrets = MemorySecrets()
        service.qq_sender = FakeQQSender()
        revision = client.get("/api/v1/configuration").json()["revision"]
        saved = client.put("/api/v1/channels/qq", json=_payload(revision))
        assert saved.status_code == 200
        assert saved.json()["has_secret"] is True
        assert "secret_ref" not in saved.text
        config_text = (settings.config_dir / "application.json").read_text("utf-8")
        assert "qq-secret-value" not in config_text
        assert "career-console:" in config_text

        tested = client.post("/api/v1/channels/qq/test")
        assert tested.status_code == 200
        assert tested.json()["status"] == "passed"
        assert tested.json()["target_masked"].startswith("c2c:sha256:")
        assert "user-open-id" not in tested.text
        assert service.qq_sender.calls[0]["secret"] == "qq-secret-value"
        history = client.get("/api/v1/channels/deliveries").json()
        assert history["total"] == 1
        assert "CareerConsole 通知通道测试成功" not in json.dumps(history)


def test_qq_revision_conflict_restores_previous_secret(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        service = client.app.state.channel_configuration
        service.secrets = MemorySecrets()
        revision = client.get("/api/v1/configuration").json()["revision"]
        assert client.put("/api/v1/channels/qq", json=_payload(revision)).status_code == 200
        conflict = client.put(
            "/api/v1/channels/qq", json=_payload(revision, "replacement-secret")
        )
        assert conflict.status_code == 409
        reference = next(iter(service.secrets.values))
        assert service.secrets.get(reference) == "qq-secret-value"


def test_qq_unexpected_delivery_error_is_sanitized_and_isolated(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        service = client.app.state.channel_configuration
        service.secrets = MemorySecrets()
        service.qq_sender = FailingQQSender()
        revision = client.get("/api/v1/configuration").json()["revision"]
        payload = _payload(revision)
        payload["quiet_hours"]["enabled"] = False
        assert client.put("/api/v1/channels/qq", json=payload).status_code == 200

        result = service.dispatch_notifications([{
            "id": "notification-id", "title": "提醒", "body": "正文",
            "status": "unread",
        }])

        assert result == {"sent": 0, "failed": 1, "skipped": 0}
        history = client.get("/api/v1/channels/deliveries").json()
        assert history["items"][0]["error_code"] == "delivery_failed"
        assert "secret-bearing" not in json.dumps(history)
