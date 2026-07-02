# -*- coding: utf-8 -*-
"""search_statistics 도구.

자연어 질의와 관련 있는 통계표를 검색해 제목/식별자 목록을 돌려준다.
  - SQL은 서버에 고정되어 있고, LLM은 검색어(query)만 파라미터로 넘긴다.
  - 의미 검색(semantic search): 질의를 임베딩 적재 때와 동일한 OpenAI 모델로
    임베딩한 뒤, statistics.embedding 과 코사인 거리(<=>)로 비교해 가까운 순으로 정렬한다.
    → "폭염"으로 검색해도 "온열질환"처럼 표현이 달라도 의미가 가까우면 상위에 뜬다.
  - 참고용으로 질의 토큰이 제목에 실제로 들어있는지(matched_tokens)도 함께 돌려준다.
"""
import re

from mcp.server.fastmcp import FastMCP

from app.db import connect
from app.query_embedding import embed_query


def _tokenize(query: str) -> list[str]:
    """질의를 검색 토큰으로 분해한다.

    - 공백/괄호/쉼표 등으로 분리
    - 2글자 미만 토큰은 노이즈로 보고 제거(단, 숫자 4자리 '연도'는 유지)
    """
    raw = re.split(r"[\s,()·/]+", query.strip())
    tokens: list[str] = []
    for t in raw:
        t = t.strip()
        if not t:
            continue
        if len(t) >= 2:
            tokens.append(t)
    return tokens


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def search_statistics(query: str, year: int | None = None, limit: int = 5) -> dict:
        """자연어 질의와 관련 있는 통계표를 검색한다.

        사용자의 질문에서 핵심 키워드가 담긴 자연어 문자열을 그대로 넘기면,
        가장 관련 있는 통계표 제목 목록을 관련도 순으로 돌려준다.

        예) query="2024년 서울 논밭 온열질환자 비율"
            → "지역별 폭염 인명피해(온열질환자)" 등이 상위로 반환됨

        Args:
            query: 검색할 자연어 질의(핵심 키워드가 포함된 문장이면 됨).
            year:  특정 연도로 한정하고 싶을 때(예: 2025). 생략하면 전체 연도.
            limit: 최대 반환 개수(기본 5).

        Returns:
            dict: {"query", "tokens", "count", "results": [...]}
                  results 각 항목은 stat_id/year/title_ko/chapter/section/unit/
                  base_date/matched_tokens/score 를 포함한다.
                  score 는 코사인 유사도(1=의미상 완전 일치, 클수록 관련도 높음)다.
        """
        if not query or not query.strip():
            return {"query": query, "tokens": [], "count": 0, "results": []}

        tokens = _tokenize(query)

        # 질의를 임베딩해 저장된 제목 벡터와 코사인 거리로 비교한다.
        # <=> 는 pgvector 의 코사인 거리(0=완전 일치 ~ 2=정반대). 작을수록 가깝다.
        query_vec = embed_query(query)

        where = ["embedding IS NOT NULL"]  # 아직 임베딩 안 된 행은 제외
        params: list = [query_vec]  # SELECT 절의 distance 계산용

        if year is not None:
            where.append("year = %s")
            params.append(year)

        params.append(query_vec)  # ORDER BY 절의 거리
        params.append(limit)      # LIMIT

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
            # score: 코사인 유사도(1=완전 일치). LLM이 관련도를 가늠하기 쉽게 거리에서 변환.
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
