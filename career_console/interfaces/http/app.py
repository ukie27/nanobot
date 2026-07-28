"""Career FastAPI application factory."""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from career_console import __version__
from career_console.application.services import (
    CareerApplicationService,
    ConnectorApplicationService,
    GovernanceApplicationService,
    InterviewApplicationService,
    JobApplicationService,
    JobFitApplicationService,
    MailApplicationService,
    MaterialAgentApplicationService,
    MaterialApplicationService,
    NowcoderConnectorApplicationService,
    OpportunityApplicationService,
    ProfileApplicationService,
    ProfileImpactApplicationService,
    ProfileMemoryApplicationService,
    ResumeDirectionApplicationService,
    RuntimeApplicationService,
    TaskApplicationService,
)
from career_console.infrastructure.agent_runtime import CareerAgentRuntime
from career_console.infrastructure.channels import ChannelConfigurationService, QQNotificationSender
from career_console.infrastructure.configuration import (
    AtomicConfigurationStore,
    ConfigurationService,
    apply_stored_runtime_configuration,
)
from career_console.infrastructure.configuration.audit import ConfigurationAuditStore
from career_console.infrastructure.configuration.integrations import IntegrationConfigurationService
from career_console.infrastructure.configuration.provider_audit import ProviderConnectionTestAudit
from career_console.infrastructure.connectors import OpenCliProcessRunner
from career_console.infrastructure.database import Database
from career_console.infrastructure.database.application_gateway import (
    SqlAlchemyApplicationGateway,
)
from career_console.infrastructure.database.backup import (
    backup_database,
    database_revision,
)
from career_console.infrastructure.database.connector_gateway import (
    SqlAlchemyConnectorGateway,
)
from career_console.infrastructure.database.governance_gateway import (
    SqlAlchemyGovernanceGateway,
)
from career_console.infrastructure.database.interview_gateway import (
    SqlAlchemyInterviewGateway,
)
from career_console.infrastructure.database.job_fit_gateway import SqlAlchemyJobFitGateway
from career_console.infrastructure.database.job_gateway import SqlAlchemyJobGateway
from career_console.infrastructure.database.mail_gateway import SqlAlchemyMailGateway
from career_console.infrastructure.database.material_agent_gateway import (
    SqlAlchemyMaterialAgentGateway,
)
from career_console.infrastructure.database.material_gateway import (
    SqlAlchemyMaterialGateway,
)
from career_console.infrastructure.database.migrations import (
    head_revision,
    upgrade_to_head,
)
from career_console.infrastructure.database.opportunity_gateway import (
    SqlAlchemyOpportunityGateway,
)
from career_console.infrastructure.database.profile_gateway import SqlAlchemyProfileGateway
from career_console.infrastructure.database.profile_impact_gateway import (
    SqlAlchemyProfileImpactGateway,
)
from career_console.infrastructure.database.profile_memory_gateway import (
    SqlAlchemyProfileMemoryGateway,
)
from career_console.infrastructure.database.resume_direction_gateway import (
    SqlAlchemyResumeDirectionGateway,
)
from career_console.infrastructure.database.runtime_gateway import SqlAlchemyRuntimeGateway
from career_console.infrastructure.database.task_gateway import SqlAlchemyTaskGateway
from career_console.infrastructure.extraction import (
    LocalJobExtractor,
    LocalResumeFactExtractor,
)
from career_console.infrastructure.files import (
    DocumentParser,
    LocalBlobStore,
    SafeJobPageFetcher,
)
from career_console.infrastructure.jobs import BackgroundJobService
from career_console.infrastructure.mail import StdlibReadOnlyImapClient
from career_console.infrastructure.materials import VerifiedPdfExporter
from career_console.infrastructure.scheduling import CareerSchedulerRuntime
from career_console.infrastructure.secrets import KeyringSecretStore
from career_console.infrastructure.settings import CareerSettings
from career_console.infrastructure.workspace import (
    NativeDirectoryPicker,
    OnboardingService,
    PortableWorkspaceService,
    WorkspaceManager,
    bootstrap_file_path,
)
from career_console.interfaces.http.errors import install_exception_handlers
from career_console.interfaces.http.middleware.correlation import CorrelationIdMiddleware
from career_console.interfaces.http.middleware.security import LocalBrowserSecurityMiddleware
from career_console.interfaces.http.routes import (
    applications,
    channels,
    configuration,
    connectors,
    governance,
    interviews,
    job_pool,
    jobs,
    mail,
    materials,
    onboarding,
    opportunities,
    profile,
    profile_memory,
    runtime,
    system,
    tasks,
    workspace,
)
from career_console.interfaces.http.routes.system import restart_current_process


