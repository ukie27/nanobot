"""Career FastAPI application factory."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from nanobot import __version__
from nanobot.career.api.errors import install_exception_handlers
from nanobot.career.api.middleware.correlation import CorrelationIdMiddleware
from nanobot.career.api.middleware.security import LocalBrowserSecurityMiddleware
from nanobot.career.api.routes import (
    applications,
    connectors,
    governance,
    interviews,
    job_pool,
    jobs,
    mail,
    materials,
    opportunities,
    profile,
    profile_memory,
    runtime,
    system,
    tasks,
)
from nanobot.career.application.services import (
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
from nanobot.career.infrastructure.connectors import OpenCliProcessRunner
from nanobot.career.infrastructure.database import Database
from nanobot.career.infrastructure.database.application_gateway import (
    SqlAlchemyApplicationGateway,
)
from nanobot.career.infrastructure.database.backup import backup_database, database_revision
from nanobot.career.infrastructure.database.connector_gateway import SqlAlchemyConnectorGateway
from nanobot.career.infrastructure.database.governance_gateway import SqlAlchemyGovernanceGateway
from nanobot.career.infrastructure.database.interview_gateway import SqlAlchemyInterviewGateway
from nanobot.career.infrastructure.database.job_fit_gateway import SqlAlchemyJobFitGateway
from nanobot.career.infrastructure.database.job_gateway import SqlAlchemyJobGateway
from nanobot.career.infrastructure.database.mail_gateway import SqlAlchemyMailGateway
from nanobot.career.infrastructure.database.material_agent_gateway import (
    SqlAlchemyMaterialAgentGateway,
)
from nanobot.career.infrastructure.database.material_gateway import SqlAlchemyMaterialGateway
from nanobot.career.infrastructure.database.migrations import head_revision, upgrade_to_head
from nanobot.career.infrastructure.database.opportunity_gateway import (
    SqlAlchemyOpportunityGateway,
)
from nanobot.career.infrastructure.database.profile_gateway import SqlAlchemyProfileGateway
from nanobot.career.infrastructure.database.profile_impact_gateway import (
    SqlAlchemyProfileImpactGateway,
)
from nanobot.career.infrastructure.database.profile_memory_gateway import (
    SqlAlchemyProfileMemoryGateway,
)
from nanobot.career.infrastructure.database.resume_direction_gateway import (
    SqlAlchemyResumeDirectionGateway,
)
from nanobot.career.infrastructure.database.runtime_gateway import SqlAlchemyRuntimeGateway
from nanobot.career.infrastructure.database.task_gateway import SqlAlchemyTaskGateway
from nanobot.career.infrastructure.extraction import LocalJobExtractor, LocalResumeFactExtractor
from nanobot.career.infrastructure.files import DocumentParser, LocalBlobStore, SafeJobPageFetcher
from nanobot.career.infrastructure.jobs import BackgroundJobService
from nanobot.career.infrastructure.mail import StdlibReadOnlyImapClient
from nanobot.career.infrastructure.materials import VerifiedPdfExporter
from nanobot.career.infrastructure.secrets import KeyringSecretStore
from nanobot.career.infrastructure.settings import CareerSettings


def create_app(settings: CareerSettings | None = None) -> FastAPI:
    settings = settings or CareerSettings()
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
        jobs_service = BackgroundJobService(database.session_factory)
        profile_service = ProfileApplicationService(
            gateway=SqlAlchemyProfileGateway(database.session_factory),
            parser=DocumentParser(max_bytes=settings.max_document_bytes),
            blob_store=LocalBlobStore(settings.blobs_dir),
            extractor=_create_fact_extractor(settings),
        )
        job_gateway = SqlAlchemyJobGateway(database.session_factory)
        job_service = JobApplicationService(
            gateway=job_gateway,
            extractor=LocalJobExtractor(),
            parser=DocumentParser(max_bytes=settings.max_document_bytes),
        )
        job_fit_service = JobFitApplicationService(
            SqlAlchemyJobFitGateway(database.session_factory), _create_job_fit_analyzer(settings)
        )
        resume_direction_service = ResumeDirectionApplicationService(
            SqlAlchemyResumeDirectionGateway(database.session_factory),
            _create_resume_direction_analyzer(settings),
        )
        material_gateway = SqlAlchemyMaterialGateway(
            database.session_factory,
            exports_dir=settings.exports_dir,
            pdf_exporter=VerifiedPdfExporter(),
        )
        material_drafter, material_reviewer = _create_material_agents(settings)
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
            secrets=KeyringSecretStore(),
            applications=application_gateway,
            tasks=task_gateway,
            jobs=jobs_service,
            analyzer=_create_mail_analyzer(settings),
        )
        interview_gateway = SqlAlchemyInterviewGateway(database.session_factory)
        governance_gateway = SqlAlchemyGovernanceGateway(
            database.session_factory, settings=settings, secrets=KeyringSecretStore()
        )
        runtime_gateway = SqlAlchemyRuntimeGateway(database.session_factory)
        profile_memory_gateway = SqlAlchemyProfileMemoryGateway(database.session_factory)
        profile_memory_service = ProfileMemoryApplicationService(
            profile_memory_gateway, _create_profile_insight_analyzer(settings)
        )
        profile_impact_service = ProfileImpactApplicationService(
            SqlAlchemyProfileImpactGateway(database.session_factory), jobs_service, job_gateway
        )
        app.state.settings = settings
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
        app.state.task_service = TaskApplicationService(task_gateway)
        app.state.connector_gateway = connector_gateway
        app.state.connector_service = connector_service
        app.state.nowcoder_connector_service = nowcoder_connector_service
        app.state.opportunity_gateway = opportunity_gateway
        app.state.opportunity_service = opportunity_service
        app.state.mail_gateway = mail_gateway
        app.state.mail_service = mail_service
        app.state.interview_gateway = interview_gateway
        app.state.interview_service = InterviewApplicationService(interview_gateway)
        app.state.governance_gateway = governance_gateway
        app.state.governance_service = GovernanceApplicationService(governance_gateway)
        app.state.runtime_gateway = runtime_gateway
        app.state.runtime_service = RuntimeApplicationService(runtime_gateway)
        app.state.profile_memory_gateway = profile_memory_gateway
        app.state.profile_memory_service = profile_memory_service
        app.state.profile_impact_service = profile_impact_service
        app.state.recovered_jobs = jobs_service.recover_expired_leases()
        app.state.scheduler_startup = task_gateway.run_due()
        scheduler_stop = asyncio.Event()
        scheduler_task = asyncio.create_task(
            _scheduler_loop(
                app.state.task_service,
                connector_service,
                nowcoder_connector_service,
                mail_service,
                profile_memory_gateway,
                profile_impact_service,
                scheduler_stop,
            )
        )
        try:
            yield
        finally:
            scheduler_stop.set()
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task
            database.close()

    app = FastAPI(
        title="Nanobot Career API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.browser_session_token = browser_session_token
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
            <title>Nanobot Career</title><style>body{font-family:system-ui;margin:4rem;max-width:52rem}
            code{background:#eef1f5;padding:.2rem .4rem;border-radius:.3rem}</style>
            <h1>Nanobot Career API 已启动</h1><p>前端尚未构建。开发模式请运行
            <code>cd web &amp;&amp; npm install &amp;&amp; npm run dev</code>。</p>
            <p><a href='/api/docs'>打开 API 文档</a></p></html>"""

    return app


