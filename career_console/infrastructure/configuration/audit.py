"""SQLAlchemy adapter for non-secret configuration history."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from career_console.infrastructure.database.models import (
    ConfigurationChangeModel,
    ConfigurationSnapshotModel,
)


class ConfigurationAuditStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def has_revision(self, revision: int) -> bool:
        with self._session_factory() as session:
            return session.scalar(select(ConfigurationSnapshotModel.id).where(
                ConfigurationSnapshotModel.revision == revision
            )) is not None

    def record(
        self,
        *,
        revision: int,
        previous_revision: int,
        schema_version: str,
        configuration: dict[str, Any],
        changed_paths: list[str],
        activation_effect: str,
        reason: str,
        created_at: datetime,
    ) -> None:
        encoded = json.dumps(
            configuration, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        snapshot_id = str(uuid4())
        with self._session_factory() as session:
            session.add(ConfigurationSnapshotModel(
                id=snapshot_id,
                revision=revision,
                schema_version=schema_version,
                configuration_json=encoded,
                content_hash=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                created_at=created_at,
            ))
            session.flush()
            session.add(ConfigurationChangeModel(
                id=str(uuid4()),
                snapshot_id=snapshot_id,
                previous_revision=previous_revision,
                new_revision=revision,
                changed_paths_json=json.dumps(changed_paths, ensure_ascii=False),
                activation_effect=activation_effect,
                reason=reason,
                created_at=created_at,
            ))
            session.commit()

    def list_changes(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ConfigurationChangeModel)
                .order_by(ConfigurationChangeModel.created_at.desc())
                .limit(max(1, min(limit, 200)))
            ).all()
            return [
                {
                    "id": row.id,
                    "previous_revision": row.previous_revision,
                    "new_revision": row.new_revision,
                    "changed_paths": json.loads(row.changed_paths_json),
                    "activation_effect": row.activation_effect,
                    "reason": row.reason,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
