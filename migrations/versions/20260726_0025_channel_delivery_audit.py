"""Add sanitized Channel delivery audit.

Revision ID: 20260726_0025
Revises: 20260726_0024
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0025"
down_revision = "20260726_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_delivery_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_type", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("source_ref", sa.String(180)),
        sa.Column("target_masked", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_channel_delivery_created", "channel_delivery_runs",
        ["channel_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_delivery_created", table_name="channel_delivery_runs")
    op.drop_table("channel_delivery_runs")
