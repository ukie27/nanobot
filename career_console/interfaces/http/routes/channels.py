"""Outbound-only business notification Channel API."""

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from career_console.infrastructure.configuration.schema import QuietHoursConfiguration
from career_console.infrastructure.configuration.service import ConfigurationRevisionConflictError

router = APIRouter(prefix="/api/v1/channels", tags=["channels"])


class QQChannelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    enabled: bool = False
    app_id: str = Field(default="", max_length=120)
    secret: str | None = Field(default=None, min_length=1, max_length=1000)
    allow_from: list[str] = Field(default_factory=list, max_length=100)
    notification_targets: list[str] = Field(default_factory=list, max_length=100)
    event_subscriptions: list[str] = Field(default_factory=list, max_length=10)
    message_format: str = "plain"
    outbound_only: bool = True
    quiet_hours: QuietHoursConfiguration = Field(default_factory=QuietHoursConfiguration)


@router.get("/qq")
def get_qq(request: Request) -> dict:
    return request.app.state.channel_configuration.get_qq()


@router.put("/qq")
def configure_qq(body: QQChannelUpdate, request: Request) -> dict:
    values = body.model_dump()
    expected_revision = values.pop("expected_revision")
    secret = values.pop("secret")
    try:
        return request.app.state.channel_configuration.configure_qq(
            expected_revision=expected_revision, secret=secret, **values
        )
    except ConfigurationRevisionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "configuration_revision_conflict", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/qq")
def delete_qq(expected_revision: int, request: Request) -> dict:
    try:
        return request.app.state.channel_configuration.delete_qq(expected_revision)
    except ConfigurationRevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/qq/test")
def test_qq(request: Request) -> dict:
    try:
        return request.app.state.channel_configuration.test_qq()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/deliveries")
def deliveries(request: Request, limit: int = Query(50, ge=1, le=200)) -> dict:
    return request.app.state.channel_configuration.list_deliveries(limit)
