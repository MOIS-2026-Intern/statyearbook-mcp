# -*- coding: utf-8 -*-
from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.controllers import chat_controller, health_controller
from backend.middleware.access_log import add_access_log_middleware


def create_app() -> FastAPI:
    app = FastAPI(title="StatYearbook Chat Backend", version="0.1.0")

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


def run() -> None:
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        access_log=False,
    )
