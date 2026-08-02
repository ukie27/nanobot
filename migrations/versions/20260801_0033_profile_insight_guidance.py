"""Add actionable profile insight guidance.

Revision ID: 20260801_0033
Revises: 20260731_0032
"""

import sqlalchemy as sa
from alembic import op

revision = "20260801_0033"
down_revision = "20260731_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profile_insight_proposals",
        sa.Column("recommended_action", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profile_insight_proposals", "recommended_action")
