"""Tasks, reminders, schedules, notifications, and transactional outbox.

Revision ID: 20260724_0006
Revises: 20260724_0005
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0006"
down_revision = "20260724_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "career_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "application_id", sa.String(36), sa.ForeignKey("applications.id", ondelete="CASCADE")
        ),
        sa.Column("job_post_id", sa.String(36), sa.ForeignKey("job_posts.id", ondelete="CASCADE")),
        sa.Column(
            "source_event_id",
            sa.String(36),
            sa.ForeignKey("application_events.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column("source_key", sa.String(255), unique=True),
        sa.Column("task_type", sa.String(48), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_career_tasks_due", "career_tasks", ["status", "due_at"])
    op.create_table(
        "reminders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("career_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("offset_minutes", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "task_id", "offset_minutes", "generation", name="uq_task_reminder_generation"
        ),
    )
    op.create_index("ix_reminders_due", "reminders", ["status", "scheduled_for"])
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "reminder_id",
            sa.String(36),
            sa.ForeignKey("reminders.id", ondelete="CASCADE"),
            unique=True,
        ),
        sa.Column("schedule_type", sa.String(24), nullable=False),
        sa.Column("handler_type", sa.String(80), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_seconds", sa.Integer()),
        sa.Column("cron_expression", sa.String(100)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_schedules_due", "schedules", ["status", "next_run_at"])
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_outbox_dispatch", "outbox_events", ["status", "next_attempt_at"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "reminder_id",
            sa.String(36),
            sa.ForeignKey("reminders.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("notification_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notifications_status", "notifications", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_outbox_dispatch", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_schedules_due", table_name="schedules")
    op.drop_table("schedules")
    op.drop_index("ix_reminders_due", table_name="reminders")
    op.drop_table("reminders")
    op.drop_index("ix_career_tasks_due", table_name="career_tasks")
    op.drop_table("career_tasks")
