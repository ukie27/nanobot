"""Add application resume binding and acceptance lifecycle.

Revision ID: 20260729_0031
Revises: 20260728_0030
"""

import sqlalchemy as sa
from alembic import op

revision = "20260729_0031"
down_revision = "20260728_0030"
branch_labels = None
depends_on = None

_NAMING_CONVENTION = {
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


def upgrade() -> None:
    op.execute(
        "UPDATE job_recommendations SET status = 'accepted' WHERE status = 'applied'"
    )
    with op.batch_alter_table(
        "job_recommendations", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("ck_job_recommendation_status", type_="check")
        batch.create_check_constraint(
            "ck_job_recommendation_status",
            "status IN ('active','accepted','dismissed','stale')",
        )

    with op.batch_alter_table(
        "applications", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("uq_applications_job_post_id", type_="unique")

    op.create_table(
        "resume_defaults",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("resume_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resume_id", name="uq_resume_defaults_resume_id"),
    )
    op.create_table(
        "application_resume_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("resume_id", sa.String(length=36), nullable=False),
        sa.Column("resume_version_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("replaced_by_binding_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active','replaced','locked')",
            name="ck_application_resume_binding_status",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_binding_id"],
            ["application_resume_bindings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["resume_version_id"], ["resume_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_application_active_resume_binding",
        "application_resume_bindings",
        ["application_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_application_resume_bindings_history",
        "application_resume_bindings",
        ["application_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_resume_bindings_history",
        table_name="application_resume_bindings",
    )
    op.drop_index(
        "uq_application_active_resume_binding",
        table_name="application_resume_bindings",
    )
    op.drop_table("application_resume_bindings")
    op.drop_table("resume_defaults")

    with op.batch_alter_table(
        "applications", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.create_unique_constraint(
            "uq_applications_job_post_id", ["job_post_id"]
        )

    op.execute(
        "UPDATE job_recommendations SET status = 'applied' WHERE status = 'accepted'"
    )
    with op.batch_alter_table(
        "job_recommendations", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint("ck_job_recommendation_status", type_="check")
        batch.create_check_constraint(
            "ck_job_recommendation_status",
            "status IN ('active','applied','dismissed','stale')",
        )
