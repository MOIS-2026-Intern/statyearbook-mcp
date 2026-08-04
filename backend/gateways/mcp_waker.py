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

# 깨우기 요청 하나가 기다리는 시간과 재시도 간격이다.
_PROBE_TIMEOUT_SECONDS = 10.0
_PROBE_INTERVAL_SECONDS = 3.0


# MCP 엔드포인트 URL에서 같은 서비스의 health 경로를 만든다.
def health_url(mcp_url: str) -> str:
    parts = urlsplit(mcp_url)
    path = parts.path.rstrip("/")
    if path.endswith("/mcp"):
        path = path[: -len("/mcp")]
    return urlunsplit((parts.scheme, parts.netloc, f"{path}/health", "", ""))


# health 요청을 반복해 휴면 인스턴스가 응답할 때까지 기다린다.
# 깨우기는 최선 노력이라 실패해도 예외 대신 False를 돌려주고 연결 시도는 이어간다.
async def wake_mcp(
    settings: Settings,
    on_cold_start: Callable[[], None] | None = None,
) -> bool:
    if not settings.mcp_wake_enabled:
        return True

    url = health_url(settings.mcp_url)
    started = perf_counter()
    deadline = started + settings.mcp_wake_timeout_seconds
    attempt = 0
    notified = False

    async with httpx.AsyncClient(
        timeout=_PROBE_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        while True:
            attempt += 1
            try:
                # 5xx는 라우터가 인스턴스를 아직 못 띄운 상태이고, 그 외 응답은 이미 깨어 있다는 뜻이다.
                awake = (await client.get(url)).status_code < 500
            except httpx.HTTPError:
                awake = False

            if awake:
                log = logger.debug if attempt == 1 else logger.info
                log(
                    "event=mcp.wake outcome=awake attempts=%s duration_ms=%s",
                    attempt,
                    _elapsed_ms(started),
                )
                return True

            if not notified:
                notified = True
                logger.info("event=mcp.wake outcome=cold url=%s", url)
                _notify_cold_start(on_cold_start)

            if perf_counter() >= deadline:
                logger.warning(
                    "event=mcp.wake outcome=timeout attempts=%s duration_ms=%s url=%s",
                    attempt,
                    _elapsed_ms(started),
                    url,
                )
                return False

            await asyncio.sleep(_PROBE_INTERVAL_SECONDS)


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
