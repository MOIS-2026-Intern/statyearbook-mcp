# -*- coding: utf-8 -*-
from __future__ import annotations

from app.embedding import EmbeddingConfigurationError
from app.vector import vector_literal
from admin.backend.services.embedding_runner_service import EmbeddingBatch


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

    def embedding_column_type(self, conn) -> str:
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

    def validate_dimension(self, conn, expected_dimension: int) -> None:
        actual_type = self.embedding_column_type(conn)
        expected_type = f"vector({expected_dimension})"
        if actual_type != expected_type:
            raise EmbeddingConfigurationError(
                f"statistics.embedding is {actual_type}, but the configured model requires "
                f"{expected_type}; apply the pgvector migration before re-embedding"
            )

    def snapshot_max_id(self, conn) -> int:
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

    def count_candidates(
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

    def fetch_batch(
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
                       chapter, section, page_start
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

    def texts(self, rows: list[dict]) -> list[str]:
        return [self.build_text(row) for row in rows]

    def build_text(self, row: dict) -> str:
        parts = [
            row.get("title_ko"),
            row.get("title_en"),
            row.get("chapter"),
            row.get("section"),
        ]
        return " ".join(filter(None, parts)).strip() or "(제목 없음)"

    def save_batch(
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

    def status(self, conn, profile_key: str) -> dict:
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
