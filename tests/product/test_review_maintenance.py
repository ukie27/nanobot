from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select

from career_console.application.ports.fact_extractor import ExtractedFact
from career_console.application.services.review_maintenance import ReviewMaintenanceService
from career_console.domain.profile.entities import FactCategory
from career_console.infrastructure.database import Database
from career_console.infrastructure.database.migrations import upgrade_to_head
from career_console.infrastructure.database.models import (
    FactRevisionModel,
    ReviewBundleItemModel,
    ReviewBundleModel,
    ReviewTaskModel,
)
from career_console.infrastructure.database.profile_gateway import SqlAlchemyProfileGateway
from career_console.infrastructure.database.runtime_gateway import SqlAlchemyRuntimeGateway
from career_console.infrastructure.settings import CareerSettings


def test_legacy_profile_review_cleanup_rejects_only_v1_local_extraction(
    tmp_path: Path,
) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    upgrade_to_head(settings)
    database = Database(settings)
    profile_gateway = SqlAlchemyProfileGateway(database.session_factory)
    runtime_gateway = SqlAlchemyRuntimeGateway(database.session_factory)
    profile_gateway.save_import(
        file_name="legacy.txt",
        media_type="text/plain",
        sha256="a" * 64,
        size_bytes=6,
        blob_relative_path="blobs/legacy.txt",
        text="Python",
        parser_name="text_v1",
        extractor_name="local_resume_extractor",
        extractor_schema_version="candidate_fact.v1",
        facts=[
            ExtractedFact(
                category=FactCategory.SKILL,
                field_key="skill",
                value="Python",
                confidence=0.9,
                evidence_text="Python",
            )
        ],
    )
    with database.session_factory() as session:
        session.execute(delete(ReviewBundleItemModel))
        session.execute(delete(ReviewBundleModel))
        session.commit()
    service = ReviewMaintenanceService(
        runtime_gateway=runtime_gateway,
        profile_gateway=profile_gateway,
    )

    matches = service.legacy_profile_fact_reviews()
    assert len(matches) == 1

    result = service.reject_legacy_profile_fact_reviews(reason="legacy cleanup")

    assert result["rejected"] == 1
    assert profile_gateway.list_facts(status="proposed") == []
    rejected = profile_gateway.list_facts(status="rejected")
    assert len(rejected) == 1
    assert runtime_gateway.list_reviews(status="open") == []
    with database.session_factory() as session:
        task = session.scalar(select(ReviewTaskModel))
        revision = session.scalar(select(FactRevisionModel))
        assert task is not None
        assert task.resolution == "rejected"
        assert task.resolved_by == "maintenance"
        assert revision is not None
        assert revision.changed_by == "maintenance"
        assert revision.reason == "legacy cleanup"
    database.close()


def test_legacy_profile_review_cleanup_ignores_current_schema(tmp_path: Path) -> None:
    settings = CareerSettings(data_dir=tmp_path / "career")
    upgrade_to_head(settings)
    database = Database(settings)
    profile_gateway = SqlAlchemyProfileGateway(database.session_factory)
    profile_gateway.save_import(
        file_name="current.txt",
        media_type="text/plain",
        sha256="b" * 64,
        size_bytes=3,
        blob_relative_path="blobs/current.txt",
        text="SQL",
        parser_name="text_v1",
        extractor_name="agent_profile_fact_extractor",
        extractor_schema_version="candidate_profile_object.v2",
        facts=[
            ExtractedFact(
                category=FactCategory.SKILL,
                field_key="skill",
                value="SQL",
                confidence=0.9,
                evidence_text="SQL",
            )
        ],
    )
    service = ReviewMaintenanceService(
        runtime_gateway=SqlAlchemyRuntimeGateway(database.session_factory),
        profile_gateway=profile_gateway,
    )

    assert service.legacy_profile_fact_reviews() == []
    assert service.reject_legacy_profile_fact_reviews(reason="legacy cleanup")["rejected"] == 0
    assert len(profile_gateway.list_facts(status="proposed")) == 1
    database.close()
