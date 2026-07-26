"""Add reviewable semantic job-fit Agent proposals.

Revision ID: 20260726_0018
Revises: 20260726_0017
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0018"
down_revision = "20260726_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_fit_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_post_id", sa.String(36), sa.ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_post_version_id", sa.String(36), sa.ForeignKey("job_post_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fact_set_hash", sa.String(64), nullable=False),
        sa.Column("preference_set_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("formal_analysis_id", sa.String(36), sa.ForeignKey("job_match_analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolution_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_job_fit_proposals_post", "job_fit_proposals", ["job_post_id", "created_at"])
    op.create_index("ix_job_fit_proposals_review", "job_fit_proposals", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_job_fit_proposals_review", table_name="job_fit_proposals")
    op.drop_index("ix_job_fit_proposals_post", table_name="job_fit_proposals")
    op.drop_table("job_fit_proposals")
