"""Make connector-backed application proposals idempotent.

Revision ID: 20260724_0009
Revises: 20260724_0008
Create Date: 2026-07-24
"""

from alembic import op

revision = "20260724_0009"
down_revision = "20260724_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("application_event_proposals") as batch:
        batch.create_unique_constraint(
            "uq_application_proposal_source_ref", ["source", "source_ref"]
        )


def downgrade() -> None:
    with op.batch_alter_table("application_event_proposals") as batch:
        batch.drop_constraint("uq_application_proposal_source_ref", type_="unique")
