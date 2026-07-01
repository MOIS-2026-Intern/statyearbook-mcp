#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
statyearbook MCP server
행정안전통계연보(statyearbook_mcp DB)를 조회하는 MCP 서버.

첫 번째 도구: search_statistics
  - 자연어 질의와 관련 있는 통계표를 검색해 제목/식별자 목록을 돌려준다.
  - SQL은 서버에 고정되어 있고, LLM은 검색어(query)만 파라미터로 넘긴다.
  - 질의를 공백으로 토큰화한 뒤 각 토큰을 title_ko/title_en 등에 ILIKE(부분일치)로
    OR 매칭하고, "몇 개의 토큰이 걸렸는가"를 점수로 매겨 정렬한다.
    → 문장에 검색어가 많아도 실제 제목에 일부만 들어있으면 상위에 뜬다.

실행:
    pip install -r requirements.txt
    python server.py            # stdio 전송으로 대기 (MCP 클라이언트가 프로세스를 띄움)

DB 접속:
    접속 정보는 환경변수 STATYEARBOOK_DSN 으로 주입한다.
    같은 폴더의 .env 파일(커밋 안 함)에 두거나 셸 환경변수로 지정한다.
    예)  cp .env.example .env  후 .env 안의 값을 채운다.
"""
import os
import re

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 같은 폴더의 .env 파일에서 환경변수를 읽어들인다(있으면).
# 실제 접속 정보(비밀번호 등)는 코드가 아니라 .env 에 두고, .env 는 커밋하지 않는다.
load_dotenv()

DSN = os.environ.get("STATYEARBOOK_DSN")
if not DSN:
    raise RuntimeError(
        "STATYEARBOOK_DSN 이 설정되지 않았습니다. "
        ".env.example 를 .env 로 복사한 뒤 접속 정보를 채워 주세요."
    )

mcp = FastMCP("statyearbook")


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
    """
    tokens = _tokenize(query)
    if not tokens:
        return {"query": query, "tokens": [], "count": 0, "results": []}

    # 검색 대상 텍스트: 제목(국/영) + 장/절. NULL은 빈 문자열로.
    doc = (
        "coalesce(title_ko,'') || ' ' || coalesce(title_en,'') || ' ' || "
        "coalesce(chapter,'') || ' ' || coalesce(section,'')"
    )

    # 토큰마다 매칭 여부(0/1)를 합산해 score 로 사용.
    score_terms = " + ".join(
        [f"(CASE WHEN {doc} ILIKE %s THEN 1 ELSE 0 END)" for _ in tokens]
    )
    params: list = [f"%{t}%" for t in tokens]  # score 계산용

    where = [f"({doc}) ILIKE ANY(%s)"]  # 최소 한 토큰은 매칭
    params.append([f"%{t}%" for t in tokens])

    if year is not None:
        where.append("year = %s")
        params.append(year)

    params.append(limit)  # LIMIT

    sql = f"""
        SELECT stat_id, year, ref_id, chapter, section,
               title_ko, title_en, unit, base_date, page_start,
               ({score_terms}) AS score
        FROM statistics
        WHERE {" AND ".join(where)}
        ORDER BY score DESC, year DESC, stat_id ASC
        LIMIT %s
    """

    with psycopg.connect(DSN, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    lowered_tokens = [t.lower() for t in tokens]
    results = []
    for r in rows:
        hay = " ".join(
            str(r.get(k) or "") for k in ("title_ko", "title_en", "chapter", "section")
        ).lower()
        matched = [t for t, lt in zip(tokens, lowered_tokens) if lt in hay]
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
                "score": r["score"],
            }
        )

    return {
        "query": query,
        "tokens": tokens,
        "count": len(results),
        "results": results,
    }


@mcp.tool()
def search_tables(stat_id: int) -> dict:
    """통계표의 실제 표 값(마크다운)을 가져온다.

    search_statistics 로 관련 통계표를 찾아 stat_id 를 얻은 뒤, 그 stat_id 를
    넘기면 해당 통계표의 표 본문을 마크다운으로 돌려준다. LLM은 이 마크다운을
    그대로 사용자에게 표로 보여주면 된다. 단위/기준일은 caption 에, 세부 설명은
    footnotes(주석)에, 자료 출처는 source 에 담겨 있으니 함께 안내한다.

    한 통계표에 표가 여러 개(seq 1..N)일 수 있으므로 tables 는 리스트로 반환된다.

    Args:
        stat_id: search_statistics 결과의 stat_id.

    Returns:
        dict: {"found", "stat_id", "year", "title_ko", "title_en", "unit",
               "base_date", "tables": [{seq, caption, n_rows, n_cols, table_md}],
               "footnotes": [...], "source": [...]}
              해당 stat_id 가 없으면 {"found": False, ...}.
    """
    with psycopg.connect(DSN, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT stat_id, year, title_ko, title_en, unit, base_date, ref_id
               FROM statistics WHERE stat_id = %s""",
            (stat_id,),
        )
        stat = cur.fetchone()
        if stat is None:
            return {"found": False, "stat_id": stat_id, "tables": []}

        cur.execute(
            """SELECT seq, caption, n_rows, n_cols, table_md
               FROM stat_tables WHERE stat_id = %s ORDER BY seq""",
            (stat_id,),
        )
        tables = cur.fetchall()

        cur.execute(
            """SELECT seq, note_no, content
               FROM footnotes WHERE stat_id = %s ORDER BY seq""",
            (stat_id,),
        )
        footnotes = cur.fetchall()

        cur.execute(
            """SELECT dept, officer, phone, source_system, source_url
               FROM contacts WHERE stat_id = %s""",
            (stat_id,),
        )
        source = cur.fetchall()

    return {
        "found": True,
        "stat_id": stat["stat_id"],
        "ref_id": stat["ref_id"],
        "year": stat["year"],
        "title_ko": stat["title_ko"],
        "title_en": stat["title_en"],
        "unit": stat["unit"],
        "base_date": stat["base_date"],
        "tables": [
            {
                "seq": t["seq"],
                "caption": t["caption"],
                "n_rows": t["n_rows"],
                "n_cols": t["n_cols"],
                "table_md": t["table_md"],
            }
            for t in tables
        ],
        "footnotes": [
            {"seq": f["seq"], "note_no": f["note_no"], "content": f["content"]}
            for f in footnotes
        ],
        "source": [
            {
                "dept": s["dept"],
                "officer": s["officer"],
                "phone": s["phone"],
                "source_system": s["source_system"],
                "source_url": s["source_url"],
            }
            for s in source
        ],
    }


if __name__ == "__main__":
    mcp.run()  # 기본 전송 = stdio
