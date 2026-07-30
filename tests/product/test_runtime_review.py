from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from career_console.infrastructure.extraction import LocalResumeFactExtractor
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


def _test_app(settings: CareerSettings):
    return create_app(settings, fact_extractor=LocalResumeFactExtractor())


def test_agent_run_and_review_task_share_one_audited_flow(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(_test_app(settings)) as client:
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
        assert run["skill_version"] is None
        assert run["schema_version"] == "candidate_profile_object.v2"
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
        assert review["entity_type"] == "review_bundle"
        assert review["bundle_type"] == "profile_section"
        assert review["agent_run_id"] == run["id"]
        assert review["source_type"] == "document_extraction"
        assert review["target_url"] == f"/reviews/{review['id']}"
        assert review["item_count"] >= 1
        assert review["items"][0]["entity_type"] == "candidate_fact"
        assert review["title"]

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
    with TestClient(_test_app(CareerSettings(data_dir=tmp_path / "career"))) as client:
        assert client.get("/api/v1/runtime/reviews/missing").status_code == 404
        assert client.get("/api/v1/runtime/agent-runs/missing").status_code == 404


def test_profile_bundle_can_be_confirmed_as_one_user_decision(tmp_path: Path) -> None:
    with TestClient(_test_app(CareerSettings(data_dir=tmp_path / "career"))) as client:
        imported = client.post(
            "/api/v1/documents/import-text",
            json={"name": "技能资料", "text": "技能：Python、SQL"},
        )
        assert imported.status_code == 201, imported.text
        bundle = client.get("/api/v1/runtime/reviews").json()["items"][0]

        resolved = client.post(
            f"/api/v1/runtime/reviews/{bundle['id']}/resolve",
            json={
                "expected_version": bundle["version"],
                "resolution": "confirmed",
                "reason": "已按整组核对原文",
            },
        )

        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["resolution"] == "confirmed"
        facts = client.get("/api/v1/facts", params={"status": "confirmed"}).json()
        assert facts["total"] >= 1


def test_profile_bundle_can_be_rejected_as_one_user_decision(tmp_path: Path) -> None:
    with TestClient(_test_app(CareerSettings(data_dir=tmp_path / "career"))) as client:
        client.post(
            "/api/v1/documents/import-text",
            json={"name": "错误资料", "text": "技能：不存在的框架"},
        )
        bundle = client.get("/api/v1/runtime/reviews").json()["items"][0]

        resolved = client.post(
            f"/api/v1/runtime/reviews/{bundle['id']}/resolve",
            json={
                "expected_version": bundle["version"],
                "resolution": "rejected",
                "reason": "该组内容不属于本人",
            },
        )

        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["resolution"] == "rejected"
        facts = client.get("/api/v1/facts", params={"status": "rejected"}).json()
        assert facts["total"] >= 1


def test_profile_bundle_rejects_stale_version(tmp_path: Path) -> None:
    with TestClient(_test_app(CareerSettings(data_dir=tmp_path / "career"))) as client:
        client.post(
            "/api/v1/documents/import-text",
            json={"name": "技能资料", "text": "技能：Python"},
        )
        bundle = client.get("/api/v1/runtime/reviews").json()["items"][0]

        stale = client.post(
            f"/api/v1/runtime/reviews/{bundle['id']}/resolve",
            json={
                "expected_version": bundle["version"] + 1,
                "resolution": "confirmed",
                "reason": "使用了过期页面",
            },
        )

        assert stale.status_code == 409
        assert "已变化" in stale.json()["detail"]
