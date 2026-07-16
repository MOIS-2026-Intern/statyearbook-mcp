# 이 파일은 관리자 FastAPI 앱, controller, 작업 실행기와 frontend 정적 경로를 조립한다.
# 관리자 서버의 유일한 ASGI 진입점이다.
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from admin.backend.config import ADMIN_API_PREFIX, ADMIN_DIR, AdminSettings, settings
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
        docs_url=f"{ADMIN_API_PREFIX}/docs",
        openapi_url=f"{ADMIN_API_PREFIX}/openapi.json",
        redoc_url=f"{ADMIN_API_PREFIX}/redoc",
        swagger_ui_oauth2_redirect_url=f"{ADMIN_API_PREFIX}/docs/oauth2-redirect",
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
