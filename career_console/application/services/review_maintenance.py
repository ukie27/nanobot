"""Narrow maintenance operations for obsolete review projections."""

from __future__ import annotations

from typing import Any

from career_console.application.ports.profile_gateway import ProfileGateway
from career_console.application.ports.runtime_gateway import RuntimeGateway


class ReviewMaintenanceService:
    """Identify and close only verified legacy profile extraction reviews."""

    def __init__(
        self,
        *,
        runtime_gateway: RuntimeGateway,
        profile_gateway: ProfileGateway,
    ) -> None:
        self.runtime_gateway = runtime_gateway
        self.profile_gateway = profile_gateway

    def legacy_profile_fact_reviews(self) -> list[dict[str, Any]]:
        facts = {
            item["id"]: item
            for item in self.profile_gateway.list_facts(status="proposed")
        }
        matches: list[dict[str, Any]] = []
        for review in self.runtime_gateway.list_reviews(status="open"):
            if (
                review["entity_type"] != "candidate_fact"
                or review["task_type"] != "candidate_fact_review"
                or review["source_type"] != "agent_extraction"
                or review["entity_id"] not in facts
                or not review["agent_run_id"]
            ):
                continue
            run = self.runtime_gateway.get_agent_run(review["agent_run_id"])
            if (
                run["implementation"] == "local_resume_extractor"
                and run["schema_version"] == "candidate_fact.v1"
            ):
                matches.append(
                    {
                        "review_id": review["id"],
                        "fact_id": review["entity_id"],
                        "fact_version": facts[review["entity_id"]]["version"],
                        "agent_run_id": review["agent_run_id"],
                        "created_at": review["created_at"],
                    }
                )
        return matches

    def reject_legacy_profile_fact_reviews(self, *, reason: str) -> dict[str, Any]:
        matches = self.legacy_profile_fact_reviews()
        if matches:
            self.profile_gateway.batch_reject(
                items=[
                    (item["fact_id"], item["fact_version"])
                    for item in matches
                ],
                reason=reason,
                changed_by="maintenance",
            )
        return {
            "matched": len(matches),
            "rejected": len(matches),
            "reason": reason,
        }
