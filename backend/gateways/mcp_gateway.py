# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging

from collections.abc import Callable
from contextlib import AsyncExitStack
from datetime import timedelta
from time import perf_counter
from typing import Any

import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend.config import Settings
from backend.gateways.mcp_waker import wake_mcp
from backend.models.tooling import ToolSpec
from backend.serializers.mcp_result_serializer import sanitize_mcp_result, to_jsonable
from utils.logging import compact_json


logger = logging.getLogger(__name__)

# 도구 호출 응답을 실어 나르는 SSE 스트림이 조용해도 끊지 않는 시간이다.
# 잠든 인스턴스로 보낸 요청을 라우터가 붙들고 있는 동안에도 이 시간만큼 기다린다.
_SSE_READ_TIMEOUT_SECONDS = 300.0

# 429를 돌려받았을 때 다시 연결해 보는 횟수와 한 번에 기다릴 최대 시간이다.
_CONNECT_MAX_ATTEMPTS = 3
_RETRY_AFTER_MAX_SECONDS = 30.0

_TOOL_SPECS_CACHE: dict[str, tuple[float, tuple[ToolSpec, ...]]] = {}


class McpGatewayError(RuntimeError):
    pass


class McpGateway:
    # MCP 연결 설정과 세션 상태를 초기화한다.
    # on_cold_start는 휴면 인스턴스를 깨우기 시작할 때 한 번 호출된다.
    def __init__(
        self,
        settings: Settings,
        on_cold_start: Callable[[], None] | None = None,
    ):
        self._settings = settings
        self._on_cold_start = on_cold_start
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tool_specs_cache_hit = False

    # 휴면 인스턴스를 깨운 뒤 streamable HTTP 연결을 열고 MCP 세션을 초기화한다.
    # 라우터가 요청량을 제한해 429를 돌려주면 잠시 기다렸다가 다시 시도한다.
    async def __aenter__(self) -> "McpGateway":
        started = perf_counter()
        await wake_mcp(self._settings, self._on_cold_start)

        for attempt in range(1, _CONNECT_MAX_ATTEMPTS + 1):
            try:
                await self._open_session()
            except BaseException as exc:
                cause = await self._close(exc)
                if _is_external_cancellation(exc):
                    raise

                delay = _retry_after_seconds(cause, attempt)
                if delay is not None and attempt < _CONNECT_MAX_ATTEMPTS:
                    logger.warning(
                        "event=mcp.connect.retry attempt=%s delay_s=%s error=%s",
                        attempt,
                        delay,
                        cause,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(
                    "event=mcp.connect.error url=%s duration_ms=%s attempts=%s error_type=%s error=%s",
                    self._settings.mcp_url,
                    _elapsed_ms(started),
                    attempt,
                    cause.__class__.__name__,
                    cause,
                    exc_info=cause,
                )
                raise McpGatewayError(
                    f"MCP 서버에 연결하지 못했습니다 ({self._settings.mcp_url}): {cause}"
                ) from cause
            break

        logger.debug(
            "event=mcp.connect duration_ms=%s attempts=%s",
            _elapsed_ms(started),
            attempt,
        )
        return self

    # streamable HTTP 연결을 열고 MCP 세션을 초기화한다.
    async def _open_session(self) -> None:
        self._stack = AsyncExitStack()
        # 전송 계층이 종료 요청을 보낼 때까지 살아 있도록 클라이언트를 먼저 등록한다.
        http_client = await self._stack.enter_async_context(self._create_http_client())
        read_stream, write_stream, _ = await self._stack.enter_async_context(
            streamable_http_client(self._settings.mcp_url, http_client=http_client)
        )
        self._session = await self._stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()

    # 콜드 스타트 직후의 느린 첫 응답을 견디도록 MCP 전용 HTTP 클라이언트를 만든다.
    def _create_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(
                self._settings.mcp_connect_timeout_seconds,
                read=_SSE_READ_TIMEOUT_SECONDS,
            ),
        )

    # 컨텍스트 종료 시 MCP 연결 자원과 세션 상태를 정리한다.
    # 세션 도중 전송이 끊기면 취소 예외 대신 원인을 알 수 있는 오류로 바꿔 알린다.
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        cause = await self._close(None)
        if cause is None:
            return
        # 본문에서 이미 원인이 분명한 예외가 올라오는 중이면 정리 오류로 덮지 않는다.
        if isinstance(exc, BaseException) and not isinstance(exc, asyncio.CancelledError):
            logger.warning(
                "event=mcp.close.error url=%s error_type=%s error=%s",
                self._settings.mcp_url,
                cause.__class__.__name__,
                cause,
            )
            return
        if _is_external_cancellation(cause):
            raise cause
        logger.error(
            "event=mcp.close.error url=%s error_type=%s error=%s",
            self._settings.mcp_url,
            cause.__class__.__name__,
            cause,
            exc_info=cause,
        )
        raise McpGatewayError(
            f"MCP 연결이 끊겼습니다 ({self._settings.mcp_url}): {cause}"
        ) from cause

    # 연결 자원을 정리하고 취소 예외에 가려져 있던 실제 실패 원인을 돌려준다.
    # 전송 계층이 실패하면 원인은 정리 단계에서 ExceptionGroup으로 드러난다.
    async def _close(self, failure: BaseException | None) -> BaseException | None:
        stack = self._stack
        self._stack = None
        self._session = None
        if stack is None:
            return failure

        try:
            await stack.aclose()
        except BaseException as close_error:
            return _root_cause(close_error)
        return failure

    # 초기화된 MCP 세션만 반환하고 미연결 상태는 오류로 알린다.
    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise McpGatewayError("MCP session is not initialized")
        return self._session

    # MCP 서버가 공개한 원본 도구 목록을 조회한다.
    async def list_tools(self) -> list[Any]:
        started = perf_counter()
        try:
            result = await self.session.list_tools()
        except Exception as exc:
            logger.exception(
                "event=mcp.tools.error duration_ms=%s error_type=%s",
                _elapsed_ms(started),
                exc.__class__.__name__,
            )
            raise
        return list(result.tools)

    # MCP 도구 메타데이터를 모델이 사용하는 사양으로 변환한다.
    async def list_tool_specs(self) -> list[ToolSpec]:
        cache_key = self._settings.mcp_url
        cached = _TOOL_SPECS_CACHE.get(cache_key)
        now = perf_counter()
        if (
            cached is not None
            and self._settings.mcp_tool_cache_ttl_seconds > 0
            and now - cached[0] < self._settings.mcp_tool_cache_ttl_seconds
        ):
            self._tool_specs_cache_hit = True
            logger.debug(
                "event=mcp.tools.cache tools=%s",
                len(cached[1]),
            )
            return list(cached[1])

        specs = tuple(tool_spec_from_mcp(tool) for tool in await self.list_tools())
        self._tool_specs_cache_hit = False
        if specs and self._settings.mcp_tool_cache_ttl_seconds > 0:
            _TOOL_SPECS_CACHE[cache_key] = (now, specs)
        return list(specs)

    # 직전 도구 사양 조회가 네트워크 대신 캐시를 사용했는지 반환한다.
    @property
    def tool_specs_cache_hit(self) -> bool:
        return self._tool_specs_cache_hit

    # 인자를 정규화해 MCP 도구를 호출하고 결과를 안전한 JSON 형태로 반환한다.
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        args = self.prepare_tool_arguments(name, arguments)
        started = perf_counter()
        try:
            result = await self.session.call_tool(
                name,
                args,
                read_timeout_seconds=timedelta(seconds=self._settings.mcp_call_timeout_seconds),
            )
            payload = sanitize_mcp_result(result)
        except Exception as exc:
            logger.exception(
                "event=mcp.call.error tool=%s duration_ms=%s error_type=%s\n"
                "    args=%s",
                name,
                _elapsed_ms(started),
                exc.__class__.__name__,
                compact_json(args, max_chars=300),
            )
            raise

        log = logger.error if payload.get("isError") else logger.debug
        log(
            "event=%s tool=%s duration_ms=%s\n    args=%s",
            "mcp.call.error" if payload.get("isError") else "mcp.call",
            name,
            _elapsed_ms(started),
            compact_json(args, max_chars=300),
        )
        return payload

    # 도구 호출 인자를 변경 가능한 복사본으로 준비한다.
    def prepare_tool_arguments(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return dict(arguments)


# Convert a monotonic start timestamp into rounded milliseconds.
def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)


