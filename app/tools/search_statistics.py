# -*- coding: utf-8 -*-
import re

from mcp.server.fastmcp import FastMCP

from app.db import connect
from app.query_embedding import embed_query


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


# search_statistics MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # 자연어 질의로 관련 통계표 목록을 찾는다.
    @mcp.tool()
    def search_statistics(query: str, year: int | None = None, limit: int = 5) -> dict:
        """자연어 질의와 관련 있는 통계표를 검색한다."""
        if not query or not query.strip():
            return {"query": query, "tokens": [], "count": 0, "results": []}

        tokens = _tokenize(query)

        # 저장된 제목 벡터와 거리순으로 비교한다.
        query_vec = embed_query(query)

        where = ["embedding IS NOT NULL"]
        params: list = [query_vec]

        if year is not None:
            where.append("year = %s")
            params.append(year)

        params.append(query_vec)
        params.append(limit)

        sql = f"""
            SELECT stat_id, year, ref_id, chapter, section,
                   title_ko, title_en, unit, base_date, page_start,
                   (embedding <=> %s::vector) AS distance
            FROM statistics
            WHERE {" AND ".join(where)}
            ORDER BY embedding <=> %s::vector, year DESC, stat_id ASC
            LIMIT %s
        """

        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        lowered_tokens = [t.lower() for t in tokens]
        results = []
        for r in rows:
            hay = " ".join(
                str(r.get(k) or "")
                for k in ("title_ko", "title_en", "chapter", "section")
            ).lower()
            matched = [t for t, lt in zip(tokens, lowered_tokens) if lt in hay]
            similarity = round(1.0 - float(r["distance"]), 4)
            results.append(
                {
                    "stat_id": r["stat_id"],
                    "year": r["year"],
                    "ref_id": r["ref_id"],
                    "chapter": r["chapter"],
                    "section": r["section"],
                    "title_ko": r["title_ko"],
                    "title_en": r["title_en"],
                    "unit": r["unit"],
                    "base_date": r["base_date"],
                    "page_start": r["page_start"],
                    "matched_tokens": matched,
                    "score": similarity,
                }
            )

        return {
            "query": query,
            "tokens": tokens,
            "count": len(results),
            "results": results,
        }
