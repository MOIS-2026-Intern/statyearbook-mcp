# 이 파일은 적재된 발간연도의 통계표·원자료 표·임베딩 건수를 검증한다.
# 검증 결과가 model profile과 다르면 관리자 작업을 실패 처리한다.
import psycopg


class YearbookVerificationService:
    def verify(self, dsn: str, year: int, profile_key: str | None) -> dict:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS statistics_count,
                       COALESCE(SUM((
                           SELECT COUNT(*) FROM stat_tables t WHERE t.stat_id = s.stat_id
                       )), 0)
                FROM statistics s WHERE s.year = %s
                """,
                (year,),
            )
            statistics_count, table_count = cur.fetchone()
            current_count = 0
            if profile_key:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM statistics
                    WHERE year = %s AND embedding IS NOT NULL
                      AND embedding_profile_key = %s
                    """,
                    (year, profile_key),
                )
                current_count = cur.fetchone()[0]
        if profile_key and current_count != statistics_count:
            raise RuntimeError(
                f"embedding verification failed: {current_count}/{statistics_count}"
            )
        return {
            "statistics_count": int(statistics_count),
            "table_count": int(table_count),
            "verified_embedding_count": int(current_count),
        }
