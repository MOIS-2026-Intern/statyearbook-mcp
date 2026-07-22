# 이 파일은 적재된 발간연도의 통계표·원자료 표·임베딩 건수를 검증한다.
# 검증 결과가 model profile과 다르면 관리자 작업을 실패 처리한다.


# dict-row와 tuple-row 모두에서 단일 집계값을 읽는다.
def _first_value(row):
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


class YearbookVerificationService:
    # 호출자가 연 트랜잭션에서 적재 건수와 두 임베딩 프로필을 교차 검증한다.
    def verify_connection(
        self,
        conn,
        year: int,
        profile_key: str | None,
        table_profile_key: str | None = None,
    ) -> dict:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS statistics_count,
                       COALESCE(SUM((
                           SELECT COUNT(*) FROM stat_tables t WHERE t.stat_id = s.stat_id
                       )), 0) AS table_count
                FROM statistics s WHERE s.year = %s
                """,
                (year,),
            )
            counts = cur.fetchone()
            if isinstance(counts, dict):
                statistics_count = counts["statistics_count"]
                table_count = counts["table_count"]
            else:
                statistics_count, table_count = counts
            current_count = 0
            table_chunk_count = 0
            current_table_count = 0
            if profile_key:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM statistics
                    WHERE year = %s AND embedding IS NOT NULL
                      AND embedding_profile_key = %s
                    """,
                    (year, profile_key),
                )
                current_count = _first_value(cur.fetchone())
            cur.execute(
                """
                SELECT COUNT(*)
                FROM table_search_chunks c
                JOIN stat_tables t ON t.table_id = c.table_id
                JOIN statistics s ON s.stat_id = t.stat_id
                WHERE s.year = %s
                """,
                (year,),
            )
            table_chunk_count = _first_value(cur.fetchone())
            if table_profile_key:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM table_search_chunks c
                    JOIN stat_tables t ON t.table_id = c.table_id
                    JOIN statistics s ON s.stat_id = t.stat_id
                    WHERE s.year = %s AND c.embedding IS NOT NULL
                      AND c.embedding_profile_key = %s
                    """,
                    (year, table_profile_key),
                )
                current_table_count = _first_value(cur.fetchone())
        if profile_key and current_count != statistics_count:
            raise RuntimeError(
                f"embedding verification failed: {current_count}/{statistics_count}"
            )
        if table_profile_key and current_table_count != table_chunk_count:
            raise RuntimeError(
                "table search embedding verification failed: "
                f"{current_table_count}/{table_chunk_count}"
            )
        return {
            "statistics_count": int(statistics_count),
            "table_count": int(table_count),
            "verified_embedding_count": int(current_count),
            "table_search_chunk_count": int(table_chunk_count),
            "verified_table_embedding_count": int(current_table_count),
        }
