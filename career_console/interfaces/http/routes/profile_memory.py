"""Structured profile preferences, change ledger, insights, strategy, and digests."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from career_console.domain.common.errors import CareerDomainError

router = APIRouter(prefix="/api/v1/profile-memory", tags=["profile-memory"])


class PreferenceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any
    expected_version: int | None = Field(default=None, ge=1)


class ResolveMemoryProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    resolution: Literal["confirmed", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


@router.get("")
def overview(request: Request) -> dict[str, Any]:
    return request.app.state.profile_memory_gateway.overview()


@router.put("/preferences/{preference_key}")
def set_preference(
    preference_key: str, body: PreferenceCommand, request: Request
) -> dict[str, Any]:
    try:
        return request.app.state.profile_memory_gateway.set_preference(
            preference_key=preference_key, **body.model_dump()
        )
    except (ValueError, CareerDomainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/digests/daily")
def generate_daily_digest(request: Request) -> dict[str, Any]:
    return request.app.state.profile_memory_gateway.generate_daily_digest()


@router.post("/strategies")
def generate_strategy(request: Request) -> dict[str, Any]:
    return request.app.state.profile_memory_gateway.generate_strategy_proposal()


@router.post("/insights")
def generate_insight(request: Request) -> list[dict[str, Any]]:
    try:
        return request.app.state.profile_memory_service.generate_insights()
    except (ValueError, CareerDomainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/impacts/run")
def run_impacts(request: Request) -> dict[str, int]:
    queued = request.app.state.profile_impact_service.enqueue_pending()
    processed = 0
    while processed < 100 and request.app.state.profile_impact_service.process_next():
        processed += 1
    return {"queued": queued, "processed": processed}


@router.post("/{entity_type}/{entity_id}/resolve")
def resolve_proposal(
    entity_type: Literal["profile_insight", "strategy_snapshot"],
    entity_id: str,
    body: ResolveMemoryProposal,
    request: Request,
) -> dict[str, Any]:
    try:
        return request.app.state.profile_memory_gateway.resolve(
            entity_type=entity_type, entity_id=entity_id, **body.model_dump()
        )
    except (ValueError, LookupError, CareerDomainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
