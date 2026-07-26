from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from career_console.domain.jobs import (
    CandidateEvidence,
    EvidenceDecision,
    JobRequirement,
    RequirementCategory,
    RequirementLevel,
    evaluate_match,
)
from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


def _confirmed_fact(client: TestClient, category: str, field_key: str, value: str) -> dict:
    created = client.post(
        "/api/v1/facts",
        json={
            "category": category,
            "field_key": field_key,
            "value": value,
            "source_note": "Part 2 test evidence",
        },
    )
    assert created.status_code == 201, created.text
    fact = created.json()
    confirmed = client.post(
        f"/api/v1/facts/{fact['id']}/confirm",
        json={"expected_version": fact["version"], "reason": "verified"},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def test_hard_requirement_veto_cannot_be_diluted() -> None:
    requirements = [
        JobRequirement(
            "must", RequirementCategory.EDUCATION, RequirementLevel.MUST, "硕士", "硕士", 1
        ),
        JobRequirement(
            "nice", RequirementCategory.SKILL, RequirementLevel.PREFERRED, "Python", "Python", 10
        ),
    ]
    evidence = [CandidateEvidence("nice", EvidenceDecision.MATCHED, ("fact-1",), "confirmed")]
    result = evaluate_match(requirements, evidence)
    assert result.score > 50
    assert result.hard_gate_passed is False
    assert result.recommendation == "blocked"


def test_job_import_dedup_versioning_and_confirmed_fact_evidence(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    original = """职位：Python 后端工程师
公司：示例科技
地点：上海
工作方式：混合办公
截止时间：2026-08-31
任职要求
- 必须熟练 Python 和 SQL
- 本科及以上学历
- 熟悉 Docker 优先
"""
    with TestClient(create_app(settings)) as client:
        skill = _confirmed_fact(client, "skill", "technical_skills", "Python、SQL、Docker")
        education = _confirmed_fact(client, "education", "degree", "计算机科学本科学历")
        first = client.post(
            "/api/v1/job-posts/import-text", json={"name": "官网 JD", "text": original}
        )
        assert first.status_code == 201, first.text
        job = first.json()
        assert job["created"] is True
        assert job["version"] == 1
        assert job["company"] == "示例科技"
        assert job["deadline_at"] == "2026-08-31T15:59:59Z"
        assert len(job["requirements"]) == 3
        assert job["latest_analysis"]["hard_gate_passed"] is True
        evidence_fact_ids = {
            fact["id"] for item in job["analyses"][0]["evidence"] for fact in item["facts"]
        }
        assert evidence_fact_ids == {skill["id"], education["id"]}

        duplicate = client.post(
            "/api/v1/job-posts/import-text", json={"name": "重复粘贴", "text": original}
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["version"] == 1

        changed = original + "- 了解 Kubernetes 优先\n"
        updated = client.post(
            "/api/v1/job-posts/import-text", json={"name": "更新 JD", "text": changed}
        )
        assert updated.status_code == 201, updated.text
        assert updated.json()["id"] == job["id"]
        assert updated.json()["version"] == 2
        assert len(updated.json()["versions"]) == 2

        listing = client.get("/api/v1/job-posts").json()
        assert listing["total"] == 1

        edited = client.post(
            f"/api/v1/facts/{skill['id']}/edit",
            json={
                "expected_version": skill["version"],
                "value": "仅保留 Python",
                "reason": "profile changed",
            },
        )
        assert edited.status_code == 200
        historical = client.get(f"/api/v1/job-posts/{job['id']}").json()["analyses"][-1]
        snapshots = [fact for item in historical["evidence"] for fact in item["facts"]]
        assert any(
            fact["value"] == "Python、SQL、Docker" and fact["version"] == skill["version"]
            for fact in snapshots
        )


def test_unmet_must_requirement_is_an_explicit_gap(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        _confirmed_fact(client, "skill", "technical_skills", "Python")
        response = client.post(
            "/api/v1/job-posts/import-text",
            json={
                "name": "高级岗位",
                "text": "职位：研究员\n公司：实验室\n任职要求\n- 必须具有博士学历\n- 熟悉 Python 优先",
            },
        )
        assert response.status_code == 201, response.text
        job = response.json()
        analysis = job["analyses"][0]
        assert analysis["hard_gate_passed"] is False
        assert analysis["must_gap_count"] == 1
        assert analysis["recommendation"] == "blocked"
        gaps = [item for item in analysis["evidence"] if item["decision"] == "gap"]
        assert len(gaps) == 1
        assert gaps[0]["facts"] == []
        assert "未在已确认" in gaps[0]["rationale"]

        refreshed = client.post(f"/api/v1/job-posts/{job['id']}/analyses")
        assert refreshed.status_code == 201
        assert refreshed.json()["reused"] is True
        assert len(client.get(f"/api/v1/job-posts/{job['id']}").json()["analyses"]) == 1


def test_same_job_analysis_input_is_idempotent_under_concurrency(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    app = create_app(settings)
    with TestClient(app) as client:
        fact = _confirmed_fact(client, "skill", "technical_skills", "Python、SQL")
        imported = client.post("/api/v1/job-posts/import-text", json={
            "name": "并发分析岗位",
            "text": "职位：后端工程师\n公司：示例科技\n任职要求\n- 熟练 Python 和 SQL",
        })
        job_id = imported.json()["id"]
        edited = client.post(f"/api/v1/facts/{fact['id']}/edit", json={
            "expected_version": fact["version"], "value": "Python",
            "reason": "触发同输入并发重算",
        })
        assert edited.status_code == 200
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda _: app.state.job_gateway.analyze_job(job_id), range(8)
            ))
        assert len({item["id"] for item in results}) == 1
        analyses = client.get(f"/api/v1/job-posts/{job_id}").json()["analyses"]
        assert len(analyses) == 2


def test_invalid_opportunity_does_not_create_partial_job(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/job-posts/import-text",
            json={
                "name": "官网 JD",
                "text": "职位：后端工程师\n公司：示例科技\n任职要求\n- 熟练 Python",
                "opportunity_id": "missing-opportunity",
            },
        )
        assert response.status_code == 404, response.text
        assert client.get("/api/v1/job-posts").json()["total"] == 0


def test_pasted_job_respects_document_size_limit(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career", max_document_bytes=1024)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/job-posts/import-text",
            json={"name": "oversized", "text": "职位：工程师\n公司：示例\n" + "任职要求很长" * 300},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "document_too_large"
