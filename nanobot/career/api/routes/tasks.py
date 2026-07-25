"""Part 5 dashboard, tasks, reminders, notifications, scheduler, and SSE API."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from nanobot.career.infrastructure.connectors import OpenCliError

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
dashboard_router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
notification_router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])
scheduler_router = APIRouter(prefix="/api/v1/scheduler", tags=["scheduler"])
event_router = APIRouter(prefix="/api/v1/events", tags=["events"])


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    task_type: str = Field(default="custom", min_length=1, max_length=48)
    due_at: datetime
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    notes: str = Field(default="", max_length=5_000)
    priority: int = Field(default=0, ge=-100, le=100)
    application_id: str | None = Field(default=None, max_length=36)
    job_post_id: str | None = Field(default=None, max_length=36)


class TaskCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class PostponeTaskRequest(TaskCommandRequest):
    due_at: datetime
    timezone: str | None = Field(default=None, max_length=64)


class CreateReminderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset_minutes: int = Field(ge=0, le=43_200)


class RunDueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    now: datetime | None = None


class ReminderResponse(BaseModel):
    id: str
    task_id: str
    offset_minutes: int
    generation: int
    scheduled_for: datetime
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    triggered_at: datetime | None


class TaskResponse(BaseModel):
    id: str
    application_id: str | None
    job_post_id: str | None
    source_event_id: str | None
    task_type: str
    title: str
    notes: str
    status: str
    priority: int
    due_at: datetime
    timezone: str
    version: int
    company: str | None
    job_title: str | None
    reminders: list[ReminderResponse]
    conflict_ids: list[str]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int


class DashboardResponse(BaseModel):
    generated_at: datetime
    timezone: str
    today: list[TaskResponse]
    overdue: list[TaskResponse]
    upcoming: list[TaskResponse]
    interviews: list[TaskResponse]
    pending_review_count: int
    unread_notification_count: int
    conflict_count: int


class NotificationResponse(BaseModel):
    id: str
    reminder_id: str
    notification_type: str
    title: str
    body: str
    status: str
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int


class RunDueResponse(BaseModel):
    schedules_processed: int
    reminders_triggered: int
    outbox_dispatched: int
    leases_recovered: int
    connector_runs_processed: int = 0
    connector_error_code: str | None = None


@router.get("", response_model=TaskListResponse)
def list_tasks(request: Request) -> dict:
    items = request.app.state.task_gateway.list_tasks()
    return {"items": items, "total": len(items)}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
def create_task(body: CreateTaskRequest, request: Request) -> dict:
    return request.app.state.task_service.create(**body.model_dump())


@router.post("/{task_id}/complete", response_model=TaskResponse)
def complete_task(task_id: str, body: TaskCommandRequest, request: Request) -> dict:
    return request.app.state.task_service.update(
        task_id, expected_version=body.expected_version, action="complete"
    )


@router.post("/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(task_id: str, body: TaskCommandRequest, request: Request) -> dict:
    return request.app.state.task_service.update(
        task_id, expected_version=body.expected_version, action="cancel"
    )


@router.post("/{task_id}/postpone", response_model=TaskResponse)
def postpone_task(task_id: str, body: PostponeTaskRequest, request: Request) -> dict:
    return request.app.state.task_service.update(task_id, action="postpone", **body.model_dump())


@router.post(
    "/{task_id}/reminders", status_code=status.HTTP_201_CREATED, response_model=ReminderResponse
)
def create_reminder(task_id: str, body: CreateReminderRequest, request: Request) -> dict:
    return request.app.state.task_service.add_reminder(task_id, **body.model_dump())


@dashboard_router.get("", response_model=DashboardResponse)
def dashboard(
    request: Request,
    timezone: str = Query(default="Asia/Shanghai", min_length=1, max_length=64),
) -> dict:
    return request.app.state.task_gateway.dashboard(timezone=timezone)


@notification_router.get("", response_model=NotificationListResponse)
def list_notifications(request: Request) -> dict:
    items = request.app.state.task_gateway.list_notifications()
    return {"items": items, "total": len(items)}


@notification_router.post("/{notification_id}/read", response_model=NotificationResponse)
def read_notification(notification_id: str, request: Request) -> dict:
    return request.app.state.task_gateway.read_notification(notification_id)


@scheduler_router.post("/run-due", response_model=RunDueResponse)
def run_due(body: RunDueRequest, request: Request) -> dict:
    result = request.app.state.task_service.run_due(now=body.now)
    try:
        connector_run = request.app.state.connector_service.run_due()
        result["connector_runs_processed"] = int(connector_run is not None)
        result["connector_error_code"] = None
    except OpenCliError as exc:
        result["connector_runs_processed"] = 0
        result["connector_error_code"] = exc.code
    except (RuntimeError, ValueError):
        result["connector_runs_processed"] = 0
        result["connector_error_code"] = "connector_failed"
    return result


@event_router.get("/stream", response_class=StreamingResponse)
def stream_events(request: Request) -> StreamingResponse:
    refs = request.app.state.task_gateway.recent_change_refs()

    def generate():
        yield "retry: 15000\n"
        yield f"event: dashboard.changed\ndata: {json.dumps({'refs': refs})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
