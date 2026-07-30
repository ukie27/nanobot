"""Add grouped reviews and explicit connector session state.

Revision ID: 20260728_0029
Revises: 20260728_0028
"""

from alembic import op
import sqlalchemy as sa

revision = "20260728_0029"
down_revision = "20260728_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("connector_configs") as batch:
        batch.add_column(
            sa.Column("session_status", sa.String(length=32), nullable=False, server_default="unknown")
        )
        batch.add_column(
            sa.Column("session_identity_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("session_checked_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "review_bundles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bundle_type", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_entity_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("section_type", sa.String(length=80), nullable=True),
        sa.Column("aggregate_key", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(length=24), nullable=True),
        sa.Column("resolution_reason", sa.String(length=500), nullable=True),
        sa.Column("resolved_by", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bundle_type", "source_type", "source_entity_id", "section_type", "aggregate_key",
            name="uq_review_bundle_source",
        ),
    )
    op.create_index(
        "ix_review_bundles_queue", "review_bundles", ["status", "priority", "created_at"]
    )
    op.create_table(
        "review_bundle_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bundle_id", sa.String(length=36), nullable=False),
        sa.Column("review_task_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("required", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["review_bundles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_task_id"], ["review_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", "review_task_id", name="uq_review_bundle_task"),
    )
    op.create_index(
        "ix_review_bundle_items_bundle_order",
        "review_bundle_items",
        ["bundle_id", "display_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_bundle_items_bundle_order", table_name="review_bundle_items")
    op.drop_table("review_bundle_items")
    op.drop_index("ix_review_bundles_queue", table_name="review_bundles")
    op.drop_table("review_bundles")
    with op.batch_alter_table("connector_configs") as batch:
        batch.drop_column("session_checked_at")
        batch.drop_column("session_identity_json")
        batch.drop_column("session_status")
