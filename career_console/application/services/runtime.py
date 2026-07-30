"""Unified review queue and AgentRun audit queries."""

from __future__ import annotations

from typing import Any

from career_console.application.ports.runtime_gateway import RuntimeGateway
from career_console.application.services.mail import MailApplicationService
from career_console.application.services.profile import ProfileApplicationService


class RuntimeApplicationService:
    def __init__(
        self,
        gateway: RuntimeGateway,
        *,
        profile: ProfileApplicationService | None = None,
        mail: MailApplicationService | None = None,
    ) -> None:
        self.gateway = gateway
        self.profile = profile
        self.mail = mail

    def reviews(self, *, status: str | None = "open") -> dict[str, Any]:
        items = self.gateway.list_reviews(status=status)
        return {"items": items, "total": len(items)}

    def review(self, review_id: str) -> dict[str, Any]:
        return self.gateway.get_review(review_id)

    def resolve_review_bundle(
        self,
        review_id: str,
        *,
        expected_version: int,
        resolution: str,
        reason: str,
    ) -> dict[str, Any]:
        bundle = self.gateway.get_review(review_id)
        if bundle["entity_type"] != "review_bundle":
            raise ValueError("该对象不是可整组处理的确认批次。")
        if bundle["version"] != expected_version:
            raise ValueError("确认批次已变化，请刷新后重试。")
        if bundle["status"] != "open":
            return bundle
        if resolution not in {"confirmed", "rejected"}:
            raise ValueError("不支持的整组处理结果。")
        open_items = [item for item in bundle["items"] if item["status"] == "open"]
        if bundle["bundle_type"] == "profile_section":
            if self.profile is None:
                raise RuntimeError("职业档案服务不可用。")
            if resolution == "confirmed":
                facts = {
                    item["id"]: item
                    for item in self.profile.gateway.list_facts(status=None)
                }
                selected = [
                    (item["entity_id"], facts[item["entity_id"]]["version"])
                    for item in open_items
                    if item["entity_id"] in facts
                ]
                self.profile.gateway.batch_confirm(items=selected)
            else:
                facts = {
                    item["id"]: item
                    for item in self.profile.gateway.list_facts(status=None)
                }
                for item in open_items:
                    fact = facts.get(item["entity_id"])
                    if fact is not None:
                        self.profile.gateway.change_fact(
                            fact_id=fact["id"],
                            expected_version=fact["version"],
                            action="reject",
                            reason=reason or "用户拒绝整组档案信息",
                        )
        elif bundle["bundle_type"] == "mail_analysis":
            if self.mail is None:
                raise RuntimeError("邮件服务不可用。")
            if resolution == "confirmed" and any(
                item.get("entity_subtype") == "create_application" for item in open_items
            ):
                raise ValueError("该邮件建议建立或关联申请，请先在邮件详情中完成关联。")
            for item in open_items:
                self.mail.resolve_intelligence_item(
                    item_id=item["entity_id"],
                    expected_version=item["version"],
                    resolution=resolution,
                    reason=reason or f"用户整组{resolution}",
                )
        else:
            raise ValueError("该确认批次暂不支持整组处理。")
        return self.gateway.get_review(review_id)

    def agent_runs(self, *, limit: int = 100) -> dict[str, Any]:
        items = self.gateway.list_agent_runs(limit=limit)
        return {"items": items, "total": len(items)}

    def agent_run(self, run_id: str) -> dict[str, Any]:
        return self.gateway.get_agent_run(run_id)
