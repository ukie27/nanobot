"""Candidate profile, document import, and fact review routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Query, Request, UploadFile

from nanobot.career.api.schemas import (
    BatchConfirmRequest,
    BatchConfirmResponse,
    CandidateFactListResponse,
    CandidateFactResponse,
    CandidateProfileResponse,
    DocumentListResponse,
    DocumentResponse,
    FactActionRequest,
    FactEditRequest,
    ManualFactRequest,
    TextImportRequest,
)

router = APIRouter(prefix="/api/v1", tags=["profile"])


@router.get("/profile", response_model=CandidateProfileResponse)
def get_profile(request: Request) -> CandidateProfileResponse:
    return CandidateProfileResponse.model_validate(request.app.state.profile_service.gateway.get_profile())


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(request: Request) -> DocumentListResponse:
    items = [
        DocumentResponse.model_validate(item)
        for item in request.app.state.profile_service.gateway.list_documents()
    ]
    return DocumentListResponse(items=items, total=len(items))


@router.post("/documents/import", response_model=DocumentResponse, status_code=201)
async def import_document(
    request: Request,
    file: UploadFile = File(...),
) -> DocumentResponse:
    limit = request.app.state.settings.max_document_bytes
    content = await file.read(limit + 1)
    result = request.app.state.profile_service.import_file(
        file_name=file.filename or "document",
        content=content,
        media_type=file.content_type,
    )
    return DocumentResponse.model_validate(result)


@router.post("/documents/import-text", response_model=DocumentResponse, status_code=201)
def import_text(request: Request, body: TextImportRequest) -> DocumentResponse:
    result = request.app.state.profile_service.import_text(name=body.name, text=body.text)
    return DocumentResponse.model_validate(result)


@router.get("/facts", response_model=CandidateFactListResponse)
def list_facts(
    request: Request,
    status: Literal["proposed", "confirmed", "rejected"] | None = Query(default=None),
) -> CandidateFactListResponse:
    items = [
        CandidateFactResponse.model_validate(item)
        for item in request.app.state.profile_service.gateway.list_facts(status=status)
    ]
    return CandidateFactListResponse(items=items, total=len(items))


@router.post("/facts", response_model=CandidateFactResponse, status_code=201)
def add_manual_fact(request: Request, body: ManualFactRequest) -> CandidateFactResponse:
    result = request.app.state.profile_service.gateway.add_manual_fact(
        category=body.category,
        field_key=body.field_key,
        value=body.value,
        source_note=body.source_note,
    )
    return CandidateFactResponse.model_validate(result)


@router.post("/facts/{fact_id}/confirm", response_model=CandidateFactResponse)
def confirm_fact(
    fact_id: str, request: Request, body: FactActionRequest
) -> CandidateFactResponse:
    result = request.app.state.profile_service.gateway.change_fact(
        fact_id=fact_id,
        expected_version=body.expected_version,
        action="confirm",
        reason=body.reason or "Confirmed by user",
    )
    return CandidateFactResponse.model_validate(result)


@router.post("/facts/{fact_id}/reject", response_model=CandidateFactResponse)
def reject_fact(fact_id: str, request: Request, body: FactActionRequest) -> CandidateFactResponse:
    result = request.app.state.profile_service.gateway.change_fact(
        fact_id=fact_id,
        expected_version=body.expected_version,
        action="reject",
        reason=body.reason or "Rejected by user",
    )
    return CandidateFactResponse.model_validate(result)


@router.post("/facts/{fact_id}/edit", response_model=CandidateFactResponse)
def edit_fact(fact_id: str, request: Request, body: FactEditRequest) -> CandidateFactResponse:
    result = request.app.state.profile_service.gateway.change_fact(
        fact_id=fact_id,
        expected_version=body.expected_version,
        action="edit",
        value=body.value,
        reason=body.reason or "Edited by user",
    )
    return CandidateFactResponse.model_validate(result)


@router.post("/facts/batch-confirm", response_model=BatchConfirmResponse)
def batch_confirm(request: Request, body: BatchConfirmRequest) -> BatchConfirmResponse:
    changed = request.app.state.profile_service.gateway.batch_confirm(
        items=[(item.id, item.expected_version) for item in body.items]
    )
    results = [CandidateFactResponse.model_validate(item) for item in changed]
    return BatchConfirmResponse(items=results, completed=len(results))
