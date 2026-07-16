# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from admin.backend.config import ADMIN_DIR, AdminSettings, settings
from admin.backend.controllers import (
    artifact_controller,
    ingestion_job_controller,
    system_controller,
)
from admin.backend.repositories.admin_job_repository import AdminJobRepository
from admin.backend.services.admin_job_orchestrator import AdminJobOrchestrator
from admin.backend.services.workspace_service import migrate_legacy_workspaces
from admin.backend.services.yearbook_ingestion_service import YearbookIngestionService


def create_app(config: AdminSettings = settings) -> FastAPI:
    repository = AdminJobRepository(config.db_path)
    migrate_legacy_workspaces(config.workspace_dir, repository)
    ingestion_service = YearbookIngestionService(config, repository)
    orchestrator = AdminJobOrchestrator(ingestion_service)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        orchestrator.close()

    app = FastAPI(
        title="StatYearbook Administration",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/admin-api/docs",
        openapi_url="/admin-api/openapi.json",
    )
    app.state.settings = config
    app.state.job_repository = repository
    app.state.job_orchestrator = orchestrator

    app.include_router(system_controller.router)
    app.include_router(ingestion_job_controller.router)
    app.include_router(artifact_controller.router)
    app.mount(
        "/",
        StaticFiles(directory=ADMIN_DIR / "frontend", html=True),
        name="admin-frontend",
    )
    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "admin.backend.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
