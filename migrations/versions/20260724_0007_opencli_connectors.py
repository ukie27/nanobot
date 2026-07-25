"""Connector foundation and OpenCLI BOSS source.

Revision ID: 20260724_0007
Revises: 20260724_0006
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0007"
down_revision = "20260724_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connector_type", sa.String(48), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("profile_alias", sa.String(120), nullable=False),
        sa.Column("search_query", sa.String(200), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("result_limit", sa.Integer(), nullable=False),
        sa.Column("schedule_enabled", sa.Integer(), nullable=False),
        sa.Column("schedule_times_json", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("next_scan_at", sa.DateTime(timezone=True)),
        sa.Column("scan_lease_run_id", sa.String(36)),
        sa.Column("scan_lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("health_status", sa.String(32), nullable=False),
        sa.Column("last_error_code", sa.String(120)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connector_type", name="uq_connector_type"),
    )
    op.create_index("ix_connector_due", "connector_configs", ["enabled", "next_scan_at"])
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connector_id",
            sa.String(36),
            sa.ForeignKey("connector_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("quarantined_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(120)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sync_runs_connector", "sync_runs", ["connector_id", "started_at"])
    op.create_table(
        "source_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connector_id",
            sa.String(36),
            sa.ForeignKey("connector_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sync_run_id",
            sa.String(36),
            sa.ForeignKey("sync_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(120)),
        sa.Column("job_post_id", sa.String(36), sa.ForeignKey("job_posts.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "connector_id", "external_id", "content_hash", name="uq_source_event_version"
        ),
    )
    op.create_index("ix_source_events_status", "source_events", ["connector_id", "status"])
    op.create_table(
        "sync_cursors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connector_id",
            sa.String(36),
            sa.ForeignKey("connector_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cursor_key", sa.String(100), nullable=False),
        sa.Column("cursor_value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connector_id", "cursor_key", name="uq_sync_cursor_key"),
    )


def downgrade() -> None:
    op.drop_table("sync_cursors")
    op.drop_index("ix_source_events_status", table_name="source_events")
    op.drop_table("source_events")
    op.drop_index("ix_sync_runs_connector", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_connector_due", table_name="connector_configs")
    op.drop_table("connector_configs")
