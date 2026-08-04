# -*- coding: utf-8 -*-
"""휴면 상태로 내려간 원격 MCP 인스턴스를 요청 전에 깨운다."""
from __future__ import annotations

import asyncio
import logging

from collections.abc import Callable
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.config import Settings


logger = logging.getLogger(__name__)

# 이미 깨어 있는지 확인하는 짧은 요청의 제한 시간이다.
_QUICK_PROBE_TIMEOUT_SECONDS = 5.0
# 인스턴스가 곧바로 오류를 돌려줄 때만 쉬었다가 다시 기다린다.
_RETRY_INTERVAL_SECONDS = 3.0


# MCP 엔드포인트 URL에서 같은 서비스의 health 경로를 만든다.
def health_url(mcp_url: str) -> str:
    parts = urlsplit(mcp_url)
    path = parts.path.rstrip("/")
    if path.endswith("/mcp"):
        path = path[: -len("/mcp")]
    return urlunsplit((parts.scheme, parts.netloc, f"{path}/health", "", ""))


# health 요청으로 휴면 인스턴스를 깨우고 응답할 때까지 기다린다.
# 깨우기는 최선 노력이라 실패해도 예외 대신 False를 돌려주고 연결 시도는 이어간다.
async def wake_mcp(
    settings: Settings,
    on_cold_start: Callable[[], None] | None = None,
) -> bool:
    if not settings.mcp_wake_enabled:
        return True

    url = health_url(settings.mcp_url)
    started = perf_counter()
    budget = settings.mcp_wake_timeout_seconds

    async with httpx.AsyncClient(follow_redirects=True) as client:
        if await _probe(client, url, _QUICK_PROBE_TIMEOUT_SECONDS):
            logger.debug(
                "event=mcp.wake outcome=awake mode=quick duration_ms=%s",
                _elapsed_ms(started),
            )
            return True

        logger.info("event=mcp.wake outcome=cold url=%s", url)
        _notify_cold_start(on_cold_start)

        # 잠든 인스턴스로 온 요청은 라우터가 붙들고 있다가 부팅이 끝나면 전달한다.
        # 짧게 끊어 재시도하면 어떤 요청도 부팅을 기다리지 못하므로 한 번에 길게 기다린다.
        attempt = 0
        while True:
            remaining = budget - (perf_counter() - started)
            if remaining <= 0:
                logger.warning(
                    "event=mcp.wake outcome=timeout attempts=%s duration_ms=%s url=%s",
                    attempt,
                    _elapsed_ms(started),
                    url,
                )
                return False

            attempt += 1
            if await _probe(client, url, remaining):
                logger.info(
                    "event=mcp.wake outcome=awake mode=patient attempts=%s duration_ms=%s",
                    attempt,
                    _elapsed_ms(started),
                )
                return True

            # 오류가 즉시 돌아온 경우에만 여기 도달한다. 잠시 쉬고 남은 예산으로 다시 기다린다.
            await asyncio.sleep(_RETRY_INTERVAL_SECONDS)


# health 응답으로 인스턴스가 깨어났는지 판단한다.
# 5xx는 라우터가 인스턴스를 아직 못 띄운 상태이고, 그 외 응답은 이미 깨어 있다는 뜻이다.
async def _probe(client: httpx.AsyncClient, url: str, timeout: float) -> bool:
    try:
        return (await client.get(url, timeout=timeout)).status_code < 500
    except httpx.HTTPError:
        return False


# 콜드 스타트 알림 실패가 깨우기 자체를 막지 않도록 콜백 예외를 흡수한다.
def _notify_cold_start(on_cold_start: Callable[[], None] | None) -> None:
    if on_cold_start is None:
        return
    try:
        on_cold_start()
    except Exception:
        logger.warning("event=mcp.wake.notify.error", exc_info=True)


# Convert a monotonic start timestamp into rounded milliseconds.
def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
