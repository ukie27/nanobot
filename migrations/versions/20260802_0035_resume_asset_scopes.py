"""Add reusable and application-owned resume asset scopes.

Revision ID: 20260802_0035
Revises: 20260801_0034
"""

import sqlalchemy as sa
from alembic import op

revision = "20260802_0035"
down_revision = "20260801_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.add_column(
            sa.Column("scope", sa.String(length=24), nullable=False, server_default="library")
        )
        batch.add_column(sa.Column("application_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("source_file_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_resumes_application_id",
            "applications",
            ["application_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_resume_scope", "scope IN ('library','application')"
        )
        batch.create_index(
            "ix_resumes_scope_active", ["scope", "retired_at", "updated_at"]
        )
        batch.create_index(
            "ix_resumes_application", ["application_id", "retired_at"]
        )

    with op.batch_alter_table("application_material_snapshots") as batch:
        batch.drop_constraint("uq_application_material", type_="unique")
        batch.alter_column(
            "material_draft_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch.create_unique_constraint(
            "uq_application_resume_snapshot",
            ["application_id", "resume_version_id"],
        )


def downgrade() -> None:
    # The previous schema cannot represent library-only submission snapshots.
    op.execute(
        sa.text(
            "DELETE FROM application_material_snapshots "
            "WHERE material_draft_id IS NULL"
        )
    )
    with op.batch_alter_table("application_material_snapshots") as batch:
        batch.drop_constraint("uq_application_resume_snapshot", type_="unique")
        batch.alter_column(
            "material_draft_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch.create_unique_constraint(
            "uq_application_material", ["application_id", "material_draft_id"]
        )

    with op.batch_alter_table("resumes") as batch:
        batch.drop_index("ix_resumes_application")
        batch.drop_index("ix_resumes_scope_active")
        batch.drop_constraint("ck_resume_scope", type_="check")
        batch.drop_constraint("fk_resumes_application_id", type_="foreignkey")
        batch.drop_column("retired_at")
        batch.drop_column("source_file_name")
        batch.drop_column("application_id")
        batch.drop_column("scope")
