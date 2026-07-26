"""Programmatic Alembic entry points used by CLI and application startup."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext

from career_console.infrastructure.database.engine import Database
from career_console.infrastructure.settings import CareerSettings


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def migration_resources() -> tuple[Path, Path]:
    """Resolve migrations in a source checkout or an installed wheel."""
    source_root = project_root()
    source_migrations = source_root / "migrations"
    if (source_migrations / "env.py").is_file():
        return source_root / "alembic.ini", source_migrations

    package_root = Path(__file__).resolve().parents[2]
    return package_root / "alembic.ini", package_root / "migrations"


def alembic_config(settings: CareerSettings) -> Config:
    ini_path, migrations_path = migration_resources()
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(migrations_path))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def upgrade_to_head(settings: CareerSettings) -> None:
    settings.ensure_directories()
    command.upgrade(alembic_config(settings), "head")


def current_revision(database: Database) -> str | None:
    with database.engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def head_revision(settings: CareerSettings) -> str:
    from alembic.script import ScriptDirectory

    revision = ScriptDirectory.from_config(alembic_config(settings)).get_current_head()
    if revision is None:
        raise RuntimeError("Alembic migration head is missing")
    return revision
