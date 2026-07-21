# 이 파일은 생성된 DML을 지정한 PostgreSQL 연결에서 트랜잭션으로 실행한다.
# DML 생성 서비스와 실제 데이터베이스 접근을 분리하는 저장소 경계다.
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


TRANSACTION_PREFIX = "BEGIN;\n"
TRANSACTION_SUFFIX = "COMMIT;\n"


# 이관용 SQL의 정확한 외부 트랜잭션 래퍼만 제거해 중첩 커밋을 막는다.
def _transaction_body(dml: str) -> str:
    if not dml.startswith(TRANSACTION_PREFIX) or not dml.endswith(TRANSACTION_SUFFIX):
        raise ValueError("DML artifact must have an exact outer BEGIN;/COMMIT; wrapper")
    body = dml[len(TRANSACTION_PREFIX):-len(TRANSACTION_SUFFIX)]
    if not body.strip():
        raise ValueError("DML artifact transaction body is empty")
    return body


class PostgresDmlRepository:
    # 적재 파이프라인 전체가 공유할 dict-row 연결을 열고 한 번만 커밋한다.
    @contextmanager
    def transaction(self, dsn: str) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(dsn, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    # 저장된 이관용 SQL의 본문만 현재 연결의 열린 트랜잭션에서 실행한다.
    def execute_dml_file(self, conn: psycopg.Connection, path: str | Path) -> None:
        dml = Path(path).read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(_transaction_body(dml))
