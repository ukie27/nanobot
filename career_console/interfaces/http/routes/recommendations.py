"""API for the visible daily job recommendation pool."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/v1/job-recommendations", tags=["job-recommendations"])


class RecommendationResponse(BaseModel):
    id: str
    job_post_id: str
    job_post_version_id: str
    source_opportunity_id: str | None
    agent_run_id: str
    application_id: str | None
    company: str
    title: str
    location: str | None
    deadline_at: datetime | None
    application_url: str | None
    schema_version: str
    decision: Literal["recommend", "reject"]
    score: int
    priority: Literal["high", "medium", "low"]
    content: dict[str, Any]
    status: Literal["active", "accepted", "dismissed", "stale"]
    version: int
    recommended_at: datetime
    resolved_at: datetime | None
    resolution_reason: str | None


class RecommendationListResponse(BaseModel):
    items: list[RecommendationResponse]
    total: int


class DismissRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(default="", max_length=500)


class AcceptRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=1, max_length=100)


@router.get("", response_model=RecommendationListResponse)
def list_recommendations(
    request: Request,
    status: Literal["active", "accepted", "dismissed", "stale"] = Query(default="active"),
) -> dict:
    return request.app.state.recommendation_service.list(status=status)


@router.get("/{recommendation_id}", response_model=RecommendationResponse)
def get_recommendation(recommendation_id: str, request: Request) -> dict:
    try:
        return request.app.state.recommendation_service.get(recommendation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{recommendation_id}/dismiss", response_model=RecommendationResponse)
def dismiss_recommendation(
    recommendation_id: str, body: DismissRecommendationRequest, request: Request
) -> dict:
    try:
        return request.app.state.recommendation_service.dismiss(
            recommendation_id, **body.model_dump()
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{recommendation_id}/accept", response_model=RecommendationResponse)
def accept_recommendation(
    recommendation_id: str, body: AcceptRecommendationRequest, request: Request
) -> dict:
    try:
        return request.app.state.recommendation_service.accept(
            recommendation_id, **body.model_dump()
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
