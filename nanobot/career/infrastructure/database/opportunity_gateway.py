"""SQLAlchemy persistence for recruitment opportunities and their versions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from nanobot.career.domain.opportunities import (
    OpportunityTriageStatus,
    normalize_opportunity_text,
)
from nanobot.career.infrastructure.database.models import (
    CompanyModel,
    JobPostModel,
    OpportunityJobLinkModel,
    OpportunitySourceModel,
    OpportunityVersionModel,
    RecruitmentOpportunityModel,
)


class SqlAlchemyOpportunityGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def ingest(
        self,
        *,
        connector_id: str,
        source_event_id: str,
        external_id: str,
        source_url: str,
        content_hash: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool, bool]:
        now = datetime.now(UTC)
        collected_at = self._datetime(payload.get("collected_at")) or now
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        with self._session_factory() as session:
            source = session.scalar(
                select(OpportunitySourceModel).where(
                    OpportunitySourceModel.connector_id == connector_id,
                    OpportunitySourceModel.external_id == external_id,
                )
            )
            opportunity = (
                session.get(RecruitmentOpportunityModel, source.opportunity_id)
                if source is not None
                else None
            )
            created = opportunity is None
            updated = False
            if opportunity is None:
                opportunity = RecruitmentOpportunityModel(
                    id=str(uuid4()),
                    company=self._required(payload, "company", 300),
                    batch=self._required(payload, "batch", 300),
                    triage_status=OpportunityTriageStatus.NEW.value,
                    version=1,
                    first_collected_at=collected_at,
                    last_collected_at=collected_at,
                    created_at=now,
                    updated_at=now,
                    **self._mutable_values(payload),
                )
                session.add(opportunity)
                session.flush()
                source = OpportunitySourceModel(
                    id=str(uuid4()),
                    opportunity_id=opportunity.id,
                    connector_id=connector_id,
                    external_id=external_id,
                    source_url=source_url,
                    content_hash=content_hash,
                    first_seen_at=collected_at,
                    last_seen_at=collected_at,
                )
                session.add(source)
            elif source.content_hash != content_hash:
                opportunity.company = self._required(payload, "company", 300)
                opportunity.batch = self._required(payload, "batch", 300)
                for key, value in self._mutable_values(payload).items():
                    setattr(opportunity, key, value)
                opportunity.version += 1
                opportunity.updated_at = now
                source.content_hash = content_hash
                source.source_url = source_url
                updated = True
            opportunity.last_collected_at = max(
                self._utc(opportunity.last_collected_at) or collected_at,
                collected_at,
            )
            source.last_seen_at = max(
                self._utc(source.last_seen_at) or collected_at,
                collected_at,
            )
            if created or updated:
                session.add(
                    OpportunityVersionModel(
                        id=str(uuid4()),
                        opportunity_id=opportunity.id,
                        source_event_id=source_event_id,
                        version_number=opportunity.version,
                        content_hash=content_hash,
                        payload_json=canonical,
                        collected_at=collected_at,
                        created_at=now,
                    )
                )
            session.commit()
            return self._view(session, opportunity), created, updated

    def list(
        self,
        *,
        triage_status: OpportunityTriageStatus | None = None,
        collected_since: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            statement = select(RecruitmentOpportunityModel)
            if triage_status is not None:
                statement = statement.where(
                    RecruitmentOpportunityModel.triage_status == triage_status.value
                )
            if collected_since is not None:
                statement = statement.where(
                    RecruitmentOpportunityModel.last_collected_at >= collected_since
                )
            rows = session.scalars(
                statement.order_by(
                    RecruitmentOpportunityModel.last_collected_at.desc(),
                    RecruitmentOpportunityModel.created_at.desc(),
                ).limit(max(1, min(limit, 1000)))
            ).all()
            return [self._view(session, row) for row in rows]

    def get(self, opportunity_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(RecruitmentOpportunityModel, opportunity_id)
            if row is None:
                raise LookupError("招聘机会不存在。")
            return self._view(session, row, detail=True)

    def triage(
        self,
        opportunity_id: str,
        *,
        triage_status: OpportunityTriageStatus,
        expected_version: int,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(RecruitmentOpportunityModel, opportunity_id)
            if row is None:
                raise LookupError("招聘机会不存在。")
            if row.version != expected_version:
                raise RuntimeError("招聘机会已被其他操作更新，请刷新后重试。")
            if row.triage_status != triage_status.value:
                row.triage_status = triage_status.value
                row.version += 1
                row.updated_at = datetime.now(UTC)
                session.commit()
            return self._view(session, row)

    def _view(
        self, session: Session, row: RecruitmentOpportunityModel, *, detail: bool = False
    ) -> dict[str, Any]:
        sources = session.scalars(
            select(OpportunitySourceModel).where(
                OpportunitySourceModel.opportunity_id == row.id
            )
        ).all()
        job_links = session.scalars(
            select(OpportunityJobLinkModel).where(
                OpportunityJobLinkModel.opportunity_id == row.id
            )
        ).all()
        linked_jobs = []
        for link in job_links:
            post = session.get(JobPostModel, link.job_post_id)
            if post is None:
                continue
            company = session.get(CompanyModel, post.company_id)
            linked_jobs.append(
                {
                    "id": post.id,
                    "company": company.canonical_name if company else "",
                    "title": post.title,
                    "location": post.location,
                    "version": post.version,
                    "created_at": self._utc(post.created_at),
                }
            )
        result = {
            "id": row.id,
            "company": row.company,
            "batch": row.batch,
            "cities": row.cities,
            "careers": row.careers,
            "industries": row.industries,
            "evaluation": row.evaluation,
            "application_starts_at": self._utc(row.application_starts_at),
            "application_ends_at": self._utc(row.application_ends_at),
            "announcement_url": row.announcement_url,
            "application_url": row.application_url,
            "triage_status": row.triage_status,
            "version": row.version,
            "first_collected_at": self._utc(row.first_collected_at),
            "last_collected_at": self._utc(row.last_collected_at),
            "created_at": self._utc(row.created_at),
            "updated_at": self._utc(row.updated_at),
            "sources": [
                {
                    "id": item.id,
                    "external_id": item.external_id,
                    "source_url": item.source_url,
                    "first_seen_at": self._utc(item.first_seen_at),
                    "last_seen_at": self._utc(item.last_seen_at),
                }
                for item in sources
            ],
            "linked_jobs": linked_jobs,
        }
        if detail:
            versions = session.scalars(
                select(OpportunityVersionModel)
                .where(OpportunityVersionModel.opportunity_id == row.id)
                .order_by(OpportunityVersionModel.version_number.desc())
            ).all()
            result["versions"] = [
                {
                    "id": item.id,
                    "version_number": item.version_number,
                    "content_hash": item.content_hash,
                    "collected_at": self._utc(item.collected_at),
                    "created_at": self._utc(item.created_at),
                }
                for item in versions
            ]
        return result

    @classmethod
    def _mutable_values(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "cities": normalize_opportunity_text(payload.get("cities"), max_length=2_000),
            "careers": normalize_opportunity_text(payload.get("careers"), max_length=2_000),
            "industries": normalize_opportunity_text(
                payload.get("industries"), max_length=2_000
            ),
            "evaluation": normalize_opportunity_text(
                payload.get("evaluation"), max_length=10_000
            ),
            "application_starts_at": cls._datetime(payload.get("application_starts_at")),
            "application_ends_at": cls._datetime(payload.get("application_ends_at")),
            "announcement_url": cls._url(
                payload.get("announcement_url"), key="announcement_url", required=False
            ),
            "application_url": cls._url(
                payload.get("application_url"), key="application_url", required=True
            ),
        }

    @staticmethod
    def _required(payload: dict[str, Any], key: str, max_length: int) -> str:
        value = normalize_opportunity_text(payload.get(key), max_length=max_length)
        if not value:
            raise ValueError(f"招聘机会缺少字段 {key}。")
        return value

    @staticmethod
    def _url(value: object, *, key: str, required: bool) -> str | None:
        text = str(value or "").strip()
        if not text:
            if required:
                raise ValueError(f"招聘机会缺少字段 {key}。")
            return None
        if len(text) > 4_000:
            raise ValueError(f"招聘机会字段 {key} 过长。")
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"招聘机会字段 {key} 不是有效的 HTTP(S) URL。")
        return text

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            result = value
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return result.astimezone(UTC)

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
