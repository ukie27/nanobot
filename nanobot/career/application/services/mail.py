"""Read-only mail synchronization, matching, and proposal orchestration."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from nanobot.career.application.ports.imap_client import ImapReadOnlyError
from nanobot.career.domain.applications import ApplicationStatus
from nanobot.career.domain.common.errors import CareerDomainError


class MailApplicationService:
    def __init__(self, *, gateway, client, secrets, applications) -> None:
        self.gateway = gateway
        self.client = client
        self.secrets = secrets
        self.applications = applications

    def get(self) -> dict[str, Any]:
        return self.gateway.get()

    def configure(self, *, password: str | None = None, **values: Any) -> dict[str, Any]:
        values["folder"] = values["folder"].strip().upper()
        values["initial_lookback_days"] = max(1, min(30, int(values["initial_lookback_days"])))
        if values["folder"] != "INBOX":
            raise ValueError("Part 7 只允许只读同步 INBOX。")
        if "@" not in values["email_address"]:
            raise ValueError("邮箱地址格式无效。")
        current = self.gateway.get()
        reference = self._secret_reference("primary")
        if password:
            self.secrets.set(reference, password)
        elif not current["configured"]:
            raise ValueError("首次配置必须提供邮箱授权码。")
        values["secret_ref"] = reference
        return self.gateway.configure(**values)

    def delete(self) -> dict[str, bool]:
        reference = self.gateway.delete_account()
        if reference:
            self.secrets.delete(reference)
        return {"deleted": reference is not None}

    def test_connection(self) -> dict[str, Any]:
        config = self._connection_config()
        try:
            result = self.client.test_connection(**config)
            return {**result, "read_only": True}
        except ImapReadOnlyError:
            raise

    def list_messages(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.gateway.list_messages(limit=limit)

    def propose_for_application(self, *, message_id: str, application_id: str) -> dict[str, Any]:
        message = self.gateway.get_message(message_id)
        if not message["event_kind"]:
            raise ValueError("该邮件没有可确认的申请事件类型。")
        application = next(
            (
                item
                for item in self.applications.list_applications()
                if item["id"] == application_id
            ),
            None,
        )
        if application is None:
            raise LookupError("所选申请不存在。")
        proposal = self.applications.propose_event(
            application_id,
            proposed_status=self._target(message["event_kind"]),
            occurred_at=self._event_time(message),
            note=self._proposal_note(message),
            source="imap",
            source_ref=message["id"],
        )
        candidate = self.gateway.attach_candidate(
            message_id,
            application_id=application_id,
            proposal_id=proposal["id"],
        )
        return {"message": self.gateway.get_message(message_id), "candidate": candidate}

    def sync(self, *, trigger_type: str = "manual") -> dict[str, Any]:
        state = self.gateway.get()
        if not state["configured"] or not state["enabled"]:
            raise ValueError("请先配置并启用只读邮箱 Connector。")
        run = self.gateway.start_run(trigger_type=trigger_type)
        counts = {
            "discovered_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "duplicate_count": 0,
        }
        try:
            config = self._connection_config(state)
            config.update(
                uid_validity=state["cursor"]["uid_validity"],
                last_uid=state["cursor"]["last_committed_uid"],
                since=datetime.now(UTC).astimezone(ZoneInfo("Asia/Shanghai")).date()
                - timedelta(days=min(30, state["account"]["initial_lookback_days"])),
            )
            result = self.client.synchronize(**config)
            counts["discovered_count"] = len(result["messages"])
            for record in result["messages"]:
                message, created = self.gateway.save_message(
                    uid_validity=result["uid_validity"], **record
                )
                if not created:
                    counts["duplicate_count"] += 1
                    if message["event_kind"] and not message.get("candidate"):
                        self._create_candidate(message)
                    continue
                counts["created_count"] += 1
                if message["event_kind"]:
                    self._create_candidate(message)
            return self.gateway.finish_run(
                run["id"],
                uid_validity=result["uid_validity"],
                last_uid=result["last_uid"],
                **counts,
            )
        except ImapReadOnlyError as exc:
            self.gateway.fail_run(run["id"], error_code=exc.code)
            raise
        except Exception:
            self.gateway.fail_run(run["id"], error_code="imap_sync_failed")
            raise

    def run_due(self) -> dict[str, Any] | None:
        return self.sync(trigger_type="schedule") if self.gateway.due() else None

    def _create_candidate(self, message: dict[str, Any]) -> None:
        application, score, reason = self._match(message)
        proposal = None
        if application and score >= 0.55:
            target = self._target(message["event_kind"])
            try:
                proposal = self.applications.propose_event(
                    application["id"],
                    proposed_status=target,
                    occurred_at=self._event_time(message),
                    note=self._proposal_note(message),
                    source="imap",
                    source_ref=message["id"],
                )
            except CareerDomainError:
                application = None
                reason = "邮件事件与当前申请状态不构成有效迁移，需人工关联。"
        self.gateway.save_candidate(
            mail_message_id=message["id"],
            application_id=application["id"] if application else None,
            match_confidence=score if application else None,
            match_reason=reason,
            status="proposal_created" if proposal else "needs_review",
            proposal_id=proposal["id"] if proposal else None,
        )

    def _match(self, message: dict[str, Any]) -> tuple[dict[str, Any] | None, float, str]:
        text = self._normalize(
            " ".join(filter(None, [message["subject"], message.get("evidence_excerpt") or ""]))
        )
        best, best_score = None, 0.0
        for item in self.applications.list_applications():
            company = self._normalize(item["company"])
            title = self._normalize(item["job_title"])
            score = (0.65 if company and company in text else 0.0) + (
                0.35 if title and title in text else 0.0
            )
            if score > best_score:
                best, best_score = item, score
        if best is None or best_score < 0.55:
            return None, best_score, "未找到置信度足够的现有申请，请人工关联。"
        return best, best_score, "公司/职位文本与现有申请确定性匹配。"

    def _connection_config(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = state or self.gateway.get()
        if not state["configured"]:
            raise ValueError("尚未配置邮箱。")
        account = state["account"]
        reference = self._secret_reference(account["id"])
        return {
            "host": account["host"],
            "port": account["port"],
            "username": account["username"],
            "password": self.secrets.get(reference),
            "folder": account["folder"],
        }

    @staticmethod
    def _secret_reference(account_id: str) -> str:
        del account_id
        return "imap-account:primary"

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.casefold())

    @staticmethod
    def _target(kind: str) -> ApplicationStatus:
        return {
            "assessment": ApplicationStatus.ASSESSMENT,
            "written_test": ApplicationStatus.WRITTEN_TEST,
            "interview": ApplicationStatus.INTERVIEW,
            "reschedule": ApplicationStatus.INTERVIEW,
            "rejected": ApplicationStatus.REJECTED,
            "offer": ApplicationStatus.OFFER,
        }[kind]

    @staticmethod
    def _proposal_note(message: dict[str, Any]) -> str:
        excerpt = message.get("evidence_excerpt") or ""
        return f"邮件证据：{message['subject']}\n{excerpt[:500]}".strip()

    @staticmethod
    def _event_time(message: dict[str, Any]) -> datetime:
        scheduled = message.get("extracted", {}).get("scheduled_at")
        if scheduled:
            return datetime.fromisoformat(str(scheduled)).astimezone(UTC)
        return message["sent_at"] or datetime.now(UTC)