def _create_fact_extractor(settings: CareerSettings):
    if settings.fact_extractor_mode == "local":
        return LocalResumeFactExtractor()

    from nanobot.career.agent import NanobotProfileFactExtractor
    from nanobot.config.loader import load_config
    from nanobot.nanobot import _make_provider

    config = load_config()
    provider = _make_provider(config)
    return NanobotProfileFactExtractor(provider, model=config.agents.defaults.model)


def _create_mail_analyzer(settings: CareerSettings):
    if settings.mail_intelligence_mode == "disabled":
        return None
    try:
        from nanobot.career.agent import NanobotMailIntelligenceAnalyzer
        from nanobot.config.loader import load_config
        from nanobot.nanobot import _make_provider

        config = load_config()
        provider = _make_provider(config)
        return NanobotMailIntelligenceAnalyzer(provider, model=config.agents.defaults.model)
    except (RuntimeError, ValueError):
        return None


def _create_profile_insight_analyzer(settings: CareerSettings):
    if settings.profile_insight_mode == "disabled":
        return None
    try:
        from nanobot.career.agent import NanobotProfileInsightAnalyzer
        from nanobot.config.loader import load_config
        from nanobot.nanobot import _make_provider

        config = load_config()
        provider = _make_provider(config)
        return NanobotProfileInsightAnalyzer(provider, model=config.agents.defaults.model)
    except (RuntimeError, ValueError):
        return None


