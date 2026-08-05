# -*- coding: utf-8 -*-
"""통계표 제목·본문 청크 검색 SQL과 PostgreSQL 실행을 담당한다."""
from collections.abc import Callable
from typing import Any

import psycopg

from app.db import connect
from app.tools.repository.publication_repository import match_key_sql


LATEST_EDITIONS_KEY_SQL = f"COALESCE({match_key_sql('title_ko')}, '#' || stat_id)"
LATEST_EDITIONS_CTE = f"""
    WITH latest_editions AS (
        SELECT stat_id
        FROM (
            SELECT stat_id, year,
                   MAX(year) OVER (PARTITION BY {LATEST_EDITIONS_KEY_SQL}) AS latest_year
            FROM statistics
        ) ranked
        WHERE year = latest_year
    )
"""
LATEST_EDITIONS_FILTER = "stat_id IN (SELECT stat_id FROM latest_editions)"


def _edition_filters(
    publication_year: int | None,
    latest_editions: bool,
    alias: str = "",
) -> list[str]:
    prefix = f"{alias}." if alias else ""
    filters = []
    if publication_year is not None:
        filters.append(f"{prefix}year = %s")
    if latest_editions:
        filters.append(f"{prefix}{LATEST_EDITIONS_FILTER}")
    return filters


def _edition_filter_sql(
    publication_year: int | None,
    latest_editions: bool,
    alias: str = "",
) -> str:
    return "".join(
        f" AND {condition}"
        for condition in _edition_filters(publication_year, latest_editions, alias)
    )


def _cte_sql(latest_editions: bool) -> str:
    return LATEST_EDITIONS_CTE if latest_editions else ""


def _where_sql(publication_year: int | None, latest_editions: bool) -> str:
    where = [
        "embedding IS NOT NULL",
        "embedding_profile_key = %s",
        *_edition_filters(publication_year, latest_editions),
    ]
    return " AND ".join(where)


def _params(
    query_vec: str,
    profile_key: str,
    publication_year: int | None,
    limit: int,
) -> list:
    params: list = [query_vec, profile_key]
    if publication_year is not None:
        params.append(publication_year)
    params.extend([query_vec, limit])
    return params


def _search_sql(publication_year: int | None, latest_editions: bool = False) -> str:
    return f"""
        {_cte_sql(latest_editions)}
        SELECT stat_id, year AS publication_year, ref_id,
               chapter_no, section_no, level3_no, level4_no,
               chapter, section, level3_title, level4_title,
               title_ko, title_en, unit, base_date, page_start,
               (embedding <=> %s::vector) AS distance
        FROM statistics
        WHERE {_where_sql(publication_year, latest_editions)}
        ORDER BY embedding <=> %s::vector, year DESC, stat_id ASC
        LIMIT %s
    """


def _table_metadata_sql() -> str:
    return """
        s.stat_id, s.year AS publication_year, s.ref_id,
        s.chapter_no, s.section_no, s.level3_no, s.level4_no,
        s.chapter, s.section, s.level3_title, s.level4_title,
        s.title_ko, s.title_en, s.unit, s.base_date, s.page_start,
        t.seq AS table_seq, c.chunk_kind, c.search_labels, c.search_text
    """


def _table_lexical_sql(publication_year: int | None, latest_editions: bool) -> str:
    edition_filter = _edition_filter_sql(publication_year, latest_editions, "s")
    return f"""
        {_cte_sql(latest_editions)}
        SELECT {_table_metadata_sql()},
               ts_rank_cd(c.search_doc, plainto_tsquery('simple', %s)) AS lexical_rank
        FROM table_search_chunks c
        JOIN stat_tables t ON t.table_id = c.table_id
        JOIN statistics s ON s.stat_id = t.stat_id
        WHERE c.search_doc @@ plainto_tsquery('simple', %s)
              {edition_filter}
        ORDER BY lexical_rank DESC, s.year DESC, s.stat_id, t.seq
        LIMIT %s
    """


def _table_vector_sql(publication_year: int | None, latest_editions: bool) -> str:
    edition_filter = _edition_filter_sql(publication_year, latest_editions, "s")
    return f"""
        {_cte_sql(latest_editions)}
        SELECT {_table_metadata_sql()},
               (c.embedding <=> %s::vector) AS distance
        FROM table_search_chunks c
        JOIN stat_tables t ON t.table_id = c.table_id
        JOIN statistics s ON s.stat_id = t.stat_id
        WHERE c.embedding IS NOT NULL
          AND c.embedding_profile_key = %s
          {edition_filter}
        ORDER BY c.embedding <=> %s::vector, s.year DESC, s.stat_id, t.seq
        LIMIT %s
    """


class StatisticsSearchRepository:
    def __init__(self, connection_factory: Callable[[], Any] = connect):
        self._connection_factory = connection_factory

    # 제목 벡터·표 전문·표 벡터 후보를 한 트랜잭션에서 조회한다.
    def fetch_rows(
        self,
        lexical_query: str,
        query_vec: str,
        title_profile_key: str,
        table_profile_key: str,
        publication_year: int | None,
        latest_editions: bool,
        limit: int,
    ) -> tuple[list[dict], list[dict], list[dict]]:
        candidate_limit = max(20, limit * 5)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                _search_sql(publication_year, latest_editions),
                _params(query_vec, title_profile_key, publication_year, candidate_limit),
            )
            title_rows = cur.fetchall()
            lexical_rows: list[dict] = []
            vector_rows: list[dict] = []
            try:
                if lexical_query:
                    lexical_params: list = [lexical_query, lexical_query]
                    if publication_year is not None:
                        lexical_params.append(publication_year)
                    lexical_params.append(candidate_limit)
                    cur.execute(
                        _table_lexical_sql(publication_year, latest_editions),
                        lexical_params,
                    )
                    lexical_rows = cur.fetchall()

                vector_params: list = [query_vec, table_profile_key]
                if publication_year is not None:
                    vector_params.append(publication_year)
                vector_params.extend([query_vec, candidate_limit])
                cur.execute(
                    _table_vector_sql(publication_year, latest_editions),
                    vector_params,
                )
                vector_rows = cur.fetchall()
            except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
                conn.rollback()
            return title_rows, lexical_rows, vector_rows
