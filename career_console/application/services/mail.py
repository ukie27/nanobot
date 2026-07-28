"""Read-only mail synchronization, matching, and proposal orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from career_console.application.ports.imap_client import ImapReadOnlyError
from career_console.domain.applications import ApplicationStatus
from career_console.domain.common.errors import CareerDomainError


class MailApplicationService:
    ANALYSIS_JOB_TYPE = "mail.intelligence.analyze"

    def __init__(
        self, *, gateway, client, secrets, applications, tasks=None, jobs=None, analyzer=None,
        secret_reference: str = "imap-account:primary",
    ) -> None:
        self.gateway = gateway
        self.client = client
        self.secrets = secrets
        self.applications = applications
        self.tasks = tasks
        self.jobs = jobs
        self.analyzer = analyzer
        self.secret_reference = secret_reference

    def get(self) -> dict[str, Any]:
        state = self.gateway.get()
        account = state.get("account")
        if account is not None:
            try:
                self.secrets.get(self._secret_reference("primary"))
                credential_configured = True
            except LookupError:
                credential_configured = False
            state = {
                **state,
                "account": {**account, "credential_configured": credential_configured},
            }
        return state

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
            self.gateway.record_health(status="healthy", error_code=None)
            return {**result, "read_only": True}
        except ImapReadOnlyError as exc:
            self.gateway.record_health(status="unavailable", error_code=exc.code)
            raise

    def list_messages(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.gateway.list_messages(limit=limit)

    def analyze_message(self, *, message_id: str) -> dict[str, Any]:
        message = self.gateway.get_message(message_id)
        if not self._is_analysis_candidate(message):
            raise CareerDomainError(
                "无关邮件仅保留最少 Header，不会进入智能分析。",
                code="mail_intelligence_unrelated",
            )
        if self.analyzer is None:
            raise CareerDomainError(
                "邮件智能分析 Agent 尚未配置，请在 CareerConsole 设置中配置模型 Provider 后重启。",
                code="mail_intelligence_unavailable",
            )
        if message.get("intelligence") is not None:
            return message["intelligence"]
        if not message["body_fetched"]:
            raise CareerDomainError(
                "该邮件只有 Header，缺少可供 Agent 核验的正文证据。",
                code="mail_intelligence_body_unavailable",
            )
        applications = self.applications.list_applications()
        input_hash = self._analysis_input_hash(message, applications)
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            result = self.analyzer.analyze(message=message, applications=applications)
        except CareerDomainError as exc:
            self.gateway.save_analysis_failure(
                message_id=message_id, input_hash=input_hash, error_code=exc.code,
                audit=self._analysis_audit(started_at, started),
            )
            raise
        output_json = result.model_dump_json(by_alias=True)
        return self.gateway.save_analysis(
            message_id=message_id, result=result, input_hash=input_hash,
            output_hash=hashlib.sha256(output_json.encode("utf-8")).hexdigest(),
            audit=self._analysis_audit(started_at, started),
        )

    def resolve_intelligence_item(
        self, *, item_id: str, expected_version: int, resolution: str, reason: str
    ) -> dict[str, Any]:
        item = self.gateway.get_intelligence_item(item_id)
        if item["status"] != "pending":
            return self.gateway.resolve_intelligence_item(
                item_id, expected_version=expected_version, resolution=resolution, reason=reason
            )
        if resolution == "confirmed":
            application_id = item.get("application_id")
            if item["item_type"] == "event" and item.get("status_candidate") and application_id:
                application = next(
                    (entry for entry in self.applications.list_applications() if entry["id"] == application_id),
                    None,
                )
                if application is None:
                    raise LookupError("Agent 匹配的申请已不存在。")
                self.applications.add_event(
                    application_id, expected_version=application["version"],
                    target_status=ApplicationStatus(item["status_candidate"]),
                    occurred_at=item["occurred_at"] or datetime.now(UTC),
                    note=f"邮件 Agent 确认：{item['title']}\n{item['details']}\n证据：{item['evidence']}",
                    command_id=f"mail-intelligence:{item_id}", source="imap_agent",
                )
            elif item["item_type"] == "schedule" and self.tasks is not None:
                self.tasks.create_task(
                    title=item["title"], task_type=item["category"],
                    due_at=item["scheduled_at"], timezone="Asia/Shanghai",
                    notes=f"{item['details']}\n证据：{item['evidence']}", priority=40,
                    application_id=application_id,
                    source_key=f"mail-intelligence:{item_id}",
                )
        return self.gateway.resolve_intelligence_item(
            item_id, expected_version=expected_version, resolution=resolution, reason=reason
        )

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
            "analysis_queued_count": 0,
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
                if self._queue_analysis(message):
                    counts["analysis_queued_count"] += 1
                if message["event_kind"]:
                    self._create_candidate(message)
            finished = self.gateway.finish_run(
                run["id"],
                uid_validity=result["uid_validity"],
                last_uid=result["last_uid"],
                **counts,
            )
            finished["analysis_queued_count"] = counts["analysis_queued_count"]
            return finished
        except ImapReadOnlyError as exc:
            self.gateway.fail_run(run["id"], error_code=exc.code)
            raise
        except Exception:
            self.gateway.fail_run(run["id"], error_code="imap_sync_failed")
            raise

    def run_due(self) -> dict[str, Any] | None:
        return self.sync(trigger_type="schedule") if self.gateway.due() else None

    def process_next_analysis_job(self, *, worker_id: str = "career-mail-worker") -> bool:
        if self.jobs is None or self.analyzer is None:
            return False
        job = self.jobs.claim_next(
            worker_id, lease_seconds=300, job_types={self.ANALYSIS_JOB_TYPE}
        )
        if job is None:
            return False
        try:
            self.analyze_message(message_id=str(job.payload["message_id"]))
        except CareerDomainError as exc:
            self.jobs.fail(job.id, worker_id, error_code=exc.code)
        except Exception:
            self.jobs.fail(job.id, worker_id, error_code="mail_intelligence_job_failed")
        else:
            self.jobs.complete(job.id, worker_id)
        return True

    def _queue_analysis(self, message: dict[str, Any]) -> bool:
        if (
            self.jobs is None or self.analyzer is None or not message.get("body_fetched")
            or not self._is_analysis_candidate(message)
            or message.get("intelligence") is not None
        ):
            return False
        self.jobs.enqueue(
            self.ANALYSIS_JOB_TYPE, {"message_id": message["id"]},
            idempotency_key=f"mail-intelligence:{message['id']}", priority=40, max_attempts=3,
        )
        return True

    @staticmethod
    def _is_analysis_candidate(message: dict[str, Any]) -> bool:
        return message.get("classification") in {"recruiting", "possibly_related"}

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

    def _secret_reference(self, account_id: str) -> str:
        del account_id
        return self.secret_reference

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

    @staticmethod
    def _analysis_input_hash(message: dict[str, Any], applications: list[dict[str, Any]]) -> str:
        payload = {
            "id": message["id"], "uid": message["uid"], "sender": message["sender"],
            "subject": message["subject"], "sent_at": str(message.get("sent_at")),
            "body_hash": message.get("body_hash"), "evidence": message.get("evidence_excerpt"),
            "applications": [
                [item["id"], item["company"], item["job_title"], item["current_status"], item["version"]]
                for item in applications
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _analysis_audit(self, started_at: datetime, started: float) -> dict[str, Any]:
        provider = getattr(self.analyzer, "provider", None)
        usage = getattr(self.analyzer, "last_usage", {}) or {}
        return {
            "implementation": getattr(self.analyzer, "name", "mail_intelligence"),
            "provider": type(provider).__name__ if provider is not None else None,
            "model": getattr(self.analyzer, "model", None),
            "prompt_version": getattr(self.analyzer, "prompt_version", "mail_intelligence.v1"),
            "created_at": started_at,
            "duration_ms": max(0, round((perf_counter() - started) * 1000)),
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "retry_count": int(getattr(self.analyzer, "last_retry_count", 0)),
        }
