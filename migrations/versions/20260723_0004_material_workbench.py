"""Application material workflow and verified exports.

Revision ID: 20260723_0004
Revises: 20260723_0003
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op

revision = "20260723_0004"
down_revision = "20260723_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resumes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "material_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_id",
            sa.String(36),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_post_id",
            sa.String(36),
            sa.ForeignKey("job_posts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "job_post_version_id",
            sa.String(36),
            sa.ForeignKey("job_post_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("job_title_snapshot", sa.String(300), nullable=False),
        sa.Column("company_name_snapshot", sa.String(300), nullable=False),
        sa.Column("material_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_material_drafts_status_updated", "material_drafts", ["status", "updated_at"]
    )
    op.create_table(
        "resume_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_id",
            sa.String(36),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_draft_id",
            sa.String(36),
            sa.ForeignKey("material_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_version_id",
            sa.String(36),
            sa.ForeignKey("resume_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("rendered_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("fact_set_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "material_draft_id", "version_number", name="uq_material_draft_version"
        ),
    )
    op.create_index(
        "ix_resume_versions_draft", "resume_versions", ["material_draft_id", "version_number"]
    )
    op.create_table(
        "material_fact_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_version_id",
            sa.String(36),
            sa.ForeignKey("resume_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fact_id",
            sa.String(36),
            sa.ForeignKey("candidate_facts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("fact_version", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("field_key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resume_version_id", "fact_id", name="uq_material_fact_snapshot"),
    )
    op.create_table(
        "material_fact_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_version_id",
            sa.String(36),
            sa.ForeignKey("resume_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fact_snapshot_id",
            sa.String(36),
            sa.ForeignKey("material_fact_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("block_id", sa.String(80), nullable=False),
        sa.UniqueConstraint(
            "resume_version_id", "fact_snapshot_id", "block_id", name="uq_material_fact_reference"
        ),
    )
    op.create_index(
        "ix_material_fact_references_version",
        "material_fact_references",
        ["resume_version_id", "block_id"],
    )
    op.create_table(
        "material_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_version_id",
            sa.String(36),
            sa.ForeignKey("resume_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_material_reviews_version", "material_reviews", ["resume_version_id", "created_at"]
    )
    op.create_table(
        "material_review_findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(36),
            sa.ForeignKey("material_reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("block_id", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "material_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_version_id",
            sa.String(36),
            sa.ForeignKey("resume_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("relative_path", sa.String(500), nullable=False, unique=True),
        sa.Column("preview_relative_path", sa.String(500), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("text_layer_ok", sa.Integer(), nullable=False),
        sa.Column("render_ok", sa.Integer(), nullable=False),
        sa.Column("extracted_text_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resume_version_id", "format", name="uq_material_export_format"),
    )


def downgrade() -> None:
    op.drop_table("material_exports")
    op.drop_table("material_review_findings")
    op.drop_index("ix_material_reviews_version", table_name="material_reviews")
    op.drop_table("material_reviews")
    op.drop_index("ix_material_fact_references_version", table_name="material_fact_references")
    op.drop_table("material_fact_references")
    op.drop_table("material_fact_snapshots")
    op.drop_index("ix_resume_versions_draft", table_name="resume_versions")
    op.drop_table("resume_versions")
    op.drop_index("ix_material_drafts_status_updated", table_name="material_drafts")
    op.drop_table("material_drafts")
    op.drop_table("resumes")
