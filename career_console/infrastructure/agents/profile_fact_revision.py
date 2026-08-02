"""Tool-free Task Agent adapter for revising one profile fact."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from threading import local
from typing import Any

from json_repair import loads as load_json
from pydantic import BaseModel, Field, ValidationError

from career_console.application.agent_tasks import CareerTaskRuntime, default_task_registry
from career_console.application.ports import ProfileFactRevision
from career_console.domain.common.errors import CareerDomainError
from career_console.domain.profile.entities import FactCategory
from career_console.domain.profile.privacy import contains_contact_information
from career_console.infrastructure.agents.fact_extractor import (
    _CANONICAL_PREFIXES,
    _validate_normalized_content,
)
from career_console.runtime.providers.base import LLMProvider


class UnavailableProfileFactReviser:
    name = "career_console_profile_fact_reviser"
    schema_version = "profile_fact_revision.v1"
    prompt_version = "profile_fact_revision.unavailable"
    skill_version = None

    def revise(self, **_: Any) -> ProfileFactRevision:
        raise CareerDomainError(
            "档案修改 Agent 尚未可用。请在“设置 > AI 服务”中配置事实提取或档案修改任务。",
            code="profile_fact_revision_unavailable",
        )


class _RevisionOutput(BaseModel):
    schema_version: str = Field(alias="schemaVersion")
    object_key: str = Field(min_length=1, max_length=100, alias="objectKey")
    content: str = Field(min_length=1, max_length=10_000)
    rationale: str = Field(min_length=1, max_length=500)


class CareerProfileFactReviser:
    name = "career_console_profile_fact_reviser"
    schema_version = "profile_fact_revision.v1"
    task_definition = default_task_registry.resolve("profile_fact_revision")
    skill_version = task_definition.skill_version
    prompt_version = f"{task_definition.skill_id}.{task_definition.skill_version}"

    def __init__(self, provider: LLMProvider, *, model: str | None = None) -> None:
        self.provider = provider
        self.model = model or provider.get_default_model()
        self.last_usage: dict[str, int] = {}
        self.last_retry_count = 0

    def revise(
        self,
        *,
        fact_id: str,
        category: str,
        field_key: str,
        current_value: str,
        instruction: str,
        evidence_texts: tuple[str, ...],
    ) -> ProfileFactRevision:
        return asyncio.run(self._revise(
            fact_id=fact_id,
            category=category,
            field_key=field_key,
            current_value=current_value,
            instruction=instruction,
            evidence_texts=evidence_texts,
        ))

    async def _revise(self, **source: Any) -> ProfileFactRevision:
        instruction = str(source["instruction"]).strip()
        if not instruction:
            raise CareerDomainError("修改指示不能为空。", code="profile_revision_instruction_empty")
        self.last_retry_count = 0
        assembly = CareerTaskRuntime().assemble(self.task_definition.task_type, source)
        if assembly.tools:
            raise CareerDomainError(
                "Profile revision task unexpectedly received tool permissions.",
                code="profile_revision_tool_policy_invalid",
            )
        category = FactCategory(source["category"])
        allowed_prefixes = "、".join(_CANONICAL_PREFIXES[category])
        system = assembly.skill + "\n\n" + (
            f"The selected category is '{category.value}'. The revised content must start "
            f"with exactly one of these canonical prefixes: {allowed_prefixes}. "
            "The current content may use a legacy shape; always migrate it to the canonical "
            "shape while preserving supported facts. Copy field_key into objectKey exactly."
        )
        response = await self._run_model(
            system=system,
            user=json.dumps(assembly.context, ensure_ascii=False),
        )
        self.last_usage = dict(response.usage)
        self._raise_provider_error(response)
        try:
            return self._validate_output(response=response, source=source, instruction=instruction)
        except CareerDomainError as first_error:
            if first_error.code not in {
                "profile_revision_schema_invalid",
                "fact_content_not_normalized",
                "fact_content_unsupported",
                "contact_information_not_allowed_in_fact",
            }:
                raise
            self.last_retry_count = 1
            repair_user = (
                "Repair the previous output and return the complete JSON object only.\n"
                f"Failure code: {first_error.code}\n"
                f"Copy objectKey exactly as: {source['field_key']}\n"
                f"The content must start with one of: {allowed_prefixes}\n"
                "Preserve supported facts and apply only the user's instruction. Do not add facts.\n"
                f"<context>\n{json.dumps(assembly.context, ensure_ascii=False)}\n</context>\n"
                f"<invalid-output>\n{response.content}\n</invalid-output>"
            )
            retry = await self._run_model(system=system, user=repair_user)
            self.last_usage = self._merge_usage(self.last_usage, retry.usage)
            self._raise_provider_error(retry)
            return self._validate_output(
                response=retry,
                source=source,
                instruction=instruction,
            )

    async def _run_model(self, *, system: str, user: str):
        return await self.provider.chat_with_retry(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            tools=None,
            model=self.model,
            max_tokens=self.task_definition.max_tokens,
            temperature=0.1,
            retry_mode="standard",
        )

    @staticmethod
    def _raise_provider_error(response: Any) -> None:
        if response.finish_reason == "error":
            raise CareerDomainError(
                "档案修改 Agent 调用失败，请检查 AI 服务后重试。",
                code=f"profile_revision_{response.error_code or 'failed'}",
            )
        if not response.content or response.tool_calls:
            raise CareerDomainError(
                "档案修改 Agent 未返回有效结果。",
                code="profile_revision_failed",
            )

    def _validate_output(
        self,
        *,
        response: Any,
        source: dict[str, Any],
        instruction: str,
    ) -> ProfileFactRevision:
        try:
            output = _RevisionOutput.model_validate(load_json(response.content))
        except (ValidationError, ValueError, TypeError) as exc:
            raise CareerDomainError(
                "档案修改结果未通过结构校验。",
                code="profile_revision_schema_invalid",
            ) from exc
        if output.schema_version != self.schema_version:
            raise CareerDomainError(
                "档案修改结果未通过结构校验。",
                code="profile_revision_schema_invalid",
            )
        # The application service owns the target fact identity. objectKey is only
        # an Agent echo and must never redirect or block the deterministic write.
        content = output.content.strip()
        if contains_contact_information(content):
            raise CareerDomainError(
                "Contact information cannot be stored as a career fact.",
                code="contact_information_not_allowed_in_fact",
            )
        supporting_texts = tuple(source["evidence_texts"]) + (instruction,)
        _validate_normalized_content(
            category=FactCategory(source["category"]),
            content=content,
            evidence_texts=supporting_texts,
        )
        if content == str(source["current_value"]).strip():
            raise CareerDomainError(
                "档案内容没有发生变化。",
                code="profile_revision_unchanged",
            )
        return ProfileFactRevision(value=content, rationale=output.rationale.strip())

    @staticmethod
    def _merge_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
        merged = dict(left)
        for key, value in right.items():
            merged[key] = merged.get(key, 0) + int(value or 0)
        return merged


class RuntimeConfiguredProfileFactReviser:
    name = CareerProfileFactReviser.name
    schema_version = CareerProfileFactReviser.schema_version
    prompt_version = CareerProfileFactReviser.prompt_version
    skill_version = CareerProfileFactReviser.skill_version

    def __init__(self, resolve: Callable[[], Any]) -> None:
        self._resolve = resolve
        self._state = local()

    @property
    def provider(self) -> LLMProvider | None:
        return getattr(self._state, "provider", None)

    @property
    def model(self) -> str | None:
        return getattr(self._state, "model", None)

    @property
    def last_usage(self) -> dict[str, int]:
        return getattr(self._state, "last_usage", {})

    @property
    def last_retry_count(self) -> int:
        return int(getattr(self._state, "last_retry_count", 0))

    def revise(self, **source: Any) -> ProfileFactRevision:
        self._state.provider = None
        self._state.model = None
        self._state.last_usage = {}
        self._state.last_retry_count = 0
        try:
            resolved = self._resolve()
        except (RuntimeError, ValueError):
            resolved = None
        if resolved is None:
            return UnavailableProfileFactReviser().revise(**source)
        reviser = CareerProfileFactReviser(resolved.provider, model=resolved.model)
        self._state.provider = resolved.provider
        self._state.model = resolved.model
        try:
            return reviser.revise(**source)
        finally:
            self._state.last_usage = dict(reviser.last_usage)
            self._state.last_retry_count = reviser.last_retry_count
