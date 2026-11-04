"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings, get_settings
from .db import init_engine
from .errors import install_error_handlers
from .logging_setup import RequestContextMiddleware, configure_logging
from .routes import curriculum, practice, profile, progress, system
from .runtime import Runtime, build_sandbox, load_policy_and_diagnostic, migrate, set_runtime
from .worker import JobWorker

log = logging.getLogger("mlforge.app")


def create_app(settings: Settings | None = None, *, start_worker: bool | None = None, sandbox=None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    init_engine(settings.resolved_database_url)
    migrate(settings)
    policy, diagnostic = load_policy_and_diagnostic(settings.content_dir)
    rt = Runtime(settings=settings, sandbox=sandbox or build_sandbox(settings), policy=policy, diagnostic=diagnostic)
    set_runtime(rt)
    run_worker = settings.embedded_worker if start_worker is None else start_worker

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if run_worker:
            rt.worker = JobWorker(rt.sandbox, rt.policy, settings.worker_threads)
            rt.worker.start()
        health = rt.sandbox.health(max_age_s=0)
        log.info(
            "ml forge api ready",
            extra={
                "runner_available": health.available,
                "runner_reason": health.reason,
                "ai_configured": settings.anthropic_api_key is not None,
            },
        )
        yield
        if rt.worker is not None:
            rt.worker.stop()

    app = FastAPI(title="ML Forge API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(system.router)
    for module in (profile, curriculum, practice, progress):
        app.include_router(module.router)
    app.include_router(system.api)
    return app
