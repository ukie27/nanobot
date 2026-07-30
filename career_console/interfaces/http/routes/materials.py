"""Part 3 application-material workbench API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from career_console.domain.materials import MaterialType

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])
resume_router = APIRouter(prefix="/api/v1/resumes", tags=["materials"])
export_router = APIRouter(prefix="/api/v1/material-exports", tags=["materials"])


class GenerateMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_post_id: str = Field(min_length=1, max_length=36)
    material_type: MaterialType = MaterialType.RESUME
    name: str = Field(default="我的基础简历", max_length=300)
    resume_id: str | None = Field(default=None, max_length=36)


class EditBlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=10_000)


class EditMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    blocks: list[EditBlockRequest] = Field(min_length=1, max_length=100)


class FinalizeMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class GenerateAgentMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_post_id: str = Field(min_length=1, max_length=36)
    resume_id: str | None = Field(default=None, max_length=36)
    resume_name: str = Field(default="我的基础简历", min_length=1, max_length=300)


class ResolveAgentMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    resolution: str = Field(pattern="^(confirmed|rejected)$")
    reason: str = Field(default="", max_length=500)


class ForkResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: str = Field(min_length=1, max_length=36)
    series_type: str = Field(pattern="^(base|direction)$")
    name: str = Field(min_length=1, max_length=300)
    parent_resume_id: str | None = Field(default=None, max_length=36)
    direction_label: str | None = Field(default=None, max_length=120)


class SetDefaultResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resume_id: str = Field(min_length=1, max_length=36)
    expected_version: int | None = Field(default=None, ge=1)


class MaterialFactSnapshotResponse(BaseModel):
    id: str
    fact_id: str
    fact_version: int
    category: str
    field_key: str
    value: str


class MaterialBlockResponse(BaseModel):
    id: str
    section: str
    text: str
    fact_snapshots: list[MaterialFactSnapshotResponse]


class MaterialVersionResponse(BaseModel):
    id: str
    parent_version_id: str | None
    source_resume_version_id: str | None
    version_scope: str
    version_number: int
    status: str
    title: str
    content_hash: str
    fact_set_hash: str
    created_at: datetime
    finalized_at: datetime | None


class CurrentMaterialVersionResponse(MaterialVersionResponse):
    rendered_text: str
    blocks: list[MaterialBlockResponse]


class ReviewFindingResponse(BaseModel):
    id: str
    severity: str
    code: str
    message: str
    block_id: str | None


class MaterialReviewResponse(BaseModel):
    id: str
    status: str
    schema_version: str
    error_count: int
    warning_count: int
    created_at: datetime
    findings: list[ReviewFindingResponse]


class MaterialExportResponse(BaseModel):
    id: str
    format: str
    sha256: str
    size_bytes: int
    page_count: int
    text_layer_ok: bool
    render_ok: bool
    extracted_text_hash: str
    created_at: datetime
    download_url: str
    preview_url: str


class MaterialSummaryResponse(BaseModel):
    id: str
    resume_id: str
    name: str
    resume_series_type: str
    source_resume_version_id: str | None
    resume_direction_selection_id: str | None
    material_type: MaterialType
    status: str
    version: int
    job_post_id: str
    job_post_version_id: str
    job_title: str
    company: str
    current_version_number: int
    strategy_stale: bool
    strategy_stale_reason: str | None
    strategy_stale_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MaterialResponse(MaterialSummaryResponse):
    current_version: CurrentMaterialVersionResponse
    versions: list[MaterialVersionResponse]
    review: MaterialReviewResponse | None
    export: MaterialExportResponse | None


class MaterialListResponse(BaseModel):
    items: list[MaterialSummaryResponse]
    total: int


class ResumeSeriesResponse(BaseModel):
    id: str
    name: str
    series_type: str
    parent_resume_id: str | None
    direction_label: str | None
    material_count: int
    latest_version: MaterialVersionResponse | None
    latest_finalized_version: MaterialVersionResponse | None = None
    is_default: bool = False
    default_version: int | None = None
    created_at: datetime
    updated_at: datetime


class ResumeSeriesListResponse(BaseModel):
    items: list[ResumeSeriesResponse]
    total: int


@router.get("/agent-proposals")
def list_agent_material_proposals(job_post_id: str, request: Request) -> dict:
    return request.app.state.material_agent_service.list_for_job(job_post_id)


@router.post("/agent-proposals", status_code=status.HTTP_201_CREATED)
def generate_agent_material(body: GenerateAgentMaterialRequest, request: Request) -> dict:
    return request.app.state.material_agent_service.generate(
        body.job_post_id, resume_id=body.resume_id, resume_name=body.resume_name
    )


@router.post("/agent-proposals/{proposal_id}/resolve")
def resolve_agent_material(proposal_id: str, body: ResolveAgentMaterialRequest,
                           request: Request) -> dict:
    return request.app.state.material_agent_service.resolve(
        proposal_id, expected_version=body.expected_version,
        resolution=body.resolution, reason=body.reason,
    )


@resume_router.get("", response_model=ResumeSeriesListResponse)
def list_resumes(request: Request) -> dict:
    items = request.app.state.material_gateway.list_resumes()
    return {"items": items, "total": len(items)}


@resume_router.get("/default", response_model=ResumeSeriesResponse | None)
def get_default_resume(request: Request) -> dict | None:
    return request.app.state.application_service.get_default_resume()


@resume_router.put("/default", response_model=ResumeSeriesResponse)
def set_default_resume(body: SetDefaultResumeRequest, request: Request) -> dict:
    return request.app.state.application_service.set_default_resume(**body.model_dump())


@resume_router.post("/from-material", status_code=status.HTTP_201_CREATED,
                    response_model=ResumeSeriesResponse)
def fork_resume(body: ForkResumeRequest, request: Request) -> dict:
    return request.app.state.material_service.fork_resume(
        body.material_id, series_type=body.series_type, name=body.name,
        parent_resume_id=body.parent_resume_id, direction_label=body.direction_label,
    )


@resume_router.get("/versions/{from_version_id}/diff/{to_version_id}")
def diff_resume_versions(from_version_id: str, to_version_id: str, request: Request) -> dict:
    return request.app.state.material_gateway.diff_versions(from_version_id, to_version_id)


@router.get("", response_model=MaterialListResponse)
def list_materials(request: Request) -> dict:
    items = request.app.state.material_gateway.list_materials()
    return {"items": items, "total": len(items)}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MaterialResponse)
def generate_material(body: GenerateMaterialRequest, request: Request) -> dict:
    return request.app.state.material_service.generate(
        job_post_id=body.job_post_id,
        material_type=body.material_type,
        name=body.name,
        resume_id=body.resume_id,
    )


@router.get("/{material_id}", response_model=MaterialResponse)
def get_material(material_id: str, request: Request) -> dict:
    return request.app.state.material_gateway.get_material(material_id)


@router.post(
    "/{material_id}/versions", status_code=status.HTTP_201_CREATED, response_model=MaterialResponse
)
def edit_material(material_id: str, body: EditMaterialRequest, request: Request) -> dict:
    return request.app.state.material_service.edit(
        material_id,
        expected_version=body.expected_version,
        blocks=[item.model_dump() for item in body.blocks],
    )


@router.post(
    "/{material_id}/reviews", status_code=status.HTTP_201_CREATED, response_model=MaterialResponse
)
def review_material(material_id: str, request: Request) -> dict:
    return request.app.state.material_service.review(material_id)


@router.post("/{material_id}/finalize", response_model=MaterialResponse)
def finalize_material(material_id: str, body: FinalizeMaterialRequest, request: Request) -> dict:
    return request.app.state.material_service.finalize(
        material_id, expected_version=body.expected_version
    )


@export_router.get("/{export_id}/download", response_class=FileResponse)
def download_export(export_id: str, request: Request) -> FileResponse:
    path, media_type = request.app.state.material_gateway.export_path(export_id)
    return FileResponse(
        path, media_type=media_type, filename=path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    )


@export_router.get("/{export_id}/preview", response_class=FileResponse)
def preview_export(export_id: str, request: Request) -> FileResponse:
    path, media_type = request.app.state.material_gateway.export_path(export_id, preview=True)
    return FileResponse(path, media_type=media_type)
