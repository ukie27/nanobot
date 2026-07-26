"""Integrated workspace and explicitly confirmed data-governance endpoints."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(min_length=1, max_length=100)


@router.get("/overview")
def overview(request: Request) -> dict:
    return request.app.state.governance_service.overview()


@router.get("/search")
def search(request: Request, q: str = Query(min_length=2, max_length=200)) -> dict:
    items = request.app.state.governance_service.search(q)
    return {"items": items, "total": len(items)}


@router.get("/reviews")
def reviews(request: Request) -> dict:
    return request.app.state.runtime_service.reviews(status="open")


@router.get("/integration-health")
def integration_health(request: Request) -> dict:
    return request.app.state.governance_service.integration_health()


@router.post("/backup")
def backup(request: Request) -> dict:
    return request.app.state.governance_service.create_backup()


@router.post("/export")
def export(request: Request) -> dict:
    return request.app.state.governance_service.export_data()


@router.post("/garbage-collect")
def garbage_collect(request: Request) -> dict:
    return request.app.state.governance_service.garbage_collect()


@router.post("/connectors/{connector_type}/delete")
def delete_connector(connector_type: str, body: ConfirmationRequest, request: Request) -> dict:
    return request.app.state.governance_service.delete_connector(
        connector_type, confirmation=body.confirmation
    )


@router.post("/delete-all")
def delete_all(body: ConfirmationRequest, request: Request) -> dict:
    return request.app.state.governance_service.delete_all(confirmation=body.confirmation)
