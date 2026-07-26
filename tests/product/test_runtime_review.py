from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


def test_agent_run_and_review_task_share_one_audited_flow(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        imported = client.post(
            "/api/v1/documents/import-text",
            json={"name": "基础简历", "text": "技能：Python"},
        )
        assert imported.status_code == 201, imported.text

        runs = client.get("/api/v1/runtime/agent-runs")
        assert runs.status_code == 200, runs.text
        assert runs.json()["total"] == 1
        run = runs.json()["items"][0]
        assert run["task_type"] == "profile_fact_extraction"
        assert run["execution_mode"] == "task"
        assert run["provider"] == "local"
        assert run["prompt_version"] == "profile_fact_extraction.v1"
        assert run["schema_version"] == "candidate_fact.v1"
        assert run["input_entity_type"] == "document"
        assert len(run["input_hash"]) == 64
        assert len(run["output_hash"]) == 64
        assert run["tool_calls"] == []
        assert run["duration_ms"] >= 0
        assert run["sensitivity"] == "sensitive"

        reviews = client.get("/api/v1/runtime/reviews")
        assert reviews.status_code == 200, reviews.text
        assert reviews.json()["total"] == 1
        review = reviews.json()["items"][0]
        assert review["entity_type"] == "candidate_fact"
        assert review["agent_run_id"] == run["id"]
        assert review["source_type"] == "agent_extraction"
        assert review["target_url"] == "/review"
        assert review["title"].startswith("确认职业事实")

        facts = client.get("/api/v1/facts", params={"status": "proposed"}).json()
        fact = facts["items"][0]
        confirmed = client.post(
            f"/api/v1/facts/{fact['id']}/confirm",
            json={"expected_version": fact["version"], "reason": "用户核对原文"},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert client.get("/api/v1/runtime/reviews").json()["total"] == 0

        resolved = client.get(
            "/api/v1/runtime/reviews", params={"status": "resolved"}
        ).json()
        assert resolved["total"] == 1
        assert resolved["items"][0]["resolution"] == "confirmed"
        assert resolved["items"][0]["resolved_by"] == "user"


def test_runtime_details_return_404(tmp_path: Path) -> None:
    with TestClient(create_app(CareerSettings(data_dir=tmp_path / "career"))) as client:
        assert client.get("/api/v1/runtime/reviews/missing").status_code == 404
        assert client.get("/api/v1/runtime/agent-runs/missing").status_code == 404
