"""Publish profile diagnostics automatically instead of creating review tasks.

Revision ID: 20260801_0034
Revises: 20260801_0033
"""

import sqlalchemy as sa
from alembic import op

revision = "20260801_0034"
down_revision = "20260801_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE profile_insight_proposals
        SET status = 'active',
            resolution_reason = NULL,
            resolved_at = NULL
        WHERE status = 'proposed'
    """))
    connection.execute(sa.text("""
        UPDATE strategy_snapshots
        SET status = 'active',
            resolution_reason = NULL,
            resolved_at = NULL
        WHERE status = 'proposed'
    """))
    connection.execute(sa.text("""
        UPDATE review_tasks
        SET status = 'resolved',
            version = version + 1,
            resolution = 'auto_published',
            resolution_reason = '洞察与策略改为自动发布，不再需要用户确认。',
            resolved_by = 'system',
            resolved_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'open'
          AND (
            (entity_type = 'profile_insight' AND task_type = 'profile_insight_review')
            OR (entity_type = 'strategy_snapshot' AND task_type = 'career_strategy_review')
          )
    """))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE profile_insight_proposals
        SET status = 'proposed'
        WHERE status = 'active'
          AND source = 'career_console_profile_insight'
    """))
    connection.execute(sa.text("""
        UPDATE strategy_snapshots
        SET status = 'proposed'
        WHERE status = 'active'
    """))
