"""Split the legacy shared Nowcoder and IMAP connector identity.

Revision ID: 20260726_0024
Revises: 20260726_0023
Create Date: 2026-07-26
"""

from alembic import op
from sqlalchemy import text

revision = "20260726_0024"
down_revision = "20260726_0023"
branch_labels = None
depends_on = None

LEGACY_ID = "00000000-0000-0000-0000-000000000007"
NOWCODER_ID = "00000000-0000-0000-0000-000000000008"


def upgrade() -> None:
    connection = op.get_bind()
    legacy = connection.execute(text(
        "SELECT * FROM connector_configs WHERE id = :id"
    ), {"id": LEGACY_ID}).mappings().first()
    if legacy is None or legacy["connector_type"] != "opencli_nowcoder":
        return
    values = dict(legacy)
    values["id"] = NOWCODER_ID
    columns = ", ".join(values)
    parameters = ", ".join(f":{name}" for name in values)
    connection.execute(
        text(f"INSERT INTO connector_configs ({columns}) VALUES ({parameters})"),
        values,
    )
    has_imap = connection.execute(text(
        "SELECT 1 FROM imap_accounts WHERE connector_id = :id LIMIT 1"
    ), {"id": LEGACY_ID}).first() is not None
    if has_imap:
        connection.execute(text(
            "UPDATE connector_configs SET connector_type = 'imap_readonly', "
            "display_name = '只读招聘邮箱' WHERE id = :id"
        ), {"id": LEGACY_ID})
        connection.execute(text(
            "UPDATE sync_runs SET connector_id = :new_id WHERE id IN "
            "(SELECT sync_run_id FROM source_events WHERE connector_id = :old_id)"
        ), {"new_id": NOWCODER_ID, "old_id": LEGACY_ID})
        connection.execute(text(
            "UPDATE source_events SET connector_id = :new_id WHERE connector_id = :old_id"
        ), {"new_id": NOWCODER_ID, "old_id": LEGACY_ID})
        connection.execute(text(
            "UPDATE sync_cursors SET connector_id = :new_id "
            "WHERE connector_id = :old_id AND cursor_key = 'last_completed_at'"
        ), {"new_id": NOWCODER_ID, "old_id": LEGACY_ID})
        return
    for table in ("sync_runs", "source_events", "sync_cursors"):
        connection.execute(text(
            f"UPDATE {table} SET connector_id = :new_id WHERE connector_id = :old_id"
        ), {"new_id": NOWCODER_ID, "old_id": LEGACY_ID})
    connection.execute(
        text("DELETE FROM connector_configs WHERE id = :id"), {"id": LEGACY_ID}
    )


def downgrade() -> None:
    # This revision repairs ambiguous production data. Re-merging two identities would
    # corrupt IMAP state, so a downgrade deliberately preserves the safe split rows.
    pass
