"""SQLite engine configuration and diagnostics."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from career_console.infrastructure.settings import CareerSettings


class Database:
    """Own the SQLAlchemy engine and session factory for one Career instance."""

    def __init__(self, settings: CareerSettings) -> None:
        settings.ensure_directories()
        self.settings = settings
        self.engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False, "timeout": 5},
            pool_pre_ping=True,
        )
        self._configure_sqlite(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )

    @staticmethod
    def _configure_sqlite(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def ready(self) -> tuple[bool, str]:
        try:
            with self.engine.connect() as connection:
                value = connection.execute(text("PRAGMA quick_check")).scalar_one()
            return value == "ok", str(value)
        except Exception as exc:  # readiness must convert infrastructure errors
            return False, type(exc).__name__

    def pragmas(self) -> dict[str, str | int]:
        names = ("journal_mode", "foreign_keys", "busy_timeout", "synchronous")
        with self.engine.connect() as connection:
            return {name: connection.execute(text(f"PRAGMA {name}")).scalar_one() for name in names}

    def close(self) -> None:
        self.engine.dispose()


def sqlite_url(path: Path) -> str:
    """Build a SQLAlchemy SQLite URL that also works with Windows paths."""
    return f"sqlite:///{path.resolve(strict=False).as_posix()}"
