"""Link recruitment opportunities to concrete job posts.

Revision ID: 20260726_0012
Revises: 20260726_0011
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0012"
down_revision = "20260726_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_job_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(36),
            sa.ForeignKey("recruitment_opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_post_id",
            sa.String(36),
            sa.ForeignKey("job_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "opportunity_id", "job_post_id", name="uq_opportunity_job_link"
        ),
    )
    op.create_index(
        "ix_opportunity_job_links_job", "opportunity_job_links", ["job_post_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_opportunity_job_links_job", table_name="opportunity_job_links")
    op.drop_table("opportunity_job_links")
