# 이 파일은 관리자 FastAPI 앱, controller, 작업 실행기와 frontend 정적 경로를 조립한다.
# 관리자 서버의 유일한 ASGI 진입점이다.
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from admin.backend.config import ADMIN_API_PREFIX, ADMIN_DIR, AdminSettings, settings
from admin.backend.controllers import (
    artifacts,
    jobs,
    publications,
    system,
)
from admin.backend.repositories.admin_jobs import AdminJobRepository
from admin.backend.services.job_queue import AdminJobOrchestrator
from admin.backend.services.load_pipeline import YearbookIngestionService
from admin.backend.services.load_workspace import migrate_legacy_workspaces
from admin.backend.services.publications import PublicationService


# 관리자 설정에 맞춰 저장소, 서비스, 라우터와 정적 화면을 한 ASGI 앱으로 조립한다.
def create_app(config: AdminSettings = settings) -> FastAPI:
    repository = AdminJobRepository(config.db_path)
    migrate_legacy_workspaces(config.workspace_dir, repository)
    ingestion_service = YearbookIngestionService(config, repository)
    orchestrator = AdminJobOrchestrator(ingestion_service)

    # 앱 종료 시 백그라운드 작업 실행기가 스레드 자원을 정리하도록 보장한다.
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
    app.state.publication_service = PublicationService(config)

    app.include_router(system.router)
    app.include_router(jobs.router)
    app.include_router(artifacts.router)
    app.include_router(publications.router)
    app.mount(
        "/",
        StaticFiles(directory=ADMIN_DIR / "frontend", html=True),
        name="admin-frontend",
    )
    return app


app = create_app()


# 현재 관리자 프로필의 호스트와 포트로 ASGI 서버를 실행한다.
def run() -> None:
    uvicorn.run(
        "admin.backend.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
