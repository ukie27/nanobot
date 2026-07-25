"""Read-only IMAP connector and message center.

Revision ID: 20260724_0008
Revises: 20260724_0007
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0008"
down_revision = "20260724_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imap_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connector_id",
            sa.String(36),
            sa.ForeignKey("connector_configs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(320), nullable=False),
        sa.Column("secret_ref", sa.String(500), nullable=False),
        sa.Column("folder", sa.String(255), nullable=False),
        sa.Column("initial_lookback_days", sa.Integer(), nullable=False),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "initial_lookback_days BETWEEN 1 AND 30",
            name="ck_imap_lookback_days",
        ),
    )
    op.create_table(
        "mail_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("imap_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("uid_validity", sa.String(64), nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(998)),
        sa.Column("sender", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(998), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("event_kind", sa.String(32)),
        sa.Column("extracted_json", sa.Text(), nullable=False),
        sa.Column("evidence_excerpt", sa.Text()),
        sa.Column("body_hash", sa.String(64)),
        sa.Column("attachments_json", sa.Text(), nullable=False),
        sa.Column("body_fetched", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "uid_validity", "uid", name="uq_mail_uid"),
        sa.UniqueConstraint("account_id", "message_id", name="uq_mail_message_id"),
    )
    op.create_index("ix_mail_messages_center", "mail_messages", ["classification", "sent_at"])
    op.create_table(
        "mail_application_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mail_message_id",
            sa.String(36),
            sa.ForeignKey("mail_messages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "application_id",
            sa.String(36),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
        ),
        sa.Column("match_confidence", sa.Float()),
        sa.Column("match_reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("application_event_proposals.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_mail_candidates_review", "mail_application_candidates", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_mail_candidates_review", table_name="mail_application_candidates")
    op.drop_table("mail_application_candidates")
    op.drop_index("ix_mail_messages_center", table_name="mail_messages")
    op.drop_table("mail_messages")
    op.drop_table("imap_accounts")
