# -*- coding: utf-8 -*-
import re
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.db import connect
from app.query_embedding import embed_query, embedding_profile
from app.tool_descriptions import SEARCH_STATISTICS, SEARCH_STATISTICS_FIELDS

SEARCH_TEXT_COLUMNS = ("title_ko", "title_en", "chapter", "section")


# 질의를 검색 토큰으로 나눈다.
def _tokenize(query: str) -> list[str]:
    raw = re.split(r"[\s,()·/]+", query.strip())
    tokens: list[str] = []
    for t in raw:
        t = t.strip()
        if not t:
            continue
        if len(t) >= 2:
            tokens.append(t)
    return tokens


# 검색 결과 행에서 토큰 매칭용 문자열을 만든다.
def _row_text(row: dict) -> str:
    values = [row.get(column) or "" for column in SEARCH_TEXT_COLUMNS]
    return " ".join(map(str, values)).lower()


# 제목/분류 문자열에 실제로 포함된 토큰을 찾는다.
def _matched_tokens(tokens: list[str], row: dict) -> list[str]:
    text = _row_text(row)
    return [token for token in tokens if token.lower() in text]


# 코사인 거리를 유사도 점수로 바꾼다.
def _similarity_score(distance: float) -> float:
    return round(1 - float(distance), 4)


# 검색 SQL의 WHERE 절을 만든다.
def _where_sql(publication_year: int | None) -> str:
    where = ["embedding IS NOT NULL", "embedding_profile_key = %s"]
    if publication_year is not None:
        where.append("year = %s")
    return " AND ".join(where)


# 검색 SQL 파라미터를 만든다.
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


# 통계표 의미 검색 SQL을 만든다.
def _search_sql(publication_year: int | None) -> str:
    where_sql = _where_sql(publication_year)
    return f"""
        SELECT stat_id, year AS publication_year, ref_id, chapter, section,
               title_ko, title_en, unit, base_date, page_start,
               (embedding <=> %s::vector) AS distance
        FROM statistics
        WHERE {where_sql}
        ORDER BY embedding <=> %s::vector, year DESC, stat_id ASC
        LIMIT %s
    """


# DB에서 관련 통계표를 조회한다.
def _fetch_rows(
    query_vec: str,
    profile_key: str,
    publication_year: int | None,
    limit: int,
) -> list:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            _search_sql(publication_year),
            _params(query_vec, profile_key, publication_year, limit),
        )
        return cur.fetchall()


# DB 행을 MCP 응답 항목으로 바꾼다.
def _result_row(row: dict, tokens: list[str]) -> dict:
    return {
        "stat_id": row["stat_id"],
        "publication_year": row["publication_year"],
        "ref_id": row["ref_id"],
        "chapter": row["chapter"],
        "section": row["section"],
        "title_ko": row["title_ko"],
        "title_en": row["title_en"],
        "unit": row["unit"],
        "base_date": row["base_date"],
        "page_start": row["page_start"],
        "matched_tokens": _matched_tokens(tokens, row),
        "score": _similarity_score(row["distance"]),
    }


# 검색 결과가 없을 때의 응답을 만든다.
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


# 검색 조건을 실행하고, 잘못 지정된 발간연도 때문에 후보가 사라지지 않도록 완화한다.
def search_statistics_data(
    query: str,
    publication_year: int | None = None,
    limit: int = 5,
) -> dict:
    if not query or not query.strip():
        return _empty_response(query, publication_year)

    tokens = _tokenize(query)
    query_vec = embed_query(query)
    profile_key = embedding_profile().profile_key
    rows = _fetch_rows(query_vec, profile_key, publication_year, limit)
    filter_relaxed = False

    if not rows and publication_year is not None:
        rows = _fetch_rows(query_vec, profile_key, None, limit)
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
        "count": len(rows),
        "results": [_result_row(row, tokens) for row in rows],
    }


# search_statistics MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # 자연어 질의로 관련 통계표 목록을 찾는다.
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
