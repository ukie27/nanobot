"""Link mail analyses to imported jobs and applications.

Revision ID: 20260726_0015
Revises: 20260726_0014
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260726_0015"
down_revision = "20260726_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mail_intelligence_analyses") as batch:
        batch.add_column(sa.Column("job_post_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_mail_analysis_job_post", "job_posts", ["job_post_id"], ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_mail_analysis_job_post", ["job_post_id"])


def downgrade() -> None:
    with op.batch_alter_table("mail_intelligence_analyses") as batch:
        batch.drop_index("ix_mail_analysis_job_post")
        batch.drop_constraint("fk_mail_analysis_job_post", type_="foreignkey")
        batch.drop_column("job_post_id")
