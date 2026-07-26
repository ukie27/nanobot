"""Unify AgentRun audit metadata and ReviewTask projections.

Revision ID: 20260726_0013
Revises: 20260726_0012
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0013"
down_revision = "20260726_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(
            sa.Column(
                "execution_mode", sa.String(24), nullable=False, server_default="task"
            )
        )
        batch.add_column(sa.Column("correlation_id", sa.String(100)))
        batch.add_column(sa.Column("provider", sa.String(100)))
        batch.add_column(sa.Column("model", sa.String(200)))
        batch.add_column(sa.Column("prompt_version", sa.String(100)))
        batch.add_column(sa.Column("skill_version", sa.String(100)))
        batch.add_column(sa.Column("input_entity_type", sa.String(80)))
        batch.add_column(sa.Column("input_entity_id", sa.String(100)))
        batch.add_column(sa.Column("input_revision", sa.String(100)))
        batch.add_column(sa.Column("input_hash", sa.String(64)))
        batch.add_column(sa.Column("output_hash", sa.String(64)))
        batch.add_column(
            sa.Column(
                "tool_calls_json", sa.Text(), nullable=False, server_default="[]"
            )
        )
        batch.add_column(sa.Column("input_tokens", sa.Integer()))
        batch.add_column(sa.Column("output_tokens", sa.Integer()))
        batch.add_column(sa.Column("duration_ms", sa.Integer()))
        batch.add_column(
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "sensitivity", sa.String(24), nullable=False, server_default="private"
            )
        )
        batch.add_column(sa.Column("retention_until", sa.DateTime(timezone=True)))
        batch.create_index("ix_agent_runs_task_created", ["task_type", "created_at"])
        batch.create_index("ix_agent_runs_status_created", ["status", "created_at"])

    with op.batch_alter_table("review_tasks") as batch:
        batch.add_column(sa.Column("title", sa.String(300)))
        batch.add_column(sa.Column("summary", sa.Text()))
        batch.add_column(sa.Column("source_type", sa.String(80)))
        batch.add_column(
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("agent_run_id", sa.String(36))
        )
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True)))
        batch.create_index(
            "ix_review_tasks_queue", ["status", "priority", "created_at"]
        )
        batch.create_index("ix_review_tasks_agent_run", ["agent_run_id"])
        batch.create_foreign_key(
            "fk_review_tasks_agent_run_id",
            "agent_runs",
            ["agent_run_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("review_tasks") as batch:
        batch.drop_constraint("fk_review_tasks_agent_run_id", type_="foreignkey")
        batch.drop_index("ix_review_tasks_agent_run")
        batch.drop_index("ix_review_tasks_queue")
        batch.drop_column("updated_at")
        batch.drop_column("agent_run_id")
        batch.drop_column("priority")
        batch.drop_column("source_type")
        batch.drop_column("summary")
        batch.drop_column("title")

    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_index("ix_agent_runs_status_created")
        batch.drop_index("ix_agent_runs_task_created")
        batch.drop_column("retention_until")
        batch.drop_column("sensitivity")
        batch.drop_column("retry_count")
        batch.drop_column("duration_ms")
        batch.drop_column("output_tokens")
        batch.drop_column("input_tokens")
        batch.drop_column("tool_calls_json")
        batch.drop_column("output_hash")
        batch.drop_column("input_hash")
        batch.drop_column("input_revision")
        batch.drop_column("input_entity_id")
        batch.drop_column("input_entity_type")
        batch.drop_column("skill_version")
        batch.drop_column("prompt_version")
        batch.drop_column("model")
        batch.drop_column("provider")
        batch.drop_column("correlation_id")
        batch.drop_column("execution_mode")
