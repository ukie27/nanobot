"""Add standalone resume Agent proposals.

Revision ID: 20260731_0032
Revises: 20260729_0031
"""

import sqlalchemy as sa
from alembic import op

revision = "20260731_0032"
down_revision = "20260729_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standalone_resume_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("resume_name", sa.String(length=300), nullable=False),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column("fact_set_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("drafter_run_id", sa.String(length=36), nullable=False),
        sa.Column("resume_id", sa.String(length=36), nullable=True),
        sa.Column("resume_version_id", sa.String(length=36), nullable=True),
        sa.Column("resolution_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["drafter_run_id"], ["agent_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["resume_version_id"], ["resume_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_standalone_resume_proposals_review",
        "standalone_resume_proposals",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_standalone_resume_proposals_review",
        table_name="standalone_resume_proposals",
    )
    op.drop_table("standalone_resume_proposals")
