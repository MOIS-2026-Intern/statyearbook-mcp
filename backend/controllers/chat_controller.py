# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.config import settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError
from backend.models.chat import ChatProgress, ChatRequest, ChatResponse
from backend.services.chat_service import ChatService
from utils.logging import compact_json


router = APIRouter()
logger = logging.getLogger(__name__)
_chat_service: ChatService | None = None


# 모델 HTTP 연결 풀을 요청 사이에 재사용할 공유 채팅 서비스를 지연 생성한다.
def _get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService(settings)
    return _chat_service


# 애플리케이션 종료 시 공유 모델 HTTP 연결 풀을 정리한다.
async def close_chat_service() -> None:
    global _chat_service
    service = _chat_service
    _chat_service = None
    if service is not None:
        await service.close()


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
    logger.debug(
        "event=chat ip=[%s]\n    message=%s",
        _client_ip(request),
        compact_json(payload.message, max_chars=300),
    )
    try:
        return await _get_chat_service().respond(payload)
    except ModelGatewayConfigurationError as exc:
        logger.error(
            "event=chat.error error_type=%s error=%s",
            exc.__class__.__name__,
            compact_json(str(exc)),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "event=chat.error error_type=%s error=%s",
            exc.__class__.__name__,
            compact_json(str(exc)),
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# 진행 상태와 최종 응답을 줄 단위 JSON으로 즉시 전달한다.
@router.post("/api/chat/stream")
async def stream_chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    logger.debug(
        "event=chat.stream ip=[%s]\n    message=%s",
        _client_ip(request),
        compact_json(payload.message, max_chars=300),
    )
    return StreamingResponse(
        _stream_chat_events(payload),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


# 서비스 실행은 별도 task에 두고 콜백은 non-blocking queue 쓰기만 수행한다.
async def _stream_chat_events(payload: ChatRequest) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def on_progress(progress: ChatProgress) -> None:
        queue.put_nowait(
            {
                "type": "progress",
                "progress": progress.model_dump(mode="json"),
            }
        )

    async def run_chat() -> None:
        try:
            response = await _get_chat_service().respond(payload, on_progress=on_progress)
            queue.put_nowait(
                {
                    "type": "result",
                    "response": response.model_dump(mode="json"),
                }
            )
        except ModelGatewayConfigurationError as exc:
            logger.error(
                "event=chat.stream.error error_type=%s error=%s",
                exc.__class__.__name__,
                compact_json(str(exc)),
            )
            queue.put_nowait({"type": "error", "error": str(exc)})
        except Exception as exc:
            logger.exception(
                "event=chat.stream.error error_type=%s error=%s",
                exc.__class__.__name__,
                compact_json(str(exc)),
            )
            queue.put_nowait({"type": "error", "error": str(exc)})

    task = asyncio.create_task(run_chat())
    try:
        while True:
            event = await queue.get()
            yield (
                json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            if event["type"] in {"result", "error"}:
                break
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
