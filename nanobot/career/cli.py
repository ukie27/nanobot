"""Operational CLI for the local Career application."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from nanobot import __version__
from nanobot.career.infrastructure.connectors import OpenCliError, OpenCliProcessRunner
from nanobot.career.infrastructure.database import Database
from nanobot.career.infrastructure.database.backup import backup_database, restore_database
from nanobot.career.infrastructure.database.governance_gateway import (
    SqlAlchemyGovernanceGateway,
)
from nanobot.career.infrastructure.database.migrations import (
    current_revision,
    head_revision,
    migration_resources,
    upgrade_to_head,
)
from nanobot.career.infrastructure.database.models import ConnectorConfigModel
from nanobot.career.infrastructure.logging import configure_logging
from nanobot.career.infrastructure.runtime import CareerInstanceLock
from nanobot.career.infrastructure.runtime.instance_lock import InstanceAlreadyRunningError
from nanobot.career.infrastructure.secrets import KeyringSecretStore
from nanobot.career.infrastructure.settings import CareerSettings

app = typer.Typer(
    name="career",
    help="Local-first Career application commands.",
    no_args_is_help=True,
)
db_app = typer.Typer(name="db", help="Career database operations.", no_args_is_help=True)
data_app = typer.Typer(name="data", help="Career data governance.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(data_app, name="data")
console = Console()


def _settings(data_dir: Path | None = None) -> CareerSettings:
    values = {"data_dir": data_dir} if data_dir is not None else {}
    return CareerSettings(**values)


def _ensure_loopback(host: str) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        console.print("[red]Career currently supports loopback binding only.[/red]")
        raise typer.Exit(2)


@app.command()
def setup(
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Create local directories, back up an old database, and migrate to the current release."""
    settings = _settings(data_dir)
    settings.ensure_directories()
    if settings.database_path.exists() and settings.database_path.stat().st_size:
        backup = backup_database(settings, label="pre-setup")
        console.print(f"[dim]Pre-setup backup: {backup}[/dim]")
    upgrade_to_head(settings)
    console.print(f"[green]Career setup complete.[/green] Data: {settings.data_dir}")
    console.print(f"[dim]Database revision: {head_revision(settings)}[/dim]")
    console.print(f"[dim]Backups: {settings.backups_dir}[/dim]")
    console.print(f"[dim]Exports: {settings.exports_dir}[/dim]")
    console.print("Start with: python -m nanobot career serve")


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
    log_path = configure_logging(
        settings.logs_dir,
        level=settings.log_level,
        verbose=verbose,
        retention_days=settings.log_retention_days,
    )

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
    connector_required = False
    nowcoder_required = False
    checks.append(("Python", sys.version.split()[0], ">= 3.11", sys.version_info >= (3, 11)))

    try:
        settings.ensure_directories()
        probe = settings.runtime_dir / ".write-probe"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        checks.append(("Data directory", str(settings.data_dir), "writable", True))
    except OSError as exc:
        checks.append(("Data directory", type(exc).__name__, "writable", False))

    controlled_dirs = (
        settings.runtime_dir,
        settings.logs_dir,
        settings.backups_dir,
        settings.blobs_dir,
        settings.exports_dir,
    )
    checks.append(
        (
            "Governance directories",
            f"{sum(path.is_dir() for path in controlled_dirs)}/{len(controlled_dirs)} ready",
            "runtime/logs/backups/blobs/exports",
            all(path.is_dir() for path in controlled_dirs),
        )
    )

    web_index = settings.web_dist_dir / "index.html"
    web_assets = settings.web_dist_dir / "assets"
    web_ready = web_index.is_file() and web_assets.is_dir() and any(web_assets.iterdir())
    checks.append(("Web resources", str(settings.web_dist_dir), "built and packaged", web_ready))
    try:
        migration_ini, migration_dir = migration_resources()
        migrations_ready = migration_ini.is_file() and (migration_dir / "env.py").is_file()
        migration_actual = str(migration_dir)
    except OSError as exc:
        migrations_ready = False
        migration_actual = type(exc).__name__
    checks.append(("Migration resources", migration_actual, "available", migrations_ready))
    checks.append(
        (
            "Browser security",
            f"loopback={settings.host in {'127.0.0.1', 'localhost', '::1'}}",
            "loopback-only + CSRF/Origin/CSP",
            settings.host in {"127.0.0.1", "localhost", "::1"},
        )
    )

    if settings.database_path.exists():
        try:
            database = Database(settings)
            healthy, detail = database.ready()
            revision = current_revision(database)
            expected = head_revision(settings)
            checks.append(("Database", detail, "quick_check=ok", healthy))
            checks.append(("DB revision", revision or "none", expected, revision == expected))
            if revision == expected:
                with database.session_factory() as session:
                    connector = session.get(
                        ConnectorConfigModel, "00000000-0000-0000-0000-000000000006"
                    )
                    connector_required = bool(connector and connector.enabled)
                    nowcoder = session.get(
                        ConnectorConfigModel, "00000000-0000-0000-0000-000000000007"
                    )
                    nowcoder_required = bool(nowcoder and nowcoder.enabled)
            database.close()
        except Exception as exc:
            checks.append(("Database", type(exc).__name__, "healthy", False))
    else:
        checks.append(("Database", "not initialized", "run db migrate", True))

    node = shutil.which("node")
    node_version = "not found"
    node_ok = False
    if node:
        try:
            node_version = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=5, check=False
            ).stdout.strip()
            node_ok = int(node_version.lstrip("v").split(".", 1)[0]) >= 20
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    checks.append(
        (
            "Node.js",
            node_version,
            ">= 20 when an OpenCLI Connector is enabled",
            node_ok or not (connector_required or nowcoder_required),
        )
    )
    runner = OpenCliProcessRunner(settings.opencli_executable)
    opencli_version = "not installed"
    opencli_ok = False
    if runner.installed:
        try:
            opencli_version = runner.version()
            opencli_ok = True
        except OpenCliError as exc:
            opencli_version = exc.code
    checks.append(
        (
            "OpenCLI",
            opencli_version,
            "available when an OpenCLI Connector is enabled",
            opencli_ok or not (connector_required or nowcoder_required),
        )
    )
    if nowcoder_required and opencli_ok:
        try:
            runner.nowcoder_schedule(lookback_days=0, limit=1)
            checks.append(("Nowcoder plugin", "schedule available", "read-only command", True))
        except OpenCliError as exc:
            checks.append(("Nowcoder plugin", exc.code, "read-only command", False))
    checks.append(("Web port", str(settings.port), "available", _port_available(settings.port)))

    table = Table(title="Nanobot Career doctor")
    table.add_column("Check")
    table.add_column("Actual")
    table.add_column("Expected")
    table.add_column("Result")
    for name, actual, expected, passed in checks:
        table.add_row(
            name, actual, expected, "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        )
    console.print(table)
    console.print(
        "[dim]OpenCLI remains external; Career-owned site commands are loaded as local plugins.[/dim]"
    )
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
    settings.ensure_directories()
    try:
        destination = backup_database(settings)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Backup created:[/green] {destination}")


@db_app.command("restore")
def db_restore(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    confirmation: str = typer.Option("", "--confirm", help="Required value: RESTORE"),
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Restore a validated SQLite backup or full bundle while the server is stopped."""
    if confirmation != "RESTORE":
        console.print("[red]Restore requires --confirm RESTORE.[/red]")
        raise typer.Exit(2)
    settings = _settings(data_dir)
    try:
        with CareerInstanceLock(settings.instance_lock_path):
            recovery_bundle = None
            if settings.database_path.exists() and settings.database_path.stat().st_size:
                current_database = Database(settings)
                try:
                    recovery_bundle = SqlAlchemyGovernanceGateway(
                        current_database.session_factory,
                        settings=settings,
                        secrets=KeyringSecretStore(),
                    ).create_backup_bundle()["path"]
                finally:
                    current_database.close()
            previous, restored_revision = restore_database(settings, source)
            upgrade_to_head(settings)
    except InstanceAlreadyRunningError as exc:
        console.print("[red]Stop the Career server before restoring a backup.[/red]")
        raise typer.Exit(1) from exc
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as exc:
        console.print(f"[red]Restore failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Database restored and migrated from revision:[/green] {restored_revision}")
    if previous:
        console.print(f"[dim]Pre-restore recovery backup: {previous}[/dim]")
    if recovery_bundle:
        console.print(f"[dim]Pre-restore full recovery bundle: {recovery_bundle}[/dim]")


def _governance(settings: CareerSettings) -> tuple[Database, SqlAlchemyGovernanceGateway]:
    database = Database(settings)
    gateway = SqlAlchemyGovernanceGateway(
        database.session_factory,
        settings=settings,
        secrets=KeyringSecretStore(),
    )
    return database, gateway


@data_app.command("backup")
def data_backup(
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Create a full database, Blob, export, and checksum bundle."""
    settings = _settings(data_dir)
    database, gateway = _governance(settings)
    try:
        result = gateway.create_backup_bundle()
    finally:
        database.close()
    console.print(f"[green]Full backup created:[/green] {result['path']}")


@data_app.command("export")
def data_export(
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Export all Career business tables to UTF-8 JSON without Keyring secrets."""
    settings = _settings(data_dir)
    database, gateway = _governance(settings)
    try:
        result = gateway.export_user_data()
    finally:
        database.close()
    console.print(f"[green]Data exported:[/green] {result['path']}")


@data_app.command("gc")
def data_gc(
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Career data directory."),
) -> None:
    """Remove unreferenced Blob files and expired Agent traces."""
    settings = _settings(data_dir)
    database, gateway = _governance(settings)
    try:
        result = gateway.garbage_collect()
    finally:
        database.close()
    console.print(
        f"[green]Garbage collection complete:[/green] "
        f"{result['removed_files']} files, {result['removed_agent_traces']} traces"
    )


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True
