"""Workspace-scoped Channel configuration and sanitized delivery audit."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from career_console.infrastructure.channels.qq import QQChannelDeliveryError
from career_console.infrastructure.configuration.schema import (
    ConfigurationUpdate,
    QQChannelConfiguration,
)
from career_console.infrastructure.database.models import ChannelDeliveryRunModel


class ChannelConfigurationService:
    def __init__(
        self, *, configuration: Any, secrets: Any, session_factory: Any,
        qq_sender: Any, qq_secret_ref: str,
    ) -> None:
        self.configuration = configuration
        self.secrets = secrets
        self.session_factory = session_factory
        self.qq_sender = qq_sender
        self.qq_secret_ref = qq_secret_ref

    def get_qq(self) -> dict[str, Any]:
        document = self.configuration.store.load()
        config = document.configuration.channels.qq if document else QQChannelConfiguration()
        return {
            **config.model_dump(mode="json", exclude={"secret_ref"}),
            "has_secret": self._has_secret(config.secret_ref),
            "configuration_revision": document.revision if document else None,
        }

    def configure_qq(
        self, *, expected_revision: int, secret: str | None = None, **values: Any
    ) -> dict[str, Any]:
        document = self.configuration.store.load()
        if document is None:
            raise RuntimeError("Workspace configuration has not been initialized.")
        current = document.configuration.channels.qq
        previous_secret: str | None = None
        secret_created = False
        if secret:
            try:
                previous_secret = self.secrets.get(self.qq_secret_ref)
            except LookupError:
                secret_created = True
            self.secrets.set(self.qq_secret_ref, secret)
        elif values.get("enabled") and not current.secret_ref:
            raise ValueError("首次启用 QQ Channel 必须提供 App Secret。")
        values["secret_ref"] = self.qq_secret_ref if (secret or current.secret_ref) else None
        updated = document.configuration.model_copy(deep=True)
        updated.channels.qq = QQChannelConfiguration(**values)
        try:
            self.configuration.update(ConfigurationUpdate(
                expected_revision=expected_revision,
                reason="更新 QQ 通知 Channel",
                configuration=updated,
            ))
        except Exception:
            if secret_created:
                self.secrets.delete(self.qq_secret_ref)
            elif previous_secret is not None:
                self.secrets.set(self.qq_secret_ref, previous_secret)
            raise
        return self.get_qq()

    def delete_qq(self, expected_revision: int) -> dict[str, bool]:
        document = self.configuration.store.load()
        if document is None:
            raise RuntimeError("Workspace configuration has not been initialized.")
        updated = document.configuration.model_copy(deep=True)
        reference = updated.channels.qq.secret_ref
        updated.channels.qq = QQChannelConfiguration()
        self.configuration.update(ConfigurationUpdate(
            expected_revision=expected_revision,
            reason="删除 QQ 通知 Channel",
            configuration=updated,
        ))
        if reference:
            self.secrets.delete(reference)
        return {"deleted": reference is not None}

    def test_qq(self) -> dict[str, Any]:
        document = self.configuration.store.load()
        if document is None:
            raise ValueError("QQ Channel 尚未配置。")
        config = document.configuration.channels.qq
        if not config.enabled or not config.secret_ref or not config.notification_targets:
            raise ValueError("请先启用 QQ Channel 并配置通知目标。")
        target = config.notification_targets[0]
        started = perf_counter()
        status, error_code = "passed", None
        try:
            self.qq_sender.send(
                app_id=config.app_id,
                secret=self.secrets.get(config.secret_ref),
                target=target,
                content="CareerConsole 通知通道测试成功。",
            )
        except LookupError:
            status, error_code = "failed", "credential_missing"
        except QQChannelDeliveryError as exc:
            status, error_code = "failed", exc.code
        return self._record(
            event_type="connection_test", source_ref=None, target=target, status=status,
            error_code=error_code,
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
        )

    def list_deliveries(self, limit: int = 50) -> dict[str, Any]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(ChannelDeliveryRunModel)
                .order_by(ChannelDeliveryRunModel.created_at.desc())
                .limit(max(1, min(limit, 200)))
            ).all()
            items = [self._view(row) for row in rows]
        return {"items": items, "total": len(items)}

    def dispatch_notifications(self, notifications: list[dict[str, Any]]) -> dict[str, int]:
        document = self.configuration.store.load()
        config = document.configuration.channels.qq if document else QQChannelConfiguration()
        if (
            not config.enabled or not config.secret_ref
            or "task_reminder" not in config.event_subscriptions
            or self._quiet(config, datetime.now(UTC))
        ):
            return {"sent": 0, "failed": 0, "skipped": len(notifications)}
        sent = failed = skipped = 0
        for notification in notifications:
            for target in config.notification_targets:
                source_ref = f"notification:{notification['id']}:{self._mask_target(target)}"
                if self._already_sent(source_ref):
                    skipped += 1
                    continue
                if self._attempt_count(source_ref) >= document.configuration.channels.send_max_retries:
                    skipped += 1
                    continue
                started = perf_counter()
                status, error_code = "passed", None
                try:
                    self.qq_sender.send(
                        app_id=config.app_id, secret=self.secrets.get(config.secret_ref),
                        target=target,
                        content=f"{notification['title']}\n{notification['body']}",
                    )
                    sent += 1
                except (LookupError, QQChannelDeliveryError) as exc:
                    failed += 1
                    status = "failed"
                    error_code = (
                        exc.code if isinstance(exc, QQChannelDeliveryError)
                        else "credential_missing"
                    )
                except Exception:
                    failed += 1
                    status = "failed"
                    error_code = "delivery_failed"
                self._record(
                    event_type="task_reminder", source_ref=source_ref, target=target,
                    status=status, error_code=error_code,
                    duration_ms=max(0, round((perf_counter() - started) * 1000)),
                )
        return {"sent": sent, "failed": failed, "skipped": skipped}

    def _record(
        self, *, event_type: str, source_ref: str | None, target: str, status: str,
        error_code: str | None, duration_ms: int,
    ) -> dict[str, Any]:
        row = ChannelDeliveryRunModel(
            id=str(uuid4()), channel_type="qq", event_type=event_type,
            source_ref=source_ref,
            target_masked=self._mask_target(target), status=status,
            error_code=error_code, duration_ms=duration_ms, created_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(row)
            session.commit()
            return self._view(row)

    def _has_secret(self, reference: str | None) -> bool:
        if not reference:
            return False
        try:
            self.secrets.get(reference)
            return True
        except (LookupError, RuntimeError):
            return False

    @staticmethod
    def _mask_target(target: str) -> str:
        target_type, value = target.split(":", 1)
        digest = hashlib.sha256(value.encode()).hexdigest()[:12]
        return f"{target_type}:sha256:{digest}"

    @staticmethod
    def _view(row: ChannelDeliveryRunModel) -> dict[str, Any]:
        return {
            "id": row.id, "channel_type": row.channel_type,
            "event_type": row.event_type, "target_masked": row.target_masked,
            "status": row.status, "error_code": row.error_code,
            "duration_ms": row.duration_ms, "created_at": row.created_at,
        }

    def _already_sent(self, source_ref: str) -> bool:
        with self.session_factory() as session:
            return session.scalar(select(ChannelDeliveryRunModel.id).where(
                ChannelDeliveryRunModel.source_ref == source_ref,
                ChannelDeliveryRunModel.status == "passed",
            ).limit(1)) is not None

    def _attempt_count(self, source_ref: str) -> int:
        with self.session_factory() as session:
            return len(session.scalars(select(ChannelDeliveryRunModel.id).where(
                ChannelDeliveryRunModel.source_ref == source_ref,
            )).all())

    @staticmethod
    def _quiet(config: QQChannelConfiguration, now: datetime) -> bool:
        quiet = config.quiet_hours
        if not quiet.enabled:
            return False
        current = now.astimezone(ZoneInfo(quiet.timezone)).strftime("%H:%M")
        return (
            quiet.start <= current < quiet.end
            if quiet.start < quiet.end
            else current >= quiet.start or current < quiet.end
        )