def create_app(settings: CareerSettings | None = None) -> FastAPI:
    settings = settings or CareerSettings()
    settings = apply_stored_runtime_configuration(settings)
    browser_session_token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()
        if settings.auto_migrate:
            expected_revision = head_revision(settings)
            installed_revision = database_revision(settings.database_path)
            if settings.database_path.is_file() and installed_revision != expected_revision:
                backup_database(settings, label=f"pre-{expected_revision}")
            upgrade_to_head(settings)
        database = Database(settings)
        configuration_service = ConfigurationService(
            AtomicConfigurationStore(settings.config_dir / "application.json"),
            ConfigurationAuditStore(database.session_factory),
        )
        configuration_service.initialize()
        onboarding_service = OnboardingService(settings.config_dir / "onboarding.json")
        secret_store = KeyringSecretStore()
        agent_runtime = CareerAgentRuntime(configuration_service, secret_store)
        workspace_manifest = json.loads(
            (settings.data_dir / "workspace.json").read_text(encoding="utf-8")
        )
        workspace_id = str(workspace_manifest["workspaceId"])
        imap_secret_reference = (
            f"career-console:{workspace_id}:connector:imap:password"
        )
        jobs_service = BackgroundJobService(database.session_factory)
        profile_service = ProfileApplicationService(
            gateway=SqlAlchemyProfileGateway(database.session_factory),
            parser=DocumentParser(max_bytes=settings.max_document_bytes),
            blob_store=LocalBlobStore(settings.blobs_dir),
            extractor=_create_fact_extractor(settings, agent_runtime),
        )
        job_gateway = SqlAlchemyJobGateway(database.session_factory)
        job_service = JobApplicationService(
            gateway=job_gateway,
            extractor=LocalJobExtractor(),
            parser=DocumentParser(max_bytes=settings.max_document_bytes),
        )
        job_fit_service = JobFitApplicationService(
            SqlAlchemyJobFitGateway(database.session_factory),
            _create_job_fit_analyzer(settings, agent_runtime),
        )
        resume_direction_service = ResumeDirectionApplicationService(
            SqlAlchemyResumeDirectionGateway(database.session_factory),
            _create_resume_direction_analyzer(settings, agent_runtime),
        )
        material_gateway = SqlAlchemyMaterialGateway(
            database.session_factory,
            exports_dir=settings.exports_dir,
            pdf_exporter=VerifiedPdfExporter(),
        )
        material_drafter, material_reviewer = _create_material_agents(
            settings, agent_runtime
        )
        material_agent_service = MaterialAgentApplicationService(
            SqlAlchemyMaterialAgentGateway(database.session_factory),
            material_drafter, material_reviewer,
        )
        application_gateway = SqlAlchemyApplicationGateway(database.session_factory)
        task_gateway = SqlAlchemyTaskGateway(database.session_factory)
        connector_gateway = SqlAlchemyConnectorGateway(database.session_factory)
        connector_service = ConnectorApplicationService(
            gateway=connector_gateway,
            runner=OpenCliProcessRunner(settings.opencli_executable),
            jobs=job_service,
        )
        connector_gateway.get_or_create_boss()
        opportunity_gateway = SqlAlchemyOpportunityGateway(database.session_factory)
        opportunity_service = OpportunityApplicationService(opportunity_gateway)
        nowcoder_connector_service = NowcoderConnectorApplicationService(
            gateway=connector_gateway,
            runner=connector_service.runner,
            opportunities=opportunity_gateway,
        )
        connector_gateway.get_or_create_nowcoder()
        mail_gateway = SqlAlchemyMailGateway(database.session_factory)
        mail_service = MailApplicationService(
            gateway=mail_gateway,
            client=StdlibReadOnlyImapClient(),
            secrets=secret_store,
            applications=application_gateway,
            tasks=task_gateway,
            jobs=jobs_service,
            analyzer=_create_mail_analyzer(settings, agent_runtime),
            secret_reference=imap_secret_reference,
        )
        integration_configuration = IntegrationConfigurationService(
            configuration=configuration_service,
            connector_service=connector_service,
            nowcoder_service=nowcoder_connector_service,
            mail_service=mail_service,
            imap_secret_ref=imap_secret_reference,
        )
        integration_configuration.import_operational_configuration()
        app.state.integration_startup_failures = integration_configuration.reconcile()
        interview_gateway = SqlAlchemyInterviewGateway(database.session_factory)
        governance_gateway = SqlAlchemyGovernanceGateway(
            database.session_factory, settings=settings, secrets=secret_store
        )
        runtime_gateway = SqlAlchemyRuntimeGateway(database.session_factory)
        profile_memory_gateway = SqlAlchemyProfileMemoryGateway(database.session_factory)
        profile_memory_service = ProfileMemoryApplicationService(
            profile_memory_gateway,
            _create_profile_insight_analyzer(settings, agent_runtime),
        )
        profile_impact_service = ProfileImpactApplicationService(
            SqlAlchemyProfileImpactGateway(database.session_factory), jobs_service, job_gateway
        )
        task_service = TaskApplicationService(task_gateway)
        channel_configuration = ChannelConfigurationService(
            configuration=configuration_service,
            secrets=secret_store,
            session_factory=database.session_factory,
            qq_sender=QQNotificationSender(),
            qq_secret_ref=f"career-console:{workspace_id}:channel:qq:secret",
        )
        scheduler_runtime = CareerSchedulerRuntime(
            configuration=configuration_service,
            session_factory=database.session_factory,
            task_service=task_service,
            connector_service=connector_service,
            nowcoder_service=nowcoder_connector_service,
            mail_service=mail_service,
            profile_memory=profile_memory_gateway,
            profile_impacts=profile_impact_service,
            channels=channel_configuration,
        )
        app.state.settings = settings
        app.state.configuration_service = configuration_service
        app.state.onboarding_service = onboarding_service
        app.state.bootstrap_workspace = (
            settings.data_dir
            == bootstrap_file_path().parent / "workspaces" / "default"
        )
        app.state.secret_store = secret_store
        app.state.agent_runtime = agent_runtime
        app.state.provider_test_audit = ProviderConnectionTestAudit(
            database.session_factory
        )
        app.state.provider_secret_reference = (
            lambda provider_id: (
                f"career-console:{workspace_id}:provider:{provider_id}:api-key"
            )
        )
        app.state.channel_configuration = channel_configuration
        workspace_manager = WorkspaceManager()
        workspace_manager.registry.finalize_committed_switch(settings.data_dir)
        app.state.workspace_manager = workspace_manager
        app.state.directory_picker = NativeDirectoryPicker()
        app.state.portable_workspace = PortableWorkspaceService(
            root=settings.data_dir,
            secret_store=secret_store,
            manager=workspace_manager,
            database_head=head_revision(settings),
        )
        app.state.database = database
        app.state.jobs = jobs_service
        app.state.profile_service = profile_service
        app.state.job_gateway = job_gateway
        app.state.job_service = job_service
        app.state.job_fit_service = job_fit_service
        app.state.resume_direction_service = resume_direction_service
        app.state.job_fetcher = SafeJobPageFetcher(max_bytes=settings.max_document_bytes)
        app.state.material_gateway = material_gateway
        app.state.material_service = MaterialApplicationService(material_gateway)
        app.state.material_agent_service = material_agent_service
        app.state.application_gateway = application_gateway
        app.state.application_service = CareerApplicationService(application_gateway)
        app.state.task_gateway = task_gateway
        app.state.task_service = task_service
        app.state.connector_gateway = connector_gateway
        app.state.connector_service = connector_service
        app.state.nowcoder_connector_service = nowcoder_connector_service
        app.state.opportunity_gateway = opportunity_gateway
        app.state.opportunity_service = opportunity_service
        app.state.mail_gateway = mail_gateway
        app.state.mail_service = mail_service
        app.state.integration_configuration = integration_configuration
        app.state.interview_gateway = interview_gateway
        app.state.interview_service = InterviewApplicationService(interview_gateway)
        app.state.governance_gateway = governance_gateway
        app.state.governance_service = GovernanceApplicationService(governance_gateway)
        app.state.runtime_gateway = runtime_gateway
        app.state.runtime_service = RuntimeApplicationService(runtime_gateway)
        app.state.profile_memory_gateway = profile_memory_gateway
        app.state.profile_memory_service = profile_memory_service
        app.state.profile_impact_service = profile_impact_service
        app.state.scheduler_runtime = scheduler_runtime
        app.state.recovered_jobs = jobs_service.recover_expired_leases()
        scheduler_config = scheduler_runtime.configuration()
        runtime_enabled = onboarding_service.is_complete()
        app.state.scheduler_startup = (
            task_gateway.run_due()
            if runtime_enabled
            and scheduler_config["enabled"]
            and scheduler_config["reminders_enabled"]
            else {
                "schedules_processed": 0,
                "reminders_triggered": 0,
                "outbox_dispatched": 0,
                "leases_recovered": 0,
            }
        )
        scheduler_stop = asyncio.Event()
        scheduler_task = (
            asyncio.create_task(_scheduler_loop(scheduler_runtime, scheduler_stop))
            if runtime_enabled
            else None
        )
        try:
            yield
        finally:
            scheduler_stop.set()
            if scheduler_task is not None:
                scheduler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await scheduler_task
            database.close()

    app = FastAPI(
        title="CareerConsole API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.browser_session_token = browser_session_token
    app.state.restart_callback = restart_current_process
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        LocalBrowserSecurityMiddleware,
        token=browser_session_token,
        allowed_origins={
            f"http://127.0.0.1:{settings.port}",
            f"http://localhost:{settings.port}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        },
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Correlation-ID", "X-CSRF-Token"],
    )
    install_exception_handlers(app)
    app.include_router(system.router)
    app.include_router(onboarding.router)
    app.include_router(configuration.router)
    app.include_router(channels.router)
    app.include_router(jobs.router)
    app.include_router(profile.router)
    app.include_router(profile_memory.router)
    app.include_router(job_pool.router)
    app.include_router(opportunities.router)
    app.include_router(materials.router)
    app.include_router(materials.resume_router)
    app.include_router(materials.export_router)
    app.include_router(applications.router)
    app.include_router(applications.proposal_router)
    app.include_router(applications.review_router)
    app.include_router(tasks.router)
    app.include_router(tasks.dashboard_router)
    app.include_router(tasks.notification_router)
    app.include_router(tasks.scheduler_router)
    app.include_router(tasks.event_router)
    app.include_router(connectors.router)
    app.include_router(interviews.router)
    app.include_router(interviews.feedback_router)
    app.include_router(interviews.improvement_router)
    app.include_router(governance.router)
    app.include_router(runtime.router)
    app.include_router(mail.router)
    app.include_router(workspace.router)

    if settings.web_dist_dir.is_dir():
        assets_dir = settings.web_dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="career-assets")

        @app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
        def career_web(full_path: str) -> FileResponse:
            if full_path.startswith(("api/", "health/")):
                raise HTTPException(status_code=404, detail="API route not found")
            return FileResponse(settings.web_dist_dir / "index.html")
    else:

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def web_not_built() -> str:
            return """<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
            <title>CareerConsole</title><style>body{font-family:system-ui;margin:4rem;max-width:52rem}
            code{background:#eef1f5;padding:.2rem .4rem;border-radius:.3rem}</style>
            <h1>CareerConsole API 已启动</h1><p>前端尚未构建。开发模式请运行
            <code>cd web &amp;&amp; npm install &amp;&amp; npm run dev</code>。</p>
            <p><a href='/api/docs'>打开 API 文档</a></p></html>"""

    return app


