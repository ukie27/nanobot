"""Career FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from nanobot import __version__
from nanobot.career.api.errors import install_exception_handlers
from nanobot.career.api.middleware.correlation import CorrelationIdMiddleware
from nanobot.career.api.routes import job_pool, jobs, profile, system
from nanobot.career.application.services import JobApplicationService, ProfileApplicationService
from nanobot.career.infrastructure.database import Database
from nanobot.career.infrastructure.database.backup import backup_database, database_revision
from nanobot.career.infrastructure.database.job_gateway import SqlAlchemyJobGateway
from nanobot.career.infrastructure.database.migrations import head_revision, upgrade_to_head
from nanobot.career.infrastructure.database.profile_gateway import SqlAlchemyProfileGateway
from nanobot.career.infrastructure.extraction import LocalJobExtractor, LocalResumeFactExtractor
from nanobot.career.infrastructure.files import DocumentParser, LocalBlobStore, SafeJobPageFetcher
from nanobot.career.infrastructure.jobs import BackgroundJobService
from nanobot.career.infrastructure.settings import CareerSettings


def create_app(settings: CareerSettings | None = None) -> FastAPI:
    settings = settings or CareerSettings()

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
        app.state.settings = settings
        app.state.database = database
        app.state.jobs = jobs_service
        app.state.profile_service = profile_service
        app.state.job_gateway = job_gateway
        app.state.job_service = job_service
        app.state.job_fetcher = SafeJobPageFetcher(max_bytes=settings.max_document_bytes)
        app.state.recovered_jobs = jobs_service.recover_expired_leases()
        try:
            yield
        finally:
            database.close()

    app = FastAPI(
        title="Nanobot Career API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Correlation-ID"],
    )
    install_exception_handlers(app)
    app.include_router(system.router)
    app.include_router(jobs.router)
    app.include_router(profile.router)
    app.include_router(job_pool.router)

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
