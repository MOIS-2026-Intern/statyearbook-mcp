#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
statyearbook MCP server
행정안전통계연보(statyearbook_mcp DB)를 조회하는 MCP 서버.

첫 번째 도구: search_statistics
  - 자연어 질의와 관련 있는 통계표를 검색해 제목/식별자 목록을 돌려준다.
  - SQL은 서버에 고정되어 있고, LLM은 검색어(query)만 파라미터로 넘긴다.
  - 의미 검색(semantic search): 질의를 임베딩 적재 때와 동일한 OpenAI 모델로
    임베딩한 뒤, statistics.embedding 과 코사인 거리(<=>)로 비교해 가까운 순으로 정렬한다.
    → "폭염"으로 검색해도 "온열질환"처럼 표현이 달라도 의미가 가까우면 상위에 뜬다.
  - 참고용으로 질의 토큰이 제목에 실제로 들어있는지(matched_tokens)도 함께 돌려준다.

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
from openai import OpenAI
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

# 의미 검색용 임베딩 모델. load/embedding.py 로 저장한 것과 반드시 동일해야
# 벡터 공간이 일치한다(text-embedding-3-small = 1536차원, 스키마 vector(1536)).
EMBED_MODEL = os.environ.get("STATYEARBOOK_EMBED_MODEL", "text-embedding-3-small")

# OpenAI 클라이언트는 처음 검색할 때 한 번만 만든다(모듈 로드 시 키가 없어도 서버는 뜨게).
_openai_client: OpenAI | None = None


def _embed_query(text: str) -> str:
    """질의를 임베딩해 pgvector 리터럴 '[0.1,0.2,...]' 로 돌려준다."""
    global _openai_client
    if _openai_client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY 미설정: 의미 검색을 하려면 .env 에 키를 넣어 주세요."
            )
        _openai_client = OpenAI()
    resp = _openai_client.embeddings.create(model=EMBED_MODEL, input=text)
    vec = resp.data[0].embedding
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


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
              score 는 코사인 유사도(1=의미상 완전 일치, 클수록 관련도 높음)다.
    """
    if not query or not query.strip():
        return {"query": query, "tokens": [], "count": 0, "results": []}

    tokens = _tokenize(query)

    # 질의를 임베딩해 저장된 제목 벡터와 코사인 거리로 비교한다.
    # <=> 는 pgvector 의 코사인 거리(0=완전 일치 ~ 2=정반대). 작을수록 가깝다.
    query_vec = _embed_query(query)

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
