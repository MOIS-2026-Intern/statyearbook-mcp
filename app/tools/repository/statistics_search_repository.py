# -*- coding: utf-8 -*-
"""통계표 제목·본문 청크·주석 검색 SQL과 PostgreSQL 실행을 담당한다."""
from collections.abc import Callable
from typing import Any

import psycopg

from app.db import connect
from app.tools.repository.publication_repository import match_key_sql
from utils.publication_kind import (
    DEFAULT_PUBLICATION_KIND,
    normalize_publication_kind,
    normalize_publication_period_filter,
)


LATEST_EDITIONS_KEY_SQL = f"COALESCE({match_key_sql('s.title_ko')}, '#' || s.stat_id)"
# 주요통계집은 같은 해에 상반기·하반기가 나오므로 최신 판은 연도만으로 정해지지 않는다.
# 연도와 반기를 한 정수로 접어 하반기가 같은 해 상반기보다 뒤에 오게 한다.
EDITION_RANK_SQL = "(s.year * 10 + CASE p.period WHEN 'H2' THEN 2 WHEN 'H1' THEN 1 ELSE 0 END)"
LATEST_EDITIONS_CTE = f"""
    WITH latest_editions AS (
        SELECT stat_id
        FROM (
            SELECT s.stat_id, {EDITION_RANK_SQL} AS edition_rank,
                   MAX({EDITION_RANK_SQL}) OVER (
                       PARTITION BY p.publication_kind, {LATEST_EDITIONS_KEY_SQL}
                   ) AS latest_rank
            FROM statistics s
            JOIN publications p ON p.pub_id = s.pub_id
        ) ranked
        WHERE edition_rank = latest_rank
    )
"""
LATEST_EDITIONS_FILTER = "stat_id IN (SELECT stat_id FROM latest_editions)"


def _edition_filters(
    publication_kind: str,
    publication_year: int | None,
    latest_editions: bool,
    publication_period: str | None = None,
    stat_alias: str = "s",
    publication_alias: str = "p",
) -> list[str]:
    stat_prefix = f"{stat_alias}." if stat_alias else ""
    publication_prefix = f"{publication_alias}." if publication_alias else ""
    filters = [f"{publication_prefix}publication_kind = %s"]
    if publication_year is not None:
        filters.append(f"{stat_prefix}year = %s")
    if publication_period is not None:
        filters.append(f"{publication_prefix}period = %s")
    if latest_editions:
        filters.append(f"{stat_prefix}{LATEST_EDITIONS_FILTER}")
    return filters


def _edition_filter_sql(
    publication_kind: str,
    publication_year: int | None,
    latest_editions: bool,
    publication_period: str | None = None,
    stat_alias: str = "s",
    publication_alias: str = "p",
) -> str:
    return "".join(
        f" AND {condition}"
        for condition in _edition_filters(
            publication_kind,
            publication_year,
            latest_editions,
            publication_period,
            stat_alias,
            publication_alias,
        )
    )


def _cte_sql(latest_editions: bool) -> str:
    return LATEST_EDITIONS_CTE if latest_editions else ""


# 조직도·도표처럼 표 본문이 없는 통계표는 수치를 읽을 수 없으므로 후보에 표시해 둔다.
def _has_tables_sql(alias: str) -> str:
    return (
        f"EXISTS (SELECT 1 FROM stat_tables st WHERE st.stat_id = {alias}.stat_id)"
        " AS has_tables"
    )


def _where_sql(
    publication_kind: str,
    publication_year: int | None,
    latest_editions: bool,
    publication_period: str | None,
) -> str:
    where = [
        "s.embedding IS NOT NULL",
        "s.embedding_profile_key = %s",
        *_edition_filters(
            publication_kind,
            publication_year,
            latest_editions,
            publication_period,
        ),
    ]
    return " AND ".join(where)


# 발간판 조건의 자리표시자 순서와 정확히 맞춘 인자를 만든다.
def _edition_params(
    publication_kind: str,
    publication_year: int | None,
    publication_period: str | None,
) -> list:
    params: list = [publication_kind]
    if publication_year is not None:
        params.append(publication_year)
    if publication_period is not None:
        params.append(publication_period)
    return params


def _params(
    query_vec: str,
    profile_key: str,
    publication_kind: str,
    publication_year: int | None,
    publication_period: str | None,
    limit: int,
) -> list:
    params: list = [query_vec, profile_key]
    params.extend(_edition_params(publication_kind, publication_year, publication_period))
    params.extend([query_vec, limit])
    return params


