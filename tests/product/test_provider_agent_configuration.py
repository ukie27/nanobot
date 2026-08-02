from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from career_console.infrastructure.agent_runtime import CareerAgentRuntime
from career_console.infrastructure.secrets import InMemorySecretStore
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app
from career_console.runtime.providers.base import LLMResponse


def _client(tmp_path: Path) -> tuple[TestClient, object]:
    settings = CareerSettings(
        data_dir=tmp_path / "workspace",
        mail_intelligence_mode="disabled",
        profile_insight_mode="disabled",
        job_fit_agent_mode="disabled",
        resume_direction_mode="disabled",
        material_agent_mode="disabled",
    )
    app = create_app(settings)
    return TestClient(app), app


def test_provider_secret_is_external_and_agent_task_resolves(tmp_path: Path) -> None:
    client, app = _client(tmp_path)
    with client:
        secrets = InMemorySecretStore()
        app.state.secret_store = secrets
        app.state.agent_runtime = CareerAgentRuntime(
            app.state.configuration_service, secrets
        )
        response = client.put("/api/v1/configuration/providers/main", json={
            "expected_revision": 1,
            "provider_type": "openai",
            "display_name": "主模型",
            "enabled": True,
            "api_base": "https://example.invalid/v1",
            "default_model": "gpt-test",
            "models": ["gpt-test", "gpt-review"],
            "api_key": "test-secret-key",
        })
        assert response.status_code == 200, response.text
        provider = response.json()["provider"]
        assert provider["has_secret"] is True
        assert "api_key" not in provider
        config_text = (
            app.state.settings.config_dir / "application.json"
        ).read_text(encoding="utf-8")
        assert "test-secret-key" not in config_text
        assert "test-secret-key" not in json.dumps(
            client.get("/api/v1/configuration/changes").json()
        )

        status = client.get("/api/v1/configuration").json()
        agents = status["configuration"]["agents"]
        agents["tasks"]["job_fit"]["enabled"] = True
        agents["tasks"]["job_fit"]["provider_id"] = "main"
        agents["tasks"]["job_fit"]["model"] = "gpt-review"
        mapped = client.put("/api/v1/configuration/agents", json={
            "expected_revision": status["revision"], "agents": agents,
        })
        assert mapped.status_code == 200, mapped.text
        resolved = app.state.agent_runtime.resolve("job_fit")
        assert resolved is not None
        assert resolved.model == "gpt-review"
        assert resolved.provider.api_key == "test-secret-key"


def test_provider_revision_conflict_restores_previous_secret(tmp_path: Path) -> None:
    client, app = _client(tmp_path)
    with client:
        secrets = InMemorySecretStore()
        app.state.secret_store = secrets
        first = client.put("/api/v1/configuration/providers/main", json={
            "expected_revision": 1, "provider_type": "openai",
            "display_name": "Main", "default_model": "gpt-test",
            "models": ["gpt-test"], "api_key": "original-key",
        })
        assert first.status_code == 200
        conflict = client.put("/api/v1/configuration/providers/main", json={
            "expected_revision": 1, "provider_type": "openai",
            "display_name": "Main", "default_model": "gpt-test",
            "models": ["gpt-test"], "api_key": "should-rollback",
        })
        assert conflict.status_code == 409
        reference = first.json()["provider"]["secret_ref"]
        assert secrets.get(reference) == "original-key"


def test_provider_connection_test_discards_content_and_audits(tmp_path: Path) -> None:
    class FakeProvider:
        async def chat(self, **_kwargs):
            return LLMResponse(content="sensitive model output", finish_reason="stop")

    client, app = _client(tmp_path)
    with client:
        created = client.put("/api/v1/configuration/providers/local", json={
            "expected_revision": 1, "provider_type": "ollama",
            "display_name": "Local", "api_base": "http://127.0.0.1:11434/v1",
            "default_model": "qwen-local", "models": ["qwen-local"],
        })
        assert created.status_code == 200, created.text
        app.state.agent_runtime.factory.build = lambda *_args: FakeProvider()
        tested = client.post("/api/v1/configuration/providers/local/test", json={})
        assert tested.status_code == 200
        assert tested.json()["status"] == "passed"
        history = client.get(
            "/api/v1/configuration/provider-tests?provider_id=local"
        ).json()
        assert history["total"] == 1
        assert "content" not in json.dumps(history).lower()
        assert "sensitive model output" not in json.dumps(history)


