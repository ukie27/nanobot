"""Interview preparation, record, feedback, and improvement endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field

from nanobot.career.domain.interviews import InterviewRound

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])
feedback_router = APIRouter(prefix="/api/v1/interview-feedback", tags=["interviews"])
improvement_router = APIRouter(prefix="/api/v1/improvement-items", tags=["interviews"])


class CreateInterviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: str = Field(min_length=1, max_length=36)
    application_event_id: str | None = Field(default=None, max_length=36)
    round_type: InterviewRound
    scheduled_at: datetime
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)


class RescheduleInterviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    scheduled_at: datetime
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)


class CancelInterviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class InterviewQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_text: str = Field(min_length=1, max_length=2_000)
    answer_summary: str = Field(default="", max_length=5_000)
    self_rating: int | None = Field(default=None, ge=1, le=5)


class SaveInterviewRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overall_summary: str = Field(min_length=1, max_length=10_000)
    self_rating: int = Field(ge=1, le=5)
    result: Literal["unknown", "pending", "passed", "rejected", "withdrawn"] = "unknown"
    questions: list[InterviewQuestionInput] = Field(default_factory=list, max_length=50)


class ResolveInterviewFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    resolution: Literal["confirmed", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


class UpdateImprovementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "completed", "dismissed"]


@router.get("")
def list_interviews(request: Request) -> dict:
    items = request.app.state.interview_service.list()
    return {"items": items, "total": len(items)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_interview(body: CreateInterviewRequest, request: Request) -> dict:
    return request.app.state.interview_service.create(**body.model_dump(mode="python"))


@router.get("/{interview_id}")
def get_interview(interview_id: str, request: Request) -> dict:
    return request.app.state.interview_service.get(interview_id)


@router.post("/{interview_id}/preparation", status_code=status.HTTP_201_CREATED)
def generate_preparation(interview_id: str, request: Request) -> dict:
    return request.app.state.interview_service.prepare(interview_id)


@router.post("/{interview_id}/reschedule")
def reschedule_interview(
    interview_id: str, body: RescheduleInterviewRequest, request: Request
) -> dict:
    return request.app.state.interview_service.reschedule(
        interview_id, **body.model_dump(mode="python")
    )


@router.post("/{interview_id}/cancel")
def cancel_interview(
    interview_id: str, body: CancelInterviewRequest, request: Request
) -> dict:
    return request.app.state.interview_service.cancel(interview_id, **body.model_dump())


@router.post("/{interview_id}/record", status_code=status.HTTP_201_CREATED)
def save_record(interview_id: str, body: SaveInterviewRecordRequest, request: Request) -> dict:
    values = body.model_dump(mode="python")
    values["questions"] = [item.model_dump() for item in body.questions]
    return request.app.state.interview_service.record(interview_id, **values)


@feedback_router.get("")
def list_feedback(request: Request) -> dict:
    items = request.app.state.interview_service.list_feedback()
    return {"items": items, "total": len(items)}


@feedback_router.post("/{feedback_id}/resolve")
def resolve_feedback(
    feedback_id: str, body: ResolveInterviewFeedbackRequest, request: Request
) -> dict:
    return request.app.state.interview_service.resolve_feedback(
        feedback_id, **body.model_dump()
    )


@improvement_router.get("")
def list_improvements(request: Request) -> dict:
    items = request.app.state.interview_service.list_improvements()
    return {"items": items, "total": len(items)}


@improvement_router.put("/{improvement_id}")
def update_improvement(
    improvement_id: str, body: UpdateImprovementRequest, request: Request
) -> dict:
    return request.app.state.interview_service.update_improvement(
        improvement_id, **body.model_dump()
    )
