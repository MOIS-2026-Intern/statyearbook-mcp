# -*- coding: utf-8 -*-
import re

from mcp.server.fastmcp import FastMCP

from app.db import connect
from app.query_embedding import embed_query

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
def _where_sql(year: int | None) -> str:
    where = ["embedding IS NOT NULL"]
    if year is not None:
        where.append("year = %s")
    return " AND ".join(where)


# 검색 SQL 파라미터를 만든다.
def _params(query_vec: str, year: int | None, limit: int) -> list:
    params: list = [query_vec]
    if year is not None:
        params.append(year)
    params.extend([query_vec, limit])
    return params


# 통계표 의미 검색 SQL을 만든다.
def _search_sql(year: int | None) -> str:
    where_sql = _where_sql(year)
    return f"""
        SELECT stat_id, year, ref_id, chapter, section,
               title_ko, title_en, unit, base_date, page_start,
               (embedding <=> %s::vector) AS distance
        FROM statistics
        WHERE {where_sql}
        ORDER BY embedding <=> %s::vector, year DESC, stat_id ASC
        LIMIT %s
    """


# DB에서 관련 통계표를 조회한다.
def _fetch_rows(query_vec: str, year: int | None, limit: int) -> list:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(_search_sql(year), _params(query_vec, year, limit))
        return cur.fetchall()


# DB 행을 MCP 응답 항목으로 바꾼다.
def _result_row(row: dict, tokens: list[str]) -> dict:
    return {
        "stat_id": row["stat_id"],
        "year": row["year"],
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
def _empty_response(query: str) -> dict:
    return {"query": query, "tokens": [], "count": 0, "results": []}


# search_statistics MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # 자연어 질의로 관련 통계표 목록을 찾는다.
    @mcp.tool()
    def search_statistics(query: str, year: int | None = None, limit: int = 5) -> dict:
        """자연어 질의와 관련 있는 통계표를 검색한다."""
        if not query or not query.strip():
            return _empty_response(query)

        tokens = _tokenize(query)

        # 저장된 제목 벡터와 거리순으로 비교한다.
        query_vec = embed_query(query)
        rows = _fetch_rows(query_vec, year, limit)
        results = [_result_row(row, tokens) for row in rows]

        return {
            "query": query,
            "tokens": tokens,
            "count": len(results),
            "results": results,
        }
