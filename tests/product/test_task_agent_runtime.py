from __future__ import annotations

from pathlib import Path

import pytest

from career_console.application.agent_tasks import (
    CareerTaskRuntime,
    TaskDefinition,
    TaskDefinitionRegistry,
    default_task_registry,
)


def test_default_registry_contains_complete_unique_task_contracts() -> None:
    definitions = default_task_registry.all()

    assert len(definitions) == 14
    assert len({item.task_type for item in definitions}) == 14
    for item in definitions:
        assert item.skill_id
        assert item.skill_version
        assert item.input_schema
        assert item.output_schema
        assert item.context_manifest
        assert item.provider_policy == "configured_task_provider"
        expected_review_policy = {
            "profile_fact_extraction": "deterministic_profile_write",
            "profile_fact_revision": "deterministic_profile_revision",
            "daily_job_recommendation": "automatic_recommendation",
        }.get(item.task_type, "proposal_requires_confirmation")
        assert item.review_policy == expected_review_policy


def test_every_registered_skill_can_be_loaded() -> None:
    runtime = CareerTaskRuntime()

    for definition in default_task_registry.all():
        source = {key: f"value:{key}" for key in definition.context_manifest}
        assembly = runtime.assemble(definition.task_type, source)
        assert assembly.definition is definition
        assert assembly.skill
        assert assembly.context == source


def test_profile_and_mail_tasks_are_tool_free() -> None:
    for task_type in (
        "profile_fact_extraction",
        "profile_fact_revision",
        "mail_intelligence",
    ):
        assert default_task_registry.resolve(task_type).tool_allowlist == ()


def test_unknown_task_and_invalid_registry_fail_closed() -> None:
    with pytest.raises(LookupError):
        default_task_registry.resolve("unknown")
    with pytest.raises(ValueError):
        TaskDefinitionRegistry([])

    definition = TaskDefinition(
        "duplicate",
        "daily_digest",
        "v1",
        "input.v1",
        "output.v1",
        ("value",),
    )
    with pytest.raises(ValueError):
        TaskDefinitionRegistry([definition, definition])


def test_context_is_minimized_and_missing_context_fails_closed() -> None:
    runtime = CareerTaskRuntime()

    assembly = runtime.assemble(
        "profile_fact_extraction",
        {
            "document_id": "document-1",
            "document_text": "技能：Python",
            "secret": "must-not-enter-context",
        },
    )
    assert assembly.context == {
        "document_id": "document-1",
        "document_text": "技能：Python",
    }

    with pytest.raises(ValueError, match="document_text"):
        runtime.assemble(
            "profile_fact_extraction",
            {"document_id": "document-1"},
        )


def test_tool_authorization_rejects_privilege_escalation() -> None:
    runtime = CareerTaskRuntime()
    definition = default_task_registry.resolve("mail_intelligence")

    with pytest.raises(PermissionError, match="shell"):
        runtime.tools.authorize(definition, ("shell",))


def test_task_schema_names_match_business_contracts() -> None:
    expected = {
        "profile_fact_extraction": ("profile_document.v1", "candidate_profile_object.v3"),
        "profile_fact_revision": (
            "profile_fact_revision_context.v1",
            "profile_fact_revision.v1",
        ),
        "mail_intelligence": ("mail_context.v1", "mail_intelligence.v1"),
        "profile_insight": ("profile_insight_context.v2", "profile_insight.v2"),
        "job_fit": ("job_fit_context.v2", "job_fit_analysis.v2"),
        "resume_direction": ("resume_direction_context.v1", "resume_direction.v1"),
        "resume_drafting": ("resume_draft_context.v2", "resume_draft.v2"),
        "standalone_resume_drafting": (
            "standalone_resume_context.v1",
            "resume_draft.v2",
        ),
        "material_review": ("material_review_context.v2", "material_review.v2"),
        "interview_preparation": (
            "interview_preparation_context.v1",
            "interview_preparation.v1",
        ),
        "interview_reflection": (
            "interview_reflection_context.v1",
            "interview_reflection.v1",
        ),
        "daily_digest": ("daily_digest_context.v1", "daily_digest.v1"),
        "weekly_strategy": ("weekly_strategy_context.v1", "career_strategy.v1"),
        "daily_job_recommendation": (
            "daily_job_recommendation_context.v1",
            "daily_job_recommendation.v1",
        ),
    }

    assert {
        item.task_type: (item.input_schema, item.output_schema)
        for item in default_task_registry.all()
    } == expected


def test_skill_registry_root_is_inside_career_console() -> None:
    root = CareerTaskRuntime().skills.root
    assert root.name == "skills"
    assert root.parent.name == "career_console"
    assert Path(root).is_dir()
