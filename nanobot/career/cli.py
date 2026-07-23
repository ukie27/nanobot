"""Operational CLI for the local Career application."""

from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from nanobot import __version__
from nanobot.career.infrastructure.database import Database
from nanobot.career.infrastructure.database.backup import backup_database
from nanobot.career.infrastructure.database.migrations import (
    current_revision,
    head_revision,
    upgrade_to_head,
)
from nanobot.career.infrastructure.logging import configure_logging
from nanobot.career.infrastructure.runtime import CareerInstanceLock
from nanobot.career.infrastructure.runtime.instance_lock import InstanceAlreadyRunningError
from nanobot.career.infrastructure.settings import CareerSettings

app = typer.Typer(
    name="career",
    help="Local-first Career application commands.",
    no_args_is_help=True,
)
db_app = typer.Typer(name="db", help="Career database operations.", no_args_is_help=True)
app.add_typer(db_app, name="db")
console = Console()


def _settings(data_dir: Path | None = None) -> CareerSettings:
    values = {"data_dir": data_dir} if data_dir is not None else {}
    return CareerSettings(**values)


def _ensure_loopback(host: str) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        console.print("[red]Career currently supports loopback binding only.[/red]")
        raise typer.Exit(2)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Loopback bind address."),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
    verbose: bool = typer.Option(False, "--verbose", help="Also emit logs to the console."),
) -> None:
    """Migrate and start the local Career Web application."""
    _ensure_loopback(host)
    settings = _settings(data_dir).model_copy(update={"host": host, "port": port})
    settings.ensure_directories()
    log_path = configure_logging(settings.logs_dir, level=settings.log_level, verbose=verbose)

    import uvicorn

    from nanobot.career.api import create_app

    try:
        with CareerInstanceLock(settings.instance_lock_path):
            console.print(f"[green]Nanobot Career[/green] http://{host}:{port}")
            console.print(f"[dim]Data: {settings.data_dir}[/dim]")
            console.print(f"[dim]Logs: {log_path}[/dim]")
            uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
    except InstanceAlreadyRunningError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@app.command()
def doctor(
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Diagnose the local runtime without printing secrets."""
    settings = _settings(data_dir)
    checks: list[tuple[str, str, str, bool]] = []
    checks.append(("Python", sys.version.split()[0], ">= 3.11", sys.version_info >= (3, 11)))

    try:
        settings.ensure_directories()
        probe = settings.runtime_dir / ".write-probe"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        checks.append(("Data directory", str(settings.data_dir), "writable", True))
    except OSError as exc:
        checks.append(("Data directory", type(exc).__name__, "writable", False))

    if settings.database_path.exists():
        try:
            database = Database(settings)
            healthy, detail = database.ready()
            revision = current_revision(database)
            expected = head_revision(settings)
            checks.append(("Database", detail, "quick_check=ok", healthy))
            checks.append(("DB revision", revision or "none", expected, revision == expected))
            database.close()
        except Exception as exc:
            checks.append(("Database", type(exc).__name__, "healthy", False))
    else:
        checks.append(("Database", "not initialized", "run db migrate", True))

    node = shutil.which("node")
    checks.append(("Node.js", node or "not found", "optional after web build", True))
    opencli = shutil.which("opencli")
    checks.append(
        (
            "OpenCLI",
            opencli or "not installed",
            "external optional tool; Part 6",
            True,
        )
    )
    checks.append(("Web port", str(settings.port), "available", _port_available(settings.port)))

    table = Table(title="Nanobot Career doctor")
    table.add_column("Check")
    table.add_column("Actual")
    table.add_column("Expected")
    table.add_column("Result")
    for name, actual, expected, passed in checks:
        table.add_row(name, actual, expected, "[green]PASS[/green]" if passed else "[red]FAIL[/red]")
    console.print(table)
    console.print("[dim]OpenCLI is consumed as an external application; this project does not develop it.[/dim]")
    if not all(item[3] for item in checks):
        raise typer.Exit(1)


@app.command()
def status(
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Show local version, paths, and database state."""
    settings = _settings(data_dir)
    console.print(f"Nanobot Career v{__version__}")
    console.print(f"Data: {settings.data_dir}")
    if not settings.database_path.exists():
        console.print("Database: not initialized")
        return
    database = Database(settings)
    try:
        healthy, detail = database.ready()
        console.print(f"Database: {'ok' if healthy else detail}")
        console.print(f"Revision: {current_revision(database) or 'none'}")
    finally:
        database.close()


@db_app.command("migrate")
def db_migrate(
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Back up an existing database and migrate it to the current head."""
    settings = _settings(data_dir)
    if settings.database_path.exists() and settings.database_path.stat().st_size:
        backup = backup_database(settings, label="pre-migration")
        console.print(f"[dim]Pre-migration backup: {backup}[/dim]")
    upgrade_to_head(settings)
    database = Database(settings)
    try:
        console.print(f"[green]Database migrated:[/green] {current_revision(database)}")
    finally:
        database.close()


@db_app.command("backup")
def db_backup(
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Create a consistent SQLite backup."""
    settings = _settings(data_dir)
    try:
        destination = backup_database(settings)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Backup created:[/green] {destination}")


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True
