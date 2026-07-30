"""Deterministic task definitions for CareerConsole background Agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    task_type: str
    skill_id: str
    skill_version: str
    input_schema: str
    output_schema: str
    context_manifest: tuple[str, ...]
    tool_allowlist: tuple[str, ...] = ()
    provider_policy: str = "configured_task_provider"
    max_iterations: int = 1
    timeout_seconds: int = 60
    max_tokens: int = 4096
    retry_policy: str = "standard"
    repair_policy: str = "schema_once"
    sensitivity: str = "sensitive"
    review_policy: str = "proposal_requires_confirmation"


@dataclass(frozen=True, slots=True)
class TaskAssembly:
    definition: TaskDefinition
    skill: str
    context: dict[str, Any]
    tools: tuple[str, ...]


class TaskDefinitionRegistry:
    def __init__(self, definitions: list[TaskDefinition]) -> None:
        if not definitions:
            raise ValueError("Career Agent task registry cannot be empty.")
        task_types = [item.task_type for item in definitions]
        duplicates = sorted({item for item in task_types if task_types.count(item) > 1})
        if duplicates:
            raise ValueError(
                "Duplicate Career Agent task type: " + ", ".join(duplicates)
            )
        for item in definitions:
            if not all(
                (
                    item.task_type,
                    item.skill_id,
                    item.skill_version,
                    item.input_schema,
                    item.output_schema,
                    item.provider_policy,
                    item.review_policy,
                )
            ):
                raise ValueError(f"Incomplete Career Agent task definition: {item.task_type}")
            if len(set(item.context_manifest)) != len(item.context_manifest):
                raise ValueError(
                    f"Duplicate context field in Career Agent task: {item.task_type}"
                )
            if len(set(item.tool_allowlist)) != len(item.tool_allowlist):
                raise ValueError(
                    f"Duplicate tool permission in Career Agent task: {item.task_type}"
                )
        self._definitions = {item.task_type: item for item in definitions}

    def resolve(self, task_type: str) -> TaskDefinition:
        try:
            return self._definitions[task_type]
        except KeyError as exc:
            raise LookupError(f"Unknown Career Agent task: {task_type}") from exc

    def all(self) -> tuple[TaskDefinition, ...]:
        return tuple(self._definitions.values())


class SkillRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2] / "skills"

    def load(self, skill_id: str, version: str) -> str:
        path = self.root / skill_id / version / "SKILL.md"
        if not path.is_file():
            raise LookupError(f"Career skill is not installed: {skill_id}@{version}")
        return path.read_text(encoding="utf-8").strip()


class CareerTaskContextAssembler:
    """Allow only fields declared by the trusted task definition."""

    def build(self, definition: TaskDefinition, source: Mapping[str, Any]) -> dict[str, Any]:
        missing = [key for key in definition.context_manifest if key not in source]
        if missing:
            raise ValueError(
                f"Career Agent task {definition.task_type} is missing context: "
                + ", ".join(missing)
            )
        return {key: source[key] for key in definition.context_manifest if key in source}


class ToolPolicyResolver:
    def resolve(self, definition: TaskDefinition) -> tuple[str, ...]:
        return definition.tool_allowlist

    def authorize(
        self, definition: TaskDefinition, requested: tuple[str, ...] | list[str]
    ) -> tuple[str, ...]:
        allowed = set(definition.tool_allowlist)
        denied = sorted(set(requested) - allowed)
        if denied:
            raise PermissionError(
                f"Career Agent task {definition.task_type} cannot use tools: "
                + ", ".join(denied)
            )
        return tuple(requested)


class ProviderPolicyResolver:
    def resolve(self, definition: TaskDefinition, configured: Any) -> Any:
        if definition.provider_policy != "configured_task_provider":
            raise ValueError("Unsupported provider policy.")
        return configured


class CareerTaskRuntime:
    """Assemble one trusted task contract before any model invocation."""

    def __init__(
        self,
        *,
        tasks: TaskDefinitionRegistry | None = None,
        skills: SkillRegistry | None = None,
        contexts: CareerTaskContextAssembler | None = None,
        tools: ToolPolicyResolver | None = None,
    ) -> None:
        self.tasks = tasks or default_task_registry
        self.skills = skills or SkillRegistry()
        self.contexts = contexts or CareerTaskContextAssembler()
        self.tools = tools or ToolPolicyResolver()

    def assemble(self, task_type: str, source: Mapping[str, Any]) -> TaskAssembly:
        definition = self.tasks.resolve(task_type)
        return TaskAssembly(
            definition=definition,
            skill=self.skills.load(definition.skill_id, definition.skill_version),
            context=self.contexts.build(definition, source),
            tools=self.tools.resolve(definition),
        )


default_task_registry = TaskDefinitionRegistry([
    TaskDefinition(
        "profile_fact_extraction", "profile_fact_extraction", "v2",
        "profile_document.v1", "candidate_profile_object.v2",
        ("document_id", "document_text"),
    ),
    TaskDefinition(
        "mail_intelligence", "mail_intelligence", "v2",
        "mail_context.v1", "mail_intelligence.v1",
        ("message", "candidate_applications", "business_timezone"),
    ),
    TaskDefinition(
        "profile_insight", "profile_insight", "v1",
        "profile_insight_context.v1", "profile_insight.v1",
        (
            "schemaVersion",
            "businessTimezone",
            "inputRevision",
            "confirmedFacts",
            "confirmedPreferences",
            "confirmedStrategy",
            "recentSevenDayAggregates",
        ),
    ),
    TaskDefinition(
        "job_fit", "job_fit", "v1",
        "job_fit_context.v2", "job_fit_analysis.v2",
        (
            "schemaVersion",
            "businessTimezone",
            "inputRevision",
            "job",
            "requirements",
            "confirmedFacts",
            "confirmedPreferences",
            "factSetHash",
            "preferenceSetHash",
        ),
    ),
    TaskDefinition(
        "daily_job_recommendation", "daily_job_recommendation", "v1",
        "daily_job_recommendation_context.v1", "daily_job_recommendation.v1",
        (
            "schemaVersion",
            "businessTimezone",
            "inputRevision",
            "job",
            "requirements",
            "confirmedFacts",
            "confirmedPreferences",
            "confirmedInsights",
            "manualDirections",
            "factSetHash",
            "preferenceSetHash",
        ),
        review_policy="automatic_recommendation",
    ),
    TaskDefinition(
        "resume_direction", "resume_direction", "v1",
        "resume_direction_context.v1", "resume_direction.v1",
        (
            "schemaVersion",
            "businessTimezone",
            "inputRevision",
            "job",
            "formalMatch",
            "requirements",
            "confirmedFacts",
            "confirmedPreferences",
            "factSetHash",
            "preferenceSetHash",
        ),
    ),
    TaskDefinition(
        "resume_drafting", "resume_drafting", "v2",
        "resume_draft_context.v2", "resume_draft.v2",
        (
            "schemaVersion",
            "businessTimezone",
            "inputRevision",
            "job",
            "activeDirectionSelection",
            "requirements",
            "confirmedFacts",
            "factSetHash",
            "resumeId",
            "baseResumeVersion",
            "resumeName",
        ),
    ),
    TaskDefinition(
        "material_review", "material_review", "v2",
        "material_review_context.v2", "material_review.v2",
        (
            "schemaVersion",
            "businessTimezone",
            "job",
            "requirements",
            "confirmedFacts",
            "draft",
        ),
    ),
    TaskDefinition(
        "interview_preparation", "interview_preparation", "v1",
        "interview_preparation_context.v1", "interview_preparation.v1",
        ("application", "job_post_version", "submitted_material"),
    ),
    TaskDefinition(
        "interview_reflection", "interview_reflection", "v1",
        "interview_reflection_context.v1", "interview_reflection.v1",
        ("reflection", "related_facts"),
    ),
    TaskDefinition(
        "daily_digest", "daily_digest", "v1",
        "daily_digest_context.v1", "daily_digest.v1",
        ("daily_events", "pending_reviews"),
    ),
    TaskDefinition(
        "weekly_strategy", "weekly_strategy", "v1",
        "weekly_strategy_context.v1", "career_strategy.v1",
        ("weekly_events", "confirmed_profile"),
    ),
])
