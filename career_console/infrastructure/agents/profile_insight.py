"""Constrained Career Task Agent for structured profile insights."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from json_repair import loads as load_json
from pydantic import ValidationError

from career_console.application.agent_tasks import CareerTaskRuntime, default_task_registry
from career_console.domain.common.errors import CareerDomainError
from career_console.domain.profile import ProfileInsightResult
from career_console.runtime.agent.runner import AgentRunner, AgentRunResult, AgentRunSpec
from career_console.runtime.agent.tools.registry import ToolRegistry
from career_console.runtime.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class CareerProfileInsightAnalyzer:
    """Use the shared Agent core without tools, chat memory, skills, or workspace context."""

    name = "career_console_profile_insight"
    schema_version = "profile_insight.v3"
    prompt_version = "profile_insight.v5"
    task_definition = default_task_registry.resolve("profile_insight")
    skill_version = task_definition.skill_version

    def __init__(self, provider: LLMProvider, *, model: str | None = None) -> None:
        self.provider = provider
        self.model = model or provider.get_default_model()
        self.runner = AgentRunner(provider)
        self.last_usage: dict[str, int] = {}
        self.last_retry_count = 0

    def analyze(self, *, context: dict) -> ProfileInsightResult:
        return asyncio.run(self._analyze(context=context))

    async def _analyze(self, *, context: dict) -> ProfileInsightResult:
        self.last_retry_count = 0
        assembly = CareerTaskRuntime().assemble(self.task_definition.task_type, context)
        if assembly.tools:
            raise CareerDomainError(
                "Profile insight task unexpectedly received tool permissions.",
                code="profile_insight_tool_policy_invalid",
            )
        system = assembly.skill + "\n\n" + (
            "You produce automatically published career diagnostic guidance from trusted "
            "structured data. The result is advisory content for direct user display, not a career "
            "fact, application event, interview feedback record, or formal business-state change. "
            "Never ask the user to confirm, approve, adopt, or reject an insight. "
            "You have no tools and may not perform actions. Return one JSON object only, without "
            "markdown fences or commentary. Use exactly this contract and field casing: "
            '{"schemaVersion":"profile_insight.v3","insights":[{"category":"interview",'
            '"analysis":"...","recommendation":"...",'
            '"evidenceFactIds":["exact-confirmed-fact-id"],'
            '"evidenceImprovementIds":["exact-confirmed-improvement-id"],'
            '"counterEvidenceFactIds":[],"confidence":0.8}]}. '
            "Do not add fields. insights must contain 1 to 20 items. category is exactly one of "
            "interview, application, resume, learning, career_direction. confidence must "
            "be a number from 0 to 1. Every insight must include one concrete recommendation and "
            "cite at least one exact ID copied from confirmedFacts into evidenceFactIds or from "
            "confirmedInterviewImprovements into evidenceImprovementIds. counterEvidenceFactIds may "
            "only contain exact confirmed fact IDs. Prioritize repeated weaknesses, actionable gaps, "
            "and the next useful behavior change. Preferences and aggregates may guide "
            "reasoning but are not evidence IDs. For each category, focus on its relevant trusted "
            "inputs. Do not output strengths as a separate concept. Be conservative and do not "
            "invent facts. Write every analysis and recommendation in concise Simplified Chinese. "
            "Technical names may remain in English where appropriate, but English-dominant output "
            "is invalid."
        )
        payload = assembly.context
        result = await self._run_model(
            system=system,
            payload=payload,
            session_key="career:profile-insight",
        )
        self.last_usage = dict(result.usage)
        if result.error or not result.final_content or result.tools_used:
            raise CareerDomainError(
                "Profile insight Agent did not return a valid tool-free response.",
                code="profile_insight_failed",
            )
        confirmed_ids = {item["id"] for item in assembly.context["confirmedFacts"]}
        improvement_ids = {
            item["id"] for item in assembly.context["confirmedInterviewImprovements"]
        }
        try:
            return self._validate_output(
                result.final_content,
                confirmed_ids=confirmed_ids,
                improvement_ids=improvement_ids,
            )
        except CareerDomainError as first_error:
            self.last_retry_count = 1
            repair_payload = {
                "originalInput": payload,
                "invalidOutput": result.final_content,
                "failureCode": first_error.code,
                "repairRules": [
                    "Return only one JSON object using the exact contract from the system message.",
                    "Do not add fields and do not omit required fields.",
                    "Use confidence numbers from 0 to 1.",
                    "Copy evidence IDs exactly from originalInput.confirmedFacts[].id.",
                    "Copy improvement IDs exactly from originalInput.confirmedInterviewImprovements[].id.",
                    "Never use preference or aggregate values as evidence IDs.",
                    "Rewrite every analysis and recommendation in concise Simplified Chinese.",
                    "Keep technical names in English only where appropriate; do not return English-dominant prose.",
                ],
            }
            retry = await self._run_model(
                system=system,
                payload=repair_payload,
                session_key="career:profile-insight:schema-repair",
            )
            self.last_usage = self._merge_usage(self.last_usage, retry.usage)
            if retry.error or not retry.final_content or retry.tools_used:
                raise first_error
            return self._validate_output(
                retry.final_content,
                confirmed_ids=confirmed_ids,
                improvement_ids=improvement_ids,
            )

    async def _run_model(
        self, *, system: str, payload: dict[str, Any], session_key: str
    ) -> AgentRunResult:
        return await self.runner.run(AgentRunSpec(
            initial_messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            tools=ToolRegistry(), model=self.model,
            max_iterations=self.task_definition.max_iterations,
            max_tool_result_chars=1_000, max_tokens=self.task_definition.max_tokens,
            temperature=0.1,
            workspace=Path.cwd(), session_key=session_key,
            provider_retry_mode="standard",
        ))

    @staticmethod
    def _validate_output(
        content: str, *, confirmed_ids: set[str], improvement_ids: set[str]
    ) -> ProfileInsightResult:
        try:
            output = ProfileInsightResult.model_validate(load_json(content))
        except ValidationError as exc:
            logger.warning(
                "Profile insight schema validation failed: %s",
                [
                    {
                        "location": ".".join(str(part) for part in error["loc"]),
                        "type": error["type"],
                    }
                    for error in exc.errors(include_input=False, include_url=False)
                ],
            )
            raise CareerDomainError(
                "Profile insight output failed schema validation.",
                code="profile_insight_schema_invalid",
            ) from exc
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Profile insight JSON parsing failed: %s",
                type(exc).__name__,
            )
            raise CareerDomainError(
                "Profile insight output failed schema validation.",
                code="profile_insight_schema_invalid",
            ) from exc
        referenced_facts = {
            fact_id
            for insight in output.insights
            for fact_id in [*insight.evidence_fact_ids, *insight.counter_evidence_fact_ids]
        }
        referenced_improvements = {
            improvement_id
            for insight in output.insights
            for improvement_id in insight.evidence_improvement_ids
        }
        if not referenced_facts <= confirmed_ids or not referenced_improvements <= improvement_ids:
            raise CareerDomainError(
                "Profile insight referenced unknown or unconfirmed evidence.",
                code="profile_insight_evidence_invalid",
            )
        if any(
            not CareerProfileInsightAnalyzer._is_chinese_dominant(text)
            for insight in output.insights
            for text in (insight.analysis, insight.recommendation)
        ):
            raise CareerDomainError(
                "Profile insight analysis and recommendation must use Simplified Chinese.",
                code="profile_insight_language_invalid",
            )
        return output

    @staticmethod
    def _is_chinese_dominant(value: str) -> bool:
        cjk_count = sum("\u4e00" <= char <= "\u9fff" for char in value)
        ascii_letter_count = sum(
            ("a" <= char <= "z") or ("A" <= char <= "Z")
            for char in value
        )
        language_character_count = cjk_count + ascii_letter_count
        return (
            cjk_count >= 12
            and language_character_count > 0
            and cjk_count / language_character_count >= 0.30
        )

    @staticmethod
    def _merge_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
        merged = dict(left)
        for key, value in right.items():
            merged[key] = merged.get(key, 0) + int(value or 0)
        return merged
