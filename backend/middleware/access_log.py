# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from time import perf_counter
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response


logger = logging.getLogger("uvicorn.error")


def add_access_log_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def access_log(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception(
                "HTTP request failed method=%s path=%s status=%s durationMs=%s errorType=%s",
                request.method,
                request.url.path,
                500,
                _elapsed_ms(started),
                exc.__class__.__name__,
            )
            raise

        logger.info(
            "HTTP request completed method=%s path=%s status=%s durationMs=%s",
            request.method,
            request.url.path,
            response.status_code,
            _elapsed_ms(started),
        )
        return response


def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
