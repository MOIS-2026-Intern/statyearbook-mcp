# 이 파일은 statistics 테이블의 임베딩 대상 조회와 벡터 저장을 담당한다.
# 발간연도 범위와 현재 model profile을 기준으로 증분 대상을 선택한다.
from __future__ import annotations

from app.embedding import EmbeddingConfigurationError
from app.vector import vector_literal
from admin.backend.services.load_embedding import EmbeddingBatch, WeightedEmbeddingTexts


LEVEL4_EMBEDDING_WEIGHT = 0.70
HIERARCHY_CONTEXT_WEIGHT = 0.30


def _first_value(row):
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


class StatisticsEmbeddingRepository:
    def __init__(self, publication_year: int | None = None):
        self.publication_year = publication_year
        self.name = (
            f"statistics:{publication_year}"
            if publication_year is not None
            else "statistics"
        )

    def _scope_sql(self) -> str:
        return "year = %s" if self.publication_year is not None else "TRUE"

    def _scope_params(self) -> list:
        return [self.publication_year] if self.publication_year is not None else []

    def select_embedding_column_type(self, conn) -> str:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                WHERE a.attrelid = 'statistics'::regclass
                  AND a.attname = 'embedding'
                  AND NOT a.attisdropped
                """
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("statistics.embedding column was not found")
        return str(next(iter(row.values())) if isinstance(row, dict) else row[0])

    def select_and_validate_dimension(self, conn, expected_dimension: int) -> None:
        actual_type = self.select_embedding_column_type(conn)
        expected_type = f"vector({expected_dimension})"
        if actual_type != expected_type:
            raise EmbeddingConfigurationError(
                f"statistics.embedding is {actual_type}, but the configured model requires "
                f"{expected_type}; apply db/schema.sql before re-embedding"
            )

    def select_max_source_id(self, conn) -> int:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COALESCE(MAX(stat_id), 0) FROM statistics WHERE {self._scope_sql()}",
                self._scope_params(),
            )
            return int(_first_value(cur.fetchone()))

    def _candidate_sql(self, force: bool) -> str:
        if force:
            return "TRUE"
        return "(embedding IS NULL OR embedding_profile_key IS DISTINCT FROM %s)"

    def select_candidate_count(
        self,
        conn,
        profile_key: str,
        force: bool,
        max_source_id: int,
    ) -> int:
        condition = self._candidate_sql(force)
        params = [] if force else [profile_key]
        params.extend(self._scope_params())
        params.append(max_source_id)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM statistics
                WHERE {condition} AND {self._scope_sql()} AND stat_id <= %s
                """,
                params,
            )
            return int(_first_value(cur.fetchone()))

    def select_candidate_batch(
        self,
        conn,
        profile_key: str,
        force: bool,
        after_source_id: int,
        max_source_id: int,
        batch_size: int,
    ) -> EmbeddingBatch:
        condition = self._candidate_sql(force)
        params = [] if force else [profile_key]
        params.extend(self._scope_params())
        params.extend([after_source_id, max_source_id, batch_size])
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT stat_id, year, ref_id, title_ko, title_en,
                       chapter, section, level3_title, level4_title, page_start
                FROM statistics
                WHERE {condition}
                  AND {self._scope_sql()}
                  AND stat_id > %s
                  AND stat_id <= %s
                ORDER BY stat_id
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
        last_source_id = int(rows[-1]["stat_id"]) if rows else after_source_id
        return EmbeddingBatch(rows=rows, last_source_id=last_source_id)

    def select_embedding_texts(self, rows: list[dict]) -> WeightedEmbeddingTexts:
        return WeightedEmbeddingTexts(groups=(
            (
                LEVEL4_EMBEDDING_WEIGHT,
                [self._build_level4_embedding_text(row) for row in rows],
            ),
            (
                HIERARCHY_CONTEXT_WEIGHT,
                [self._build_hierarchy_context_text(row) for row in rows],
            ),
        ))

    def _join_unique(self, parts: list[str | None]) -> str:
        unique_parts = []
        for part in parts:
            if part and part not in unique_parts:
                unique_parts.append(part)
        return " ".join(unique_parts).strip() or "(제목 없음)"

    def _build_level4_embedding_text(self, row: dict) -> str:
        return self._join_unique([
            row.get("level4_title"),
            row.get("title_ko"),
            row.get("title_en"),
        ])

    def _build_hierarchy_context_text(self, row: dict) -> str:
        return self._join_unique([
            row.get("level3_title"),
            row.get("section"),
            row.get("chapter"),
        ])

    def update_embedding_batch(
        self,
        conn,
        rows: list[dict],
        vectors: list[list[float]],
        profile_key: str,
    ) -> None:
        params = [
            (vector_literal(vector), profile_key, row["stat_id"])
            for vector, row in zip(vectors, rows)
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """
                UPDATE statistics
                SET embedding = %s::vector, embedding_profile_key = %s
                WHERE stat_id = %s
                """,
                params,
            )

    def select_embedding_status(self, conn, profile_key: str) -> dict:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS total_count,
                       COUNT(embedding) AS embedded_count,
                       COUNT(*) FILTER (
                           WHERE embedding IS NOT NULL
                             AND embedding_profile_key = %s
                       ) AS current_count
                FROM statistics
                WHERE {self._scope_sql()}
                """,
                [profile_key, *self._scope_params()],
            )
            row = cur.fetchone()
        status = dict(row) if isinstance(row, dict) else {
            "total_count": row[0],
            "embedded_count": row[1],
            "current_count": row[2],
        }
        status["pending_count"] = status["total_count"] - status["current_count"]
        return status
