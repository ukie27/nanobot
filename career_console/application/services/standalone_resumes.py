"""Standalone resume Agent proposal orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from career_console.application.ports.material_agent import ResumeDrafter
from career_console.domain.common.errors import CareerDomainError
from career_console.domain.materials import FactSnapshot, MaterialBlock, review_material


class StandaloneResumeApplicationService:
    def __init__(self, gateway: Any, drafter: ResumeDrafter | None) -> None:
        self.gateway = gateway
        self.drafter = drafter

    def generate(self, *, name: str, prompt: str) -> dict[str, Any]:
        if self.drafter is None:
            raise CareerDomainError(
                "简历生成 Agent 未配置，请先在设置中配置简历生成模型。",
                code="standalone_resume_agent_unavailable",
            )
        context = self.gateway.context(name=name, prompt=prompt)
        input_hash = self._hash(context)
        existing = self.gateway.existing(input_hash)
        if existing is not None:
            return existing
        started_at = datetime.now(UTC)
        started = perf_counter()
        draft = None
        try:
            draft = self.drafter.draft(context=context)
            self._validate_draft(draft, context)
        except Exception as exc:
            code = exc.code if isinstance(exc, CareerDomainError) else "standalone_resume_agent_failed"
            self.gateway.save_failure(
                context=context,
                input_hash=input_hash,
                error_code=code,
                audit=self._audit(started_at, started),
            )
            if isinstance(exc, CareerDomainError):
                raise
            raise CareerDomainError("简历生成 Agent 执行失败。", code=code) from exc
        output = draft.model_dump(mode="json", by_alias=True)
        return self.gateway.save(
            context=context,
            draft=draft,
            input_hash=input_hash,
            output_hash=self._hash(output),
            audit=self._audit(started_at, started),
        )

    def list(self) -> dict[str, Any]:
        items = self.gateway.list()
        return {"items": items, "total": len(items)}

    def resolve(
        self,
        proposal_id: str,
        *,
        expected_version: int,
        resolution: str,
        reason: str,
    ) -> dict[str, Any]:
        return self.gateway.resolve(
            proposal_id,
            expected_version=expected_version,
            resolution=resolution,
            reason=reason,
        )

    @staticmethod
    def _validate_draft(draft: Any, context: dict[str, Any]) -> None:
        facts = {item["id"]: item for item in context["confirmedFacts"]}
        for block in draft.blocks:
            if not block.fact_ids or not set(block.fact_ids) <= set(facts):
                raise CareerDomainError(
                    "简历候选引用了不存在或未确认的职业事实。",
                    code="standalone_resume_fact_invalid",
                )
            if block.requirement_ids:
                raise CareerDomainError(
                    "通用简历候选不能引用岗位要求。",
                    code="standalone_resume_requirement_invalid",
                )
        snapshots = [
            FactSnapshot(item["id"], item["id"], item["version"], item["value"])
            for item in facts.values()
        ]
        blocks = [
            MaterialBlock(item.block_id, item.section, item.text, tuple(item.fact_ids))
            for item in draft.blocks
        ]
        findings = review_material(blocks, snapshots)
        if any(item.severity == "error" for item in findings):
            code = next(item.code for item in findings if item.severity == "error")
            raise CareerDomainError("简历候选包含无事实支持的陈述。", code=code)

    def _audit(self, started_at: datetime, started: float) -> dict[str, Any]:
        provider = getattr(self.drafter, "provider", None)
        usage = getattr(self.drafter, "last_usage", {}) or {}
        return {
            "implementation": getattr(
                self.drafter, "name", "standalone_resume_drafter"
            ),
            "provider": type(provider).__name__ if provider is not None else None,
            "model": getattr(self.drafter, "model", None),
            "prompt_version": getattr(self.drafter, "prompt_version", None),
            "skill_version": getattr(self.drafter, "skill_version", None),
            "created_at": started_at,
            "duration_ms": max(0, round((perf_counter() - started) * 1000)),
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "retry_count": int(getattr(self.drafter, "last_retry_count", 0)),
        }

    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()
