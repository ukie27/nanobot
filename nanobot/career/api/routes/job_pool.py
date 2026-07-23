"""Part 2 job pool and explainable matching API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

router = APIRouter(prefix="/api/v1/job-posts", tags=["job-pool"])


class ImportJobTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)


class ImportJobUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl
    confirmed: bool


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


class JobPostListResponse(BaseModel):
    items: list[JobPostSummaryResponse]
    total: int


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
    return request.app.state.job_service.import_text(name=body.name, text=body.text)


@router.post("/import-file", status_code=status.HTTP_201_CREATED, response_model=JobPostResponse)
async def import_job_file(request: Request, file: UploadFile = File(...)) -> dict:
    content = await file.read(request.app.state.settings.max_document_bytes + 1)
    return request.app.state.job_service.import_file(
        file_name=file.filename or "job.txt", content=content, media_type=file.content_type
    )


@router.post("/import-url", status_code=status.HTTP_201_CREATED, response_model=JobPostResponse)
def import_job_url(body: ImportJobUrlRequest, request: Request) -> dict:
    if not body.confirmed:
        from nanobot.career.domain.common.errors import CareerDomainError

        raise CareerDomainError(
            "Explicit confirmation is required before fetching a URL.",
            code="job_url_confirmation_required",
        )
    url = str(body.url)
    name, text = request.app.state.job_fetcher.fetch(url)
    return request.app.state.job_service.import_text(name=name, text=text, source_url=url)


@router.post(
    "/{job_id}/analyses", status_code=status.HTTP_201_CREATED, response_model=JobAnalysisResponse
)
def analyze_job_post(job_id: str, request: Request) -> dict:
    return request.app.state.job_gateway.analyze_job(job_id)
