"""Independent CareerConsole command line interface."""

from __future__ import annotations

import socket
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from career_console import __version__
from career_console.infrastructure.configuration import apply_stored_runtime_configuration
from career_console.infrastructure.database import Database
from career_console.infrastructure.database.backup import (
    backup_database,
    database_revision,
)
from career_console.infrastructure.database.migrations import (
    head_revision,
    upgrade_to_head,
)
from career_console.infrastructure.logging import configure_logging
from career_console.infrastructure.runtime import CareerInstanceLock
from career_console.infrastructure.runtime.instance_lock import InstanceAlreadyRunningError
from career_console.infrastructure.settings import CareerSettings
from career_console.infrastructure.workspace import WorkspaceManager

app = typer.Typer(
    name="career-console",
    help="CareerConsole local-first job search workspace.",
    no_args_is_help=True,
)
workspace_app = typer.Typer(name="workspace", help="Create and select workspaces.")
app.add_typer(workspace_app, name="workspace")
console = Console()


def _settings(workspace: Path | None) -> CareerSettings:
    manager = WorkspaceManager()
    root = manager.resolve_active(workspace)
    manager.ensure(root)
    return apply_stored_runtime_configuration(CareerSettings(data_dir=root))


@workspace_app.command("create")
def create_workspace(
    parent: Path = typer.Argument(..., help="Parent directory; CareerConsole is created below it."),
    name: str = typer.Option("CareerConsole", "--name"),
) -> None:
    manager = WorkspaceManager()
    try:
        manifest = manager.create(parent, name=name, activate=True)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Workspace could not be created:[/red] {exc}")
        raise typer.Exit(2) from exc
    root = manager.registry.active_workspace()
    console.print(f"[green]Workspace created:[/green] {root}")
    console.print(f"[dim]Workspace ID: {manifest.workspace_id}[/dim]")


@workspace_app.command("show")
def show_workspace() -> None:
    root = WorkspaceManager().resolve_active()
    console.print(f"CareerConsole workspace: {root}")


@app.command()
def setup(
    workspace: Path | None = typer.Option(None, "--workspace", help="Exact workspace path."),
) -> None:
    settings = _settings(workspace)
    if settings.database_path.is_file() and settings.database_path.stat().st_size:
        backup = backup_database(settings, label="pre-setup")
        console.print(f"[dim]Pre-setup backup: {backup}[/dim]")
    upgrade_to_head(settings)
    console.print("[green]CareerConsole setup complete.[/green]")
    console.print(f"Workspace: {settings.data_dir}")
    console.print(f"Database revision: {head_revision(settings)}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    workspace: Path | None = typer.Option(None, "--workspace", help="Exact workspace path."),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        raise typer.BadParameter("Unsupported bind address.")
    if host == "0.0.0.0":
        console.print(
            "[yellow]Warning: binding all interfaces; restrict access with a host firewall "
            "or a loopback-only container port mapping.[/yellow]"
        )
    settings = _settings(workspace).model_copy(update={"host": host, "port": port})
    log_path = configure_logging(
        settings.logs_dir, level=settings.log_level, verbose=verbose,
        retention_days=settings.log_retention_days,
    )
    import uvicorn

    from career_console.interfaces.http import create_app

    try:
        with CareerInstanceLock(settings.instance_lock_path):
            console.print(f"[green]CareerConsole[/green] http://{host}:{port}")
            console.print(f"[dim]Workspace: {settings.data_dir}[/dim]")
            console.print(f"[dim]Logs: {log_path}[/dim]")
            uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
    except InstanceAlreadyRunningError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@app.command()
def doctor(
    workspace: Path | None = typer.Option(None, "--workspace", help="Exact workspace path."),
) -> None:
    settings = _settings(workspace)
    settings.ensure_directories()
    checks: list[tuple[str, str, str, bool]] = []
    checks.append(("Workspace", str(settings.data_dir), "writable", _writable(settings.runtime_dir)))
    checks.append(("Manifest", str(settings.data_dir / "workspace.json"), "available",
                   (settings.data_dir / "workspace.json").is_file()))
    if settings.database_path.is_file():
        database = Database(settings)
        healthy, detail = database.ready()
        actual = database_revision(settings.database_path)
        expected = head_revision(settings)
        database.close()
        checks.append(("Database", detail, "quick_check=ok", healthy))
        checks.append(("DB revision", actual or "none", expected, actual == expected))
    else:
        checks.append(("Database", "not initialized", "run setup", True))
    checks.append(("Web port", str(settings.port), "available", _port_available(settings.port)))
    table = Table(title="CareerConsole doctor")
    for label in ("Check", "Actual", "Expected", "Result"):
        table.add_column(label)
    for name, actual, expected, passed in checks:
        table.add_row(name, actual, expected, "[green]PASS[/green]" if passed else "[red]FAIL[/red]")
    console.print(table)
    if not all(item[3] for item in checks):
        raise typer.Exit(1)


@app.command()
def status(
    workspace: Path | None = typer.Option(None, "--workspace", help="Exact workspace path."),
) -> None:
    settings = _settings(workspace)
    console.print(f"CareerConsole v{__version__}")
    console.print(f"Workspace: {settings.data_dir}")
    console.print(f"Database: {settings.database_path}")
    console.print(f"Revision: {database_revision(settings.database_path) or 'not initialized'}")


def _writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".doctor-write-probe"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        return True
    except OSError:
        return False


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
