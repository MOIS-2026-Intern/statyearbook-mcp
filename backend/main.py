# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.controllers import chat_controller, health_controller
from backend.middleware.access_log import add_access_log_middleware


BANNER_PATH = Path(__file__).with_name("banner.txt")


# 배너 파일이 있으면 서버 시작 시 콘솔에 출력한다.
def print_banner() -> None:
    if not BANNER_PATH.exists():
        return

    banner = BANNER_PATH.read_text(encoding="utf-8")
    print(f"\n{banner}\n", flush=True)


# FastAPI 시작 시 배너와 향후 생명주기 자원을 준비한다.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    print_banner()
    yield


# 라우터와 공통 미들웨어를 조합해 FastAPI 앱을 생성한다.
def create_app() -> FastAPI:
    app = FastAPI(title="MOIS StatYearbook Chat Backend", version="0.1.0", lifespan=lifespan)

    add_access_log_middleware(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_controller.router)
    app.include_router(chat_controller.router)

    return app


app = create_app()


# 현재 프로필의 호스트·포트·reload 설정으로 ASGI 서버를 실행한다.
def run() -> None:
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        access_log=False,
    )
