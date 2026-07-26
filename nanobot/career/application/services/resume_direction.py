"""Resume Direction Planner orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from nanobot.career.application.ports.resume_direction import ResumeDirectionAnalyzer
from nanobot.career.domain.common.errors import CareerDomainError


class ResumeDirectionApplicationService:
    def __init__(self, gateway: Any, analyzer: ResumeDirectionAnalyzer | None) -> None:
        self.gateway = gateway
        self.analyzer = analyzer

    def generate(self, job_id: str) -> dict[str, Any]:
        if self.analyzer is None:
            raise CareerDomainError(
                "简历方向 Agent 未配置，请先配置模型提供方。",
                code="resume_direction_unavailable",
            )
        context = self.gateway.context(job_id)
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
        input_hash = hashlib.sha256(encoded.encode()).hexdigest()
        existing = self.gateway.existing(job_id, input_hash)
        if existing is not None:
            return existing
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            result = self.analyzer.analyze(context=context)
            self._validate(result, context)
        except Exception as exc:
            code = exc.code if isinstance(exc, CareerDomainError) else "resume_direction_agent_failed"
            self.gateway.save_failure(
                job_id=job_id, input_hash=input_hash,
                input_revision=context["inputRevision"], error_code=code,
                audit=self._audit(started_at, started),
            )
            if isinstance(exc, CareerDomainError):
                raise
            raise CareerDomainError("简历方向 Agent 执行失败。", code=code) from exc
        output = result.model_dump(mode="json", by_alias=True)
        output_hash = hashlib.sha256(
            json.dumps(output, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        return self.gateway.save(
            job_id=job_id, result=result, context=context, input_hash=input_hash,
            output_hash=output_hash, audit=self._audit(started_at, started),
        )

    def list_for_job(self, job_id: str) -> dict[str, Any]:
        return self.gateway.list_for_job(job_id)

    def resolve(self, proposal_id: str, *, expected_version: int, resolution: str,
                selected_direction_ids: list[str], reason: str) -> dict[str, Any]:
        return self.gateway.resolve(
            proposal_id, expected_version=expected_version, resolution=resolution,
            selected_direction_ids=selected_direction_ids, reason=reason,
        )

    @staticmethod
    def _validate(result: Any, context: dict[str, Any]) -> None:
        requirement_ids = {item["id"] for item in context["requirements"]}
        fact_ids = {item["id"] for item in context["confirmedFacts"]}
        names = {item.name.strip().casefold() for item in result.directions}
        narratives = {item.narrative.strip().casefold() for item in result.directions}
        if len(names) != len(result.directions) or len(narratives) != len(result.directions):
            raise CareerDomainError(
                "简历方向必须具有真实不同的名称和核心叙事。",
                code="resume_direction_not_distinct",
            )
        for item in result.directions:
            if not set(item.focus_requirement_ids) <= requirement_ids:
                raise CareerDomainError(
                    "简历方向引用了未知 Requirement ID。",
                    code="resume_direction_requirement_invalid",
                )
            if not set([*item.emphasize_fact_ids, *item.de_emphasize_fact_ids]) <= fact_ids:
                raise CareerDomainError(
                    "简历方向引用了不存在或未确认的 Fact ID。",
                    code="resume_direction_fact_invalid",
                )

    def _audit(self, started_at: datetime, started: float) -> dict[str, Any]:
        provider = getattr(self.analyzer, "provider", None)
        usage = getattr(self.analyzer, "last_usage", {}) or {}
        return {
            "implementation": getattr(self.analyzer, "name", "resume_direction"),
            "provider": type(provider).__name__ if provider is not None else None,
            "model": getattr(self.analyzer, "model", None),
            "prompt_version": getattr(self.analyzer, "prompt_version", "resume_direction.v1"),
            "created_at": started_at,
            "duration_ms": max(0, round((perf_counter() - started) * 1000)),
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "retry_count": int(getattr(self.analyzer, "last_retry_count", 0)),
        }
