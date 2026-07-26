"""Pure application lifecycle and event-stream rules."""

from __future__ import annotations

from enum import StrEnum

from career_console.domain.common.errors import CareerDomainError


class ApplicationStatus(StrEnum):
    DISCOVERED = "discovered"
    PREPARING_MATERIALS = "preparing_materials"
    READY_TO_APPLY = "ready_to_apply"
    SUBMITTED = "submitted"
    APPLICATION_CONFIRMED = "application_confirmed"
    ASSESSMENT = "assessment"
    WRITTEN_TEST = "written_test"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    ARCHIVED = "archived"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.DISCOVERED: {
        ApplicationStatus.PREPARING_MATERIALS,
        ApplicationStatus.READY_TO_APPLY,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.PREPARING_MATERIALS: {
        ApplicationStatus.READY_TO_APPLY,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.READY_TO_APPLY: {
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SUBMITTED: {
        ApplicationStatus.APPLICATION_CONFIRMED,
        ApplicationStatus.ASSESSMENT,
        ApplicationStatus.WRITTEN_TEST,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.APPLICATION_CONFIRMED: {
        ApplicationStatus.ASSESSMENT,
        ApplicationStatus.WRITTEN_TEST,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.ASSESSMENT: {
        ApplicationStatus.WRITTEN_TEST,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.WRITTEN_TEST: {
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.INTERVIEW: {
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.OFFER: {ApplicationStatus.WITHDRAWN},
    ApplicationStatus.REJECTED: set(),
    ApplicationStatus.WITHDRAWN: set(),
    ApplicationStatus.ARCHIVED: set(),
}


def ensure_transition(current: ApplicationStatus, target: ApplicationStatus) -> None:
    if target == ApplicationStatus.ARCHIVED and current != ApplicationStatus.ARCHIVED:
        return
    if target not in _TRANSITIONS[current]:
        raise CareerDomainError(
            f"Application cannot transition from {current.value} to {target.value}.",
            code="invalid_application_transition",
        )


def event_type_for(target: ApplicationStatus) -> str:
    return {
        ApplicationStatus.SUBMITTED: "application_submitted",
        ApplicationStatus.APPLICATION_CONFIRMED: "application_confirmed",
        ApplicationStatus.ASSESSMENT: "assessment_scheduled",
        ApplicationStatus.WRITTEN_TEST: "written_test_scheduled",
        ApplicationStatus.INTERVIEW: "interview_scheduled",
        ApplicationStatus.OFFER: "offer_received",
        ApplicationStatus.REJECTED: "application_rejected",
        ApplicationStatus.WITHDRAWN: "application_withdrawn",
        ApplicationStatus.ARCHIVED: "application_archived",
    }.get(target, "application_status_changed")
