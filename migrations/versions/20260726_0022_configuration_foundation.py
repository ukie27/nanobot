"""Add unified configuration snapshots and change audit.

Revision ID: 20260726_0022
Revises: 20260726_0021
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0022"
down_revision = "20260726_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Earlier queue workers could concurrently persist the same deterministic
    # job-fit result. Repoint any review references, retain one row per input,
    # then enforce the invariant at the database boundary.
    with op.batch_alter_table("job_match_analyses") as batch:
        batch.add_column(sa.Column(
            "analysis_origin", sa.String(24), nullable=False,
            server_default="deterministic",
        ))
    op.execute("""
        UPDATE job_match_analyses
        SET analysis_origin = 'agent_confirmed'
        WHERE id IN (
            SELECT formal_analysis_id
            FROM job_fit_proposals
            WHERE formal_analysis_id IS NOT NULL
        )
    """)
    op.execute("""
        UPDATE job_fit_proposals
        SET formal_analysis_id = (
            SELECT MIN(keeper.id)
            FROM job_match_analyses AS current
            JOIN job_match_analyses AS keeper
              ON keeper.job_post_id = current.job_post_id
             AND keeper.job_post_version_id = current.job_post_version_id
             AND keeper.profile_id = current.profile_id
             AND keeper.fact_set_hash = current.fact_set_hash
             AND keeper.analysis_origin = current.analysis_origin
            WHERE current.id = job_fit_proposals.formal_analysis_id
        )
        WHERE formal_analysis_id IS NOT NULL
    """)
    op.execute("""
        DELETE FROM job_match_analyses
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM job_match_analyses
            GROUP BY job_post_id, job_post_version_id, profile_id,
                     fact_set_hash, analysis_origin
        )
    """)
    with op.batch_alter_table("job_match_analyses") as batch:
        batch.create_unique_constraint(
            "uq_job_match_analysis_input",
            [
                "job_post_id", "job_post_version_id", "profile_id",
                "fact_set_hash", "analysis_origin",
            ],
        )
    op.create_table(
        "configuration_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, unique=True),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "configuration_changes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(36),
            sa.ForeignKey("configuration_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("previous_revision", sa.Integer(), nullable=False),
        sa.Column("new_revision", sa.Integer(), nullable=False, unique=True),
        sa.Column("changed_paths_json", sa.Text(), nullable=False),
        sa.Column("activation_effect", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_configuration_changes_created",
        "configuration_changes",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_configuration_changes_created", table_name="configuration_changes")
    op.drop_table("configuration_changes")
    op.drop_table("configuration_snapshots")
    with op.batch_alter_table("job_match_analyses") as batch:
        batch.drop_constraint("uq_job_match_analysis_input", type_="unique")
        batch.drop_column("analysis_origin")
