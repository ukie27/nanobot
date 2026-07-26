"""Part 4 application board, immutable timeline, and proposal review API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field

from nanobot.career.domain.applications import ApplicationStatus

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])
proposal_router = APIRouter(prefix="/api/v1/application-event-proposals", tags=["applications"])
review_router = APIRouter(prefix="/api/v1/application-review-tasks", tags=["applications"])


def _command_id() -> str:
    return str(uuid4())


class CreateApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_post_id: str = Field(min_length=1, max_length=36)


class VersionedCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    command_id: str = Field(default_factory=_command_id, min_length=1, max_length=100)


class SubmitApplicationRequest(VersionedCommandRequest):
    material_ids: list[str] = Field(min_length=1, max_length=10)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = Field(default="", max_length=5_000)


class AddApplicationEventRequest(VersionedCommandRequest):
    target_status: ApplicationStatus
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = Field(default="", max_length=5_000)


class CorrectApplicationEventRequest(VersionedCommandRequest):
    occurred_at: datetime
    note: str = Field(min_length=1, max_length=5_000)


class ArchiveApplicationRequest(VersionedCommandRequest):
    note: str = Field(default="用户归档", max_length=5_000)


class ProposeApplicationEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposed_status: ApplicationStatus
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = Field(min_length=1, max_length=5_000)
    source: str = Field(default="manual_proposal", min_length=1, max_length=32)
    source_ref: str | None = Field(default=None, max_length=300)


class ResolveProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    application_expected_version: int = Field(ge=1)
    resolution: Literal["confirmed", "rejected"]
    reason: str = Field(min_length=1, max_length=500)
    command_id: str = Field(default_factory=_command_id, min_length=1, max_length=100)


class ApplicationSummaryResponse(BaseModel):
    id: str
    job_post_id: str
    job_post_version_id: str
    job_title: str
    company: str
    job_content_hash: str
    current_status: ApplicationStatus
    version: int
    material_count: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ApplicationEventResponse(BaseModel):
    id: str
    sequence_number: int
    event_type: str
    from_status: str | None
    to_status: str
    occurred_at: datetime
    note: str
    source: str
    proposal_id: str | None
    supersedes_event_id: str | None
    superseded: bool
    created_at: datetime


class ApplicationMaterialSnapshotResponse(BaseModel):
    id: str
    material_draft_id: str
    resume_version_id: str
    material_type: str
    title: str
    rendered_text: str
    content_hash: str
    fact_set_hash: str
    export_id: str | None
    export_sha256: str | None
    created_at: datetime


class AvailableFinalMaterialResponse(BaseModel):
    id: str
    name: str
    material_type: str


class ApplicationMailEvidenceItemResponse(BaseModel):
    id: str
    item_type: str
    category: str
    title: str
    details: str
    evidence: str
    occurred_at: datetime | None
    scheduled_at: datetime | None
    status: str


class ApplicationMailEvidenceResponse(BaseModel):
    analysis_id: str
    message_id: str
    agent_run_id: str
    sender: str
    subject: str
    sent_at: datetime | None
    message_type: str
    summary: str
    match_confidence: float
    items: list[ApplicationMailEvidenceItemResponse]
    created_at: datetime


class ApplicationProposalResponse(BaseModel):
    id: str
    application_id: str
    proposed_status: ApplicationStatus
    occurred_at: datetime
    note: str
    source: str
    source_ref: str | None
    status: str
    version: int
    resolution_reason: str | None
    created_at: datetime
    resolved_at: datetime | None


class ApplicationReviewTaskResponse(ApplicationProposalResponse):
    task_id: str
    task_status: str
    task_version: int
    resolution: str | None
    resolved_by: str | None
    application_version: int
    job_title: str
    company: str


class ApplicationResponse(ApplicationSummaryResponse):
    events: list[ApplicationEventResponse]
    material_snapshots: list[ApplicationMaterialSnapshotResponse]
    proposals: list[ApplicationProposalResponse]
    available_final_materials: list[AvailableFinalMaterialResponse]
    mail_evidence: list[ApplicationMailEvidenceResponse]


class ApplicationListResponse(BaseModel):
    items: list[ApplicationSummaryResponse]
    total: int


class ApplicationReviewTaskListResponse(BaseModel):
    items: list[ApplicationReviewTaskResponse]
    total: int


@router.get("", response_model=ApplicationListResponse)
def list_applications(request: Request) -> dict:
    items = request.app.state.application_gateway.list_applications()
    return {"items": items, "total": len(items)}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApplicationResponse)
def create_application(body: CreateApplicationRequest, request: Request) -> dict:
    return request.app.state.application_service.create(job_post_id=body.job_post_id)


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(application_id: str, request: Request) -> dict:
    return request.app.state.application_gateway.get_application(application_id)


@router.post("/{application_id}/submit", response_model=ApplicationResponse)
def submit_application(
    application_id: str, body: SubmitApplicationRequest, request: Request
) -> dict:
    return request.app.state.application_service.submit(application_id, **body.model_dump())


@router.post("/{application_id}/events", response_model=ApplicationResponse)
def add_application_event(
    application_id: str, body: AddApplicationEventRequest, request: Request
) -> dict:
    return request.app.state.application_service.add_event(application_id, **body.model_dump())


@router.post("/{application_id}/events/{event_id}/corrections", response_model=ApplicationResponse)
def correct_application_event(
    application_id: str,
    event_id: str,
    body: CorrectApplicationEventRequest,
    request: Request,
) -> dict:
    return request.app.state.application_service.correct_event(
        application_id, event_id, **body.model_dump()
    )


@router.post("/{application_id}/archive", response_model=ApplicationResponse)
def archive_application(
    application_id: str, body: ArchiveApplicationRequest, request: Request
) -> dict:
    return request.app.state.application_service.archive(application_id, **body.model_dump())


@router.post(
    "/{application_id}/event-proposals",
    status_code=status.HTTP_201_CREATED,
    response_model=ApplicationReviewTaskResponse,
)
def propose_application_event(
    application_id: str, body: ProposeApplicationEventRequest, request: Request
) -> dict:
    return request.app.state.application_service.propose_event(application_id, **body.model_dump())


@review_router.get("", response_model=ApplicationReviewTaskListResponse)
def list_application_review_tasks(request: Request) -> dict:
    items = request.app.state.application_gateway.list_review_tasks()
    return {"items": items, "total": len(items)}


@proposal_router.post("/{proposal_id}/resolve", response_model=ApplicationReviewTaskResponse)
def resolve_application_event_proposal(
    proposal_id: str, body: ResolveProposalRequest, request: Request
) -> dict:
    return request.app.state.application_service.resolve_proposal(proposal_id, **body.model_dump())
