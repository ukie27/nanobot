"""Add Provider connection test audit.

Revision ID: 20260726_0023
Revises: 20260726_0022
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0023"
down_revision = "20260726_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_connection_test_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_provider_tests_provider_created",
        "provider_connection_test_runs",
        ["provider_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_tests_provider_created",
        table_name="provider_connection_test_runs",
    )
    op.drop_table("provider_connection_test_runs")
