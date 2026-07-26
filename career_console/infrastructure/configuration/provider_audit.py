"""Persistence for sanitized Provider connection-test results."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from career_console.infrastructure.database.models import ProviderConnectionTestRunModel


class ProviderConnectionTestAudit:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def record(
        self,
        *,
        provider_id: str,
        provider_type: str,
        model: str,
        status: str,
        error_code: str | None,
        duration_ms: int,
        created_at: datetime,
    ) -> dict[str, Any]:
        row = ProviderConnectionTestRunModel(
            id=str(uuid4()), provider_id=provider_id, provider_type=provider_type,
            model=model, status=status, error_code=error_code,
            duration_ms=duration_ms, created_at=created_at,
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            return self._view(row)

    def list(self, provider_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        statement = select(ProviderConnectionTestRunModel)
        if provider_id:
            statement = statement.where(
                ProviderConnectionTestRunModel.provider_id == provider_id
            )
        statement = statement.order_by(
            ProviderConnectionTestRunModel.created_at.desc()
        ).limit(max(1, min(limit, 200)))
        with self._session_factory() as session:
            return [self._view(row) for row in session.scalars(statement).all()]

    @staticmethod
    def _view(row: ProviderConnectionTestRunModel) -> dict[str, Any]:
        return {
            "id": row.id, "provider_id": row.provider_id,
            "provider_type": row.provider_type, "model": row.model,
            "status": row.status, "error_code": row.error_code,
            "duration_ms": row.duration_ms, "created_at": row.created_at,
        }
