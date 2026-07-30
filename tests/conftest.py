from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def browser_session_for_test_clients(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Make product tests use the same local-session handshake as the web client."""

    original_request = TestClient.request

    def request(self: TestClient, method: str, url: str, **kwargs: Any):
        headers = dict(kwargs.pop("headers", {}) or {})
        skip_bootstrap = headers.pop("X-Test-Skip-Session-Bootstrap", None)
        if (
            not skip_bootstrap
            and method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            and url != "/api/v1/system/session"
        ):
            session = original_request(self, "GET", "/api/v1/system/session")
            session.raise_for_status()
            headers.setdefault("X-CSRF-Token", session.json()["csrf_token"])
        return original_request(self, method, url, headers=headers, **kwargs)

    monkeypatch.setattr(TestClient, "request", request)
    yield
