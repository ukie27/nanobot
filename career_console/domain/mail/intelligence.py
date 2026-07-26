"""Validated output contract for tool-free recruiting-mail intelligence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MailRelevance(StrEnum):
    RECRUITING = "recruiting"
    POSSIBLY_RELATED = "possibly_related"
    UNRELATED = "unrelated"


class MailIntelligenceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    event_type: str = Field(min_length=1, max_length=64, alias="eventType")
    status_candidate: Literal[
        "assessment", "written_test", "interview", "rejected", "offer"
    ] | None = Field(default=None, alias="statusCandidate")
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")
    title: str = Field(min_length=1, max_length=300)
    details: str = Field(default="", max_length=5_000)
    evidence: str = Field(min_length=1, max_length=2_000)
    confidence: float = Field(ge=0, le=1)

    @field_validator("occurred_at")
    @classmethod
    def china_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("occurredAt requires an explicit timezone")
        return value.astimezone(ZoneInfo("Asia/Shanghai"))


class MailIntelligenceSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schedule_type: str = Field(min_length=1, max_length=64, alias="scheduleType")
    scheduled_at: datetime = Field(alias="scheduledAt")
    title: str = Field(min_length=1, max_length=300)
    instructions: str = Field(default="", max_length=5_000)
    evidence: str = Field(min_length=1, max_length=2_000)
    confidence: float = Field(ge=0, le=1)

    @field_validator("scheduled_at")
    @classmethod
    def china_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scheduledAt requires an explicit timezone")
        return value.astimezone(ZoneInfo("Asia/Shanghai"))


class MailAttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    category: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    details: str = Field(min_length=1, max_length=5_000)
    evidence: str = Field(min_length=1, max_length=2_000)
    severity: str = Field(pattern="^(info|warning|critical)$")


class MailApplicationMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    application_id: str | None = Field(default=None, max_length=36, alias="applicationId")
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)
    create_record_recommended: bool = Field(default=False, alias="createRecordRecommended")

    @model_validator(mode="after")
    def consistent_create_recommendation(self) -> "MailApplicationMatch":
        if self.application_id and self.create_record_recommended:
            raise ValueError("A matched application cannot also request record creation.")
        return self


class MailIntelligenceResult(BaseModel):
    """`mail_intelligence.v1`; evidence is verified after model output."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_version: str = Field(alias="schemaVersion")
    relevance: MailRelevance
    message_type: str = Field(min_length=1, max_length=64, alias="messageType")
    summary: str = Field(min_length=1, max_length=2_000)
    company: str | None = Field(default=None, max_length=300)
    job_title: str | None = Field(default=None, max_length=300, alias="jobTitle")
    application_reference: str | None = Field(default=None, max_length=100, alias="applicationReference")
    application_match: MailApplicationMatch = Field(alias="applicationMatch")
    events: list[MailIntelligenceEvent] = Field(default_factory=list, max_length=20)
    schedules: list[MailIntelligenceSchedule] = Field(default_factory=list, max_length=20)
    attention_items: list[MailAttentionItem] = Field(default_factory=list, max_length=20, alias="attentionItems")

    @model_validator(mode="after")
    def schema_is_supported(self) -> "MailIntelligenceResult":
        if self.schema_version != "mail_intelligence.v1":
            raise ValueError("Unsupported mail intelligence schema version.")
        return self
