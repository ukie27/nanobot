"""Add structured Agent mail intelligence and review items.

Revision ID: 20260726_0014
Revises: 20260726_0013
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0014"
down_revision = "20260726_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_intelligence_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mail_message_id", sa.String(36), sa.ForeignKey("mail_messages.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("relevance", sa.String(32), nullable=False),
        sa.Column("message_type", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("company", sa.String(300)),
        sa.Column("job_title", sa.String(300)),
        sa.Column("application_reference", sa.String(100)),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id", ondelete="SET NULL")),
        sa.Column("match_confidence", sa.Float(), nullable=False),
        sa.Column("match_reason", sa.String(500), nullable=False),
        sa.Column("create_record_recommended", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mail_analysis_relevance", "mail_intelligence_analyses", ["relevance", "created_at"])
    op.create_table(
        "mail_intelligence_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("mail_intelligence_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("status_candidate", sa.String(32)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("severity", sa.String(24)),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("resolution_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_mail_intelligence_items_review", "mail_intelligence_items", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_mail_intelligence_items_review", table_name="mail_intelligence_items")
    op.drop_table("mail_intelligence_items")
    op.drop_index("ix_mail_analysis_relevance", table_name="mail_intelligence_analyses")
    op.drop_table("mail_intelligence_analyses")
