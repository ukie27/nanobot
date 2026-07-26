"""Build Career task providers from workspace config and secret references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from career_console.infrastructure.configuration.schema import (
    AgentTaskConfiguration,
    ProviderConfiguration,
)
from career_console.runtime.providers.base import GenerationSettings, LLMProvider
from career_console.runtime.providers.registry import find_by_name


class ProviderConfigurationError(ValueError):
    pass


class CareerProviderFactory:
    def __init__(self, secrets: Any) -> None:
        self.secrets = secrets

    def build(
        self,
        provider_config: ProviderConfiguration,
        task: AgentTaskConfiguration,
    ) -> LLMProvider:
        spec = find_by_name(provider_config.provider_type)
        if spec is None:
            raise ProviderConfigurationError("不支持该 Provider 类型。")
        api_key: str | None = None
        if provider_config.secret_ref:
            try:
                api_key = self.secrets.get(provider_config.secret_ref)
            except LookupError as exc:
                raise ProviderConfigurationError("Provider API Key 尚未配置。") from exc
        if not api_key and not (spec.is_local or spec.is_oauth or spec.is_direct):
            raise ProviderConfigurationError("Provider API Key 尚未配置。")
        api_base = provider_config.api_base or spec.default_api_base or None
        model = task.model or provider_config.default_model
        if spec.backend == "azure_openai":
            if not api_key or not api_base:
                raise ProviderConfigurationError("Azure OpenAI 需要 API Key 和 API URL。")
            from career_console.runtime.providers.azure_openai_provider import AzureOpenAIProvider

            provider: LLMProvider = AzureOpenAIProvider(
                api_key=api_key, api_base=api_base, default_model=model
            )
        elif spec.backend == "anthropic":
            from career_console.runtime.providers.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(
                api_key=api_key, api_base=api_base, default_model=model
            )
        else:
            from career_console.runtime.providers.openai_compat_provider import OpenAICompatProvider

            provider = OpenAICompatProvider(
                api_key=api_key,
                api_base=api_base,
                default_model=model,
                spec=spec,
            )
        provider.generation = GenerationSettings(
            temperature=task.temperature,
            max_tokens=task.max_tokens,
            reasoning_effort=task.reasoning_effort,
        )
        return provider


@dataclass(frozen=True, slots=True)
class ResolvedAgentTask:
    provider: LLMProvider
    model: str
    configuration: AgentTaskConfiguration


class CareerAgentRuntime:
    def __init__(self, configuration_service: Any, secrets: Any) -> None:
        self.configuration_service = configuration_service
        self.factory = CareerProviderFactory(secrets)

    def resolve(self, task_name: str) -> ResolvedAgentTask | None:
        document = self.configuration_service.store.load()
        if document is None:
            return None
        configuration = document.configuration
        task = getattr(configuration.agents.tasks, task_name)
        if not task.enabled or not task.provider_id:
            return None
        provider_config = configuration.providers.get(task.provider_id)
        if provider_config is None or not provider_config.enabled:
            return None
        provider = self.factory.build(provider_config, task)
        return ResolvedAgentTask(
            provider=provider,
            model=task.model or provider_config.default_model,
            configuration=task,
        )
