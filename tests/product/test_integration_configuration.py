from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from career_console.infrastructure.configuration.schema import CareerConsoleConfiguration
from career_console.infrastructure.database.connector_gateway import (
    NOWCODER_CONNECTOR_ID,
)
from career_console.infrastructure.database.mail_gateway import IMAP_CONNECTOR_ID
from career_console.infrastructure.database.models import ConnectorConfigModel
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


def test_connector_schema_enforces_product_boundaries() -> None:
    configuration = CareerConsoleConfiguration.model_validate({
        "connectors": {
            "opencli": {"nowcoder": {
                "schedule_enabled": True, "schedule_times": ["9:05"],
            }},
            "imap": {"initial_lookback_days": 30},
        },
    })
    assert configuration.connectors.opencli.nowcoder.schedule_times == ["09:05"]
    assert configuration.connectors.opencli.nowcoder.timezone == "Asia/Shanghai"
    assert configuration.connectors.imap.initial_lookback_days == 30
    assert configuration.channels.qq.outbound_only is True


def test_frontend_connector_writes_are_workspace_scoped_and_separated(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path / "workspace")
    with TestClient(create_app(settings)) as client:
        secrets = MemorySecrets()
        client.app.state.mail_service.secrets = secrets
        opencli = client.put(
            "/api/v1/connectors/opencli", json={"executable": "D:/tools/opencli.cmd"}
        )
        assert opencli.status_code == 200
        nowcoder = client.put("/api/v1/connectors/nowcoder", json={
            "enabled": True, "search_query": "后端", "city": "全国",
            "result_limit": 500, "schedule_enabled": True,
            "schedule_times": ["09:00"],
        })
        assert nowcoder.status_code == 200
        mail = client.put("/api/v1/mail/account", json={
            "enabled": True, "email_address": "candidate@example.com",
            "host": "imap.example.com", "port": 993,
            "username": "candidate@example.com", "password": "mail-secret-value",
            "folder": "INBOX", "initial_lookback_days": 30,
            "poll_interval_minutes": 10,
        })
        assert mail.status_code == 200
        configuration = client.get("/api/v1/configuration").json()["configuration"]
        serialized = json.dumps(configuration)
        assert "mail-secret-value" not in serialized
        assert configuration["connectors"]["opencli"]["executable"] == "D:/tools/opencli.cmd"
        assert configuration["connectors"]["opencli"]["nowcoder"]["enabled"] is True
        reference = configuration["connectors"]["imap"]["secret_ref"]
        assert reference.startswith("career-console:")
        assert reference.endswith(":connector:imap:password")
        assert secrets.get(reference) == "mail-secret-value"
        with client.app.state.database.session_factory() as session:
            identities = set(session.scalars(select(ConnectorConfigModel.id)).all())
        assert NOWCODER_CONNECTOR_ID in identities
        assert IMAP_CONNECTOR_ID in identities
        assert NOWCODER_CONNECTOR_ID != IMAP_CONNECTOR_ID
