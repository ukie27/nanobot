"""Recruitment opportunity pool API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from nanobot.career.domain.opportunities import OpportunityTriageStatus

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


class OpportunitySourceResponse(BaseModel):
    id: str
    external_id: str
    source_url: str
    first_seen_at: datetime
    last_seen_at: datetime


class OpportunityVersionResponse(BaseModel):
    id: str
    version_number: int
    content_hash: str
    collected_at: datetime
    created_at: datetime


class LinkedJobResponse(BaseModel):
    id: str
    company: str
    title: str
    location: str | None
    version: int
    created_at: datetime


class OpportunityResponse(BaseModel):
    id: str
    company: str
    batch: str
    cities: str
    careers: str
    industries: str
    evaluation: str
    application_starts_at: datetime | None
    application_ends_at: datetime | None
    announcement_url: str | None
    application_url: str
    triage_status: OpportunityTriageStatus
    version: int
    first_collected_at: datetime
    last_collected_at: datetime
    created_at: datetime
    updated_at: datetime
    sources: list[OpportunitySourceResponse]
    linked_jobs: list[LinkedJobResponse]


class OpportunityDetailResponse(OpportunityResponse):
    versions: list[OpportunityVersionResponse]


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]
    total: int


class OpportunityTriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    triage_status: OpportunityTriageStatus
    expected_version: int = Field(ge=1)


@router.get("", response_model=OpportunityListResponse)
def list_opportunities(
    request: Request,
    triage_status: OpportunityTriageStatus | None = Query(default=None),
    today: bool = Query(default=False),
) -> dict:
    return request.app.state.opportunity_service.list(
        triage_status=triage_status,
        today=today,
    )


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
def get_opportunity(opportunity_id: str, request: Request) -> dict:
    try:
        return request.app.state.opportunity_service.get(opportunity_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{opportunity_id}/triage", response_model=OpportunityResponse)
def triage_opportunity(
    opportunity_id: str,
    body: OpportunityTriageRequest,
    request: Request,
) -> dict:
    try:
        return request.app.state.opportunity_service.triage(
            opportunity_id,
            triage_status=body.triage_status,
            expected_version=body.expected_version,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
