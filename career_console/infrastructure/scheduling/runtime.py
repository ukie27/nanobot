"""Configuration-driven business scheduling with sanitized run audit."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select

from career_console.infrastructure.configuration.schema import (
    ConfigurationUpdate,
    SchedulerConfiguration,
)
from career_console.infrastructure.database.models import SchedulerRunModel


class CareerSchedulerRuntime:
    def __init__(
        self, *, configuration: Any, session_factory: Any, task_service: Any,
        connector_service: Any, nowcoder_service: Any, mail_service: Any,
        profile_memory: Any, profile_impacts: Any, channels: Any,
    ) -> None:
        self.configuration_service = configuration
        self.session_factory = session_factory
        self.task_service = task_service
        self.connector_service = connector_service
        self.nowcoder_service = nowcoder_service
        self.mail_service = mail_service
        self.profile_memory = profile_memory
        self.profile_impacts = profile_impacts
        self.channels = channels

    def configuration(self) -> dict[str, Any]:
        document = self.configuration_service.store.load()
        return {
            **document.configuration.scheduler.model_dump(mode="json"),
            "configuration_revision": document.revision,
        }

    def configure(self, expected_revision: int, values: dict[str, Any]) -> dict[str, Any]:
        document = self.configuration_service.store.load()
        updated = document.configuration.model_copy(deep=True)
        updated.scheduler = SchedulerConfiguration(**values)
        self.configuration_service.update(ConfigurationUpdate(
            expected_revision=expected_revision, reason="更新业务 Scheduler",
            configuration=updated,
        ))
        return self.configuration()

    def run_once(
        self, *, trigger_type: str = "schedule", now: datetime | None = None
    ) -> dict[str, Any]:
        started = now or datetime.now(UTC)
        config = self.configuration_service.store.load().configuration.scheduler
        counters: dict[str, int] = {
            "schedules_processed": 0, "reminders_triggered": 0,
            "outbox_dispatched": 0, "leases_recovered": 0,
            "connector_runs_processed": 0,
            "mail_analysis_processed": 0, "profile_jobs_processed": 0,
            "profile_digest_generated": 0, "profile_insights_created": 0,
            "profile_insights_reused": 0, "profile_insight_skipped": 0,
            "profile_insight_failed": 0, "profile_strategy_processed": 0,
            "channel_sent": 0, "channel_failed": 0,
            "opportunities_discovered": 0, "jd_discovered": 0,
            "jd_imported": 0, "recommendations_created": 0,
            "recommendations_rejected": 0, "jd_discovery_failed": 0,
            "recommendation_failed": 0,
        }
        errors: list[str] = []
        if config.enabled:
            if config.reminders_enabled:
                self._merge(counters, self._safe(errors, "reminders", self.task_service.run_due, now=now))
            if config.connector_jobs_enabled:
                for name, service in (("boss", self.connector_service), ("nowcoder", self.nowcoder_service), ("imap", self.mail_service)):
                    result = self._safe(
                        errors, name, service.run_due,
                        **({"now": now or started} if name == "nowcoder" else {})
                    )
                    self._merge(counters, result)
                    counters["connector_runs_processed"] += int(result is not None)
                for _ in range(10):
                    result = self._safe(errors, "mail_analysis", self.mail_service.process_next_analysis_job)
                    if not result:
                        break
                    counters["mail_analysis_processed"] += 1
            if config.profile_maintenance_enabled and self._profile_due(
                config.profile_maintenance_time, now or started
            ) and not self._profile_completed_today(now or started):
                result = self._safe(
                    errors, "profile_memory", self.profile_memory.run_due, now=now or started
                )
                self._merge(counters, result)
                self._safe(errors, "profile_impacts", self.profile_impacts.enqueue_pending)
                for _ in range(20):
                    result = self._safe(errors, "profile_impacts", self.profile_impacts.process_next)
                    if not result:
                        break
                    counters["profile_jobs_processed"] += 1
            if config.channel_dispatch_enabled:
                notifications = [
                    notification
                    for notification in self.task_service.gateway.list_notifications()
                    if notification.get("status") == "unread"
                ]
                deliveries = self.channels.dispatch_notifications(
                    notifications
                )
                counters["channel_sent"] = deliveries["sent"]
                counters["channel_failed"] = deliveries["failed"]
        finished = datetime.now(UTC)
        status = "failed" if errors and not any(counters.values()) else (
            "partial" if errors else ("skipped" if not config.enabled else "succeeded")
        )
        row = SchedulerRunModel(
            id=str(uuid4()), trigger_type=trigger_type, status=status,
            counters_json=json.dumps(counters, separators=(",", ":")),
            error_codes_json=json.dumps(errors, separators=(",", ":")),
            started_at=started, finished_at=finished,
        )
        with self.session_factory() as session:
            session.add(row)
            session.flush()
            self._prune_runs(session, reference_time=finished)
            session.commit()
        return {"id": row.id, "trigger_type": trigger_type, "status": status,
                "counters": counters, "error_codes": errors,
                "started_at": started, "finished_at": finished}

    def list_runs(self, limit: int = 50) -> dict[str, Any]:
        with self.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(SchedulerRunModel)) or 0
            rows = session.scalars(select(SchedulerRunModel).order_by(
                SchedulerRunModel.started_at.desc()
            ).limit(max(1, min(limit, 200)))).all()
            items = [{"id": row.id, "trigger_type": row.trigger_type,
                      "status": row.status, "counters": json.loads(row.counters_json),
                      "error_codes": json.loads(row.error_codes_json),
                      "started_at": row.started_at, "finished_at": row.finished_at}
                     for row in rows]
        return {"items": items, "total": total}

    @staticmethod
    def _prune_runs(session: Any, *, reference_time: datetime) -> None:
        cutoff = reference_time - timedelta(days=30)
        session.execute(
            delete(SchedulerRunModel).where(SchedulerRunModel.started_at < cutoff)
        )
        stale_ids = session.scalars(
            select(SchedulerRunModel.id)
            .order_by(SchedulerRunModel.started_at.desc())
            .offset(200)
        ).all()
        if stale_ids:
            session.execute(
                delete(SchedulerRunModel).where(SchedulerRunModel.id.in_(stale_ids))
            )

    @staticmethod
    def _safe(errors: list[str], name: str, function: Any, **kwargs: Any) -> Any:
        try:
            return function(**kwargs)
        except Exception as exc:
            code = str(getattr(exc, "code", f"{name}_failed"))
            errors.append(code[:80])
            return None

    @staticmethod
    def _merge(target: dict[str, int], values: dict[str, Any] | None) -> None:
        for key, value in (values or {}).items():
            if key in target and isinstance(value, int):
                target[key] += value

    @staticmethod
    def _profile_due(configured_time: str, now: datetime) -> bool:
        local = now.astimezone(ZoneInfo("Asia/Shanghai"))
        return local.strftime("%H:%M") >= configured_time

    def _profile_completed_today(self, now: datetime) -> bool:
        china = ZoneInfo("Asia/Shanghai")
        local = now.astimezone(china)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        end = (start.astimezone(china).replace(hour=0) + timedelta(days=1)).astimezone(UTC)
        with self.session_factory() as session:
            counters = session.scalars(
                select(SchedulerRunModel.counters_json).where(
                    SchedulerRunModel.started_at >= start,
                    SchedulerRunModel.started_at < end,
                )
            ).all()
        return any(
            int(json.loads(value).get("profile_jobs_processed", 0)) > 0
            for value in counters
        )
