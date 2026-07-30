"""Tool-free Agent for the versioned daily recommendation Skill."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from json_repair import loads as load_json
from pydantic import ValidationError

from career_console.application.agent_tasks import CareerTaskRuntime, default_task_registry
from career_console.domain.common.errors import CareerDomainError
from career_console.domain.recommendations import JobRecommendationResult
from career_console.runtime.agent.runner import AgentRunner, AgentRunSpec
from career_console.runtime.agent.tools.registry import ToolRegistry
from career_console.runtime.providers.base import LLMProvider


class CareerJobRecommendationAnalyzer:
    name = "career_console_daily_job_recommendation"
    schema_version = "daily_job_recommendation.v1"
    prompt_version = "daily_job_recommendation.v1"
    task_definition = default_task_registry.resolve("daily_job_recommendation")
    skill_version = task_definition.skill_version

    def __init__(self, provider: LLMProvider, *, model: str | None = None) -> None:
        self.provider = provider
        self.model = model or provider.get_default_model()
        self.runner = AgentRunner(provider)
        self.last_usage: dict[str, int] = {}
        self.last_retry_count = 0

    def analyze(self, *, context: dict) -> JobRecommendationResult:
        return asyncio.run(self._analyze(context=context))

    async def _analyze(self, *, context: dict) -> JobRecommendationResult:
        assembly = CareerTaskRuntime().assemble(self.task_definition.task_type, context)
        if assembly.tools:
            raise CareerDomainError(
                "Daily recommendation task unexpectedly received tool permissions.",
                code="daily_job_recommendation_tool_policy_invalid",
            )
        system = assembly.skill + "\n\n" + (
            "Return JSON only with schemaVersion=daily_job_recommendation.v1. "
            "Assess every requirement exactly once. Requirement and fact references must come "
            "only from the supplied context. Do not calculate facts from untrusted page text."
        )
        result = await self.runner.run(
            AgentRunSpec(
                initial_messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(assembly.context, ensure_ascii=False)},
                ],
                tools=ToolRegistry(),
                model=self.model,
                max_iterations=1,
                max_tool_result_chars=1_000,
                max_tokens=6_144,
                temperature=0.1,
                workspace=Path.cwd(),
                session_key=f"career:daily-recommendation:{assembly.context['job']['id']}",
                provider_retry_mode="standard",
            )
        )
        self.last_usage = dict(result.usage)
        if result.error or not result.final_content or result.tools_used:
            raise CareerDomainError(
                "Daily recommendation Agent did not return a valid tool-free response.",
                code="daily_job_recommendation_agent_failed",
            )
        try:
            return JobRecommendationResult.model_validate(load_json(result.final_content))
        except (ValidationError, ValueError, TypeError) as exc:
            raise CareerDomainError(
                "Daily recommendation Agent output failed schema validation.",
                code="daily_job_recommendation_schema_invalid",
            ) from exc