def _create_job_fit_analyzer(settings: CareerSettings):
    if settings.job_fit_agent_mode == "disabled":
        return None
    try:
        from nanobot.career.agent import NanobotJobFitAnalyzer
        from nanobot.config.loader import load_config
        from nanobot.nanobot import _make_provider

        config = load_config()
        provider = _make_provider(config)
        return NanobotJobFitAnalyzer(provider, model=config.agents.defaults.model)
    except (RuntimeError, ValueError):
        return None


def _create_resume_direction_analyzer(settings: CareerSettings):
    if settings.resume_direction_mode == "disabled":
        return None
    try:
        from nanobot.career.agent import NanobotResumeDirectionAnalyzer
        from nanobot.config.loader import load_config
        from nanobot.nanobot import _make_provider

        config = load_config()
        provider = _make_provider(config)
        return NanobotResumeDirectionAnalyzer(provider, model=config.agents.defaults.model)
    except (RuntimeError, ValueError):
        return None


def _create_material_agents(settings: CareerSettings):
    if settings.material_agent_mode == "disabled":
        return None, None
    try:
        from nanobot.career.agent import NanobotMaterialReviewer, NanobotResumeDrafter
        from nanobot.config.loader import load_config
        from nanobot.nanobot import _make_provider

        config = load_config()
        provider = _make_provider(config)
        model = config.agents.defaults.model
        return NanobotResumeDrafter(provider, model=model), NanobotMaterialReviewer(provider, model=model)
    except (RuntimeError, ValueError):
        return None, None


async def _scheduler_loop(
    task_service: Any,
    connector_service: Any,
    nowcoder_connector_service: Any,
    mail_service: Any,
    profile_memory_gateway: Any,
    profile_impact_service: Any,
    stop: asyncio.Event,
) -> None:
    """Run persisted schedules while the local application is alive."""
    while not stop.is_set():
        await asyncio.to_thread(task_service.run_due)
        try:
            await asyncio.to_thread(connector_service.run_due)
        except Exception:
            # Connector failures are persisted on SyncRun and must not stop reminders.
            pass
        try:
            # The service itself hard-codes the scheduled scope to China-calendar today.
            await asyncio.to_thread(nowcoder_connector_service.run_due)
        except Exception:
            pass
        try:
            await asyncio.to_thread(mail_service.run_due)
        except Exception:
            # Mail failures are persisted and isolated from all other schedules.
            pass
        for _ in range(10):
            processed = await asyncio.to_thread(mail_service.process_next_analysis_job)
            if not processed:
                break
        try:
            await asyncio.to_thread(profile_memory_gateway.run_due)
        except Exception:
            pass
        try:
            await asyncio.to_thread(profile_impact_service.enqueue_pending)
            for _ in range(20):
                processed = await asyncio.to_thread(profile_impact_service.process_next)
                if not processed:
                    break
        except Exception:
            # Every impact and queue attempt is durable; one failure must not stop schedules.
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            continue
