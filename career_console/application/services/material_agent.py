"""Drafter–Reviewer orchestration with strict reference validation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from career_console.application.ports.material_agent import MaterialReviewer, ResumeDrafter
from career_console.domain.common.errors import CareerDomainError
from career_console.domain.materials import FactSnapshot, MaterialBlock, review_material


class MaterialAgentApplicationService:
    def __init__(self, gateway: Any, drafter: ResumeDrafter | None,
                 reviewer: MaterialReviewer | None) -> None:
        self.gateway = gateway
        self.drafter = drafter
        self.reviewer = reviewer

    def generate(self, job_id: str, *, resume_id: str | None, resume_name: str) -> dict[str, Any]:
        if self.drafter is None or self.reviewer is None:
            raise CareerDomainError("材料 Drafter/Reviewer 未配置，请先配置模型提供方。",
                                    code="material_agent_unavailable")
        context = self.gateway.context(job_id, resume_id=resume_id, resume_name=resume_name)
        input_hash = self._hash(context)
        existing = self.gateway.existing(job_id, input_hash)
        if existing is not None:
            return existing
        draft_started_at = datetime.now(UTC)
        draft_started = perf_counter()
        draft = None
        try:
            draft = self.drafter.draft(context=context)
            self._validate_draft(draft, context)
        except Exception as exc:
            code = exc.code if isinstance(exc, CareerDomainError) else "resume_draft_agent_failed"
            self.gateway.save_failure(context=context, input_hash=input_hash, stage="draft",
                                      error_code=code, draft=None,
                                      draft_audit=self._audit(self.drafter, draft_started_at, draft_started),
                                      review_audit=None)
            if isinstance(exc, CareerDomainError):
                raise
            raise CareerDomainError("Drafter 执行失败。", code=code) from exc
        draft_audit = self._audit(self.drafter, draft_started_at, draft_started)
        draft_output = draft.model_dump(mode="json", by_alias=True)
        reviewer_context = {
            "schemaVersion": "material_review_context.v2", "businessTimezone": "Asia/Shanghai",
            "job": context["job"], "requirements": context["requirements"],
            "confirmedFacts": context["confirmedFacts"], "draft": draft_output,
        }
        review_started_at = datetime.now(UTC)
        review_started = perf_counter()
        try:
            review = self.reviewer.review(context=reviewer_context)
            block_ids = {item.block_id for item in draft.blocks}
            if any(item.block_id is not None and item.block_id not in block_ids
                   for item in review.findings):
                raise CareerDomainError("Reviewer 引用了未知 blockId。",
                                        code="material_review_block_invalid")
        except Exception as exc:
            code = exc.code if isinstance(exc, CareerDomainError) else "material_review_agent_failed"
            self.gateway.save_failure(
                context=context, input_hash=input_hash, stage="review", error_code=code,
                draft=draft, draft_audit=draft_audit,
                review_audit=self._audit(self.reviewer, review_started_at, review_started),
            )
            if isinstance(exc, CareerDomainError):
                raise
            raise CareerDomainError("Reviewer 执行失败。", code=code) from exc
        output_hash = self._hash(draft_output)
        return self.gateway.save(
            context=context, draft=draft, review=review, input_hash=input_hash,
            output_hash=output_hash, draft_audit=draft_audit,
            review_audit=self._audit(self.reviewer, review_started_at, review_started),
        )

    def list_for_job(self, job_id: str) -> dict[str, Any]:
        items = self.gateway.list_for_job(job_id)
        return {"items": items, "total": len(items)}

    def resolve(self, proposal_id: str, *, expected_version: int,
                resolution: str, reason: str) -> dict[str, Any]:
        return self.gateway.resolve(proposal_id, expected_version=expected_version,
                                    resolution=resolution, reason=reason)

    @staticmethod
    def _validate_draft(draft: Any, context: dict[str, Any]) -> None:
        facts = {item["id"]: item for item in context["confirmedFacts"]}
        requirement_ids = {item["id"] for item in context["requirements"]}
        for block in draft.blocks:
            if not set(block.fact_ids) <= set(facts):
                raise CareerDomainError("草稿引用了不存在或未确认的 Fact ID。",
                                        code="resume_draft_fact_invalid")
            if not set(block.requirement_ids) <= requirement_ids:
                raise CareerDomainError("草稿引用了未知 Requirement ID。",
                                        code="resume_draft_requirement_invalid")
        snapshots = [FactSnapshot(fid, fid, item["version"], item["value"])
                     for fid, item in facts.items()]
        blocks = [MaterialBlock(item.block_id, item.section, item.text, tuple(item.fact_ids))
                  for item in draft.blocks]
        findings = review_material(blocks, snapshots)
        if any(item.severity == "error" for item in findings):
            code = next(item.code for item in findings if item.severity == "error")
            raise CareerDomainError("草稿包含无事实支持的陈述。", code=code)

    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                         default=str).encode()).hexdigest()

    @staticmethod
    def _audit(agent: Any, started_at: datetime, started: float) -> dict[str, Any]:
        provider = getattr(agent, "provider", None)
        usage = getattr(agent, "last_usage", {}) or {}
        return {"implementation": getattr(agent, "name", "material_agent"),
                "provider": type(provider).__name__ if provider is not None else None,
                "model": getattr(agent, "model", None),
                "prompt_version": getattr(agent, "prompt_version", None),
                "created_at": started_at,
                "duration_ms": max(0, round((perf_counter() - started) * 1000)),
                "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
                "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
                "retry_count": int(getattr(agent, "last_retry_count", 0))}
