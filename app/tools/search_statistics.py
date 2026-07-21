# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from typing import Annotated

import psycopg
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.db import connect
from app.query_embedding import (
    embed_query,
    embedding_profile,
    table_search_embedding_profile,
)
from app.tool_descriptions import SEARCH_STATISTICS, SEARCH_STATISTICS_FIELDS


SEARCH_TEXT_COLUMNS = (
    "ref_id",
    "chapter",
    "section",
    "level3_title",
    "level4_title",
    "title_ko",
    "title_en",
)
RRF_K = 60
TITLE_WEIGHT = 1.0
TABLE_VECTOR_WEIGHT = 1.8
TABLE_LEXICAL_WEIGHT = 3.0
EXACT_LABEL_BONUS = 0.05
LABEL_TOKEN_BONUS = 0.04
_QUERY_STOP_TOKENS = {
    "알려줘",
    "알려주세요",
    "보여줘",
    "보여주세요",
    "찾아줘",
    "찾아주세요",
    "검색해줘",
    "검색해주세요",
    "통계",
    "현황",
}


def _tokenize(query: str) -> list[str]:
    raw = re.split(r"[\s,()·/]+", query.strip())
    return [token.strip() for token in raw if len(token.strip()) >= 2]


def _lexical_query(query: str) -> str:
    tokens = [
        token
        for token in _tokenize(query)
        if token not in _QUERY_STOP_TOKENS
        and not re.fullmatch(r"\d{4}년?", token)
    ]
    return " ".join(tokens)


def _row_text(row: dict) -> str:
    values = [row.get(column) or "" for column in SEARCH_TEXT_COLUMNS]
    values.append(row.get("matched_text") or "")
    return " ".join(map(str, values)).lower()


def _matched_tokens(tokens: list[str], row: dict) -> list[str]:
    text = _row_text(row)
    return [token for token in tokens if token.lower() in text]


