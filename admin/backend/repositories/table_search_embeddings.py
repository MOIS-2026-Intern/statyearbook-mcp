# 이 파일은 표 검색 청크 생성, 임베딩 대상 조회와 벡터 저장을 담당한다.
from __future__ import annotations

import json

from psycopg.types.json import Jsonb

from admin.backend.models.embedding import EmbeddingBatch
from shared.embedding import EmbeddingConfigurationError
from shared.table_search import build_table_search_chunks
from shared.vector import vector_literal


def _first_value(row):
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


class TableSearchEmbeddingRepository:
    def __init__(self, publication_year: int | None = None):
        self.publication_year = publication_year
        self.name = (
            f"table_search:{publication_year}"
            if publication_year is not None
            else "table_search"
        )

    def _scope_sql(self) -> str:
        return "s.year = %s" if self.publication_year is not None else "TRUE"

    def _scope_params(self) -> list:
        return [self.publication_year] if self.publication_year is not None else []

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
                f"model requires {expected_type}; apply db/schema.sql before re-embedding"
            )

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

    def _candidate_sql(self, force: bool) -> str:
        if force:
            return "TRUE"
        return "(c.embedding IS NULL OR c.embedding_profile_key IS DISTINCT FROM %s)"

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

    def select_embedding_texts(self, rows: list[dict]) -> list[str]:
        return [str(row["search_text"]) for row in rows]

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

    def select_embedding_status(self, conn, profile_key: str) -> dict:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS total_count,
                       COUNT(c.embedding) AS embedded_count,
                       COUNT(*) FILTER (
                           WHERE c.embedding IS NOT NULL
                             AND c.embedding_profile_key = %s
                       ) AS current_count
                FROM table_search_chunks c
                JOIN stat_tables t ON t.table_id = c.table_id
                JOIN statistics s ON s.stat_id = t.stat_id
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

    def rebuild_chunks(self, conn) -> int:
        """기존 stat_tables.body에서 검색 청크를 idempotent하게 다시 만든다."""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT s.stat_id, s.year, s.ref_id, s.chapter, s.section,
                       s.level3_title, s.level4_title, s.title_ko, s.title_en,
                       t.table_id, t.seq, t.caption, t.body
                FROM stat_tables t
                JOIN statistics s ON s.stat_id = t.stat_id
                WHERE {self._scope_sql()}
                ORDER BY t.table_id
                """,
                self._scope_params(),
            )
            tables = cur.fetchall()
            if self.publication_year is None:
                cur.execute("DELETE FROM table_search_chunks")
            else:
                cur.execute(
                    """
                    DELETE FROM table_search_chunks c
                    USING stat_tables t, statistics s
                    WHERE c.table_id = t.table_id
                      AND t.stat_id = s.stat_id
                      AND s.year = %s
                    """,
                    (self.publication_year,),
                )

            inserted = 0
            for row in tables:
                body = row["body"]
                if isinstance(body, str):
                    body = json.loads(body)
                table = {"body": body, "caption": row.get("caption"), "seq": row["seq"]}
                for chunk in build_table_search_chunks(dict(row), table):
                    cur.execute(
                        """
                        INSERT INTO table_search_chunks (
                            table_id, chunk_no, chunk_kind, search_labels,
                            search_text, search_doc
                        ) VALUES (%s, %s, %s, %s, %s, to_tsvector('simple', %s))
                        """,
                        (
                            row["table_id"],
                            chunk["chunk_no"],
                            chunk["chunk_kind"],
                            Jsonb(chunk["search_labels"]),
                            chunk["search_text"],
                            chunk["search_text"],
                        ),
                    )
                    inserted += 1
        conn.commit()
        return inserted
