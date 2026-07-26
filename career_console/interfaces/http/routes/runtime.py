"""Unified human review queue and AgentRun audit API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/runtime", tags=["career-runtime"])


class ReviewTaskResponse(BaseModel):
    id: str
    task_type: str
    entity_type: str
    entity_id: str
    title: str
    summary: str
    source_type: str
    priority: int
    status: str
    version: int
    agent_run_id: str | None
    target_url: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    resolution: str | None
    resolution_reason: str | None
    resolved_by: str | None


class ReviewTaskListResponse(BaseModel):
    items: list[ReviewTaskResponse]
    total: int


class AgentRunResponse(BaseModel):
    id: str
    task_type: str
    execution_mode: str
    implementation: str
    provider: str | None
    model: str | None
    prompt_version: str | None
    skill_version: str | None
    schema_version: str
    input_entity_type: str | None
    input_entity_id: str | None
    input_revision: str | None
    input_hash: str | None
    output_hash: str | None
    tool_calls: list[dict[str, Any]]
    status: str
    output_count: int
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    retry_count: int
    sensitivity: str
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
    retention_until: datetime | None


class AgentRunListResponse(BaseModel):
    items: list[AgentRunResponse]
    total: int


@router.get("/reviews", response_model=ReviewTaskListResponse)
def list_reviews(
    request: Request,
    status: str | None = Query(default="open", max_length=24),
) -> dict:
    return request.app.state.runtime_service.reviews(status=status)


@router.get("/reviews/{review_id}", response_model=ReviewTaskResponse)
def get_review(review_id: str, request: Request) -> dict:
    try:
        return request.app.state.runtime_service.review(review_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agent-runs", response_model=AgentRunListResponse)
def list_agent_runs(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return request.app.state.runtime_service.agent_runs(limit=limit)


@router.get("/agent-runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run(run_id: str, request: Request) -> dict:
    try:
        return request.app.state.runtime_service.agent_run(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
