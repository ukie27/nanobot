"""SQLAlchemy persistence for connector configuration, runs, and source events."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from career_console.domain.connectors import next_scan_time
from career_console.infrastructure.database.models import (
    ConnectorConfigModel,
    SourceEventModel,
    SyncCursorModel,
    SyncRunModel,
)

BOSS_CONNECTOR_ID = "00000000-0000-0000-0000-000000000006"
NOWCODER_CONNECTOR_ID = "00000000-0000-0000-0000-000000000008"


class SqlAlchemyConnectorGateway:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def get_or_create_boss(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.scalar(
                select(ConnectorConfigModel).where(
                    ConnectorConfigModel.connector_type == "opencli_boss"
                )
            )
            if row is None:
                row = ConnectorConfigModel(
                    id=BOSS_CONNECTOR_ID,
                    connector_type="opencli_boss",
                    display_name="BOSS 直聘（OpenCLI）",
                    enabled=0,
                    profile_alias="default",
                    search_query="",
                    city="全国",
                    result_limit=15,
                    schedule_enabled=0,
                    schedule_times_json='["09:00","18:00"]',
                    timezone="Asia/Shanghai",
                    next_scan_at=None,
                    scan_lease_run_id=None,
                    scan_lease_expires_at=None,
                    health_status="unknown",
                    last_error_code=None,
                    last_success_at=None,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                try:
                    session.add(row)
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    row = session.scalar(
                        select(ConnectorConfigModel).where(
                            ConnectorConfigModel.connector_type == "opencli_boss"
                        )
                    )
                    if row is None:
                        raise
            return self._config_view(row)

    def get_or_create_nowcoder(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.scalar(
                select(ConnectorConfigModel).where(
                    ConnectorConfigModel.connector_type == "opencli_nowcoder"
                )
            )
            if row is None:
                row = ConnectorConfigModel(
                    id=NOWCODER_CONNECTOR_ID,
                    connector_type="opencli_nowcoder",
                    display_name="牛客校招日程（OpenCLI）",
                    enabled=0,
                    profile_alias="default",
                    search_query="",
                    city="全国",
                    result_limit=500,
                    schedule_enabled=0,
                    schedule_times_json='["09:00"]',
                    timezone="Asia/Shanghai",
                    next_scan_at=None,
                    scan_lease_run_id=None,
                    scan_lease_expires_at=None,
                    health_status="unknown",
                    last_error_code=None,
                    last_success_at=None,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                try:
                    session.add(row)
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    row = session.scalar(
                        select(ConnectorConfigModel).where(
                            ConnectorConfigModel.connector_type == "opencli_nowcoder"
                        )
                    )
                    if row is None:
                        raise
            return self._config_view(row)

    def update_boss(self, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        self.get_or_create_boss()
        with self._session_factory() as session:
            row = session.get(ConnectorConfigModel, BOSS_CONNECTOR_ID)
            for key in (
                "enabled",
                "profile_alias",
                "search_query",
                "city",
                "result_limit",
                "schedule_enabled",
                "timezone",
                "health_status",
                "last_error_code",
                "last_success_at",
            ):
                if key in values:
                    value = values[key]
                    if key in {"enabled", "schedule_enabled"}:
                        value = int(bool(value))
                    setattr(row, key, value)
            if "schedule_times" in values:
                row.schedule_times_json = json.dumps(
                    values["schedule_times"], separators=(",", ":")
                )
            if row.enabled and row.schedule_enabled:
                row.next_scan_at = next_scan_time(
                    now, json.loads(row.schedule_times_json), row.timezone
                )
            else:
                row.next_scan_at = None
            row.version += 1
            row.updated_at = now
            session.commit()
            return self._config_view(row)

    def update_nowcoder(self, **values: Any) -> dict[str, Any]:
        return self._update_config(NOWCODER_CONNECTOR_ID, self.get_or_create_nowcoder, **values)

    def _update_config(self, connector_id: str, ensure: Any, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        ensure()
        with self._session_factory() as session:
            row = session.get(ConnectorConfigModel, connector_id)
            for key in (
                "enabled",
                "search_query",
                "city",
                "result_limit",
                "schedule_enabled",
                "health_status",
                "last_error_code",
                "last_success_at",
            ):
                if key in values:
                    value = values[key]
                    if key in {"enabled", "schedule_enabled"}:
                        value = int(bool(value))
                    setattr(row, key, value)
            if "schedule_times" in values:
                row.schedule_times_json = json.dumps(
                    values["schedule_times"], separators=(",", ":")
                )
            row.timezone = "Asia/Shanghai"
            if row.enabled and row.schedule_enabled:
                row.next_scan_at = next_scan_time(
                    now, json.loads(row.schedule_times_json), row.timezone
                )
            else:
                row.next_scan_at = None
            row.version += 1
            row.updated_at = now
            session.commit()
            return self._config_view(row)

    def list_runs(
        self, *, limit: int = 20, connector_id: str | None = None
    ) -> list[dict[str, Any]]:
        connector_id = connector_id or BOSS_CONNECTOR_ID
        with self._session_factory() as session:
            rows = session.scalars(
                select(SyncRunModel)
                .where(SyncRunModel.connector_id == connector_id)
                .order_by(SyncRunModel.started_at.desc())
                .limit(max(1, min(limit, 100)))
            ).all()
            return [self._run_view(row) for row in rows]

    def start_run(
        self, *, trigger_type: str, connector_id: str | None = None
    ) -> dict[str, Any]:
        connector_id = connector_id or BOSS_CONNECTOR_ID
        now = datetime.now(UTC)
        self._ensure_connector(connector_id)
        with self._session_factory() as session:
            run_id = str(uuid4())
            acquired = session.execute(
                update(ConnectorConfigModel)
                .where(
                    ConnectorConfigModel.id == connector_id,
                    or_(
                        ConnectorConfigModel.scan_lease_expires_at.is_(None),
                        ConnectorConfigModel.scan_lease_expires_at < now,
                    ),
                )
                .values(
                    scan_lease_run_id=run_id,
                    scan_lease_expires_at=now + timedelta(minutes=10),
                )
            )
            if not acquired.rowcount:
                session.rollback()
                raise RuntimeError("该 Browser Profile 已有扫描正在运行。")
            row = SyncRunModel(
                id=run_id,
                connector_id=connector_id,
                trigger_type=trigger_type,
                status="running",
                discovered_count=0,
                created_count=0,
                updated_count=0,
                duplicate_count=0,
                quarantined_count=0,
                error_code=None,
                started_at=now,
                finished_at=None,
            )
            session.add(row)
            session.commit()
            return self._run_view(row)

    def finish_run(self, run_id: str, **counts: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(SyncRunModel, run_id)
            if row is None:
                raise LookupError("同步运行不存在。")
            for key in (
                "discovered_count",
                "created_count",
                "updated_count",
                "duplicate_count",
                "quarantined_count",
            ):
                setattr(row, key, int(counts.get(key, 0)))
            row.status = "partial" if row.quarantined_count else "succeeded"
            row.finished_at = now
            config = session.get(ConnectorConfigModel, row.connector_id)
            config.health_status = "healthy"
            config.last_error_code = None
            config.last_success_at = now
            config.updated_at = now
            if config.scan_lease_run_id == run_id:
                config.scan_lease_run_id = None
                config.scan_lease_expires_at = None
            if config.enabled and config.schedule_enabled:
                config.next_scan_at = next_scan_time(
                    now, json.loads(config.schedule_times_json), config.timezone
                )
            cursor = session.scalar(
                select(SyncCursorModel).where(
                    SyncCursorModel.connector_id == config.id,
                    SyncCursorModel.cursor_key == "last_completed_at",
                )
            )
            if cursor is None:
                cursor = SyncCursorModel(
                    id=str(uuid4()),
                    connector_id=config.id,
                    cursor_key="last_completed_at",
                    cursor_value=now.isoformat(),
                    updated_at=now,
                )
                session.add(cursor)
            else:
                cursor.cursor_value = now.isoformat()
                cursor.updated_at = now
            session.commit()
            return self._run_view(row)

    def fail_run(self, run_id: str, *, error_code: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(SyncRunModel, run_id)
            if row is None:
                raise LookupError("同步运行不存在。")
            row.status = "failed"
            row.error_code = error_code[:120]
            row.finished_at = now
            config = session.get(ConnectorConfigModel, row.connector_id)
            config.health_status = (
                "requires_login" if error_code == "requires_login" else "unavailable"
            )
            config.last_error_code = error_code[:120]
            config.updated_at = now
            if config.scan_lease_run_id == run_id:
                config.scan_lease_run_id = None
                config.scan_lease_expires_at = None
            if config.enabled and config.schedule_enabled:
                config.next_scan_at = next_scan_time(
                    now, json.loads(config.schedule_times_json), config.timezone
                )
            session.commit()
            return self._run_view(row)

    def source_event(self, **values: Any) -> tuple[dict[str, Any], bool]:
        now = datetime.now(UTC)
        connector_id = values.pop("connector_id", BOSS_CONNECTOR_ID)
        row = SourceEventModel(
            id=str(uuid4()),
            connector_id=connector_id,
            sync_run_id=values["sync_run_id"],
            external_id=values["external_id"],
            source_url=values["source_url"],
            content_hash=values["content_hash"],
            schema_version=values.get("schema_version", "boss.v1"),
            payload_json=json.dumps(values["payload"], ensure_ascii=False, separators=(",", ":")),
            status="pending",
            error_code=None,
            job_post_id=None,
            created_at=now,
            processed_at=None,
        )
        with self._session_factory() as session:
            try:
                session.add(row)
                session.commit()
                return self._event_view(row), True
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(SourceEventModel).where(
                        SourceEventModel.connector_id == connector_id,
                        SourceEventModel.external_id == values["external_id"],
                        SourceEventModel.content_hash == values["content_hash"],
                    )
                )
                return self._event_view(existing), False

    def complete_event(self, event_id: str, *, job_post_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(SourceEventModel, event_id)
            row.status = "processed"
            row.job_post_id = job_post_id
            row.processed_at = datetime.now(UTC)
            session.commit()

    def complete_opportunity_event(self, event_id: str, *, opportunity_id: str) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(SourceEventModel, event_id)
            if row is None:
                raise LookupError("来源事件不存在。")
            row.status = "processed"
            row.opportunity_id = opportunity_id
            row.processed_at = now
            session.commit()

    def quarantine_event(self, event_id: str, *, error_code: str) -> None:
        with self._session_factory() as session:
            row = session.get(SourceEventModel, event_id)
            row.status = "quarantined"
            row.error_code = error_code[:120]
            row.processed_at = datetime.now(UTC)
            session.commit()

    def list_quarantine(
        self, *, limit: int = 50, connector_id: str | None = None
    ) -> list[dict[str, Any]]:
        connector_id = connector_id or BOSS_CONNECTOR_ID
        with self._session_factory() as session:
            rows = session.scalars(
                select(SourceEventModel)
                .where(
                    SourceEventModel.connector_id == connector_id,
                    SourceEventModel.status == "quarantined",
                )
                .order_by(SourceEventModel.created_at.desc())
                .limit(max(1, min(limit, 100)))
            ).all()
            return [self._event_view(row) for row in rows]

    def due(self, *, connector_id: str | None = None) -> bool:
        connector_id = connector_id or BOSS_CONNECTOR_ID
        config = self._ensure_connector(connector_id)
        next_at = config["next_scan_at"]
        return bool(
            config["enabled"]
            and config["schedule_enabled"]
            and next_at
            and next_at <= datetime.now(UTC)
        )

    def _ensure_connector(self, connector_id: str) -> dict[str, Any]:
        if connector_id == BOSS_CONNECTOR_ID:
            return self.get_or_create_boss()
        if connector_id == NOWCODER_CONNECTOR_ID:
            return self.get_or_create_nowcoder()
        raise ValueError("未知 Connector。")

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _config_view(cls, row: ConnectorConfigModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "connector_type": row.connector_type,
            "display_name": row.display_name,
            "enabled": bool(row.enabled),
            "profile_alias": row.profile_alias,
            "search_query": row.search_query,
            "city": row.city,
            "result_limit": row.result_limit,
            "schedule_enabled": bool(row.schedule_enabled),
            "schedule_times": json.loads(row.schedule_times_json),
            "timezone": row.timezone,
            "next_scan_at": cls._aware(row.next_scan_at),
            "health_status": row.health_status,
            "last_error_code": row.last_error_code,
            "last_success_at": cls._aware(row.last_success_at),
            "version": row.version,
            "created_at": cls._aware(row.created_at),
            "updated_at": cls._aware(row.updated_at),
        }

    @classmethod
    def _run_view(cls, row: SyncRunModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "connector_id": row.connector_id,
            "trigger_type": row.trigger_type,
            "status": row.status,
            "discovered_count": row.discovered_count,
            "created_count": row.created_count,
            "updated_count": row.updated_count,
            "duplicate_count": row.duplicate_count,
            "quarantined_count": row.quarantined_count,
            "error_code": row.error_code,
            "started_at": cls._aware(row.started_at),
            "finished_at": cls._aware(row.finished_at),
        }

    @classmethod
    def _event_view(cls, row: SourceEventModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "sync_run_id": row.sync_run_id,
            "external_id": row.external_id,
            "source_url": row.source_url,
            "content_hash": row.content_hash,
            "schema_version": row.schema_version,
            "status": row.status,
            "error_code": row.error_code,
            "job_post_id": row.job_post_id,
            "opportunity_id": row.opportunity_id,
            "created_at": cls._aware(row.created_at),
            "processed_at": cls._aware(row.processed_at),
        }
