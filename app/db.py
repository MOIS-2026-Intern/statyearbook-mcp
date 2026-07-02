# -*- coding: utf-8 -*-
"""DB 접속 헬퍼.

도구들이 매번 DSN/row_factory 를 직접 다루지 않도록 얇게 감싼다.
psycopg 커넥션은 with 문으로 쓰면 블록을 벗어날 때 자동으로 닫힌다.
"""
import psycopg
from psycopg.rows import dict_row

from app.config import DSN


def connect() -> psycopg.Connection:
    """dict_row 로 결과를 돌려주는 psycopg 커넥션을 연다.

    사용 예)
        with connect() as conn, conn.cursor() as cur:
            cur.execute(...)
    """
    return psycopg.connect(DSN, row_factory=dict_row)
