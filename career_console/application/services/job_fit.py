"""Semantic job-fit Agent orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from career_console.application.ports.job_fit import JobFitAnalyzer
from career_console.domain.common.errors import CareerDomainError


class JobFitApplicationService:
    def __init__(self, gateway: Any, analyzer: JobFitAnalyzer | None) -> None:
        self.gateway = gateway
        self.analyzer = analyzer

    def generate(self, job_id: str) -> dict[str, Any]:
        if self.analyzer is None:
            raise CareerDomainError(
                "岗位匹配 Agent 未配置，请先配置模型提供方。",
                code="job_fit_agent_unavailable",
            )
        context = self.gateway.context(job_id)
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
        input_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        existing = self.gateway.existing(job_id=job_id, input_hash=input_hash)
        if existing is not None:
            return existing
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            result = self.analyzer.analyze(context=context)
            self._validate_references(result, context)
        except Exception as exc:
            code = exc.code if isinstance(exc, CareerDomainError) else "job_fit_agent_failed"
            self.gateway.save_failure(
                job_id=job_id, input_hash=input_hash,
                input_revision=context["inputRevision"], error_code=code,
                audit=self._audit(started_at, started),
            )
            if isinstance(exc, CareerDomainError):
                raise
            raise CareerDomainError("岗位匹配 Agent 执行失败。", code=code) from exc
        output = result.model_dump(mode="json", by_alias=True)
        output_hash = hashlib.sha256(
            json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return self.gateway.save(
            job_id=job_id, result=result, input_hash=input_hash, output_hash=output_hash,
            context=context, audit=self._audit(started_at, started),
        )

    def list_for_job(self, job_id: str) -> list[dict[str, Any]]:
        return self.gateway.list_for_job(job_id)

    def resolve(self, proposal_id: str, *, expected_version: int, resolution: str,
                reason: str) -> dict[str, Any]:
        return self.gateway.resolve(
            proposal_id, expected_version=expected_version, resolution=resolution, reason=reason
        )

    def _validate_references(self, result: Any, context: dict[str, Any]) -> None:
        requirement_ids = {item["id"] for item in context["requirements"]}
        returned_ids = {item.requirement_id for item in result.assessments}
        if returned_ids != requirement_ids:
            raise CareerDomainError(
                "Agent 必须且只能分析当前岗位版本的全部要求。",
                code="job_fit_requirement_reference_invalid",
            )
        confirmed_ids = {item["id"] for item in context["confirmedFacts"]}
        fact_ids = {
            fact_id
            for item in result.assessments
            for fact_id in [*item.evidence_fact_ids, *item.transferable_fact_ids]
        }
        if not fact_ids <= confirmed_ids:
            raise CareerDomainError(
                "Agent 引用了不存在或未确认的 Fact ID。",
                code="job_fit_fact_reference_invalid",
            )

    def _audit(self, started_at: datetime, started: float) -> dict[str, Any]:
        provider = getattr(self.analyzer, "provider", None)
        usage = getattr(self.analyzer, "last_usage", {}) or {}
        return {
            "implementation": getattr(self.analyzer, "name", "job_fit_analysis"),
            "provider": type(provider).__name__ if provider is not None else None,
            "model": getattr(self.analyzer, "model", None),
            "prompt_version": getattr(self.analyzer, "prompt_version", "job_fit_analysis.v2"),
            "created_at": started_at,
            "duration_ms": max(0, round((perf_counter() - started) * 1000)),
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "retry_count": int(getattr(self.analyzer, "last_retry_count", 0)),
        }
