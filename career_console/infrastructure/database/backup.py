"""Consistent SQLite backup helpers used by CLI and automatic upgrades."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from career_console.infrastructure.settings import CareerSettings


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
    safe_label = "".join(
        character for character in label if character.isalnum() or character == "-"
    )
    destination = settings.backups_dir / f"career-{stamp}-{safe_label or 'backup'}.sqlite3"
    with sqlite3.connect(settings.database_path) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
    return destination


def restore_database(settings: CareerSettings, source: Path) -> tuple[Path | None, str | None]:
    """Atomically restore a validated SQLite file or Career full-backup bundle."""
    source = source.expanduser().resolve(strict=True)
    settings.ensure_directories()
    handle, temporary_name = tempfile.mkstemp(
        prefix="career-restore-", suffix=".sqlite3", dir=settings.runtime_dir
    )
    os.close(handle)
    temporary = Path(temporary_name)
    staged_root = Path(tempfile.mkdtemp(prefix="career-restore-files-", dir=settings.runtime_dir))
    restore_files = False
    try:
        if source.suffix.casefold() == ".zip":
            with zipfile.ZipFile(source) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                for archive_name, metadata in manifest["files"].items():
                    if archive_name != "career.sqlite3" and not archive_name.startswith(
                        ("blobs/", "exports/")
                    ):
                        raise ValueError("Backup bundle contains an unsupported file path.")
                    relative = Path(archive_name)
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("Backup bundle contains an unsafe file path.")
                    content = archive.read(archive_name)
                    if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
                        raise ValueError(f"Backup checksum mismatch: {archive_name}")
                    if archive_name == "career.sqlite3":
                        temporary.write_bytes(content)
                    else:
                        destination = staged_root / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(content)
                restore_files = True
        else:
            shutil.copy2(source, temporary)
        if temporary.stat().st_size == 0:
            raise ValueError("Backup does not contain a Career database.")
        with sqlite3.connect(f"file:{temporary.as_posix()}?mode=ro", uri=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise ValueError("Backup database failed SQLite quick_check.")
        restored_revision = database_revision(temporary)
        previous = (
            backup_database(settings, label="pre-restore")
            if settings.database_path.exists() and settings.database_path.stat().st_size
            else None
        )
        os.replace(temporary, settings.database_path)
        if restore_files:
            for name, destination in (
                ("blobs", settings.blobs_dir),
                ("exports", settings.exports_dir),
            ):
                shutil.rmtree(destination, ignore_errors=True)
                staged = staged_root / name
                if staged.exists():
                    shutil.move(str(staged), destination)
                else:
                    destination.mkdir(parents=True, exist_ok=True)
        return previous, restored_revision
    finally:
        temporary.unlink(missing_ok=True)
        shutil.rmtree(staged_root, ignore_errors=True)
