"""Part 2 job pool and explainable matching API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from career_console.domain.common.errors import CareerDomainError

router = APIRouter(prefix="/api/v1/job-posts", tags=["job-pool"])


class ImportJobTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)
    opportunity_id: str | None = Field(default=None, min_length=1, max_length=36)
    mail_analysis_id: str | None = Field(default=None, min_length=1, max_length=36)


class ImportJobUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl
    confirmed: bool
    opportunity_id: str | None = Field(default=None, min_length=1, max_length=36)
    mail_analysis_id: str | None = Field(default=None, min_length=1, max_length=36)


class JobRequirementResponse(BaseModel):
    id: str
    category: str
    level: str
    description: str
    evidence_text: str
    keywords: list[str]
    weight: int
    ordinal: int


class FactEvidenceResponse(BaseModel):
    id: str
    category: str
    field_key: str
    value: str
    version: int


class JobEvidenceResponse(BaseModel):
    requirement: JobRequirementResponse
    decision: str
    rationale: str
    facts: list[FactEvidenceResponse]


class JobAnalysisResponse(BaseModel):
    id: str
    job_post_version_id: str
    hard_gate_passed: bool
    score: int
    matched_count: int
    gap_count: int
    must_gap_count: int
    recommendation: str
    created_at: datetime
    reused: bool = False
    evidence: list[JobEvidenceResponse] = Field(default_factory=list)


class JobPostSummaryResponse(BaseModel):
    id: str
    company: str
    title: str
    location: str | None
    employment_type: str | None
    work_mode: str | None
    deadline_at: datetime | None
    status: str
    version: int
    latest_analysis: JobAnalysisResponse | None
    created_at: datetime
    updated_at: datetime


class JobVersionResponse(BaseModel):
    id: str
    version_number: int
    content_hash: str
    created_at: datetime


class JobSourceResponse(BaseModel):
    id: str
    source_type: str
    source_url: str | None
    display_name: str
    discovered_at: datetime
    last_seen_at: datetime


class JobPostResponse(JobPostSummaryResponse):
    duplicate: bool
    created: bool
    target_audience: str | None
    raw_text: str
    content_hash: str
    requirements: list[JobRequirementResponse]
    versions: list[JobVersionResponse]
    sources: list[JobSourceResponse]
    analyses: list[JobAnalysisResponse]
    opportunity_ids: list[str]


class JobPostListResponse(BaseModel):
    items: list[JobPostSummaryResponse]
    total: int


class JobFitProposalResponse(BaseModel):
    id: str
    job_post_id: str
    job_post_version_id: str
    fact_set_hash: str
    preference_set_hash: str
    schema_version: str
    content: dict[str, Any]
    status: str
    version: int
    agent_run_id: str
    review_task_id: str | None
    formal_analysis_id: str | None
    resolution_reason: str | None
    created_at: datetime
    resolved_at: datetime | None
    decision_projection: dict[str, Any]


class JobFitProposalListResponse(BaseModel):
    items: list[JobFitProposalResponse]
    total: int


class ResolveJobFitProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    resolution: Literal["confirmed", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


class ResumeDirectionProposalResponse(BaseModel):
    id: str
    job_post_id: str
    job_post_version_id: str
    job_match_analysis_id: str
    fact_set_hash: str
    preference_set_hash: str
    schema_version: str
    content: dict[str, Any]
    status: str
    version: int
    agent_run_id: str
    review_task_id: str | None
    selection_id: str | None
    resolution_reason: str | None
    created_at: datetime
    resolved_at: datetime | None


class ResumeDirectionSelectionResponse(BaseModel):
    id: str
    proposal_id: str
    job_post_id: str
    job_post_version_id: str
    selected_direction_ids: list[str]
    selected_directions: list[dict[str, Any]]
    status: str
    version: int
    created_at: datetime


class ResumeDirectionOverviewResponse(BaseModel):
    proposals: list[ResumeDirectionProposalResponse]
    selections: list[ResumeDirectionSelectionResponse]


class ResolveResumeDirectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    resolution: Literal["confirmed", "rejected"]
    selected_direction_ids: list[str] = Field(default_factory=list, max_length=2)
    reason: str = Field(min_length=1, max_length=500)


@router.get("", response_model=JobPostListResponse)
def list_job_posts(
    request: Request, job_status: str | None = Query(default=None, alias="status")
) -> dict:
    items = request.app.state.job_gateway.list_jobs(status=job_status)
    return {"items": items, "total": len(items)}


@router.get("/{job_id}", response_model=JobPostResponse)
def get_job_post(job_id: str, request: Request) -> dict:
    return request.app.state.job_gateway.get_job(job_id)


@router.post("/import-text", status_code=status.HTTP_201_CREATED, response_model=JobPostResponse)
def import_job_text(body: ImportJobTextRequest, request: Request) -> dict:
    try:
        return request.app.state.job_service.import_text(
            name=body.name,
            text=body.text,
            opportunity_id=body.opportunity_id,
            mail_analysis_id=body.mail_analysis_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/import-file", status_code=status.HTTP_201_CREATED, response_model=JobPostResponse)
async def import_job_file(
    request: Request,
    file: UploadFile = File(...),
    opportunity_id: str | None = Form(default=None, min_length=1, max_length=36),
    mail_analysis_id: str | None = Form(default=None, min_length=1, max_length=36),
) -> dict:
    content = await file.read(request.app.state.settings.max_document_bytes + 1)
    try:
        return request.app.state.job_service.import_file(
            file_name=file.filename or "job.txt",
            content=content,
            media_type=file.content_type,
            opportunity_id=opportunity_id,
            mail_analysis_id=mail_analysis_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/import-url", status_code=status.HTTP_201_CREATED, response_model=JobPostResponse)
def import_job_url(body: ImportJobUrlRequest, request: Request) -> dict:
    if not body.confirmed:
        from career_console.domain.common.errors import CareerDomainError

        raise CareerDomainError(
            "Explicit confirmation is required before fetching a URL.",
            code="job_url_confirmation_required",
        )
    url = str(body.url)
    name, text = request.app.state.job_fetcher.fetch(url)
    try:
        return request.app.state.job_service.import_text(
            name=name,
            text=text,
            source_url=url,
            opportunity_id=body.opportunity_id,
            mail_analysis_id=body.mail_analysis_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{job_id}/analyses", status_code=status.HTTP_201_CREATED, response_model=JobAnalysisResponse
)
def analyze_job_post(job_id: str, request: Request) -> dict:
    return request.app.state.job_gateway.analyze_job(job_id)


@router.get("/{job_id}/agent-fit-proposals", response_model=JobFitProposalListResponse)
def list_agent_fit_proposals(job_id: str, request: Request) -> dict:
    items = request.app.state.job_fit_service.list_for_job(job_id)
    return {"items": items, "total": len(items)}


@router.post(
    "/{job_id}/agent-fit-proposals", status_code=status.HTTP_201_CREATED,
    response_model=JobFitProposalResponse,
)
def generate_agent_fit_proposal(job_id: str, request: Request) -> dict:
    try:
        return request.app.state.job_fit_service.generate(job_id)
    except (ValueError, LookupError, CareerDomainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/agent-fit-proposals/{proposal_id}/resolve", response_model=JobFitProposalResponse
)
def resolve_agent_fit_proposal(
    proposal_id: str, body: ResolveJobFitProposalRequest, request: Request
) -> dict:
    try:
        return request.app.state.job_fit_service.resolve(proposal_id, **body.model_dump())
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{job_id}/resume-directions", response_model=ResumeDirectionOverviewResponse)
def list_resume_directions(job_id: str, request: Request) -> dict:
    return request.app.state.resume_direction_service.list_for_job(job_id)


@router.post(
    "/{job_id}/resume-directions", status_code=status.HTTP_201_CREATED,
    response_model=ResumeDirectionProposalResponse,
)
def generate_resume_directions(job_id: str, request: Request) -> dict:
    try:
        return request.app.state.resume_direction_service.generate(job_id)
    except (ValueError, LookupError, CareerDomainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/resume-directions/{proposal_id}/resolve", response_model=ResumeDirectionProposalResponse
)
def resolve_resume_directions(
    proposal_id: str, body: ResolveResumeDirectionRequest, request: Request
) -> dict:
    try:
        return request.app.state.resume_direction_service.resolve(
            proposal_id, **body.model_dump()
        )
    except (ValueError, LookupError, CareerDomainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
