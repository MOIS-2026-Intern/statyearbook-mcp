# 이 파일은 생성된 DML을 지정한 PostgreSQL 연결에서 트랜잭션으로 실행한다.
# DML 생성 서비스와 실제 데이터베이스 접근을 분리하는 저장소 경계다.
from pathlib import Path

import psycopg


class PostgresDmlRepository:
    def execute_dml(self, dsn: str, dml: str) -> None:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(dml)
            conn.commit()

    def execute_dml_file(self, dsn: str, path: str | Path) -> None:
        self.execute_dml(dsn, Path(path).read_text(encoding="utf-8"))