# 취소가 호출자에게서 온 것인지 전송 계층 내부에서 온 것인지 구분한다.
# 전송 실패로 생긴 취소는 자원 정리 과정에서 해제되어 카운터가 0으로 돌아오지만,
# 요청 취소나 종료로 생긴 취소는 카운터가 남아 있으므로 그대로 전파해야 한다.
def _is_external_cancellation(error: BaseException) -> bool:
    if not isinstance(error, asyncio.CancelledError):
        return False
    task = asyncio.current_task()
    return task is None or task.cancelling() > 0


# 429 응답이면 다시 시도하기까지 기다릴 시간을 정하고, 그 외 오류는 재시도하지 않는다.
# 서버가 Retry-After를 주지 않으면 시도 횟수에 따라 지수적으로 물러난다.
def _retry_after_seconds(error: BaseException, attempt: int) -> float | None:
    if not isinstance(error, httpx.HTTPStatusError):
        return None
    if error.response.status_code != httpx.codes.TOO_MANY_REQUESTS:
        return None

    try:
        delay = float(error.response.headers.get("retry-after", ""))
    except ValueError:
        delay = float(2**attempt)
    return min(max(delay, 1.0), _RETRY_AFTER_MAX_SECONDS)


# ExceptionGroup에 감싸인 원인 중 취소가 아닌 첫 예외를 실제 실패 원인으로 고른다.
def _root_cause(error: BaseException) -> BaseException:
    if not isinstance(error, BaseExceptionGroup):
        return error
    for nested in error.exceptions:
        found = _root_cause(nested)
        if not isinstance(found, asyncio.CancelledError):
            return found
    return error


