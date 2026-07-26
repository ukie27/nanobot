"""Persistence models; these are deliberately not domain entities."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ConfigurationSnapshotModel(Base):
    __tablename__ = "configuration_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConfigurationChangeModel(Base):
    __tablename__ = "configuration_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("configuration_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    previous_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    new_revision: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    changed_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    activation_effect: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        Index("ix_configuration_changes_created", "created_at"),
    )


class ProviderConnectionTestRunModel(Base):
    __tablename__ = "provider_connection_test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        Index("ix_provider_tests_provider_created", "provider_id", "created_at"),
    )


class ChannelDeliveryRunModel(Base):
    __tablename__ = "channel_delivery_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(180))
    target_masked: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        Index("ix_channel_delivery_created", "channel_type", "created_at"),
    )


class SchedulerRunModel(Base):
    __tablename__ = "scheduler_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trigger_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    counters_json: Mapped[str] = mapped_column(Text, nullable=False)
    error_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_scheduler_runs_started", "started_at"),)


class BackgroundJobModel(Base):
    __tablename__ = "background_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(120))
    last_error_message_redacted: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_background_jobs_claim", "status", "run_after", "priority"),
        Index("ix_background_jobs_lease", "status", "lease_expires_at"),
    )


class ConnectorConfigModel(Base):
    __tablename__ = "connector_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_type: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profile_alias: Mapped[str] = mapped_column(String(120), nullable=False, default="default")
    search_query: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="全国")
    result_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    schedule_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    schedule_times_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='["09:00","18:00"]'
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_lease_run_id: Mapped[str | None] = mapped_column(String(36))
    scan_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_error_code: Mapped[str | None] = mapped_column(String(120))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_connector_due", "enabled", "next_scan_at"),)


class SyncRunModel(Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connector_configs.id", ondelete="CASCADE"), nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_sync_runs_connector", "connector_id", "started_at"),)


class SourceEventModel(Base):
    __tablename__ = "source_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connector_configs.id", ondelete="CASCADE"), nullable=False
    )
    sync_run_id: Mapped[str] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))
    job_post_id: Mapped[str | None] = mapped_column(ForeignKey("job_posts.id", ondelete="SET NULL"))
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("recruitment_opportunities.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "connector_id", "external_id", "content_hash", name="uq_source_event_version"
        ),
        Index("ix_source_events_status", "connector_id", "status"),
    )


class SyncCursorModel(Base):
    __tablename__ = "sync_cursors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connector_configs.id", ondelete="CASCADE"), nullable=False
    )
    cursor_key: Mapped[str] = mapped_column(String(100), nullable=False)
    cursor_value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("connector_id", "cursor_key", name="uq_sync_cursor_key"),)


class ImapAccountModel(Base):
    __tablename__ = "imap_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connector_configs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    username: Mapped[str] = mapped_column(String(320), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    folder: Mapped[str] = mapped_column(String(255), nullable=False, default="INBOX")
    initial_lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint("initial_lookback_days BETWEEN 1 AND 30", name="ck_imap_lookback_days"),
    )


class MailMessageModel(Base):
    __tablename__ = "mail_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("imap_accounts.id", ondelete="CASCADE"), nullable=False
    )
    uid_validity: Mapped[str] = mapped_column(String(64), nullable=False)
    uid: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(998))
    sender: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    event_kind: Mapped[str | None] = mapped_column(String(32))
    extracted_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    body_hash: Mapped[str | None] = mapped_column(String(64))
    attachments_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    body_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("account_id", "uid_validity", "uid", name="uq_mail_uid"),
        UniqueConstraint("account_id", "message_id", name="uq_mail_message_id"),
        Index("ix_mail_messages_center", "classification", "sent_at"),
    )


class MailApplicationCandidateModel(Base):
    __tablename__ = "mail_application_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mail_message_id: Mapped[str] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    application_id: Mapped[str | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    match_confidence: Mapped[float | None] = mapped_column(Float)
    match_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("application_event_proposals.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_mail_candidates_review", "status", "created_at"),)


class MailIntelligenceAnalysisModel(Base):
    __tablename__ = "mail_intelligence_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mail_message_id: Mapped[str] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    relevance: Mapped[str] = mapped_column(String(32), nullable=False)
    message_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(String(300))
    job_title: Mapped[str | None] = mapped_column(String(300))
    application_reference: Mapped[str | None] = mapped_column(String(100))
    application_id: Mapped[str | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    job_post_id: Mapped[str | None] = mapped_column(
        ForeignKey("job_posts.id", ondelete="SET NULL")
    )
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    match_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    create_record_recommended: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_mail_analysis_relevance", "relevance", "created_at"),)


class MailIntelligenceItemModel(Base):
    __tablename__ = "mail_intelligence_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("mail_intelligence_analyses.id", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    status_candidate: Mapped[str | None] = mapped_column(String(32))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_mail_intelligence_items_review", "status", "created_at"),)


class CandidateProfileModel(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CareerPreferenceModel(Base):
    __tablename__ = "career_preferences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    preference_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("profile_id", "preference_key", name="uq_career_preference_key"),)


class ProfileChangeEventModel(Base):
    __tablename__ = "profile_change_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entity_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    impact_scopes_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_profile_change_events_time", "profile_id", "occurred_at"),)


class ProfileImpactRunModel(Base):
    __tablename__ = "profile_impact_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    change_event_id: Mapped[str] = mapped_column(
        ForeignKey("profile_change_events.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    background_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="SET NULL")
    )
    input_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("change_event_id", "scope", name="uq_profile_impact_event_scope"),
        Index("ix_profile_impact_runs_status", "status", "created_at"),
    )


class ProfileInsightProposalModel(Base):
    __tablename__ = "profile_insight_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    insight_type: Mapped[str] = mapped_column(String(64), nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs_json: Mapped[str] = mapped_column(Text, nullable=False)
    counter_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_profile_insights_review", "status", "created_at"),)


class StrategySnapshotModel(Base):
    __tablename__ = "strategy_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("profile_id", "version_number", name="uq_strategy_snapshot_version"),
        Index("ix_strategy_snapshots_status", "status", "created_at"),
    )


class DailyDigestModel(Base):
    __tablename__ = "daily_digests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    digest_date: Mapped[str] = mapped_column(String(10), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("profile_id", "digest_date", name="uq_daily_digest_date"),)


class BlobModel(Base):
    __tablename__ = "blobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    blob_id: Mapped[str | None] = mapped_column(ForeignKey("blobs.id", ondelete="RESTRICT"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(24), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    parser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CandidateFactModel(Base):
    __tablename__ = "candidate_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_candidate_facts_profile_status", "profile_id", "status", "category"),
        UniqueConstraint(
            "profile_id",
            "category",
            "field_key",
            "normalized_value",
            name="uq_candidate_fact_dedup",
        ),
    )


class FactSourceModel(Base):
    __tablename__ = "fact_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fact_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_facts.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_fact_sources_fact", "fact_id"),)


class FactRevisionModel(Base):
    __tablename__ = "fact_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fact_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_facts.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("fact_id", "revision_number", name="uq_fact_revision_number"),
        Index("ix_fact_revisions_fact", "fact_id", "revision_number"),
    )


class ReviewTaskModel(Base):
    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(24))
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    resolved_by: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (
        Index("ix_review_tasks_open", "status", "task_type", "created_at"),
        Index("ix_review_tasks_queue", "status", "priority", "created_at"),
        Index("ix_review_tasks_agent_run", "agent_run_id"),
        UniqueConstraint("task_type", "entity_type", "entity_id", name="uq_review_task_entity"),
    )


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="task")
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    implementation: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    skill_version: Mapped[str | None] = mapped_column(String(100))
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    input_entity_type: Mapped[str | None] = mapped_column(String(80))
    input_entity_id: Mapped[str | None] = mapped_column(String(100))
    input_revision: Mapped[str | None] = mapped_column(String(100))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    tool_calls_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    output_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sensitivity: Mapped[str] = mapped_column(String(24), nullable=False, default="private")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_agent_runs_task_created", "task_type", "created_at"),
        Index("ix_agent_runs_status_created", "status", "created_at"),
    )


class CompanyModel(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompanyAliasModel(Base):
    __tablename__ = "company_aliases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecruitmentOpportunityModel(Base):
    __tablename__ = "recruitment_opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    batch: Mapped[str] = mapped_column(String(300), nullable=False)
    cities: Mapped[str] = mapped_column(Text, nullable=False, default="")
    careers: Mapped[str] = mapped_column(Text, nullable=False, default="")
    industries: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evaluation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    application_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    announcement_url: Mapped[str | None] = mapped_column(Text)
    application_url: Mapped[str] = mapped_column(Text, nullable=False)
    triage_status: Mapped[str] = mapped_column(String(24), nullable=False, default="new")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_opportunities_triage", "triage_status", "last_collected_at"),
        CheckConstraint(
            "triage_status IN ('new','following','ignored')",
            name="ck_opportunity_triage_status",
        ),
    )


class OpportunitySourceModel(Base):
    __tablename__ = "opportunity_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("recruitment_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connector_configs.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("connector_id", "external_id", name="uq_opportunity_source_external"),
        Index("ix_opportunity_sources_opportunity", "opportunity_id"),
    )


class OpportunityVersionModel(Base):
    __tablename__ = "opportunity_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("recruitment_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_events.id", ondelete="SET NULL")
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "version_number", name="uq_opportunity_version_number"
        ),
        Index("ix_opportunity_versions_opportunity", "opportunity_id", "version_number"),
    )


class OpportunityJobLinkModel(Base):
    __tablename__ = "opportunity_job_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("recruitment_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "job_post_id", name="uq_opportunity_job_link"
        ),
        Index("ix_opportunity_job_links_job", "job_post_id"),
    )


class JobPostModel(Base):
    __tablename__ = "job_posts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str | None] = mapped_column(String(300))
    normalized_location: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    employment_type: Mapped[str | None] = mapped_column(String(100))
    work_mode: Mapped[str | None] = mapped_column(String(100))
    target_audience: Mapped[str | None] = mapped_column(String(200))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "normalized_title",
            "normalized_location",
            name="uq_job_post_exact_identity",
        ),
        Index("ix_job_posts_status_updated", "status", "updated_at"),
    )


class JobPostSourceModel(Base):
    __tablename__ = "job_post_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobPostVersionModel(Base):
    __tablename__ = "job_post_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extractor_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("job_post_id", "version_number", name="uq_job_post_version_number"),
        UniqueConstraint("job_post_id", "content_hash", name="uq_job_post_content_hash"),
    )


class JobRequirementModel(Base):
    __tablename__ = "job_requirements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_post_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_post_versions.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (Index("ix_job_requirements_version", "job_post_version_id", "ordinal"),)


class JobMatchAnalysisModel(Base):
    __tablename__ = "job_match_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False
    )
    job_post_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_post_versions.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    fact_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_origin: Mapped[str] = mapped_column(
        String(24), nullable=False, default="deterministic"
    )
    hard_gate_passed: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_count: Mapped[int] = mapped_column(Integer, nullable=False)
    must_gap_count: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "job_post_id",
            "job_post_version_id",
            "profile_id",
            "fact_set_hash",
            "analysis_origin",
            name="uq_job_match_analysis_input",
        ),
        Index("ix_job_match_analysis_post", "job_post_id", "created_at"),
    )


class JobFitProposalModel(Base):
    __tablename__ = "job_fit_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False
    )
    job_post_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_post_versions.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    fact_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    preference_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False
    )
    formal_analysis_id: Mapped[str | None] = mapped_column(
        ForeignKey("job_match_analyses.id", ondelete="SET NULL")
    )
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_job_fit_proposals_post", "job_post_id", "created_at"),
        Index("ix_job_fit_proposals_review", "status", "created_at"),
    )


class ResumeDirectionProposalModel(Base):
    __tablename__ = "resume_direction_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False
    )
    job_post_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_post_versions.id", ondelete="CASCADE"), nullable=False
    )
    job_match_analysis_id: Mapped[str] = mapped_column(
        ForeignKey("job_match_analyses.id", ondelete="RESTRICT"), nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    fact_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    preference_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False
    )
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_resume_direction_proposals_post", "job_post_id", "created_at"),
        Index("ix_resume_direction_proposals_review", "status", "created_at"),
    )


class ResumeDirectionSelectionModel(Base):
    __tablename__ = "resume_direction_selections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("resume_direction_proposals.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False
    )
    job_post_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_post_versions.id", ondelete="RESTRICT"), nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    fact_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    preference_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_direction_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    selected_content_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_resume_direction_selections_job", "job_post_id", "created_at"),)


class MaterialAgentProposalModel(Base):
    __tablename__ = "material_agent_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_post_id: Mapped[str] = mapped_column(ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False)
    job_post_version_id: Mapped[str] = mapped_column(ForeignKey("job_post_versions.id", ondelete="RESTRICT"), nullable=False)
    resume_direction_selection_id: Mapped[str] = mapped_column(ForeignKey("resume_direction_selections.id", ondelete="RESTRICT"), nullable=False)
    profile_id: Mapped[str] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    resume_id: Mapped[str | None] = mapped_column(ForeignKey("resumes.id", ondelete="RESTRICT"))
    base_resume_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="RESTRICT")
    )
    resume_name: Mapped[str] = mapped_column(String(300), nullable=False)
    material_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fact_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    review_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    review_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    drafter_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False)
    reviewer_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False)
    material_draft_id: Mapped[str | None] = mapped_column(ForeignKey("material_drafts.id", ondelete="SET NULL"))
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_material_agent_proposals_job", "job_post_id", "created_at"),
        Index("ix_material_agent_proposals_review", "status", "created_at"),
    )


class JobMatchEvidenceModel(Base):
    __tablename__ = "job_match_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("job_match_analyses.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("job_requirements.id", ondelete="CASCADE"), nullable=False
    )
    fact_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_facts.id", ondelete="RESTRICT")
    )
    fact_version: Mapped[int | None] = mapped_column(Integer)
    fact_value_snapshot: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (Index("ix_job_match_evidence_analysis", "analysis_id", "requirement_id"),)


class ResumeModel(Base):
    __tablename__ = "resumes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    series_type: Mapped[str] = mapped_column(String(24), nullable=False, default="base")
    parent_resume_id: Mapped[str | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="RESTRICT")
    )
    direction_label: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MaterialDraftModel(Base):
    __tablename__ = "material_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resume_id: Mapped[str] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="RESTRICT"), nullable=False
    )
    job_post_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_post_versions.id", ondelete="RESTRICT"), nullable=False
    )
    source_resume_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="RESTRICT")
    )
    resume_direction_selection_id: Mapped[str | None] = mapped_column(
        ForeignKey("resume_direction_selections.id", ondelete="RESTRICT")
    )
    job_title_snapshot: Mapped[str] = mapped_column(String(300), nullable=False)
    company_name_snapshot: Mapped[str] = mapped_column(String(300), nullable=False)
    material_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    strategy_stale: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strategy_stale_reason: Mapped[str | None] = mapped_column(String(500))
    strategy_stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_material_drafts_status_updated", "status", "updated_at"),)


class ResumeVersionModel(Base):
    __tablename__ = "resume_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resume_id: Mapped[str] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    material_draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("material_drafts.id", ondelete="CASCADE")
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="RESTRICT")
    )
    source_resume_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="RESTRICT")
    )
    version_scope: Mapped[str] = mapped_column(String(24), nullable=False, default="job_tailored")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("material_draft_id", "version_number", name="uq_material_draft_version"),
        Index("ix_resume_versions_draft", "material_draft_id", "version_number"),
    )


class FactSnapshotModel(Base):
    __tablename__ = "material_fact_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False
    )
    fact_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_facts.id", ondelete="RESTRICT"), nullable=False
    )
    fact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("resume_version_id", "fact_id", name="uq_material_fact_snapshot"),
    )


class FactReferenceModel(Base):
    __tablename__ = "material_fact_references"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False
    )
    fact_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("material_fact_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    block_id: Mapped[str] = mapped_column(String(80), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "resume_version_id", "fact_snapshot_id", "block_id", name="uq_material_fact_reference"
        ),
        Index("ix_material_fact_references_version", "resume_version_id", "block_id"),
    )


class MaterialReviewModel(Base):
    __tablename__ = "material_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_material_reviews_version", "resume_version_id", "created_at"),)


class ReviewFindingModel(Base):
    __tablename__ = "material_review_findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("material_reviews.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    block_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MaterialExportModel(Base):
    __tablename__ = "material_exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="RESTRICT"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    preview_relative_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    text_layer_ok: Mapped[int] = mapped_column(Integer, nullable=False)
    render_ok: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("resume_version_id", "format", name="uq_material_export_format"),
    )


class ApplicationModel(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_post_id: Mapped[str] = mapped_column(
        ForeignKey("job_posts.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    job_post_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_post_versions.id", ondelete="RESTRICT"), nullable=False
    )
    job_title_snapshot: Mapped[str] = mapped_column(String(300), nullable=False)
    company_name_snapshot: Mapped[str] = mapped_column(String(300), nullable=False)
    job_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_applications_status_updated", "current_status", "updated_at"),)


class ApplicationEventModel(Base):
    __tablename__ = "application_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(String(36))
    supersedes_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("application_events.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("application_id", "sequence_number", name="uq_application_event_sequence"),
        UniqueConstraint("application_id", "idempotency_key", name="uq_application_event_command"),
        Index("ix_application_events_timeline", "application_id", "sequence_number"),
    )


class ApplicationMaterialSnapshotModel(Base):
    __tablename__ = "application_material_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    material_draft_id: Mapped[str] = mapped_column(
        ForeignKey("material_drafts.id", ondelete="RESTRICT"), nullable=False
    )
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="RESTRICT"), nullable=False
    )
    material_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    rendered_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    export_id: Mapped[str | None] = mapped_column(
        ForeignKey("material_exports.id", ondelete="RESTRICT")
    )
    export_sha256: Mapped[str | None] = mapped_column(String(64))
    export_relative_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("application_id", "material_draft_id", name="uq_application_material"),
    )


class ApplicationEventProposalModel(Base):
    __tablename__ = "application_event_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    proposed_status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("source", "source_ref", name="uq_application_proposal_source_ref"),
        Index("ix_application_proposals_review", "status", "created_at"),
    )


class InterviewModel(Base):
    __tablename__ = "interviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    application_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("application_events.id", ondelete="SET NULL"), unique=True
    )
    round_type: Mapped[str] = mapped_column(String(24), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_interviews_schedule", "status", "scheduled_at"),)


class InterviewPreparationPackModel(Base):
    __tablename__ = "interview_preparation_packs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    interview_id: Mapped[str] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    job_post_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_post_versions.id", ondelete="RESTRICT"), nullable=False
    )
    material_snapshot_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_fact_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    prior_improvement_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("interview_id", "version_number", name="uq_interview_pack_version"),
        Index("ix_interview_packs_interview", "interview_id", "version_number"),
    )


class InterviewRecordModel(Base):
    __tablename__ = "interview_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    interview_id: Mapped[str] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    overall_summary: Mapped[str] = mapped_column(Text, nullable=False)
    self_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InterviewQuestionModel(Base):
    __tablename__ = "interview_questions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("interview_records.id", ondelete="CASCADE"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_summary: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    self_rating: Mapped[int | None] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("record_id", "ordinal", name="uq_interview_question_ordinal"),
    )


class InterviewFeedbackModel(Base):
    __tablename__ = "interview_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("interview_records.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_interview_feedback_review", "status", "created_at"),)


class ImprovementItemModel(Base):
    __tablename__ = "improvement_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    feedback_id: Mapped[str] = mapped_column(
        ForeignKey("interview_feedback.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_improvement_items_status", "status", "updated_at"),)


class CareerTaskModel(Base):
    __tablename__ = "career_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    job_post_id: Mapped[str | None] = mapped_column(ForeignKey("job_posts.id", ondelete="CASCADE"))
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("application_events.id", ondelete="RESTRICT"), unique=True
    )
    source_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    task_type: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_career_tasks_due", "status", "due_at"),)


class ReminderModel(Base):
    __tablename__ = "reminders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("career_tasks.id", ondelete="CASCADE"), nullable=False
    )
    offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "task_id", "offset_minutes", "generation", name="uq_task_reminder_generation"
        ),
        Index("ix_reminders_due", "status", "scheduled_for"),
    )


class ScheduleModel(Base):
    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reminder_id: Mapped[str | None] = mapped_column(
        ForeignKey("reminders.id", ondelete="CASCADE"), unique=True
    )
    schedule_type: Mapped[str] = mapped_column(String(24), nullable=False)
    handler_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    cron_expression: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_schedules_due", "status", "next_run_at"),)


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_outbox_dispatch", "status", "next_attempt_at"),)


class NotificationModel(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reminder_id: Mapped[str] = mapped_column(
        ForeignKey("reminders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    notification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_notifications_status", "status", "created_at"),)
