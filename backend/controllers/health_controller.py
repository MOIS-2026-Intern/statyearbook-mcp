# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.models.health import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
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
