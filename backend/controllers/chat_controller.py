# -*- coding: utf-8 -*-
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from backend.config import settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError
from backend.models.chat import ChatRequest, ChatResponse
from backend.services.chat_service import ChatService


router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# 프록시 헤더를 우선해 로그에 남길 클라이언트 IP를 구한다.
def _client_ip(request: Request) -> str | None:
    """Resolve the requester's IP, preferring proxy-forwarded headers."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else None


# 채팅 요청을 서비스에 위임하고 구성·실행 오류를 HTTP 응답으로 변환한다.
@router.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    logger.info(
        "Chat request received clientIp=%s\n          message=%r",
        _client_ip(request),
        payload.message,
    )
    try:
        return await ChatService(settings).respond(payload)
    except ModelGatewayConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
