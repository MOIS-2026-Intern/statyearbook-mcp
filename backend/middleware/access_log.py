# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from time import perf_counter
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response


logger = logging.getLogger(__name__)


# health 성공을 제외한 HTTP 결과와 소요 시간을 기록하는 미들웨어를 등록한다.
def add_access_log_middleware(app: FastAPI) -> None:
    # 요청을 실행하고 성공·실패 상태와 처리 시간을 서버 로그에 남긴다.
    @app.middleware("http")
    async def access_log(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            event = "health" if request.url.path == "/health" else "http"
            logger.exception(
                "event=%s.error method=%s path=%s status=%s "
                "duration_ms=%s error_type=%s",
                event,
                request.method,
                request.url.path,
                500,
                _elapsed_ms(started),
                exc.__class__.__name__,
            )
            raise

        if request.url.path == "/health":
            if response.status_code >= 400:
                logger.error(
                    "event=health.error method=%s path=%s status=%s duration_ms=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    _elapsed_ms(started),
                )
            return response

        logger.info(
            "event=http method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            _elapsed_ms(started),
        )
        return response


# 요청 시작 시각부터의 경과 시간을 밀리초로 계산한다.
def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
