"""Constrained Career Task Agent for structured profile insights."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from json_repair import loads as load_json
from pydantic import ValidationError

from nanobot.agent.runner import AgentRunner, AgentRunSpec
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.career.domain.common.errors import CareerDomainError
from nanobot.career.domain.profile import ProfileInsightResult
from nanobot.providers.base import LLMProvider


class NanobotProfileInsightAnalyzer:
    """Use the shared Agent core without tools, chat memory, skills, or workspace context."""

    name = "nanobot_profile_insight"
    schema_version = "profile_insight.v1"
    prompt_version = "profile_insight.v1"

    def __init__(self, provider: LLMProvider, *, model: str | None = None) -> None:
        self.provider = provider
        self.model = model or provider.get_default_model()
        self.runner = AgentRunner(provider)
        self.last_usage: dict[str, int] = {}
        self.last_retry_count = 0

    def analyze(self, *, context: dict) -> ProfileInsightResult:
        return asyncio.run(self._analyze(context=context))

    async def _analyze(self, *, context: dict) -> ProfileInsightResult:
        system = (
            "You produce reviewable career-profile insight proposals from trusted structured data. "
            "You have no tools and may not perform actions. Return JSON only with "
            "schemaVersion=profile_insight.v1 and insights[]. Each insightType is one of strength, "
            "gap, stable_preference, outcome_pattern, growth_direction. Every conclusion must cite "
            "at least one exact ID from confirmedFacts in evidenceFactIds. counterEvidenceFactIds "
            "may only cite those same confirmed facts. Preferences and aggregates may guide reasoning "
            "but are not factual evidence IDs. Be conservative and do not invent facts."
        )
        result = await self.runner.run(AgentRunSpec(
            initial_messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            tools=ToolRegistry(), model=self.model, max_iterations=1,
            max_tool_result_chars=1_000, max_tokens=4_096, temperature=0.1,
            workspace=Path.cwd(), session_key="career:profile-insight",
            provider_retry_mode="standard",
        ))
        self.last_usage = dict(result.usage)
        if result.error or not result.final_content or result.tools_used:
            raise CareerDomainError(
                "Profile insight Agent did not return a valid tool-free response.",
                code="profile_insight_failed",
            )
        try:
            output = ProfileInsightResult.model_validate(load_json(result.final_content))
        except (ValidationError, ValueError, TypeError) as exc:
            raise CareerDomainError(
                "Profile insight output failed schema validation.",
                code="profile_insight_schema_invalid",
            ) from exc
        confirmed_ids = {item["id"] for item in context["confirmedFacts"]}
        referenced = {
            fact_id
            for insight in output.insights
            for fact_id in [*insight.evidence_fact_ids, *insight.counter_evidence_fact_ids]
        }
        if not referenced <= confirmed_ids:
            raise CareerDomainError(
                "Profile insight referenced an unknown or unconfirmed Fact ID.",
                code="profile_insight_evidence_invalid",
            )
        return output
