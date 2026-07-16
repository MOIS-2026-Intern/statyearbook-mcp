# 이 파일은 생성된 DML을 지정한 PostgreSQL 연결에서 트랜잭션으로 실행한다.
# DML 생성 서비스와 실제 데이터베이스 접근을 분리하는 저장소 경계다.
import psycopg


class PostgresDmlRepository:
    def execute(self, dsn: str, dml: str) -> None:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(dml)
            conn.commit()
