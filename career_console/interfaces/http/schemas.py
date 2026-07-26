"""Public API response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    database: str
    revision: str | None
    expected_revision: str


class SystemPathsResponse(BaseModel):
    data_dir: str
    database: str
    logs: str
    backups: str


class SystemStatusResponse(BaseModel):
    version: str
    health: str
    database: str
    database_revision: str | None
    expected_revision: str
    recovered_jobs_at_startup: int
    paths: SystemPathsResponse


class ConnectorConfigUpdate(BaseModel):
    enabled: bool = False
    profile_alias: str = Field(min_length=1, max_length=120)
    search_query: str = Field(default="", max_length=200)
    city: str = Field(default="全国", min_length=1, max_length=100)
    result_limit: int = Field(default=15, ge=1, le=50)
    schedule_enabled: bool = False
    schedule_times: list[str] = Field(
        default_factory=lambda: ["09:00", "18:00"], min_length=1, max_length=8
    )
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)


class ConnectorLoginRequest(BaseModel):
    timeout: int = Field(default=300, ge=30, le=600)


class OpenCliRuntimeUpdate(BaseModel):
    executable: str | None = Field(default=None, max_length=1000)


class NowcoderConnectorConfigUpdate(BaseModel):
    enabled: bool = False
    search_query: str = Field(default="", max_length=200)
    city: str = Field(default="全国", min_length=1, max_length=100)
    result_limit: int = Field(default=500, ge=1, le=1000)
    schedule_enabled: bool = False
    schedule_times: list[str] = Field(
        default_factory=lambda: ["09:00"], min_length=1, max_length=8
    )


class NowcoderScanRequest(BaseModel):
    lookback_days: int = Field(default=0)


class ImapAccountUpdate(BaseModel):
    enabled: bool = False
    email_address: str = Field(min_length=3, max_length=320)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=993, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=320)
    password: str | None = Field(default=None, min_length=1, max_length=1000)
    folder: str = Field(default="INBOX", min_length=1, max_length=255)
    initial_lookback_days: int = Field(default=30, ge=1, le=30)
    poll_interval_minutes: int = Field(default=10, ge=5, le=1440)


class MailProposalRequest(BaseModel):
    application_id: str = Field(min_length=1, max_length=36)


class BackgroundJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    status: str
    priority: int
    run_after: datetime
    attempt_count: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_error_code: str | None


class BackgroundJobListResponse(BaseModel):
    items: list[BackgroundJobResponse]
    total: int


class FactCountsResponse(BaseModel):
    proposed: int
    confirmed: int
    rejected: int


class CandidateProfileResponse(BaseModel):
    id: str
    display_name: str | None
    timezone: str
    version: int
    fact_counts: FactCountsResponse
    created_at: datetime
    updated_at: datetime


class FactSourceResponse(BaseModel):
    id: str
    document_id: str | None
    source_type: str
    evidence_text: str
    created_at: datetime


class FactRevisionResponse(BaseModel):
    id: str
    revision_number: int
    previous_value: str
    new_value: str
    previous_status: str
    new_status: str
    reason: str
    changed_by: str
    created_at: datetime


class CandidateFactResponse(BaseModel):
    id: str
    profile_id: str
    category: str
    field_key: str
    value: str
    status: str
    confidence: float | None
    version: int
    sources: list[FactSourceResponse]
    revisions: list[FactRevisionResponse]
    created_at: datetime
    updated_at: datetime


class CandidateFactListResponse(BaseModel):
    items: list[CandidateFactResponse]
    total: int


class DocumentResponse(BaseModel):
    id: str
    file_name: str
    media_type: str
    sha256: str
    size_bytes: int
    parse_status: str
    parser_name: str
    text_preview: str
    fact_source_count: int
    duplicate: bool = False
    proposed_fact_count: int | None = None
    extracted_candidate_count: int | None = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


class TextImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)


class ManualFactRequest(BaseModel):
    category: str
    field_key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=10_000)
    source_note: str = Field(default="", max_length=2_000)


class FactActionRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(default="", max_length=500)


class FactEditRequest(FactActionRequest):
    value: str = Field(min_length=1, max_length=10_000)


class BatchFactItem(BaseModel):
    id: str
    expected_version: int = Field(ge=1)


class BatchConfirmRequest(BaseModel):
    items: list[BatchFactItem] = Field(min_length=1, max_length=200)


class BatchConfirmResponse(BaseModel):
    items: list[CandidateFactResponse]
    completed: int