def _search_sql(
    publication_kind: str,
    publication_year: int | None,
    latest_editions: bool = False,
    publication_period: str | None = None,
) -> str:
    return f"""
        {_cte_sql(latest_editions)}
        SELECT s.stat_id, p.publication_kind, p.period AS publication_period,
               s.year AS publication_year, s.ref_id,
               s.chapter_no, s.section_no, s.level3_no, s.level4_no,
               s.chapter, s.section, s.level3_title, s.level4_title,
               s.title_ko, s.title_en, s.unit, s.base_date, s.page_start,
               {_has_tables_sql("s")},
               (s.embedding <=> %s::vector) AS distance
        FROM statistics s
        JOIN publications p ON p.pub_id = s.pub_id
        WHERE {_where_sql(publication_kind, publication_year, latest_editions, publication_period)}
        ORDER BY s.embedding <=> %s::vector, s.year DESC, s.stat_id ASC
        LIMIT %s
    """


def _table_metadata_sql() -> str:
    return f"""
        s.stat_id, p.publication_kind, p.period AS publication_period,
        s.year AS publication_year, s.ref_id,
        s.chapter_no, s.section_no, s.level3_no, s.level4_no,
        s.chapter, s.section, s.level3_title, s.level4_title,
        s.title_ko, s.title_en, s.unit, s.base_date, s.page_start,
        t.seq AS table_seq, c.chunk_kind, c.search_labels, c.search_text,
        {_has_tables_sql("s")}
    """


def _table_lexical_sql(
    publication_kind: str,
    publication_year: int | None,
    latest_editions: bool,
    publication_period: str | None = None,
) -> str:
    edition_filter = _edition_filter_sql(
        publication_kind, publication_year, latest_editions, publication_period
    )
    return f"""
        {_cte_sql(latest_editions)}
        SELECT {_table_metadata_sql()},
               ts_rank_cd(c.search_doc, plainto_tsquery('simple', %s)) AS lexical_rank
        FROM table_search_chunks c
        JOIN statistics s ON s.stat_id = c.stat_id
        JOIN publications p ON p.pub_id = s.pub_id
        LEFT JOIN stat_tables t ON t.table_id = c.table_id
        WHERE c.search_doc @@ plainto_tsquery('simple', %s)
              {edition_filter}
        ORDER BY lexical_rank DESC, s.year DESC, s.stat_id, t.seq
        LIMIT %s
    """


def _table_vector_sql(
    publication_kind: str,
    publication_year: int | None,
    latest_editions: bool,
    publication_period: str | None = None,
) -> str:
    edition_filter = _edition_filter_sql(
        publication_kind, publication_year, latest_editions, publication_period
    )
    return f"""
        {_cte_sql(latest_editions)}
        SELECT {_table_metadata_sql()},
               (c.embedding <=> %s::vector) AS distance
        FROM table_search_chunks c
        JOIN statistics s ON s.stat_id = c.stat_id
        JOIN publications p ON p.pub_id = s.pub_id
        LEFT JOIN stat_tables t ON t.table_id = c.table_id
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
        publication_kind: str = DEFAULT_PUBLICATION_KIND,
        publication_period: str | None = None,
    ) -> tuple[list[dict], list[dict], list[dict]]:
        publication_kind = normalize_publication_kind(publication_kind)
        publication_period = normalize_publication_period_filter(publication_period)
        candidate_limit = max(20, limit * 5)
        edition_params = _edition_params(
            publication_kind,
            publication_year,
            publication_period,
        )
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                _search_sql(
                    publication_kind,
                    publication_year,
                    latest_editions,
                    publication_period,
                ),
                _params(
                    query_vec,
                    title_profile_key,
                    publication_kind,
                    publication_year,
                    publication_period,
                    candidate_limit,
                ),
            )
            title_rows = cur.fetchall()
            lexical_rows: list[dict] = []
            vector_rows: list[dict] = []
            try:
                if lexical_query:
                    lexical_params: list = [lexical_query, lexical_query]
                    lexical_params.extend(edition_params)
                    lexical_params.append(candidate_limit)
                    cur.execute(
                        _table_lexical_sql(
                            publication_kind,
                            publication_year,
                            latest_editions,
                            publication_period,
                        ),
                        lexical_params,
                    )
                    lexical_rows = cur.fetchall()

                vector_params: list = [query_vec, table_profile_key]
                vector_params.extend(edition_params)
                vector_params.extend([query_vec, candidate_limit])
                cur.execute(
                    _table_vector_sql(
                        publication_kind,
                        publication_year,
                        latest_editions,
                        publication_period,
                    ),
                    vector_params,
                )
                vector_rows = cur.fetchall()
            except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
                conn.rollback()
            return title_rows, lexical_rows, vector_rows
