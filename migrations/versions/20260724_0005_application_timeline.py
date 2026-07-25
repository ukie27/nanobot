"""Application management and immutable event timeline.

Revision ID: 20260724_0005
Revises: 20260723_0004
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0005"
down_revision = "20260723_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("review_tasks") as batch:
        batch.add_column(sa.Column("resolution", sa.String(24)))
        batch.add_column(sa.Column("resolution_reason", sa.String(500)))
        batch.add_column(sa.Column("resolved_by", sa.String(80)))

    op.create_table(
        "applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_post_id",
            sa.String(36),
            sa.ForeignKey("job_posts.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "job_post_version_id",
            sa.String(36),
            sa.ForeignKey("job_post_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("job_title_snapshot", sa.String(300), nullable=False),
        sa.Column("company_name_snapshot", sa.String(300), nullable=False),
        sa.Column("job_content_hash", sa.String(64), nullable=False),
        sa.Column("current_status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_applications_status_updated", "applications", ["current_status", "updated_at"]
    )
    op.create_table(
        "application_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "application_id",
            sa.String(36),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("from_status", sa.String(32)),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("proposal_id", sa.String(36)),
        sa.Column(
            "supersedes_event_id",
            sa.String(36),
            sa.ForeignKey("application_events.id", ondelete="RESTRICT"),
        ),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "application_id", "sequence_number", name="uq_application_event_sequence"
        ),
        sa.UniqueConstraint(
            "application_id", "idempotency_key", name="uq_application_event_command"
        ),
    )
    op.create_index(
        "ix_application_events_timeline",
        "application_events",
        ["application_id", "sequence_number"],
    )
    op.create_table(
        "application_material_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "application_id",
            sa.String(36),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_draft_id",
            sa.String(36),
            sa.ForeignKey("material_drafts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "resume_version_id",
            sa.String(36),
            sa.ForeignKey("resume_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("material_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("rendered_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("fact_set_hash", sa.String(64), nullable=False),
        sa.Column(
            "export_id", sa.String(36), sa.ForeignKey("material_exports.id", ondelete="RESTRICT")
        ),
        sa.Column("export_sha256", sa.String(64)),
        sa.Column("export_relative_path", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("application_id", "material_draft_id", name="uq_application_material"),
    )
    op.create_table(
        "application_event_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "application_id",
            sa.String(36),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("proposed_status", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(300)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("resolution_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_application_proposals_review", "application_event_proposals", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_application_proposals_review", table_name="application_event_proposals")
    op.drop_table("application_event_proposals")
    op.drop_table("application_material_snapshots")
    op.drop_index("ix_application_events_timeline", table_name="application_events")
    op.drop_table("application_events")
    op.drop_index("ix_applications_status_updated", table_name="applications")
    op.drop_table("applications")
    with op.batch_alter_table("review_tasks") as batch:
        batch.drop_column("resolved_by")
        batch.drop_column("resolution_reason")
        batch.drop_column("resolution")
