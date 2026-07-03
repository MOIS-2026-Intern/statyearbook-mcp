# -*- coding: utf-8 -*-
from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.models import ChatRequest, ChatResponse, HealthResponse
from backend.services.chat_service import ChatService
from backend.services.openai_responses import OpenAIConfigurationError


def create_app() -> FastAPI:
    app = FastAPI(title="StatYearbook Chat Backend", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            app=settings.app_name,
            openaiModel=settings.openai_model,
            openaiConfigured=settings.has_openai_key,
            mcp={
                "transport": "stdio",
                "serverLabel": settings.mcp_server_label,
                "command": settings.mcp_command,
                "args": settings.mcp_args,
                "cwd": settings.mcp_cwd,
            },
        )

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        try:
            return await ChatService(settings).respond(request)
        except OpenAIConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
