"""Add the daily concrete-job recommendation pool.

Revision ID: 20260728_0030
Revises: 20260728_0029
"""

from alembic import op
import sqlalchemy as sa

revision = "20260728_0030"
down_revision = "20260728_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_recommendations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_post_id", sa.String(length=36), nullable=False),
        sa.Column("job_post_version_id", sa.String(length=36), nullable=False),
        sa.Column("source_opportunity_id", sa.String(length=36), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("fact_set_hash", sa.String(length=64), nullable=False),
        sa.Column("preference_set_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=48), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=True),
        sa.Column("recommended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "status IN ('active','applied','dismissed','stale')",
            name="ck_job_recommendation_status",
        ),
        sa.CheckConstraint(
            "decision IN ('recommend','reject')",
            name="ck_job_recommendation_decision",
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_post_id"], ["job_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["job_post_version_id"], ["job_post_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_opportunity_id"], ["recruitment_opportunities.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_post_version_id",
            "fact_set_hash",
            "preference_set_hash",
            name="uq_job_recommendation_input",
        ),
    )
    op.create_index(
        "ix_job_recommendations_pool",
        "job_recommendations",
        ["status", "priority", "recommended_at"],
    )
    op.create_index(
        "ix_job_recommendations_job",
        "job_recommendations",
        ["job_post_id", "recommended_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_recommendations_job", table_name="job_recommendations")
    op.drop_index("ix_job_recommendations_pool", table_name="job_recommendations")
    op.drop_table("job_recommendations")