def test_provider_connection_test_preserves_sanitized_error_code(tmp_path: Path) -> None:
    class FakeProvider:
        async def chat(self, **_kwargs):
            return LLMResponse(
                content="Error calling LLM: authentication failed.",
                finish_reason="error",
                error_code="provider_authentication_failed",
            )

    client, app = _client(tmp_path)
    with client:
        created = client.put("/api/v1/configuration/providers/local", json={
            "expected_revision": 1, "provider_type": "ollama",
            "display_name": "Local", "api_base": "http://127.0.0.1:11434/v1",
            "default_model": "qwen-local", "models": ["qwen-local"],
        })
        assert created.status_code == 200, created.text
        app.state.agent_runtime.factory.build = lambda *_args: FakeProvider()

        tested = client.post("/api/v1/configuration/providers/local/test", json={})

        assert tested.status_code == 200
        assert tested.json()["status"] == "failed"
        assert tested.json()["error_code"] == "provider_authentication_failed"


def test_resume_import_uses_updated_provider_without_service_restart(
    tmp_path: Path,
) -> None:
    import_calls: list[tuple[str, str | None]] = []

    class FakeProvider:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        async def chat(self, **_kwargs):
            return LLMResponse(content="OK")

        async def chat_with_retry(self, **kwargs):
            import_calls.append((self.api_key, kwargs.get("model")))
            return LLMResponse(
                content=json.dumps(
                    {
                        "schemaVersion": "candidate_profile_object.v3",
                        "objects": [],
                    }
                )
            )

    client, app = _client(tmp_path)
    with client:
        secrets = InMemorySecretStore()
        app.state.secret_store = secrets
        app.state.agent_runtime.factory.secrets = secrets

        def build(provider_config, _task):
            return FakeProvider(secrets.get(provider_config.secret_ref))

        app.state.agent_runtime.factory.build = build
        created = client.put(
            "/api/v1/configuration/providers/main",
            json={
                "expected_revision": 1,
                "provider_type": "openai",
                "display_name": "Main",
                "default_model": "model-v1",
                "models": ["model-v1", "model-v2"],
                "api_key": "credential-v1",
            },
        )
        assert created.status_code == 200, created.text

        status = client.get("/api/v1/configuration").json()
        agents = status["configuration"]["agents"]
        agents["tasks"]["fact_extraction"].update(
            {
                "enabled": True,
                "provider_id": "main",
                "model": "model-v1",
            }
        )
        mapped = client.put(
            "/api/v1/configuration/agents",
            json={"expected_revision": status["revision"], "agents": agents},
        )
        assert mapped.status_code == 200, mapped.text

        first_import = client.post(
            "/api/v1/documents/import-text",
            json={"name": "resume-v1", "text": "Skills: Python"},
        )
        assert first_import.status_code == 201, first_import.text

        status = client.get("/api/v1/configuration").json()
        updated = client.put(
            "/api/v1/configuration/providers/main",
            json={
                "expected_revision": status["revision"],
                "provider_type": "openai",
                "display_name": "Main",
                "default_model": "model-v2",
                "models": ["model-v1", "model-v2"],
                "api_key": "credential-v2",
            },
        )
        assert updated.status_code == 200, updated.text

        status = client.get("/api/v1/configuration").json()
        agents = status["configuration"]["agents"]
        agents["tasks"]["fact_extraction"]["model"] = "model-v2"
        remapped = client.put(
            "/api/v1/configuration/agents",
            json={"expected_revision": status["revision"], "agents": agents},
        )
        assert remapped.status_code == 200, remapped.text
        tested = client.post("/api/v1/configuration/providers/main/test", json={})
        assert tested.status_code == 200
        assert tested.json()["status"] == "passed"

        second_import = client.post(
            "/api/v1/documents/import-text",
            json={"name": "resume-v2", "text": "Skills: Python and SQL"},
        )
        assert second_import.status_code == 201, second_import.text

    assert import_calls == [
        ("credential-v1", "model-v1"),
        ("credential-v2", "model-v2"),
    ]
