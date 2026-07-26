"""Separate recruitment opportunities from concrete job posts.

Revision ID: 20260726_0011
Revises: 20260724_0010
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0011"
down_revision = "20260724_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recruitment_opportunities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company", sa.String(300), nullable=False),
        sa.Column("batch", sa.String(300), nullable=False),
        sa.Column("cities", sa.Text(), nullable=False),
        sa.Column("careers", sa.Text(), nullable=False),
        sa.Column("industries", sa.Text(), nullable=False),
        sa.Column("evaluation", sa.Text(), nullable=False),
        sa.Column("application_starts_at", sa.DateTime(timezone=True)),
        sa.Column("application_ends_at", sa.DateTime(timezone=True)),
        sa.Column("announcement_url", sa.Text()),
        sa.Column("application_url", sa.Text(), nullable=False),
        sa.Column("triage_status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("first_collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "triage_status IN ('new','following','ignored')",
            name="ck_opportunity_triage_status",
        ),
    )
    op.create_index(
        "ix_opportunities_triage",
        "recruitment_opportunities",
        ["triage_status", "last_collected_at"],
    )
    op.create_table(
        "opportunity_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(36),
            sa.ForeignKey("recruitment_opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connector_id",
            sa.String(36),
            sa.ForeignKey("connector_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "connector_id", "external_id", name="uq_opportunity_source_external"
        ),
    )
    op.create_index(
        "ix_opportunity_sources_opportunity", "opportunity_sources", ["opportunity_id"]
    )
    op.create_table(
        "opportunity_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(36),
            sa.ForeignKey("recruitment_opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_event_id",
            sa.String(36),
            sa.ForeignKey("source_events.id", ondelete="SET NULL"),
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "opportunity_id", "version_number", name="uq_opportunity_version_number"
        ),
    )
    op.create_index(
        "ix_opportunity_versions_opportunity",
        "opportunity_versions",
        ["opportunity_id", "version_number"],
    )
    with op.batch_alter_table("source_events") as batch:
        batch.add_column(sa.Column("opportunity_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_source_events_opportunity_id",
            "recruitment_opportunities",
            ["opportunity_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("source_events") as batch:
        batch.drop_constraint("fk_source_events_opportunity_id", type_="foreignkey")
        batch.drop_column("opportunity_id")
    op.drop_index("ix_opportunity_versions_opportunity", table_name="opportunity_versions")
    op.drop_table("opportunity_versions")
    op.drop_index("ix_opportunity_sources_opportunity", table_name="opportunity_sources")
    op.drop_table("opportunity_sources")
    op.drop_index("ix_opportunities_triage", table_name="recruitment_opportunities")
    op.drop_table("recruitment_opportunities")
