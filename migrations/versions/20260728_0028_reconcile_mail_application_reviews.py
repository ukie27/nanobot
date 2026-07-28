"""Resolve stale create-application reviews after an application is linked.

Revision ID: 20260728_0028
Revises: 20260728_0027
"""

from alembic import op

revision = "20260728_0028"
down_revision = "20260728_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE mail_intelligence_analyses
        SET create_record_recommended = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE application_id IS NOT NULL
          AND create_record_recommended <> 0
        """
    )
    op.execute(
        """
        UPDATE mail_intelligence_items
        SET status = 'confirmed',
            version = version + 1,
            resolution_reason = '已从该邮件建立正式申请档案。',
            resolved_at = CURRENT_TIMESTAMP
        WHERE item_type = 'create_application'
          AND status = 'pending'
          AND analysis_id IN (
              SELECT id
              FROM mail_intelligence_analyses
              WHERE application_id IS NOT NULL
          )
        """
    )
    op.execute(
        """
        UPDATE review_tasks
        SET status = 'resolved',
            version = version + 1,
            updated_at = CURRENT_TIMESTAMP,
            resolved_at = CURRENT_TIMESTAMP,
            resolution = 'confirmed',
            resolution_reason = '已从该邮件建立正式申请档案。',
            resolved_by = 'system'
        WHERE entity_type = 'mail_intelligence_item'
          AND status = 'open'
          AND entity_id IN (
              SELECT id
              FROM mail_intelligence_items
              WHERE item_type = 'create_application'
                AND status = 'confirmed'
          )
        """
    )


def downgrade() -> None:
    # A linked application is durable business state; reopening the obsolete
    # create-record review during downgrade would be misleading.
    pass
