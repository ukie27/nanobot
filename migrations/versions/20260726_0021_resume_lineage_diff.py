"""Add base, direction and job-tailored resume lineage.

Revision ID: 20260726_0021
Revises: 20260726_0020
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0021"
down_revision = "20260726_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.add_column(sa.Column("series_type", sa.String(24), nullable=False, server_default="base"))
        batch.add_column(sa.Column("parent_resume_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("direction_label", sa.String(120), nullable=True))
        batch.create_foreign_key("fk_resumes_parent", "resumes", ["parent_resume_id"], ["id"], ondelete="RESTRICT")
    with op.batch_alter_table("material_drafts") as batch:
        batch.add_column(sa.Column("source_resume_version_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("resume_direction_selection_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_material_source_version", "resume_versions", ["source_resume_version_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_material_direction_selection", "resume_direction_selections", ["resume_direction_selection_id"], ["id"], ondelete="RESTRICT")
    with op.batch_alter_table("resume_versions") as batch:
        batch.alter_column("material_draft_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("source_resume_version_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("version_scope", sa.String(24), nullable=False, server_default="job_tailored"))
        batch.create_foreign_key("fk_resume_version_source", "resume_versions", ["source_resume_version_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    with op.batch_alter_table("resume_versions") as batch:
        batch.drop_constraint("fk_resume_version_source", type_="foreignkey")
        batch.drop_column("version_scope")
        batch.drop_column("source_resume_version_id")
        batch.alter_column("material_draft_id", existing_type=sa.String(36), nullable=False)
    with op.batch_alter_table("material_drafts") as batch:
        batch.drop_constraint("fk_material_direction_selection", type_="foreignkey")
        batch.drop_constraint("fk_material_source_version", type_="foreignkey")
        batch.drop_column("resume_direction_selection_id")
        batch.drop_column("source_resume_version_id")
    with op.batch_alter_table("resumes") as batch:
        batch.drop_constraint("fk_resumes_parent", type_="foreignkey")
        batch.drop_column("direction_label")
        batch.drop_column("parent_resume_id")
        batch.drop_column("series_type")