def _create_fact_extractor(settings: CareerSettings, runtime: CareerAgentRuntime):
    if settings.fact_extractor_mode == "local":
        return LocalResumeFactExtractor()

    from career_console.infrastructure.agents import CareerProfileFactExtractor
    resolved = runtime.resolve("fact_extraction")
    if resolved is None:
        return LocalResumeFactExtractor()
    return CareerProfileFactExtractor(resolved.provider, model=resolved.model)


def _create_mail_analyzer(settings: CareerSettings, runtime: CareerAgentRuntime):
    if settings.mail_intelligence_mode == "disabled":
        return None
    try:
        from career_console.infrastructure.agents import CareerMailIntelligenceAnalyzer
        resolved = runtime.resolve("mail_intelligence")
        return (
            CareerMailIntelligenceAnalyzer(resolved.provider, model=resolved.model)
            if resolved else None
        )
    except (RuntimeError, ValueError):
        return None


def _create_profile_insight_analyzer(
    settings: CareerSettings, runtime: CareerAgentRuntime
):
    if settings.profile_insight_mode == "disabled":
        return None
    try:
        from career_console.infrastructure.agents import CareerProfileInsightAnalyzer
        resolved = runtime.resolve("profile_insight")
        return (
            CareerProfileInsightAnalyzer(resolved.provider, model=resolved.model)
            if resolved else None
        )
    except (RuntimeError, ValueError):
        return None


