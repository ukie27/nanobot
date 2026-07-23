"""Job pool, versioned requirements, and explainable matching.

Revision ID: 20260723_0003
Revises: 20260723_0002
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op

revision = "20260723_0003"
down_revision = "20260723_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_name", sa.String(300), nullable=False),
        sa.Column("normalized_name", sa.String(300), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "company_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(300), nullable=False),
        sa.Column("normalized_alias", sa.String(300), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "job_posts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("normalized_title", sa.String(300), nullable=False),
        sa.Column("location", sa.String(300)),
        sa.Column("normalized_location", sa.String(300), nullable=False),
        sa.Column("employment_type", sa.String(100)),
        sa.Column("work_mode", sa.String(100)),
        sa.Column("target_audience", sa.String(200)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "normalized_title",
            "normalized_location",
            name="uq_job_post_exact_identity",
        ),
    )
    op.create_index("ix_job_posts_status_updated", "job_posts", ["status", "updated_at"])
    op.create_table(
        "job_post_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_post_id",
            sa.String(36),
            sa.ForeignKey("job_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_key", sa.String(500), nullable=False, unique=True),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "job_post_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_post_id",
            sa.String(36),
            sa.ForeignKey("job_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("extractor_schema_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_post_id", "version_number", name="uq_job_post_version_number"),
        sa.UniqueConstraint("job_post_id", "content_hash", name="uq_job_post_content_hash"),
    )
    op.create_table(
        "job_requirements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_post_version_id",
            sa.String(36),
            sa.ForeignKey("job_post_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("level", sa.String(24), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("keywords_json", sa.Text(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_job_requirements_version", "job_requirements", ["job_post_version_id", "ordinal"]
    )
    op.create_table(
        "job_match_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_post_id",
            sa.String(36),
            sa.ForeignKey("job_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_post_version_id",
            sa.String(36),
            sa.ForeignKey("job_post_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fact_set_hash", sa.String(64), nullable=False),
        sa.Column("hard_gate_passed", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("gap_count", sa.Integer(), nullable=False),
        sa.Column("must_gap_count", sa.Integer(), nullable=False),
        sa.Column("recommendation", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_job_match_analysis_post", "job_match_analyses", ["job_post_id", "created_at"]
    )
    op.create_table(
        "job_match_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(36),
            sa.ForeignKey("job_match_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requirement_id",
            sa.String(36),
            sa.ForeignKey("job_requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fact_id", sa.String(36), sa.ForeignKey("candidate_facts.id", ondelete="RESTRICT")
        ),
        sa.Column("fact_version", sa.Integer()),
        sa.Column("fact_value_snapshot", sa.Text()),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_job_match_evidence_analysis", "job_match_evidence", ["analysis_id", "requirement_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_match_evidence_analysis", table_name="job_match_evidence")
    op.drop_table("job_match_evidence")
    op.drop_index("ix_job_match_analysis_post", table_name="job_match_analyses")
    op.drop_table("job_match_analyses")
    op.drop_index("ix_job_requirements_version", table_name="job_requirements")
    op.drop_table("job_requirements")
    op.drop_table("job_post_versions")
    op.drop_table("job_post_sources")
    op.drop_index("ix_job_posts_status_updated", table_name="job_posts")
    op.drop_table("job_posts")
    op.drop_table("company_aliases")
    op.drop_table("companies")
