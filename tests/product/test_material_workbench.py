from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfReader

from career_console.infrastructure.settings import CareerSettings
from career_console.interfaces.http import create_app


def _fact(
    client: TestClient, category: str, field_key: str, value: str, *, confirm: bool = True
) -> dict:
    response = client.post(
        "/api/v1/facts",
        json={
            "category": category,
            "field_key": field_key,
            "value": value,
            "source_note": "material test",
        },
    )
    assert response.status_code == 201, response.text
    fact = response.json()
    if not confirm:
        return fact
    response = client.post(
        f"/api/v1/facts/{fact['id']}/confirm",
        json={"expected_version": fact["version"], "reason": "verified"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _job(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/job-posts/import-text",
        json={
            "name": "真实 JD",
            "text": "职位：Python 后端工程师\n公司：示例科技\n地点：上海\n任职要求\n- 必须熟练 Python 和 SQL\n- 本科及以上学历\n- 熟悉 Docker 优先",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _edit_payload(material: dict, transform=None) -> dict:
    blocks = []
    for index, block in enumerate(material["current_version"]["blocks"]):
        text = transform(index, block) if transform else block["text"]
        blocks.append({"id": block["id"], "text": text})
    return {"expected_version": material["version"], "blocks": blocks}


def test_profile_change_recomputes_job_fit_and_invalidates_material_strategy(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(
        data_dir=tmp_path / "career", mail_intelligence_mode="disabled",
        profile_insight_mode="disabled",
    )
    with TestClient(create_app(settings)) as client:
        skill = _fact(client, "skill", "technical_skills", "Python、SQL、Docker")
        _fact(client, "education", "degree", "计算机科学本科学历")
        job = _job(client)
        material_response = client.post(
            "/api/v1/materials",
            json={"job_post_id": job["id"], "material_type": "resume", "name": "基础简历"},
        )
        assert material_response.status_code == 201, material_response.text
        material = material_response.json()
        assert material["strategy_stale"] is False

        edited_fact = client.post(
            f"/api/v1/facts/{skill['id']}/edit",
            json={
                "expected_version": skill["version"], "value": "Python、SQL",
                "reason": "档案证据发生变化",
            },
        )
        assert edited_fact.status_code == 200, edited_fact.text
        impact = client.post("/api/v1/profile-memory/impacts/run")
        assert impact.status_code == 200, impact.text

        refreshed_job = client.get(f"/api/v1/job-posts/{job['id']}").json()
        assert len(refreshed_job["analyses"]) == 2
        stale = client.get(f"/api/v1/materials/{material['id']}").json()
        assert stale["strategy_stale"] is True
        assert "基础档案变化" in stale["strategy_stale_reason"]

        saved = client.post(
            f"/api/v1/materials/{material['id']}/versions", json=_edit_payload(stale)
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["strategy_stale"] is False


def test_resume_with_one_fact_cannot_be_finalized(tmp_path: Path) -> None:
    settings = CareerSettings(
        data_dir=tmp_path / "career",
        mail_intelligence_mode="disabled",
        profile_insight_mode="disabled",
        material_agent_mode="disabled",
    )
    with TestClient(create_app(settings)) as client:
        _fact(client, "skill", "technical_skills", "Python、SQL、FastAPI")
        job = _job(client)

        generated = client.post(
            "/api/v1/materials",
            json={"job_post_id": job["id"], "material_type": "resume", "name": "不完整简历"},
        )

        assert generated.status_code == 201, generated.text
        material = generated.json()
        assert any(
            finding["code"] == "resume_incomplete"
            for finding in material["review"]["findings"]
        )

        finalized = client.post(
            f"/api/v1/materials/{material['id']}/finalize",
            json={"expected_version": material["version"]},
        )
        assert finalized.status_code == 422
        assert finalized.json()["code"] == "material_review_blocked"


def test_drafter_reviewer_version_chain_and_verified_pdf(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        skill = _fact(client, "skill", "technical_skills", "熟练使用 Python、SQL 和 Docker")
        _fact(client, "education", "degree", "计算机科学本科学历")
        _fact(client, "project", "achievement", "负责求职系统后端开发，将接口响应时间降低 30%")
        proposed = _fact(client, "award", "unverified_award", "获得未核实的国际大奖", confirm=False)
        job = _job(client)

        generated = client.post(
            "/api/v1/materials",
            json={"job_post_id": job["id"], "material_type": "resume", "name": "后端方向基础简历"},
        )
        assert generated.status_code == 201, generated.text
        material = generated.json()
        resume_id = material["resume_id"]
        assert material["status"] == "reviewed"
        assert material["review"]["error_count"] == 0
        snapshots = [
            snapshot
            for block in material["current_version"]["blocks"]
            for snapshot in block["fact_snapshots"]
        ]
        assert skill["id"] in {item["fact_id"] for item in snapshots}
        assert proposed["id"] not in {item["fact_id"] for item in snapshots}

        series = client.get("/api/v1/resumes")
        assert series.status_code == 200
        resume_series = series.json()["items"][0]
        assert resume_series["id"] == resume_id
        assert resume_series["name"] == "后端方向基础简历"
        assert resume_series["series_type"] == "base"
        assert resume_series["parent_resume_id"] is None
        assert resume_series["material_count"] == 1
        assert resume_series["latest_version"]["version_scope"] == "job_tailored"
        reused = client.post(
            "/api/v1/materials",
            json={
                "job_post_id": job["id"],
                "material_type": "cover_letter",
                "name": "",
                "resume_id": resume_id,
            },
        )
        assert reused.status_code == 201, reused.text
        assert reused.json()["resume_id"] == resume_id
        updated_series = client.get("/api/v1/resumes").json()["items"]
        assert updated_series[0]["material_count"] == 2

        edited = client.post(
            f"/api/v1/materials/{material['id']}/versions",
            json=_edit_payload(
                material,
                lambda index, block: f"重点经历：{block['text']}" if index == 0 else block["text"],
            ),
        )
        assert edited.status_code == 201, edited.text
        material = edited.json()
        assert material["current_version"]["version_number"] == 2
        assert material["current_version"]["parent_version_id"] is not None
        assert material["status"] == "reviewed"

        invented = client.post(
            f"/api/v1/materials/{material['id']}/versions",
            json=_edit_payload(
                material,
                lambda index, block: (
                    f"曾担任首席架构师，{block['text']}" if index == 0 else block["text"]
                ),
            ),
        )
        assert invented.status_code == 201
        invented_material = invented.json()
        assert invented_material["status"] == "draft"
        assert any(
            item["code"] == "unsupported_claim" for item in invented_material["review"]["findings"]
        )

        repaired_after_invention = client.post(
            f"/api/v1/materials/{material['id']}/versions",
            json=_edit_payload(
                invented_material,
                lambda _index, block: block["fact_snapshots"][0]["value"],
            ),
        )
        assert repaired_after_invention.status_code == 201
        material = repaired_after_invention.json()

        unsupported = client.post(
            f"/api/v1/materials/{material['id']}/versions",
            json=_edit_payload(
                material,
                lambda index, block: (
                    f"{block['text']}，业绩提升 99%" if index == 0 else block["text"]
                ),
            ),
        )
        assert unsupported.status_code == 201
        material = unsupported.json()
        assert material["status"] == "draft"
        assert any(item["code"] == "unsupported_number" for item in material["review"]["findings"])
        blocked = client.post(
            f"/api/v1/materials/{material['id']}/finalize",
            json={"expected_version": material["version"]},
        )
        assert blocked.status_code == 422
        assert blocked.json()["code"] == "material_review_blocked"

        repaired = client.post(
            f"/api/v1/materials/{material['id']}/versions",
            json=_edit_payload(material, lambda _index, block: block["fact_snapshots"][0]["value"]),
        )
        assert repaired.status_code == 201
        material = repaired.json()
        finalized = client.post(
            f"/api/v1/materials/{material['id']}/finalize",
            json={"expected_version": material["version"]},
        )
        assert finalized.status_code == 200, finalized.text
        material = finalized.json()
        assert material["status"] == "final"
        assert material["export"]["page_count"] >= 1
        assert material["export"]["text_layer_ok"] is True
        assert material["export"]["render_ok"] is True
        assert len(material["export"]["sha256"]) == 64

        pdf_response = client.get(material["export"]["download_url"])
        preview_response = client.get(material["export"]["preview_url"])
        assert pdf_response.status_code == 200
        assert pdf_response.content.startswith(b"%PDF-")
        assert preview_response.content.startswith(b"\x89PNG\r\n\x1a\n")
        pdf = PdfReader(BytesIO(pdf_response.content))
        extracted = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert "Python" in extracted and "30%" in extracted

        immutable = client.post(
            f"/api/v1/materials/{material['id']}/versions", json=_edit_payload(material)
        )
        assert immutable.status_code == 422
        assert immutable.json()["code"] == "final_material_immutable"

        changed_fact = client.post(
            f"/api/v1/facts/{skill['id']}/edit",
            json={
                "expected_version": skill["version"],
                "value": "仅使用 Python",
                "reason": "later profile update",
            },
        )
        assert changed_fact.status_code == 200
        persisted = client.get(f"/api/v1/materials/{material['id']}").json()
        old_values = [
            snapshot["value"]
            for block in persisted["current_version"]["blocks"]
            for snapshot in block["fact_snapshots"]
        ]
        assert "熟练使用 Python、SQL 和 Docker" in old_values


def test_base_direction_job_tailored_lineage_and_diff(tmp_path: Path) -> None:
    settings = CareerSettings(
        data_dir=tmp_path / "career", mail_intelligence_mode="disabled",
        profile_insight_mode="disabled", material_agent_mode="disabled",
    )
    with TestClient(create_app(settings)) as client:
        _fact(client, "skill", "technical_skills", "Python、SQL、FastAPI")
        _fact(client, "project", "achievement", "负责后端服务开发并完成稳定交付")
        job = _job(client)
        first = client.post("/api/v1/materials", json={
            "job_post_id": job["id"], "material_type": "resume", "name": "临时材料系列",
        }).json()

        base_response = client.post("/api/v1/resumes/from-material", json={
            "material_id": first["id"], "series_type": "base", "name": "通用基础简历",
        })
        assert base_response.status_code == 201, base_response.text
        base = base_response.json()
        assert base["series_type"] == "base"
        assert base["latest_version"]["version_scope"] == "base"

        direction_response = client.post("/api/v1/resumes/from-material", json={
            "material_id": first["id"], "series_type": "direction", "name": "后端方向简历",
            "parent_resume_id": base["id"], "direction_label": "后端工程",
        })
        assert direction_response.status_code == 201, direction_response.text
        direction = direction_response.json()
        assert direction["parent_resume_id"] == base["id"]
        assert direction["latest_version"]["source_resume_version_id"] == base["latest_version"]["id"]

        tailored_response = client.post("/api/v1/materials", json={
            "job_post_id": job["id"], "material_type": "resume", "name": "",
            "resume_id": direction["id"],
        })
        assert tailored_response.status_code == 201, tailored_response.text
        tailored = tailored_response.json()
        assert tailored["resume_series_type"] == "direction"
        assert tailored["source_resume_version_id"] == direction["latest_version"]["id"]
        edited_response = client.post(
            f"/api/v1/materials/{tailored['id']}/versions",
            json=_edit_payload(
                tailored,
                lambda index, block: f"重点经历：{block['text']}" if index == 0 else block["text"],
            ),
        )
        assert edited_response.status_code == 201, edited_response.text
        edited = edited_response.json()
        diff = client.get(
            f"/api/v1/resumes/versions/{direction['latest_version']['id']}/diff/"
            f"{edited['current_version']['id']}"
        )
        assert diff.status_code == 200, diff.text
        result = diff.json()
        assert result["summary"]["changed"] >= 1
        assert any(item["change"] == "changed" for item in result["blocks"])
        assert result["fact_changes"] == {"added_fact_ids": [], "removed_fact_ids": []}
def test_cover_letter_and_introduction_use_fact_bound_blocks(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    with TestClient(create_app(settings)) as client:
        _fact(client, "skill", "technical_skills", "熟练使用 Python 和 SQL")
        job = _job(client)
        for material_type in ("cover_letter", "introduction"):
            response = client.post(
                "/api/v1/materials",
                json={"job_post_id": job["id"], "material_type": material_type, "name": "基础材料"},
            )
            assert response.status_code == 201, response.text
            material = response.json()
            assert material["material_type"] == material_type
            assert material["current_version"]["blocks"]
            assert all(block["fact_snapshots"] for block in material["current_version"]["blocks"])