def _create_job_fit_analyzer(settings: CareerSettings, runtime: CareerAgentRuntime):
    if settings.job_fit_agent_mode == "disabled":
        return None
    try:
        from career_console.infrastructure.agents import CareerJobFitAnalyzer
        resolved = runtime.resolve("job_fit")
        return (
            CareerJobFitAnalyzer(resolved.provider, model=resolved.model)
            if resolved else None
        )
    except (RuntimeError, ValueError):
        return None


def _create_resume_direction_analyzer(
    settings: CareerSettings, runtime: CareerAgentRuntime
):
    if settings.resume_direction_mode == "disabled":
        return None
    try:
        from career_console.infrastructure.agents import CareerResumeDirectionAnalyzer
        resolved = runtime.resolve("resume_direction")
        return (
            CareerResumeDirectionAnalyzer(resolved.provider, model=resolved.model)
            if resolved else None
        )
    except (RuntimeError, ValueError):
        return None


def _create_material_agents(settings: CareerSettings, runtime: CareerAgentRuntime):
    if settings.material_agent_mode == "disabled":
        return None, None
    try:
        from career_console.infrastructure.agents import CareerMaterialReviewer, CareerResumeDrafter
        drafter = runtime.resolve("resume_drafting")
        reviewer = runtime.resolve("material_review")
        return (
            CareerResumeDrafter(drafter.provider, model=drafter.model) if drafter else None,
            CareerMaterialReviewer(reviewer.provider, model=reviewer.model) if reviewer else None,
        )
    except (RuntimeError, ValueError):
        return None, None


async def _scheduler_loop(
    scheduler_runtime: CareerSchedulerRuntime,
    stop: asyncio.Event,
) -> None:
    """Run the configuration-driven scheduler while the local app is alive."""
    while not stop.is_set():
        await asyncio.to_thread(scheduler_runtime.run_once)
        poll_seconds = scheduler_runtime.configuration()["poll_seconds"]
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
        except TimeoutError:
            continue
