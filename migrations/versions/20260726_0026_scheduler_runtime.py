"""Add sanitized Scheduler run audit.

Revision ID: 20260726_0026
Revises: 20260726_0025
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0026"
down_revision = "20260726_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduler_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trigger_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("counters_json", sa.Text(), nullable=False),
        sa.Column("error_codes_json", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scheduler_runs_started", "scheduler_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduler_runs_started", table_name="scheduler_runs")
    op.drop_table("scheduler_runs")
