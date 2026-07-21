# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.models.health import HealthResponse


router = APIRouter()


# 백엔드의 프로필·모델·MCP 연결 상태를 헬스 정보로 반환한다.
@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        profile=settings.profile,
        modelProvider=settings.model_provider,
        chatModel=settings.chat_model,
        modelConfigured=settings.model_configured,
        mcp={
            "transport": "streamable-http",
            "serverLabel": settings.mcp_server_label,
            "url": settings.mcp_url,
        },
    )
