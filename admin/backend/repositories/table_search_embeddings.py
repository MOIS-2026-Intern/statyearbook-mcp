# 이 파일은 표 검색 청크 생성, 임베딩 대상 조회와 벡터 저장을 담당한다.
from __future__ import annotations

from admin.backend.models.embedding import EmbeddingBatch
from utils.embedding import EmbeddingConfigurationError
from utils.vector import vector_literal


# tuple과 dict 결과 모두에서 단일 집계값을 꺼낸다.
def _first_value(row):
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


class TableSearchEmbeddingRepository:
    # 표 검색 임베딩 작업을 선택한 발간연도에 한정한다.
    def __init__(self, publication_year: int | None = None):
        self.publication_year = publication_year
        self.name = (
            f"table_search:{publication_year}"
            if publication_year is not None
            else "table_search"
        )

    # statistics 별칭을 기준으로 선택적 연도 범위 조건을 만든다.
    def _scope_sql(self) -> str:
        return "s.year = %s" if self.publication_year is not None else "TRUE"

    # 연도 범위 조건에 필요한 인자만 순서대로 반환한다.
    def _scope_params(self) -> list:
        return [self.publication_year] if self.publication_year is not None else []

    # 표 검색 벡터 열의 실제 차원이 모델과 일치하는지 쓰기 전에 확인한다.
    def select_and_validate_dimension(self, conn, expected_dimension: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                WHERE a.attrelid = 'table_search_chunks'::regclass
                  AND a.attname = 'embedding'
                  AND NOT a.attisdropped
                """
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("table_search_chunks.embedding column was not found")
        actual_type = str(_first_value(row))
        expected_type = f"vector({expected_dimension})"
        if actual_type != expected_type:
            raise EmbeddingConfigurationError(
                f"table_search_chunks.embedding is {actual_type}, but the configured "
                f"model requires {expected_type}; provision the matching database schema "
                "before re-embedding"
            )

    # 실행 중 새 청크가 섞이지 않도록 시작 시점의 최대 청크 ID를 고정한다.
    def select_max_source_id(self, conn) -> int:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(MAX(c.chunk_id), 0)
                FROM table_search_chunks c
                JOIN stat_tables t ON t.table_id = c.table_id
                JOIN statistics s ON s.stat_id = t.stat_id
                WHERE {self._scope_sql()}
                """,
                self._scope_params(),
            )
            return int(_first_value(cur.fetchone()))

    # 강제 실행 또는 profile 불일치에 맞는 후보 SQL 조건을 반환한다.
    def _candidate_sql(self, force: bool) -> str:
        if force:
            return "TRUE"
        return "(c.embedding IS NULL OR c.embedding_profile_key IS DISTINCT FROM %s)"

    # 현재 연도와 고정된 최대 ID 안에서 처리 대상 청크 수를 센다.
    def select_candidate_count(
        self,
        conn,
        profile_key: str,
        force: bool,
        max_source_id: int,
    ) -> int:
        params = [] if force else [profile_key]
        params.extend(self._scope_params())
        params.append(max_source_id)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM table_search_chunks c
                JOIN stat_tables t ON t.table_id = c.table_id
                JOIN statistics s ON s.stat_id = t.stat_id
                WHERE {self._candidate_sql(force)}
                  AND {self._scope_sql()}
                  AND c.chunk_id <= %s
                """,
                params,
            )
            return int(_first_value(cur.fetchone()))

    # 청크 ID 커서를 사용해 다음 검색 문구 배치를 안정적으로 조회한다.
    def select_candidate_batch(
        self,
        conn,
        profile_key: str,
        force: bool,
        after_source_id: int,
        max_source_id: int,
        batch_size: int,
    ) -> EmbeddingBatch:
        params = [] if force else [profile_key]
        params.extend(self._scope_params())
        params.extend([after_source_id, max_source_id, batch_size])
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT c.chunk_id, c.chunk_no, c.chunk_kind, c.search_text,
                       t.seq AS table_seq,
                       s.year, s.ref_id, s.title_ko
                FROM table_search_chunks c
                JOIN stat_tables t ON t.table_id = c.table_id
                JOIN statistics s ON s.stat_id = t.stat_id
                WHERE {self._candidate_sql(force)}
                  AND {self._scope_sql()}
                  AND c.chunk_id > %s
                  AND c.chunk_id <= %s
                ORDER BY c.chunk_id
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
        last_source_id = int(rows[-1]["chunk_id"]) if rows else after_source_id
        return EmbeddingBatch(rows=rows, last_source_id=last_source_id)

    # 저장된 표 검색 문구를 모델 입력 순서 그대로 추출한다.
    def select_embedding_texts(self, rows: list[dict]) -> list[str]:
        return [str(row["search_text"]) for row in rows]

    # 생성된 벡터와 profile key를 대응하는 검색 청크에 일괄 반영한다.
    def update_embedding_batch(
        self,
        conn,
        rows: list[dict],
        vectors: list[list[float]],
        profile_key: str,
    ) -> None:
        params = [
            (vector_literal(vector), profile_key, row["chunk_id"])
            for row, vector in zip(rows, vectors)
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """
                UPDATE table_search_chunks
                SET embedding = %s::vector, embedding_profile_key = %s
                WHERE chunk_id = %s
                """,
                params,
            )
