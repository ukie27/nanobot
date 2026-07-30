"""Deterministic reconciliation of recruiting-mail candidates with applications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class MailReconciliationDecision:
    action: str
    reason: str
    job_post_id: str | None = None
    occurred_at: datetime | None = None
    evidence: str = ""
    item_categories: tuple[str, ...] = ()


class MailApplicationReconciliationPolicy:
    AUTO_MESSAGE_TYPES = {
        "application_submission_confirmation",
        "application_received",
    }
    AUTO_EVENT_TYPES = {
        "application_submitted",
        "application_submission_confirmed",
        "application_received",
        "submission_confirmation",
    }
    MIN_CONFIDENCE = 0.9

    def evaluate(
        self,
        *,
        analysis: dict[str, Any],
        jobs: list[dict[str, Any]],
        applications: list[dict[str, Any]],
        default_resume: dict[str, Any] | None,
    ) -> MailReconciliationDecision:
        if analysis.get("application_match", {}).get("application_id"):
            return self._review("邮件已关联现有申请，不自动补建申请。")
        if analysis.get("message_type") not in self.AUTO_MESSAGE_TYPES:
            return self._review("邮件类型不是明确的投递成功或申请已收到确认。")
        company = str(analysis.get("company") or "").strip()
        title = str(analysis.get("job_title") or "").strip()
        if not company or not title:
            return self._review("邮件中的公司或岗位不完整。")
        match = analysis.get("application_match") or {}
        if not match.get("create_record_recommended"):
            return self._review("Agent 未建议建立新的申请档案。")
        if float(match.get("confidence") or 0) < self.MIN_CONFIDENCE:
            return self._review("邮件与申请事实的匹配置信度不足。")

        matching_jobs = [
            job
            for job in jobs
            if job.get("status") == "active"
            and self._normalize(str(job.get("company") or "")) == self._normalize(company)
            and self._normalize(str(job.get("title") or "")) == self._normalize(title)
        ]
        if len(matching_jobs) != 1:
            return self._review("公司和岗位无法唯一匹配一个具体岗位。")
        job_post_id = str(matching_jobs[0]["id"])
        conflicting = [
            item
            for item in applications
            if item.get("job_post_id") == job_post_id
            and item.get("current_status") != "archived"
        ]
        if conflicting:
            return self._review("该岗位已有未归档申请，不能推断本次邮件使用的材料。")
        if default_resume is None or not default_resume.get("latest_finalized_version"):
            return self._review("没有可用于保守推断的默认定稿简历。")

        evidence_items = [
            item
            for item in analysis.get("items", [])
            if item.get("item_type") == "event"
            and item.get("category") in self.AUTO_EVENT_TYPES
            and float(item.get("confidence") or 0) >= self.MIN_CONFIDENCE
            and item.get("occurred_at")
            and str(item.get("evidence") or "").strip()
        ]
        if len(evidence_items) != 1:
            return self._review("投递时间或可引用证据不完整或存在歧义。")
        evidence_item = evidence_items[0]
        occurred_at = evidence_item["occurred_at"]
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        if occurred_at.tzinfo is None:
            return self._review("投递时间缺少明确时区。")
        return MailReconciliationDecision(
            action="auto_submit",
            reason=(
                "明确投递确认、唯一岗位、高置信度证据和默认定稿简历均已满足。"
            ),
            job_post_id=job_post_id,
            occurred_at=occurred_at.astimezone(UTC),
            evidence=str(evidence_item["evidence"]).strip(),
            item_categories=(str(evidence_item["category"]),),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.casefold())

    @staticmethod
    def _review(reason: str) -> MailReconciliationDecision:
        return MailReconciliationDecision(action="review", reason=reason)


class MailApplicationReconciliationService:
    def __init__(
        self,
        *,
        gateway: Any,
        applications: Any,
        job_posts: Any,
        tasks: Any | None,
        policy: MailApplicationReconciliationPolicy | None = None,
    ) -> None:
        self.gateway = gateway
        self.applications = applications
        self.job_posts = job_posts
        self.tasks = tasks
        self.policy = policy or MailApplicationReconciliationPolicy()

    def reconcile(
        self, *, message: dict[str, Any], analysis: dict[str, Any]
    ) -> dict[str, Any]:
        decision = self.policy.evaluate(
            analysis=analysis,
            jobs=self.job_posts.list_jobs(status="active"),
            applications=self.applications.list_applications(),
            default_resume=self.applications.get_default_resume(),
        )
        if decision.action != "auto_submit":
            return analysis

        self.gateway.link_analysis_job(
            analysis["id"], job_post_id=str(decision.job_post_id)
        )
        application = self.applications.create_application(
            job_post_id=str(decision.job_post_id)
        )
        application = self.applications.bind_resume(
            application["id"],
            expected_version=application["version"],
            command_id=f"mail-default-bind:{analysis['id']}",
            resume_version_id=None,
            use_default=True,
            source="mail_default",
            reason=decision.reason,
        )
        binding = application["active_resume_binding"]
        application = self.applications.submit_application(
            application["id"],
            expected_version=application["version"],
            resume_version_id=binding["resume_version_id"],
            occurred_at=decision.occurred_at,
            note=f"招聘邮件自动补录。{decision.reason}\n证据：{decision.evidence}",
            command_id=f"mail-auto-submit:{analysis['id']}",
            source="imap_policy",
        )
        self.gateway.complete_auto_reconciliation(
            analysis["id"],
            application_id=application["id"],
            job_post_id=str(decision.job_post_id),
            reason=decision.reason,
            item_categories=decision.item_categories,
        )
        if self.tasks is not None:
            self.tasks.create_task(
                title=f"已从招聘邮件补录投递：{application['company']} · {application['job_title']}",
                task_type="mail_application_backfill",
                due_at=datetime.now(UTC) + timedelta(days=1),
                timezone="Asia/Shanghai",
                notes=decision.reason,
                priority=20,
                application_id=application["id"],
                source_key=f"mail-auto-submit:{analysis['id']}",
            )
        return self.gateway.get_message(message["id"])["intelligence"]
