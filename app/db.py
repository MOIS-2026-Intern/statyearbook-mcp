# -*- coding: utf-8 -*-
import psycopg
from psycopg.rows import dict_row

from app.config import settings


# 결과 행을 dict 형태로 받는 DB 커넥션을 연다.
def connect() -> psycopg.Connection:
    return psycopg.connect(settings.dsn, row_factory=dict_row)
