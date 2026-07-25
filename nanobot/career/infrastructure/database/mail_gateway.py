"""SQLAlchemy persistence for the single-account read-only IMAP connector."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from nanobot.career.infrastructure.database.models import (
    ConnectorConfigModel,
    ImapAccountModel,
    MailApplicationCandidateModel,
    MailMessageModel,
    SyncCursorModel,
    SyncRunModel,
)

IMAP_CONNECTOR_ID = "00000000-0000-0000-0000-000000000007"


class SqlAlchemyMailGateway:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def get(self) -> dict[str, Any]:
        with self._session_factory() as session:
            connector = session.get(ConnectorConfigModel, IMAP_CONNECTOR_ID)
            account = session.scalar(
                select(ImapAccountModel).where(ImapAccountModel.connector_id == IMAP_CONNECTOR_ID)
            )
            cursor = self._cursor_map(session)
            runs = session.scalars(
                select(SyncRunModel)
                .where(SyncRunModel.connector_id == IMAP_CONNECTOR_ID)
                .order_by(SyncRunModel.started_at.desc())
                .limit(20)
            ).all()
            return {
                "configured": account is not None,
                "enabled": bool(connector.enabled) if connector else False,
                "health_status": connector.health_status if connector else "unconfigured",
                "last_error_code": connector.last_error_code if connector else None,
                "last_success_at": self._utc(connector.last_success_at) if connector else None,
                "next_sync_at": self._utc(connector.next_scan_at) if connector else None,
                "account": self._account_view(account) if account else None,
                "cursor": cursor,
                "runs": [self._run_view(row) for row in runs],
            }

    def configure(self, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            connector = session.get(ConnectorConfigModel, IMAP_CONNECTOR_ID)
            if connector is None:
                connector = ConnectorConfigModel(
                    id=IMAP_CONNECTOR_ID,
                    connector_type="imap_readonly",
                    display_name="只读招聘邮箱",
                    enabled=int(bool(values["enabled"])),
                    profile_alias="default",
                    search_query="",
                    city="",
                    result_limit=100,
                    schedule_enabled=1,
                    schedule_times_json="[]",
                    timezone="Asia/Shanghai",
                    next_scan_at=now if values["enabled"] else None,
                    scan_lease_run_id=None,
                    scan_lease_expires_at=None,
                    health_status="unknown",
                    last_error_code=None,
                    last_success_at=None,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(connector)
            else:
                connector.enabled = int(bool(values["enabled"]))
                connector.next_scan_at = now if values["enabled"] else None
                connector.version += 1
                connector.updated_at = now
            account = session.scalar(
                select(ImapAccountModel).where(ImapAccountModel.connector_id == IMAP_CONNECTOR_ID)
            )
            if account is None:
                account = ImapAccountModel(
                    id=str(uuid4()),
                    connector_id=IMAP_CONNECTOR_ID,
                    created_at=now,
                    **self._account_values(values),
                )
                session.add(account)
            else:
                for key, value in self._account_values(values).items():
                    setattr(account, key, value)
            account.updated_at = now
            session.commit()
        return self.get()

    def delete_account(self) -> str | None:
        with self._session_factory() as session:
            account = session.scalar(
                select(ImapAccountModel).where(ImapAccountModel.connector_id == IMAP_CONNECTOR_ID)
            )
            reference = account.secret_ref if account else None
            connector = session.get(ConnectorConfigModel, IMAP_CONNECTOR_ID)
            if connector:
                session.delete(connector)
            session.commit()
            return reference

    def list_messages(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(MailMessageModel)
                .order_by(MailMessageModel.sent_at.desc(), MailMessageModel.created_at.desc())
                .limit(max(1, min(limit, 500)))
            ).all()
            return [self._message_view(session, row) for row in rows]

    def get_message(self, message_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(MailMessageModel, message_id)
            if row is None:
                raise LookupError("邮件记录不存在。")
            return self._message_view(session, row)

    def start_run(self, *, trigger_type: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            run_id = str(uuid4())
            acquired = session.execute(
                update(ConnectorConfigModel)
                .where(
                    ConnectorConfigModel.id == IMAP_CONNECTOR_ID,
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
                if session.get(ConnectorConfigModel, IMAP_CONNECTOR_ID) is None:
                    raise LookupError("只读邮箱 Connector 不存在。")
                raise RuntimeError("已有邮箱同步正在运行，请稍后再试。")
            row = SyncRunModel(
                id=run_id,
                connector_id=IMAP_CONNECTOR_ID,
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

    def finish_run(self, run_id: str, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(SyncRunModel, run_id)
            if row is None or row.connector_id != IMAP_CONNECTOR_ID:
                raise LookupError("邮箱同步运行不存在。")
            for key in ("discovered_count", "created_count", "updated_count", "duplicate_count"):
                setattr(row, key, int(values.get(key, 0)))
            row.status = "succeeded"
            row.finished_at = now
            connector = session.get(ConnectorConfigModel, IMAP_CONNECTOR_ID)
            if connector is None:
                raise LookupError("只读邮箱 Connector 不存在。")
            account = session.scalar(
                select(ImapAccountModel).where(ImapAccountModel.connector_id == IMAP_CONNECTOR_ID)
            )
            if account is None:
                raise LookupError("只读邮箱账户不存在。")
            connector.health_status = "healthy"
            connector.last_error_code = None
            connector.last_success_at = now
            connector.next_scan_at = now + timedelta(minutes=account.poll_interval_minutes)
            connector.updated_at = now
            if connector.scan_lease_run_id == run_id:
                connector.scan_lease_run_id = None
                connector.scan_lease_expires_at = None
            self._set_cursor(session, "uid_validity", str(values["uid_validity"]), now)
            self._set_cursor(session, "last_committed_uid", str(values["last_uid"]), now)
            session.commit()
            return self._run_view(row)

    def fail_run(self, run_id: str, *, error_code: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(SyncRunModel, run_id)
            if row is None or row.connector_id != IMAP_CONNECTOR_ID:
                raise LookupError("邮箱同步运行不存在。")
            row.status = "failed"
            row.error_code = error_code[:120]
            row.finished_at = now
            connector = session.get(ConnectorConfigModel, IMAP_CONNECTOR_ID)
            if connector is None:
                raise LookupError("只读邮箱 Connector 不存在。")
            account = session.scalar(
                select(ImapAccountModel).where(ImapAccountModel.connector_id == IMAP_CONNECTOR_ID)
            )
            if account is None:
                raise LookupError("只读邮箱账户不存在。")
            connector.health_status = "unavailable"
            connector.last_error_code = error_code[:120]
            connector.next_scan_at = now + timedelta(minutes=account.poll_interval_minutes)
            connector.updated_at = now
            if connector.scan_lease_run_id == run_id:
                connector.scan_lease_run_id = None
                connector.scan_lease_expires_at = None
            session.commit()
            return self._run_view(row)

    def save_message(self, **values: Any) -> tuple[dict[str, Any], bool]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.scalar(
                select(ImapAccountModel).where(ImapAccountModel.connector_id == IMAP_CONNECTOR_ID)
            )
            if account is None:
                raise LookupError("只读邮箱账户不存在。")
            row = MailMessageModel(
                id=str(uuid4()),
                account_id=account.id,
                uid_validity=values["uid_validity"],
                uid=values["uid"],
                message_id=values.get("message_id"),
                sender=values["sender"],
                subject=values["subject"],
                sent_at=values.get("sent_at"),
                classification=values["classification"],
                event_kind=values.get("event_kind"),
                extracted_json=json.dumps(values.get("extracted", {}), ensure_ascii=False),
                evidence_excerpt=values.get("evidence_excerpt"),
                body_hash=values.get("body_hash"),
                attachments_json=json.dumps(values.get("attachments", []), ensure_ascii=False),
                body_fetched=int(bool(values.get("body_fetched"))),
                created_at=now,
            )
            try:
                session.add(row)
                session.commit()
                return self._message_view(session, row), True
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(MailMessageModel).where(
                        MailMessageModel.account_id == account.id,
                        or_(
                            (
                                (MailMessageModel.uid_validity == values["uid_validity"])
                                & (MailMessageModel.uid == values["uid"])
                            ),
                            (MailMessageModel.message_id == values.get("message_id"))
                            if values.get("message_id")
                            else False,
                        ),
                    )
                )
                if existing is None:
                    raise
                return self._message_view(session, existing), False

    def save_candidate(self, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            existing = session.scalar(
                select(MailApplicationCandidateModel).where(
                    MailApplicationCandidateModel.mail_message_id == values["mail_message_id"]
                )
            )
            if existing:
                return self._candidate_view(existing)
            row = MailApplicationCandidateModel(
                id=str(uuid4()),
                mail_message_id=values["mail_message_id"],
                application_id=values.get("application_id"),
                match_confidence=values.get("match_confidence"),
                match_reason=values["match_reason"][:500],
                status=values["status"],
                proposal_id=values.get("proposal_id"),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()
            return self._candidate_view(row)

    def attach_candidate(self, message_id: str, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.scalar(
                select(MailApplicationCandidateModel).where(
                    MailApplicationCandidateModel.mail_message_id == message_id
                )
            )
            if row is None:
                raise LookupError("邮件候选记录不存在。")
            if row.proposal_id:
                raise ValueError("该邮件已经生成 Proposal，不能重复关联。")
            row.application_id = values["application_id"]
            row.match_confidence = None
            row.match_reason = "用户在消息中心手动关联申请。"
            row.status = "proposal_created"
            row.proposal_id = values["proposal_id"]
            row.updated_at = now
            session.commit()
            return self._candidate_view(row)

    def due(self) -> bool:
        data = self.get()
        return bool(
            data["configured"]
            and data["enabled"]
            and data["next_sync_at"]
            and data["next_sync_at"] <= datetime.now(UTC)
        )

    @staticmethod
    def _account_values(values: dict[str, Any]) -> dict[str, Any]:
        return {
            key: values[key]
            for key in (
                "email_address",
                "host",
                "port",
                "username",
                "secret_ref",
                "folder",
                "initial_lookback_days",
                "poll_interval_minutes",
            )
        }

    def _cursor_map(self, session) -> dict[str, Any]:
        rows = session.scalars(
            select(SyncCursorModel).where(SyncCursorModel.connector_id == IMAP_CONNECTOR_ID)
        ).all()
        values = {row.cursor_key: row.cursor_value for row in rows}
        return {
            "uid_validity": values.get("uid_validity"),
            "last_committed_uid": int(values.get("last_committed_uid", "0")),
        }

    @staticmethod
    def _set_cursor(session, key: str, value: str, now: datetime) -> None:
        row = session.scalar(
            select(SyncCursorModel).where(
                SyncCursorModel.connector_id == IMAP_CONNECTOR_ID, SyncCursorModel.cursor_key == key
            )
        )
        if row is None:
            session.add(
                SyncCursorModel(
                    id=str(uuid4()),
                    connector_id=IMAP_CONNECTOR_ID,
                    cursor_key=key,
                    cursor_value=value,
                    updated_at=now,
                )
            )
        else:
            row.cursor_value = value
            row.updated_at = now

    @classmethod
    def _account_view(cls, account: ImapAccountModel) -> dict[str, Any]:
        return {
            "id": account.id,
            "email_address": account.email_address,
            "host": account.host,
            "port": account.port,
            "username": account.username,
            "folder": account.folder,
            "initial_lookback_days": account.initial_lookback_days,
            "poll_interval_minutes": account.poll_interval_minutes,
            "credential_configured": bool(account.secret_ref),
            "username_masked": cls._mask(account.username),
            "created_at": cls._utc(account.created_at),
            "updated_at": cls._utc(account.updated_at),
        }

    @classmethod
    def _message_view(cls, session, row: MailMessageModel) -> dict[str, Any]:
        candidate = session.scalar(
            select(MailApplicationCandidateModel).where(
                MailApplicationCandidateModel.mail_message_id == row.id
            )
        )
        return {
            "id": row.id,
            "uid": row.uid,
            "sender": row.sender,
            "subject": row.subject,
            "sent_at": cls._utc(row.sent_at),
            "classification": row.classification,
            "event_kind": row.event_kind,
            "extracted": json.loads(row.extracted_json),
            "evidence_excerpt": row.evidence_excerpt,
            "body_hash": row.body_hash,
            "attachments": json.loads(row.attachments_json),
            "body_fetched": bool(row.body_fetched),
            "candidate": cls._candidate_view(candidate) if candidate else None,
            "created_at": cls._utc(row.created_at),
        }

    @classmethod
    def _run_view(cls, row: SyncRunModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "trigger_type": row.trigger_type,
            "status": row.status,
            "discovered_count": row.discovered_count,
            "created_count": row.created_count,
            "duplicate_count": row.duplicate_count,
            "error_code": row.error_code,
            "started_at": cls._utc(row.started_at),
            "finished_at": cls._utc(row.finished_at),
        }

    @classmethod
    def _candidate_view(cls, row: MailApplicationCandidateModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "application_id": row.application_id,
            "match_confidence": row.match_confidence,
            "match_reason": row.match_reason,
            "status": row.status,
            "proposal_id": row.proposal_id,
            "created_at": cls._utc(row.created_at),
            "updated_at": cls._utc(row.updated_at),
        }

    @staticmethod
    def _mask(value: str) -> str:
        if "@" in value:
            name, domain = value.split("@", 1)
            return f"{name[:2]}***@{domain}"
        return f"{value[:2]}***"

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
