# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from time import perf_counter
from textwrap import dedent
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import settings
from utils.logging import compact_json


logger = logging.getLogger(__name__)


class ObservedCursor(psycopg.Cursor):
    """Log every MCP database statement without expanding large vector values."""

    # Record the submitted SQL, bounded parameters, outcome, and database duration.
    def execute(
        self,
        query,
        params=None,
        *,
        prepare: bool | None = None,
        binary: bool | None = None,
    ):
        started = perf_counter()
        sql = _sql_text(query, self)
        logged_params = compact_json(_compact_params(params), max_chars=1_200)
        try:
            result = super().execute(
                query,
                params,
                prepare=prepare,
                binary=binary,
            )
        except Exception as exc:
            logger.exception(
                "event=sql.error duration_ms=%s error_type=%s params=%s\n    sql=%s",
                _elapsed_ms(started),
                exc.__class__.__name__,
                logged_params,
                _indent_sql(sql),
            )
            raise
        logger.debug(
            "event=sql duration_ms=%s rows=%s params=%s\n    sql=%s",
            _elapsed_ms(started),
            self.rowcount,
            logged_params,
            _indent_sql(sql),
        )
        return result


# 결과 행을 dict 형태로 받는 DB 커넥션을 연다.
def connect() -> psycopg.Connection:
    started = perf_counter()
    try:
        connection = psycopg.connect(
            settings.dsn,
            row_factory=dict_row,
            cursor_factory=ObservedCursor,
        )
    except Exception as exc:
        logger.exception(
            "event=db.connect.error duration_ms=%s error_type=%s",
            _elapsed_ms(started),
            exc.__class__.__name__,
        )
        raise
    return connection


# Normalize string and psycopg SQL objects while preserving useful SQL line breaks.
def _sql_text(query: Any, cursor: psycopg.Cursor) -> str:
    if hasattr(query, "as_string"):
        text = query.as_string(cursor.connection)
    else:
        text = str(query)
    return "\n".join(
        line.strip()
        for line in dedent(text).strip().splitlines()
        if line.strip()
    )


# Indent every continuation line under the SQL log header.
def _indent_sql(sql: str) -> str:
    return sql.replace("\n", "\n        ")


# Replace large SQL parameters such as pgvector literals with compact summaries.
def _compact_params(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 200:
        return f"{value[:120]}...<chars={len(value)}>"
    if isinstance(value, bytes) and len(value) > 80:
        return f"<bytes={len(value)}>"
    if isinstance(value, dict):
        return {str(key): _compact_params(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_compact_params(item) for item in value]
    return value


# Convert a monotonic start timestamp into rounded milliseconds.
def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
