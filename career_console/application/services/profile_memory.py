"""Application orchestration for profile intelligence and durable impact processing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from career_console.application.ports.profile_insight import ProfileInsightAnalyzer
from career_console.domain.common.errors import CareerDomainError


class ProfileMemoryApplicationService:
    def __init__(self, gateway: Any, analyzer: ProfileInsightAnalyzer | None) -> None:
        self.gateway = gateway
        self.analyzer = analyzer

    def generate_insights(self) -> list[dict[str, Any]]:
        items, _reused = self._generate_insights()
        return items

    def run_due(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Run the complete daily profile-maintenance workflow in China Standard Time."""
        started = now or datetime.now(UTC)
        local = started.astimezone(ZoneInfo("Asia/Shanghai"))
        digest = self.gateway.generate_daily_digest(day=local.date().isoformat())
        counters = {
            "profile_jobs_processed": 1,
            "profile_digest_generated": 1,
            "profile_insights_created": 0,
            "profile_insights_reused": 0,
            "profile_insight_skipped": 0,
            "profile_insight_failed": 0,
            "profile_strategy_processed": 0,
        }
        insight_ids: list[str] = []
        insight_status = "created"
        try:
            insights, reused = self._generate_insights()
            insight_ids = [str(item["id"]) for item in insights]
            counters["profile_insights_reused" if reused else "profile_insights_created"] = (
                len(insights)
            )
            insight_status = "reused" if reused else "created"
        except CareerDomainError as exc:
            if exc.code == "profile_insight_unavailable":
                counters["profile_insight_skipped"] = 1
                insight_status = "skipped_unavailable"
            else:
                counters["profile_insight_failed"] = 1
                insight_status = "failed"
        except ValueError:
            counters["profile_insight_skipped"] = 1
            insight_status = "skipped_no_confirmed_facts"

        return {
            **counters,
            "digest_id": digest["id"],
            "insight_ids": insight_ids,
            "insight_status": insight_status,
            "strategy_id": None,
            "business_date": local.date().isoformat(),
            "business_timezone": "Asia/Shanghai",
        }

    def _generate_insights(self) -> tuple[list[dict[str, Any]], bool]:
        if self.analyzer is None:
            raise CareerDomainError(
                "档案洞察 Agent 未配置，请先配置模型提供方。",
                code="profile_insight_unavailable",
            )
        context = self.gateway.profile_insight_context()
        generation_policy = {
            "schema_version": getattr(
                self.analyzer, "schema_version", "profile_insight.v3"
            ),
            "prompt_version": getattr(
                self.analyzer, "prompt_version", "profile_insight.v5"
            ),
            "skill_version": getattr(self.analyzer, "skill_version", None),
        }
        encoded = json.dumps(
            {"context": context, "generation_policy": generation_policy},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        input_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        existing = self.gateway.existing_profile_insights(input_hash=input_hash)
        if existing is not None:
            return existing, True
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            result = self.analyzer.analyze(context=context)
            confirmed_ids = {item["id"] for item in context["confirmedFacts"]}
            improvement_ids = {
                item["id"] for item in context["confirmedInterviewImprovements"]
            }
            referenced_fact_ids = {
                fact_id
                for item in result.insights
                for fact_id in [*item.evidence_fact_ids, *item.counter_evidence_fact_ids]
            }
            referenced_improvement_ids = {
                improvement_id
                for item in result.insights
                for improvement_id in item.evidence_improvement_ids
            }
            if (
                not referenced_fact_ids <= confirmed_ids
                or not referenced_improvement_ids <= improvement_ids
            ):
                raise CareerDomainError(
                    "档案洞察引用了不存在或未确认的依据。",
                    code="profile_insight_evidence_invalid",
                )
        except Exception as exc:
            audit = self._audit(started_at, started)
            code = exc.code if isinstance(exc, CareerDomainError) else "profile_insight_failed"
            self.gateway.save_profile_insight_failure(
                input_hash=input_hash,
                input_revision=context["inputRevision"],
                error_code=code,
                audit=audit,
            )
            if isinstance(exc, CareerDomainError):
                raise
            raise CareerDomainError("档案洞察 Agent 执行失败。", code=code) from exc
        output = result.model_dump(mode="json", by_alias=True)
        output_hash = hashlib.sha256(
            json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return self.gateway.save_profile_insights(
            result=result,
            input_hash=input_hash,
            input_revision=context["inputRevision"],
            output_hash=output_hash,
            audit=self._audit(started_at, started),
        ), False

    def _audit(self, started_at: datetime, started: float) -> dict[str, Any]:
        provider = getattr(self.analyzer, "provider", None)
        usage = getattr(self.analyzer, "last_usage", {}) or {}
        return {
            "implementation": getattr(self.analyzer, "name", "profile_insight"),
            "provider": type(provider).__name__ if provider is not None else None,
            "model": getattr(self.analyzer, "model", None),
            "prompt_version": getattr(self.analyzer, "prompt_version", "profile_insight.v5"),
            "skill_version": getattr(self.analyzer, "skill_version", None),
            "created_at": started_at,
            "duration_ms": max(0, round((perf_counter() - started) * 1000)),
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "retry_count": int(getattr(self.analyzer, "last_retry_count", 0)),
        }


class ProfileImpactApplicationService:
    JOB_TYPES = {
        "job_fit": "profile.recompute.job_fit",
        "material_strategy": "profile.invalidate.material_strategy",
        "opportunity_filter": "profile.recompute.opportunity_filter",
        "career_strategy": "profile.recompute.career_strategy",
    }

    def __init__(self, gateway: Any, jobs: Any, job_gateway: Any) -> None:
        self.gateway = gateway
        self.jobs = jobs
        self.job_gateway = job_gateway
        self.worker_id = "career-profile-impact-worker"

    def enqueue_pending(self) -> int:
        count = 0
        for item in self.gateway.unscheduled_impacts():
            job_type = self.JOB_TYPES.get(item["scope"])
            if job_type is None:
                continue
            job_id = self.jobs.enqueue(
                job_type,
                {"change_event_id": item["change_event_id"], "scope": item["scope"]},
                idempotency_key=f"profile-impact:{item['change_event_id']}:{item['scope']}",
                priority=10,
            )
            self.gateway.ensure_impact_run(
                change_event_id=item["change_event_id"], scope=item["scope"],
                input_revision=item["input_revision"], background_job_id=job_id,
            )
            count += 1
        return count

    def process_next(self) -> bool:
        job = self.jobs.claim_next(
            self.worker_id, job_types=set(self.JOB_TYPES.values())
        )
        if job is None:
            return False
        event_id = str(job.payload.get("change_event_id") or "")
        scope = str(job.payload.get("scope") or "")
        try:
            self.gateway.start_impact(event_id, scope)
            if scope == "job_fit":
                affected = sum(
                    1 for job_id in self.gateway.active_job_ids()
                    if not self.job_gateway.analyze_job(job_id).get("reused", False)
                )
            elif scope == "material_strategy":
                affected = self.gateway.invalidate_material_strategy(event_id)
            else:
                # These scopes are durable projections reserved for their owning modules.
                affected = 0
            self.gateway.complete_impact(event_id, scope, affected_count=affected)
            self.jobs.complete(job.id, self.worker_id)
        except Exception:
            self.gateway.fail_impact(event_id, scope, error_code="profile_impact_failed")
            self.jobs.fail(job.id, self.worker_id, error_code="profile_impact_failed")
        return True
