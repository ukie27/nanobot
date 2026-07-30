"""Independent CareerConsole command line interface."""

from __future__ import annotations

import socket
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from career_console import __version__
from career_console.application.services.review_maintenance import ReviewMaintenanceService
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
from career_console.infrastructure.database.profile_gateway import SqlAlchemyProfileGateway
from career_console.infrastructure.database.runtime_gateway import SqlAlchemyRuntimeGateway
from career_console.infrastructure.datasets import (
    DatasetError,
    DevelopmentDatasetManager,
    ProductEvaluationManager,
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
dev_app = typer.Typer(name="dev", help="Development and acceptance utilities.")
dataset_app = typer.Typer(name="dataset", help="Manage deterministic test datasets.")
evaluation_app = typer.Typer(name="eval", help="Validate and run product benchmarks.")
review_app = typer.Typer(name="reviews", help="Inspect and repair review projections.")
app.add_typer(workspace_app, name="workspace")
app.add_typer(dev_app, name="dev")
dev_app.add_typer(dataset_app, name="dataset")
dev_app.add_typer(evaluation_app, name="eval")
dev_app.add_typer(review_app, name="reviews")
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
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise typer.BadParameter("CareerConsole only supports loopback bind addresses.")
    import uvicorn

    from career_console.interfaces.http import create_app

    selected_workspace = workspace
    while True:
        settings = _settings(selected_workspace).model_copy(
            update={"host": host, "port": port}
        )
        log_path = configure_logging(
            settings.logs_dir, level=settings.log_level, verbose=verbose,
            retention_days=settings.log_retention_days,
        )
        runtime_app = create_app(settings)
        restart_requested = False
        restart_workspace = settings.data_dir
        server = uvicorn.Server(
            uvicorn.Config(runtime_app, host=host, port=port, log_level="info")
        )

        def request_restart() -> None:
            nonlocal restart_requested, restart_workspace
            restart_requested = True
            workspace_override = getattr(
                runtime_app.state, "restart_workspace_override", None
            )
            if workspace_override is not None:
                restart_workspace = workspace_override
            server.should_exit = True

        runtime_app.state.restart_callback = request_restart
        try:
            with CareerInstanceLock(settings.instance_lock_path):
                console.print(f"[green]CareerConsole[/green] http://{host}:{port}")
                console.print(f"[dim]Workspace: {settings.data_dir}[/dim]")
                console.print(f"[dim]Logs: {log_path}[/dim]")
                server.run()
        except InstanceAlreadyRunningError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        if not restart_requested:
            break
        selected_workspace = restart_workspace
        console.print("[dim]正在重新加载 CareerConsole…[/dim]")


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


@dataset_app.command("validate")
def validate_dataset() -> None:
    """Validate the repository dataset without changing a workspace."""
    try:
        result = DevelopmentDatasetManager().validate()
    except DatasetError as exc:
        console.print(f"[red]Dataset validation failed:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Dataset valid.[/green] {result['dataset']} · "
        f"{result['file_count']} files · {result['timezone']}"
    )


@dataset_app.command("seed")
def seed_dataset(
    scenario: str = typer.Option("full-journey", "--scenario"),
    workspace: Path | None = typer.Option(
        None, "--workspace", help="Marked test workspace; defaults to the active workspace."
    ),
) -> None:
    """Copy a deterministic scenario into a marked test workspace."""
    root = WorkspaceManager().resolve_active(workspace)
    try:
        result = DevelopmentDatasetManager().seed(root, scenario=scenario)
    except DatasetError as exc:
        console.print(f"[red]Dataset seed refused:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Dataset seeded.[/green] {result['scenario']} · "
        f"{result['file_count']} files"
    )
    console.print(f"[dim]Target: {result['target']}[/dim]")


@dataset_app.command("expect")
def expect_dataset(
    scenario: str = typer.Option("full-journey", "--scenario"),
    workspace: Path | None = typer.Option(
        None, "--workspace", help="Marked test workspace; defaults to the active workspace."
    ),
) -> None:
    """Verify that a seeded test workspace still matches its inventory."""
    root = WorkspaceManager().resolve_active(workspace)
    try:
        result = DevelopmentDatasetManager().expect(root, scenario=scenario)
    except DatasetError as exc:
        console.print(f"[red]Dataset expectation failed:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Dataset matches expectations.[/green] "
        f"{result['scenario']} · {result['file_count']} files"
    )


@dataset_app.command("reset")
def reset_dataset(
    workspace: Path = typer.Option(
        ..., "--workspace", help="Exact marked test workspace path."
    ),
) -> None:
    """Remove only seeded dataset files from an explicitly marked test workspace."""
    try:
        result = DevelopmentDatasetManager().reset(workspace)
    except DatasetError as exc:
        console.print(f"[red]Dataset reset refused:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Dataset reset complete.[/green] "
        f"{result['removed_file_count']} files removed"
    )


@evaluation_app.command("validate")
def validate_evaluation() -> None:
    """Validate benchmark definitions, gold outputs, and scoring invariants."""
    try:
        result = ProductEvaluationManager().validate()
    except DatasetError as exc:
        console.print(f"[red]Evaluation validation failed:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Evaluation valid.[/green] {result['benchmark']} · "
        f"{result['case_count']} cases · {result['dimension_count']} dimensions · "
        f"reference {result['reference_score']:.2f}"
    )


@evaluation_app.command("run")
def run_evaluation(
    results: Path | None = typer.Option(
        None,
        "--results",
        help="Normalized evaluation-results JSON; defaults to the gold reference run.",
    ),
    report: Path | None = typer.Option(
        None,
        "--report",
        help="Optional destination for the complete JSON evaluation report.",
    ),
) -> None:
    """Score a normalized CareerConsole product run against the benchmark."""
    manager = ProductEvaluationManager()
    try:
        outcome = manager.run(results_path=results)
        report_path = manager.write_report(outcome, report) if report else None
    except DatasetError as exc:
        console.print(f"[red]Evaluation failed:[/red] {exc}")
        raise typer.Exit(2) from exc
    result_style = "green" if outcome["passed"] else "red"
    console.print(
        f"[{result_style}]Evaluation {'passed' if outcome['passed'] else 'failed'}."
        f"[/{result_style}] score={outcome['score']:.2f} "
        f"minimum={outcome['minimumScore']:.2f}"
    )
    for dimension in outcome["dimensions"]:
        console.print(
            f"  {dimension['name']}: {dimension['score']:.2f} "
            f"({dimension['case_count']} cases)"
        )
    if outcome["criticalFailures"]:
        console.print(
            "[red]Critical failures:[/red] "
            + ", ".join(outcome["criticalFailures"])
        )
    if report_path:
        console.print(f"[dim]Report: {report_path}[/dim]")
    if not outcome["passed"]:
        raise typer.Exit(1)


@review_app.command("clear-legacy-profile-facts")
def clear_legacy_profile_facts(
    workspace: Path | None = typer.Option(None, "--workspace", help="Exact workspace path."),
    apply: bool = typer.Option(False, "--apply", help="Reject the matched legacy facts."),
) -> None:
    """Close obsolete candidate_fact.v1 reviews without deleting their evidence."""
    settings = _settings(workspace)
    database = Database(settings)
    try:
        service = ReviewMaintenanceService(
            runtime_gateway=SqlAlchemyRuntimeGateway(database.session_factory),
            profile_gateway=SqlAlchemyProfileGateway(database.session_factory),
        )
        matches = service.legacy_profile_fact_reviews()
        console.print(
            f"Matched legacy profile fact reviews: [bold]{len(matches)}[/bold]"
        )
        if not apply:
            console.print("[dim]Preview only. Add --apply to reject the matched reviews.[/dim]")
            return
        result = service.reject_legacy_profile_fact_reviews(
            reason="旧版 local_resume_extractor candidate_fact.v1 候选清理"
        )
        console.print(
            f"[green]Rejected legacy reviews:[/green] {result['rejected']}"
        )
    finally:
        database.close()


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


if __name__ == "__main__":
    app()
