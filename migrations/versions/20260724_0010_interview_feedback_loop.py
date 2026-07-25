"""Interview preparation and confirmed feedback loop.

Revision ID: 20260724_0010
Revises: 20260724_0009
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0010"
down_revision = "20260724_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_event_id", sa.String(36), sa.ForeignKey("application_events.id", ondelete="SET NULL"), unique=True),
        sa.Column("round_type", sa.String(24), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interviews_schedule", "interviews", ["status", "scheduled_at"])
    op.create_table(
        "interview_preparation_packs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("interview_id", sa.String(36), sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("job_post_version_id", sa.String(36), sa.ForeignKey("job_post_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("material_snapshot_ids_json", sa.Text(), nullable=False),
        sa.Column("confirmed_fact_ids_json", sa.Text(), nullable=False),
        sa.Column("prior_improvement_ids_json", sa.Text(), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("interview_id", "version_number", name="uq_interview_pack_version"),
    )
    op.create_index("ix_interview_packs_interview", "interview_preparation_packs", ["interview_id", "version_number"])
    op.create_table(
        "interview_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("interview_id", sa.String(36), sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overall_summary", sa.Text(), nullable=False),
        sa.Column("self_rating", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("self_rating BETWEEN 1 AND 5", name="ck_interview_record_rating"),
    )
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("record_id", sa.String(36), sa.ForeignKey("interview_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("self_rating", sa.Integer()),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.UniqueConstraint("record_id", "ordinal", name="uq_interview_question_ordinal"),
        sa.CheckConstraint("self_rating IS NULL OR self_rating BETWEEN 1 AND 5", name="ck_interview_question_rating"),
    )
    op.create_table(
        "interview_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("record_id", sa.String(36), sa.ForeignKey("interview_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_interview_feedback_review", "interview_feedback", ["status", "created_at"])
    op.create_table(
        "improvement_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("feedback_id", sa.String(36), sa.ForeignKey("interview_feedback.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_improvement_items_status", "improvement_items", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_improvement_items_status", table_name="improvement_items")
    op.drop_table("improvement_items")
    op.drop_index("ix_interview_feedback_review", table_name="interview_feedback")
    op.drop_table("interview_feedback")
    op.drop_table("interview_questions")
    op.drop_table("interview_records")
    op.drop_index("ix_interview_packs_interview", table_name="interview_preparation_packs")
    op.drop_table("interview_preparation_packs")
    op.drop_index("ix_interviews_schedule", table_name="interviews")
    op.drop_table("interviews")