def _where_sql(publication_year: int | None, alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    where = [
        f"{prefix}embedding IS NOT NULL",
        f"{prefix}embedding_profile_key = %s",
    ]
    if publication_year is not None:
        where.append(f"{prefix}year = %s")
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


def _search_sql(publication_year: int | None) -> str:
    where_sql = _where_sql(publication_year)
    return f"""
        SELECT stat_id, year AS publication_year, ref_id,
               chapter_no, section_no, level3_no, level4_no,
               chapter, section, level3_title, level4_title,
               title_ko, title_en, unit, base_date, page_start,
               (embedding <=> %s::vector) AS distance
        FROM statistics
        WHERE {where_sql}
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


def _table_lexical_sql(publication_year: int | None) -> str:
    year_filter = " AND s.year = %s" if publication_year is not None else ""
    return f"""
        SELECT {_table_metadata_sql()},
               ts_rank_cd(c.search_doc, plainto_tsquery('simple', %s)) AS lexical_rank
        FROM table_search_chunks c
        JOIN stat_tables t ON t.table_id = c.table_id
        JOIN statistics s ON s.stat_id = t.stat_id
        WHERE c.search_doc @@ plainto_tsquery('simple', %s)
              {year_filter}
        ORDER BY lexical_rank DESC, s.year DESC, s.stat_id, t.seq
        LIMIT %s
    """


def _table_vector_sql(publication_year: int | None) -> str:
    year_filter = " AND s.year = %s" if publication_year is not None else ""
    return f"""
        SELECT {_table_metadata_sql()},
               (c.embedding <=> %s::vector) AS distance
        FROM table_search_chunks c
        JOIN stat_tables t ON t.table_id = c.table_id
        JOIN statistics s ON s.stat_id = t.stat_id
        WHERE c.embedding IS NOT NULL
          AND c.embedding_profile_key = %s
          {year_filter}
        ORDER BY c.embedding <=> %s::vector, s.year DESC, s.stat_id, t.seq
        LIMIT %s
    """


def _fetch_rows(
    query: str,
    query_vec: str,
    title_profile_key: str,
    table_profile_key: str,
    publication_year: int | None,
    limit: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    candidate_limit = max(20, limit * 5)
    lexical_query = _lexical_query(query)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            _search_sql(publication_year),
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
                cur.execute(_table_lexical_sql(publication_year), lexical_params)
                lexical_rows = cur.fetchall()

            vector_params: list = [query_vec, table_profile_key]
            if publication_year is not None:
                vector_params.append(publication_year)
            vector_params.extend([query_vec, candidate_limit])
            cur.execute(_table_vector_sql(publication_year), vector_params)
            vector_rows = cur.fetchall()
        except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
            # 점진 배포 중 새 schema가 아직 적용되지 않은 DB는 제목 검색만 제공한다.
            conn.rollback()
        return title_rows, lexical_rows, vector_rows


def _labels(row: dict) -> list[str]:
    labels = row.get("search_labels") or []
    if isinstance(labels, str):
        labels = json.loads(labels)
    return [str(label) for label in labels]


def _compact_match_text(value: str) -> str:
    return re.sub(r"[\s·･_/-]+", "", value.casefold())


def _best_matched_text(
    query: str,
    row: dict,
) -> tuple[str | None, bool, float]:
    labels = _labels(row)
    if not labels:
        return None, False, 0.0
    lexical = _lexical_query(query).casefold()
    if lexical:
        for label in labels:
            if lexical in label.casefold():
                return label, True, 1.0
    search_tokens = _tokenize(_lexical_query(query))
    compact_tokens = [_compact_match_text(token) for token in search_tokens]

    def matched_count(label: str) -> int:
        compact_label = _compact_match_text(label)
        return sum(token in compact_label for token in compact_tokens)

    ranked = sorted(
        labels,
        key=lambda label: (matched_count(label), len(label)),
        reverse=True,
    )
    matched = ranked[0]
    count = matched_count(matched)
    coverage = count / len(compact_tokens) if compact_tokens else 0.0
    exact = bool(compact_tokens) and count == len(compact_tokens)
    return matched, exact, coverage


def _base_candidate(row: dict) -> dict:
    return {
        "stat_id": row["stat_id"],
        "publication_year": row["publication_year"],
        "ref_id": row["ref_id"],
        "chapter_no": row["chapter_no"],
        "section_no": row["section_no"],
        "level3_no": row["level3_no"],
        "level4_no": row["level4_no"],
        "chapter": row["chapter"],
        "section": row["section"],
        "level3_title": row["level3_title"],
        "level4_title": row["level4_title"],
        "title_ko": row["title_ko"],
        "title_en": row["title_en"],
        "unit": row["unit"],
        "base_date": row["base_date"],
        "page_start": row["page_start"],
        "table_seq": None,
        "matched_source": "title",
        "matched_text": row.get("title_ko"),
        "_priority": 1,
        "_score": 0.0,
        "_source_scores": {},
    }


def _add_candidate(
    candidates: dict[int, dict],
    row: dict,
    contribution: float,
    matched_source: str,
    matched_text: str | None,
    priority: int,
    score_source: str,
) -> None:
    stat_id = int(row["stat_id"])
    candidate = candidates.setdefault(stat_id, _base_candidate(row))
    previous = float(candidate["_source_scores"].get(score_source, 0.0))
    if contribution > previous:
        candidate["_score"] += contribution - previous
        candidate["_source_scores"][score_source] = contribution
    if priority > candidate["_priority"]:
        candidate["_priority"] = priority
        candidate["matched_source"] = matched_source
        candidate["matched_text"] = matched_text
        candidate["table_seq"] = row.get("table_seq")


def _merge_candidates(
    query: str,
    title_rows: list[dict],
    lexical_rows: list[dict],
    vector_rows: list[dict],
    limit: int,
) -> list[dict]:
    tokens = _tokenize(query)
    candidates: dict[int, dict] = {}

    for rank, row in enumerate(title_rows, start=1):
        _add_candidate(
            candidates,
            row,
            TITLE_WEIGHT / (RRF_K + rank),
            "title",
            row.get("title_ko"),
            1,
            "title",
        )

    for rank, row in enumerate(lexical_rows, start=1):
        matched_text, exact, coverage = _best_matched_text(query, row)
        source = "column" if row["chunk_kind"] == "headers" else "row_label"
        contribution = TABLE_LEXICAL_WEIGHT / (RRF_K + rank)
        contribution += LABEL_TOKEN_BONUS * coverage
        if exact:
            contribution += EXACT_LABEL_BONUS
        _add_candidate(
            candidates,
            row,
            contribution,
            source,
            matched_text,
            5 if exact and source == "column" else 4,
            "lexical",
        )

    for rank, row in enumerate(vector_rows, start=1):
        matched_text, _exact, coverage = _best_matched_text(query, row)
        source = "column" if row["chunk_kind"] == "headers" else "row_label"
        _add_candidate(
            candidates,
            row,
            TABLE_VECTOR_WEIGHT / (RRF_K + rank) + LABEL_TOKEN_BONUS * coverage,
            source,
            matched_text,
            3 if source == "column" else 2,
            "table_vector",
        )

    ranked_results = sorted(
        candidates.values(),
        key=lambda item: (
            -item["_score"],
            -int(item["publication_year"]),
            int(item["stat_id"]),
        ),
    )
    results = []
    seen_tables: set[tuple[str, str]] = set()
    for candidate in ranked_results:
        semantic_key = (str(candidate.get("ref_id")), str(candidate.get("title_ko")))
        if semantic_key in seen_tables:
            continue
        seen_tables.add(semantic_key)
        results.append(candidate)
        if len(results) == limit:
            break
    for result in results:
        result["score"] = round(result.pop("_score"), 6)
        result.pop("_priority", None)
        result.pop("_source_scores", None)
        result["matched_tokens"] = _matched_tokens(tokens, result)
    return results


def _empty_response(query: str, publication_year: int | None = None) -> dict:
    return {
        "query": query,
        "tokens": [],
        "requested_publication_year": publication_year,
        "applied_publication_year": publication_year,
        "publication_year_filter_relaxed": False,
        "message": None,
        "count": 0,
        "results": [],
    }


def search_statistics_data(
    query: str,
    publication_year: int | None = None,
    limit: int = 5,
) -> dict:
    if not query or not query.strip():
        return _empty_response(query, publication_year)

    tokens = _tokenize(query)
    semantic_query = _lexical_query(query) or query.strip()
    query_vec = embed_query(semantic_query)
    title_profile_key = embedding_profile().profile_key
    table_profile_key = table_search_embedding_profile().profile_key
    rows = _fetch_rows(
        query,
        query_vec,
        title_profile_key,
        table_profile_key,
        publication_year,
        limit,
    )
    results = _merge_candidates(query, *rows, limit)
    filter_relaxed = False

    if not results and publication_year is not None:
        rows = _fetch_rows(
            query,
            query_vec,
            title_profile_key,
            table_profile_key,
            None,
            limit,
        )
        results = _merge_candidates(query, *rows, limit)
        filter_relaxed = True

    return {
        "query": query,
        "tokens": tokens,
        "requested_publication_year": publication_year,
        "applied_publication_year": None if filter_relaxed else publication_year,
        "publication_year_filter_relaxed": filter_relaxed,
        "message": (
            "요청한 발간연도에는 후보가 없어 발간연도 필터를 제외하고 재검색했습니다."
            if filter_relaxed
            else None
        ),
        "count": len(results),
        "results": results,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(description=SEARCH_STATISTICS)
    def search_statistics(
        query: Annotated[str, Field(description=SEARCH_STATISTICS_FIELDS["query"])],
        publication_year: Annotated[
            int | None,
            Field(description=SEARCH_STATISTICS_FIELDS["publication_year"]),
        ] = None,
        limit: Annotated[
            int,
            Field(description=SEARCH_STATISTICS_FIELDS["limit"], ge=1, le=20),
        ] = 5,
    ) -> dict:
        return search_statistics_data(query, publication_year, limit)