# MCP 도구의 입력 스키마를 유효한 JSON object 스키마로 정규화한다.
def _tool_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    payload = to_jsonable(schema)
    if not isinstance(payload, dict) or payload.get("type") != "object":
        return {"type": "object", "properties": {}}
    return payload


# MCP 도구 객체를 모델 gateway용 도구 사양으로 변환한다.
def tool_spec_from_mcp(tool: Any) -> ToolSpec:
    name = str(getattr(tool, "name", ""))
    return ToolSpec(
        name=name,
        description=getattr(tool, "description", None) or f"MCP tool {name}",
        input_schema=_tool_schema(tool),
    )


# trace에 담을 수 있도록 도구 사양을 일반 딕셔너리로 풀어낸다.
def describe_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


# 테스트와 명시적인 새로고침에서 공유 도구 사양 캐시를 비운다.
def clear_tool_specs_cache() -> None:
    _TOOL_SPECS_CACHE.clear()


# backend 기동 직후 MCP 인스턴스를 미리 깨우고 도구 사양 캐시를 채운다.
# 첫 채팅 요청이 콜드 스타트를 기다리지 않도록 백그라운드에서 실행한다.
async def warm_up_mcp(settings: Settings) -> None:
    if not settings.mcp_wake_enabled:
        return

    started = perf_counter()
    try:
        async with McpGateway(settings) as gateway:
            tools = await gateway.list_tool_specs()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "event=mcp.warmup.error duration_ms=%s error_type=%s",
            _elapsed_ms(started),
            exc.__class__.__name__,
        )
        return

    logger.info(
        "event=mcp.warmup tools=%s duration_ms=%s",
        len(tools),
        _elapsed_ms(started),
    )
