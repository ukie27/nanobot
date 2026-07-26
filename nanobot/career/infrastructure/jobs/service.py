"""Minimal persistent job queue used as a foundation by later modules."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from nanobot.career.infrastructure.database.models import BackgroundJobModel


@dataclass(frozen=True, slots=True)
class BackgroundJobView:
    id: str
    job_type: str
    status: str
    priority: int
    run_after: datetime
    attempt_count: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_error_code: str | None
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BackgroundJobService:
    """Queue operations with short, explicit transactions."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        priority: int = 0,
        run_after: datetime | None = None,
        max_attempts: int = 3,
    ) -> str:
        now = datetime.now(UTC)
        job = BackgroundJobModel(
            id=str(uuid4()),
            job_type=job_type,
            payload_json=json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")),
            idempotency_key=idempotency_key,
            status="pending",
            priority=priority,
            run_after=run_after or now,
            attempt_count=0,
            max_attempts=max_attempts,
            created_at=now,
        )
        with self._session_factory() as session:
            try:
                session.add(job)
                session.commit()
                return job.id
            except IntegrityError:
                session.rollback()
                if idempotency_key is None:
                    raise
                existing = session.scalar(
                    select(BackgroundJobModel).where(
                        BackgroundJobModel.idempotency_key == idempotency_key
                    )
                )
                if existing is None:
                    raise
                return existing.id

    def list_jobs(self, *, limit: int = 50) -> list[BackgroundJobView]:
        query: Select = (
            select(BackgroundJobModel)
            .order_by(BackgroundJobModel.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        with self._session_factory() as session:
            return [self._view(row) for row in session.scalars(query).all()]

    def recover_expired_leases(self, *, now: datetime | None = None) -> int:
        """Return abandoned running jobs to pending after their lease expires."""
        now = now or datetime.now(UTC)
        with self._session_factory() as session:
            result = session.execute(
                update(BackgroundJobModel)
                .where(
                    BackgroundJobModel.status == "running",
                    BackgroundJobModel.lease_expires_at.is_not(None),
                    BackgroundJobModel.lease_expires_at < now,
                )
                .values(
                    status="pending",
                    lease_owner=None,
                    lease_expires_at=None,
                    run_after=now,
                    last_error_code="lease_expired",
                    last_error_message_redacted="Worker lease expired; job recovered.",
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def claim_next(
        self, worker_id: str, *, lease_seconds: int = 60, now: datetime | None = None,
        job_types: set[str] | None = None,
    ) -> BackgroundJobView | None:
        now = now or datetime.now(UTC)
        with self._session_factory() as session:
            statement = select(BackgroundJobModel).where(
                    BackgroundJobModel.status == "pending",
                    BackgroundJobModel.run_after <= now,
                    BackgroundJobModel.attempt_count < BackgroundJobModel.max_attempts,
                )
            if job_types:
                statement = statement.where(BackgroundJobModel.job_type.in_(job_types))
            row = session.scalar(statement.order_by(
                BackgroundJobModel.priority.desc(), BackgroundJobModel.created_at
            ))
            if row is None:
                return None
            row.status = "running"
            row.attempt_count += 1
            row.started_at = row.started_at or now
            row.lease_owner = worker_id
            row.lease_expires_at = now + timedelta(seconds=max(10, lease_seconds))
            session.commit()
            return self._view(row)

    def complete(self, job_id: str, worker_id: str, *, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(BackgroundJobModel, job_id)
            self._expect_owned(row, worker_id)
            row.status = "succeeded"
            row.finished_at = now
            row.lease_owner = None
            row.lease_expires_at = None
            session.commit()

    def fail(
        self,
        job_id: str,
        worker_id: str,
        *,
        error_code: str,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(BackgroundJobModel, job_id)
            self._expect_owned(row, worker_id)
            exhausted = row.attempt_count >= row.max_attempts
            row.status = "failed" if exhausted else "pending"
            row.run_after = now + timedelta(seconds=min(300, 2**row.attempt_count))
            row.last_error_code = error_code[:120]
            row.last_error_message_redacted = "Background job handler failed."
            row.lease_owner = None
            row.lease_expires_at = None
            row.finished_at = now if exhausted else None
            session.commit()

    def cancel(self, job_id: str) -> BackgroundJobView:
        with self._session_factory() as session:
            row = session.get(BackgroundJobModel, job_id)
            if row is None:
                raise LookupError("Background job was not found.")
            if row.status in {"succeeded", "failed", "cancelled"}:
                return self._view(row)
            row.status = "cancelled"
            row.finished_at = datetime.now(UTC)
            row.lease_owner = None
            row.lease_expires_at = None
            session.commit()
            return self._view(row)

    def retry(self, job_id: str) -> BackgroundJobView:
        with self._session_factory() as session:
            row = session.get(BackgroundJobModel, job_id)
            if row is None:
                raise LookupError("Background job was not found.")
            if row.status not in {"failed", "cancelled"}:
                raise ValueError("Only failed or cancelled jobs can be retried.")
            row.status = "pending"
            row.run_after = datetime.now(UTC)
            row.attempt_count = 0
            row.started_at = None
            row.finished_at = None
            row.last_error_code = None
            row.last_error_message_redacted = None
            session.commit()
            return self._view(row)

    @staticmethod
    def _expect_owned(row: BackgroundJobModel | None, worker_id: str) -> None:
        if row is None:
            raise LookupError("Background job was not found.")
        if row.status != "running" or row.lease_owner != worker_id:
            raise RuntimeError("Background job lease is not owned by this worker.")

    @staticmethod
    def _view(row: BackgroundJobModel) -> BackgroundJobView:
        return BackgroundJobView(
            id=row.id,
            job_type=row.job_type,
            status=row.status,
            priority=row.priority,
            run_after=row.run_after,
            attempt_count=row.attempt_count,
            max_attempts=row.max_attempts,
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            last_error_code=row.last_error_code,
            payload=json.loads(row.payload_json),
        )
