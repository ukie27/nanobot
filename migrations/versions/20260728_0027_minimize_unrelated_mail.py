"""Remove previously persisted body evidence from unrelated mail.

Revision ID: 20260728_0027
Revises: 20260726_0026
"""

from alembic import op

revision = "20260728_0027"
down_revision = "20260726_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE mail_messages
        SET event_kind = NULL,
            extracted_json = '{}',
            evidence_excerpt = NULL,
            body_hash = NULL,
            attachments_json = '[]',
            body_fetched = 0
        WHERE classification = 'unrelated'
        """
    )


def downgrade() -> None:
    # Removed private body evidence cannot and should not be reconstructed.
    pass
