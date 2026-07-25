"""Candidate profile, document, and fact library.

Revision ID: 20260723_0002
Revises: 20260723_0001
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op

revision = "20260723_0002"
down_revision = "20260723_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(200)),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "blobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("relative_path", sa.String(500), nullable=False, unique=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("blob_id", sa.String(36), sa.ForeignKey("blobs.id", ondelete="RESTRICT")),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("parse_status", sa.String(24), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "candidate_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("field_key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "profile_id",
            "category",
            "field_key",
            "normalized_value",
            name="uq_candidate_fact_dedup",
        ),
    )
    op.create_index(
        "ix_candidate_facts_profile_status",
        "candidate_facts",
        ["profile_id", "status", "category"],
    )
    op.create_table(
        "fact_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "fact_id",
            sa.String(36),
            sa.ForeignKey("candidate_facts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fact_sources_fact", "fact_sources", ["fact_id"])
    op.create_table(
        "fact_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "fact_id",
            sa.String(36),
            sa.ForeignKey("candidate_facts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("previous_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.String(24), nullable=False),
        sa.Column("new_status", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("changed_by", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fact_id", "revision_number", name="uq_fact_revision_number"),
    )
    op.create_index("ix_fact_revisions_fact", "fact_revisions", ["fact_id", "revision_number"])
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("task_type", "entity_type", "entity_id", name="uq_review_task_entity"),
    )
    op.create_index("ix_review_tasks_open", "review_tasks", ["status", "task_type", "created_at"])
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_type", sa.String(100), nullable=False),
        sa.Column("implementation", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("output_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_index("ix_review_tasks_open", table_name="review_tasks")
    op.drop_table("review_tasks")
    op.drop_index("ix_fact_revisions_fact", table_name="fact_revisions")
    op.drop_table("fact_revisions")
    op.drop_index("ix_fact_sources_fact", table_name="fact_sources")
    op.drop_table("fact_sources")
    op.drop_index("ix_candidate_facts_profile_status", table_name="candidate_facts")
    op.drop_table("candidate_facts")
    op.drop_table("documents")
    op.drop_table("blobs")
    op.drop_table("candidate_profiles")
