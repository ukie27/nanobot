"""Add reviewable Agent material drafts.

Revision ID: 20260726_0020
Revises: 20260726_0019
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0020"
down_revision = "20260726_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_agent_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_post_id", sa.String(36), sa.ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_post_version_id", sa.String(36), sa.ForeignKey("job_post_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("resume_direction_selection_id", sa.String(36), sa.ForeignKey("resume_direction_selections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", sa.String(36), sa.ForeignKey("resumes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("base_resume_version_id", sa.String(36), sa.ForeignKey("resume_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("resume_name", sa.String(300), nullable=False),
        sa.Column("material_type", sa.String(32), nullable=False),
        sa.Column("fact_set_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("review_schema_version", sa.String(32), nullable=False),
        sa.Column("review_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("drafter_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewer_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("material_draft_id", sa.String(36), sa.ForeignKey("material_drafts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolution_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_material_agent_proposals_job", "material_agent_proposals", ["job_post_id", "created_at"])
    op.create_index("ix_material_agent_proposals_review", "material_agent_proposals", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_material_agent_proposals_review", table_name="material_agent_proposals")
    op.drop_index("ix_material_agent_proposals_job", table_name="material_agent_proposals")
    op.drop_table("material_agent_proposals")
