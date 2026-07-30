"""Automatic recommendation orchestration for one concrete job."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from career_console.application.ports.job_recommendation import JobRecommendationAnalyzer
from career_console.domain.common.errors import CareerDomainError


class JobRecommendationApplicationService:
    def __init__(self, gateway: Any, analyzer: JobRecommendationAnalyzer | None) -> None:
        self.gateway = gateway
        self.analyzer = analyzer

    def analyze(
        self,
        job_id: str,
        *,
        opportunity_id: str | None = None,
        manual_directions: list[str] | None = None,
    ) -> dict[str, Any] | None:
        if self.analyzer is None:
            raise CareerDomainError(
                "每日岗位推荐 Agent 未配置，请先配置模型提供方。",
                code="daily_job_recommendation_agent_unavailable",
            )
        context = self.gateway.context(job_id, manual_directions=manual_directions)
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
        input_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        existing = self.gateway.existing(job_id=job_id, input_hash=input_hash)
        if existing is not None:
            return existing if existing["status"] == "active" else None
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            result = self.analyzer.analyze(context=context)
            self._validate_references(result, context)
        except Exception as exc:
            code = (
                exc.code
                if isinstance(exc, CareerDomainError)
                else "daily_job_recommendation_agent_failed"
            )
            self.gateway.save_failure(
                job_id=job_id,
                input_hash=input_hash,
                input_revision=context["inputRevision"],
                error_code=code,
                audit=self._audit(started_at, started),
            )
            if isinstance(exc, CareerDomainError):
                raise
            raise CareerDomainError("每日岗位推荐 Agent 执行失败。", code=code) from exc
        output = result.model_dump(mode="json", by_alias=True)
        output_hash = hashlib.sha256(
            json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return self.gateway.save(
            job_id=job_id,
            opportunity_id=opportunity_id,
            result=result,
            input_hash=input_hash,
            output_hash=output_hash,
            context=context,
            audit=self._audit(started_at, started),
        )

    def list(self, *, status: str = "active") -> dict[str, Any]:
        return self.gateway.list(status=status)

    def get(self, recommendation_id: str) -> dict[str, Any]:
        return self.gateway.get(recommendation_id)

    def dismiss(self, recommendation_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.dismiss(recommendation_id, **kwargs)

    def accept(self, recommendation_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.gateway.accept(recommendation_id, **kwargs)

    @staticmethod
    def _validate_references(result: Any, context: dict[str, Any]) -> None:
        requirement_ids = {item["id"] for item in context["requirements"]}
        returned_ids = {item.requirement_id for item in result.assessments}
        if returned_ids != requirement_ids:
            raise CareerDomainError(
                "Agent 必须且只能分析当前岗位版本的全部要求。",
                code="daily_job_recommendation_requirement_reference_invalid",
            )
        confirmed_ids = {item["id"] for item in context["confirmedFacts"]}
        referenced = {
            fact_id
            for item in result.assessments
            for fact_id in [*item.evidence_fact_ids, *item.transferable_fact_ids]
        }
        if not referenced <= confirmed_ids:
            raise CareerDomainError(
                "Agent 引用了不存在或未确认的 Fact ID。",
                code="daily_job_recommendation_fact_reference_invalid",
            )
        hard_categories = {"education", "experience", "language", "location", "work_mode"}
        category_by_id = {item["id"]: item["category"] for item in context["requirements"]}
        for assessment in result.assessments:
            if (
                category_by_id[assessment.requirement_id] in hard_categories
                and assessment.decision == "matched"
                and not assessment.evidence_fact_ids
            ):
                raise CareerDomainError(
                    "硬性门槛必须由直接可信事实支持。",
                    code="daily_job_recommendation_hard_gate_invalid",
                )

    def _audit(self, started_at: datetime, started: float) -> dict[str, Any]:
        provider = getattr(self.analyzer, "provider", None)
        usage = getattr(self.analyzer, "last_usage", {}) or {}
        return {
            "implementation": getattr(
                self.analyzer, "name", "daily_job_recommendation"
            ),
            "provider": type(provider).__name__ if provider is not None else None,
            "model": getattr(self.analyzer, "model", None),
            "prompt_version": getattr(
                self.analyzer, "prompt_version", "daily_job_recommendation.v1"
            ),
            "skill_version": getattr(self.analyzer, "skill_version", None),
            "created_at": started_at,
            "duration_ms": max(0, round((perf_counter() - started) * 1000)),
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "retry_count": int(getattr(self.analyzer, "last_retry_count", 0)),
        }
