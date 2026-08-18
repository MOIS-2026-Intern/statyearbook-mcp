# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.config import settings
from backend.gateways.model_gateway import (
    ModelGatewayConfigurationError,
    UnsupportedChatModelError,
)
from backend.models.chat import (
    ChatModelOption,
    ChatModelsResponse,
    ChatProgress,
    ChatRequest,
    ChatResponse,
)
from backend.services.chat_service import ChatService
from utils.logging import compact_json


router = APIRouter()
logger = logging.getLogger(__name__)
_chat_service: ChatService | None = None

_MODEL_LABELS = {
    "openai/gpt-5-mini": "GPT-5 mini",
    "anthropic/claude-sonnet-5": "Claude Sonnet 5",
}


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


# UI가 백엔드와 같은 허용 목록과 기본값으로 모델 선택기를 구성하도록 공개한다.
@router.get("/api/models", response_model=ChatModelsResponse)
async def chat_models() -> ChatModelsResponse:
    return ChatModelsResponse(
        defaultModel=settings.chat_model,
        models=[
            ChatModelOption(id=model, label=_MODEL_LABELS.get(model, model))
            for model in settings.chat_models
        ],
    )


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
    except UnsupportedChatModelError as exc:
        logger.warning(
            "event=chat.error error_type=%s error=%s",
            exc.__class__.__name__,
            compact_json(str(exc)),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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

    # 생성 중인 답변 조각으로, 최종 result가 도착하면 그 내용으로 대체된다.
    def on_text_delta(text: str) -> None:
        queue.put_nowait({"type": "delta", "text": text})

    async def run_chat() -> None:
        try:
            response = await _get_chat_service().respond(
                payload,
                on_progress=on_progress,
                on_text_delta=on_text_delta,
            )
            queue.put_nowait(
                {
                    "type": "result",
                    "response": response.model_dump(mode="json"),
                }
            )
        except asyncio.CancelledError:
            # 중단된 요청은 알릴 상대가 없다. 결과를 queue에 남기지 않고 그대로 끝낸다.
            raise
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
    except (asyncio.CancelledError, GeneratorExit):
        # 멈춤 버튼은 클라이언트가 스트림을 끊는 것으로 도착한다. 서버는 이 지점에서
        # 취소되며, 아래 finally가 진행 중이던 추론·도구 호출을 함께 끊는다.
        logger.info(
            "event=chat.stream.stopped conversation=%s reason=client_disconnect",
            payload.conversationId,
        )
        raise
    finally:
        await _cancel_chat_run(task)


# 취소가 전파되면 모델 스트림과 MCP 세션을 닫는 동안만 기다린다. 정리가 응답하지 않는
# 연결에 걸려도 요청 처리가 그 자리에 묶이지 않도록 대기에 한도를 둔다.
_STOP_CLEANUP_TIMEOUT_SECONDS = 5.0


# 중단된 요청이 모델 토큰과 MCP 호출을 계속 쓰지 않도록 실행 task를 끊고 정리를 기다린다.
async def _cancel_chat_run(task: asyncio.Task[None]) -> None:
    if task.done():
        return

    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=_STOP_CLEANUP_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        pass
    except TimeoutError:
        # 취소는 이미 걸어 두었으므로 남은 정리는 task가 스스로 마친다.
        logger.warning(
            "event=chat.stream.stop_cleanup_timeout timeout_s=%s",
            _STOP_CLEANUP_TIMEOUT_SECONDS,
        )
