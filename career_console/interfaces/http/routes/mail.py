"""Read-only IMAP configuration, synchronization, and Agent analysis endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from career_console.domain.common.errors import CareerDomainError
from career_console.infrastructure.mail import ImapReadOnlyError
from career_console.interfaces.http.schemas import ImapAccountUpdate, MailProposalRequest

router = APIRouter(prefix="/api/v1/mail", tags=["mail"])


class ResolveMailIntelligenceItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    resolution: Literal["confirmed", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


@router.get("/account")
def get_account(request: Request) -> dict:
    return request.app.state.mail_service.get()


@router.put("/account")
def configure_account(body: ImapAccountUpdate, request: Request) -> dict:
    try:
        return request.app.state.integration_configuration.configure_imap(
            **body.model_dump()
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/account")
def delete_account(request: Request) -> dict:
    return request.app.state.integration_configuration.delete_imap()


@router.post("/account/test")
def test_account(request: Request) -> dict:
    try:
        return request.app.state.mail_service.test_connection()
    except (ValueError, LookupError, ImapReadOnlyError) as exc:
        code = exc.code if isinstance(exc, ImapReadOnlyError) else "imap_configuration_invalid"
        raise HTTPException(status_code=409, detail={"code": code, "message": str(exc)}) from exc


@router.post("/sync")
def synchronize(request: Request) -> dict:
    try:
        return request.app.state.mail_service.sync()
    except (ValueError, LookupError, RuntimeError, ImapReadOnlyError) as exc:
        if isinstance(exc, ImapReadOnlyError):
            code = exc.code
        elif isinstance(exc, RuntimeError):
            code = "imap_sync_in_progress"
        else:
            code = "imap_configuration_invalid"
        raise HTTPException(status_code=409, detail={"code": code, "message": str(exc)}) from exc


@router.get("/messages")
def list_messages(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    items = request.app.state.mail_service.list_messages(limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/messages/{message_id}/analyze")
def analyze_message(message_id: str, request: Request) -> dict:
    try:
        return request.app.state.mail_service.analyze_message(message_id=message_id)
    except (ValueError, LookupError, CareerDomainError) as exc:
        code = exc.code if isinstance(exc, CareerDomainError) else "mail_intelligence_invalid"
        raise HTTPException(status_code=409, detail={"code": code, "message": str(exc)}) from exc


@router.post("/intelligence-items/{item_id}/resolve")
def resolve_intelligence_item(
    item_id: str, body: ResolveMailIntelligenceItemRequest, request: Request
) -> dict:
    try:
        return request.app.state.mail_service.resolve_intelligence_item(
            item_id=item_id, **body.model_dump()
        )
    except (ValueError, LookupError, CareerDomainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/messages/{message_id}/proposal")
def propose_message(message_id: str, body: MailProposalRequest, request: Request) -> dict:
    try:
        return request.app.state.mail_service.propose_for_application(
            message_id=message_id, application_id=body.application_id
        )
    except (ValueError, LookupError, CareerDomainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
