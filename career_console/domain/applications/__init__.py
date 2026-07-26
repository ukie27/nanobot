"""Application lifecycle domain."""

from career_console.domain.applications.entities import (
    ApplicationStatus,
    ProposalStatus,
    ensure_transition,
    event_type_for,
)

__all__ = ["ApplicationStatus", "ProposalStatus", "ensure_transition", "event_type_for"]
