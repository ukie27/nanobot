"""Consistent SQLite backup helpers used by CLI and automatic upgrades."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from nanobot.career.infrastructure.settings import CareerSettings


def database_revision(path: Path) -> str | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            if table is None:
                return None
            row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
            return str(row[0]) if row else None
    except sqlite3.Error:
        return None


def backup_database(settings: CareerSettings, *, label: str = "manual") -> Path:
    if not settings.database_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {settings.database_path}")
    settings.ensure_directories()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_label = "".join(character for character in label if character.isalnum() or character == "-")
    destination = settings.backups_dir / f"career-{stamp}-{safe_label or 'backup'}.sqlite3"
    with sqlite3.connect(settings.database_path) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
    return destination
