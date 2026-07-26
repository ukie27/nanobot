"""Add structured profile business memory.

Revision ID: 20260726_0016
Revises: 20260726_0015
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0016"
down_revision = "20260726_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("career_preferences",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("profile_id", sa.String(36), sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("preference_key", sa.String(100), nullable=False), sa.Column("value_json", sa.Text(), nullable=False), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "preference_key", name="uq_career_preference_key"))
    op.create_table("profile_change_events",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("profile_id", sa.String(36), sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False), sa.Column("entity_type", sa.String(80), nullable=False), sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("entity_revision", sa.Integer(), nullable=False), sa.Column("changed_fields_json", sa.Text(), nullable=False), sa.Column("impact_scopes_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_profile_change_events_time", "profile_change_events", ["profile_id", "occurred_at"])
    op.create_table("profile_insight_proposals",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("profile_id", sa.String(36), sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insight_type", sa.String(64), nullable=False), sa.Column("conclusion", sa.Text(), nullable=False), sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("counter_evidence_json", sa.Text(), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("source", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="SET NULL")), sa.Column("resolution_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.create_index("ix_profile_insights_review", "profile_insight_proposals", ["status", "created_at"])
    op.create_table("strategy_snapshots",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("profile_id", sa.String(36), sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False), sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False), sa.Column("evidence_refs_json", sa.Text(), nullable=False), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("resolution_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("profile_id", "version_number", name="uq_strategy_snapshot_version"))
    op.create_index("ix_strategy_snapshots_status", "strategy_snapshots", ["status", "created_at"])
    op.create_table("daily_digests",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("profile_id", sa.String(36), sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("digest_date", sa.String(10), nullable=False), sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False), sa.Column("input_hash", sa.String(64), nullable=False), sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "digest_date", name="uq_daily_digest_date"))


def downgrade() -> None:
    op.drop_table("daily_digests")
    op.drop_index("ix_strategy_snapshots_status", table_name="strategy_snapshots")
    op.drop_table("strategy_snapshots")
    op.drop_index("ix_profile_insights_review", table_name="profile_insight_proposals")
    op.drop_table("profile_insight_proposals")
    op.drop_index("ix_profile_change_events_time", table_name="profile_change_events")
    op.drop_table("profile_change_events")
    op.drop_table("career_preferences")
