"""Persistence for profile-change impact projections."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from nanobot.career.infrastructure.database.models import (
    JobPostModel,
    MaterialDraftModel,
    ProfileChangeEventModel,
    ProfileImpactRunModel,
)


class SqlAlchemyProfileImpactGateway:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def unscheduled_impacts(self) -> list[dict[str, str]]:
        with self._session_factory() as session:
            events = session.scalars(
                select(ProfileChangeEventModel).order_by(ProfileChangeEventModel.occurred_at)
            ).all()
            existing = {
                (row.change_event_id, row.scope)
                for row in session.scalars(select(ProfileImpactRunModel)).all()
            }
            return [
                {
                    "change_event_id": event.id,
                    "scope": scope,
                    "input_revision": f"{event.entity_type}:{event.entity_id}:{event.entity_revision}",
                }
                for event in events
                for scope in json.loads(event.impact_scopes_json)
                if (event.id, scope) not in existing
            ]

    def ensure_impact_run(self, *, change_event_id: str, scope: str,
                          input_revision: str, background_job_id: str) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            try:
                session.add(ProfileImpactRunModel(
                    id=str(uuid4()), change_event_id=change_event_id, scope=scope,
                    status="queued", background_job_id=background_job_id,
                    input_revision=input_revision, affected_count=0, error_code=None,
                    created_at=now, started_at=None, finished_at=None,
                ))
                session.commit()
            except IntegrityError:
                session.rollback()

    def start_impact(self, event_id: str, scope: str) -> None:
        with self._session_factory() as session:
            row = self._run(session, event_id, scope)
            row.status = "running"
            row.started_at = row.started_at or datetime.now(UTC)
            row.error_code = None
            session.commit()

    def complete_impact(self, event_id: str, scope: str, *, affected_count: int) -> None:
        with self._session_factory() as session:
            row = self._run(session, event_id, scope)
            row.status = "succeeded"
            row.affected_count = affected_count
            row.finished_at = datetime.now(UTC)
            row.error_code = None
            session.commit()

    def fail_impact(self, event_id: str, scope: str, *, error_code: str) -> None:
        with self._session_factory() as session:
            row = self._run(session, event_id, scope)
            row.status = "failed"
            row.error_code = error_code[:120]
            row.finished_at = datetime.now(UTC)
            session.commit()

    def active_job_ids(self) -> list[str]:
        with self._session_factory() as session:
            return list(session.scalars(
                select(JobPostModel.id).where(JobPostModel.status == "active")
            ).all())

    def invalidate_material_strategy(self, event_id: str) -> int:
        now = datetime.now(UTC)
        reason = f"基础档案变化（事件 {event_id}）后材料策略需要复核。"
        with self._session_factory() as session:
            rows = session.scalars(select(MaterialDraftModel).where(
                MaterialDraftModel.strategy_stale == 0
            )).all()
            for row in rows:
                row.strategy_stale = 1
                row.strategy_stale_reason = reason
                row.strategy_stale_at = now
            session.commit()
            return len(rows)

    @staticmethod
    def _run(session: Session, event_id: str, scope: str) -> ProfileImpactRunModel:
        row = session.scalar(select(ProfileImpactRunModel).where(
            ProfileImpactRunModel.change_event_id == event_id,
            ProfileImpactRunModel.scope == scope,
        ))
        if row is None:
            raise LookupError("Profile impact run was not found.")
        return row
