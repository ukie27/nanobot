"""Add durable profile impact recomputation and material invalidation.

Revision ID: 20260726_0017
Revises: 20260726_0016
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0017"
down_revision = "20260726_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_impact_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "change_event_id", sa.String(36),
            sa.ForeignKey("profile_change_events.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "background_job_id", sa.String(36),
            sa.ForeignKey("background_jobs.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("input_revision", sa.String(100), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "change_event_id", "scope", name="uq_profile_impact_event_scope"
        ),
    )
    op.create_index(
        "ix_profile_impact_runs_status", "profile_impact_runs", ["status", "created_at"]
    )
    with op.batch_alter_table("material_drafts") as batch:
        batch.add_column(
            sa.Column("strategy_stale", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("strategy_stale_reason", sa.String(500), nullable=True))
        batch.add_column(
            sa.Column("strategy_stale_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("material_drafts") as batch:
        batch.drop_column("strategy_stale_at")
        batch.drop_column("strategy_stale_reason")
        batch.drop_column("strategy_stale")
    op.drop_index("ix_profile_impact_runs_status", table_name="profile_impact_runs")
    op.drop_table("profile_impact_runs")
