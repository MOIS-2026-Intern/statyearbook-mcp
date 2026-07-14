# -*- coding: utf-8 -*-
import json

from mcp.server.fastmcp import FastMCP

from app.db import connect
from app.table_cache import cache_table
from app.tool_descriptions import SEARCH_TABLES


STAT_SQL = """
    SELECT stat_id, year AS publication_year, title_ko, title_en, unit, base_date, ref_id
    FROM statistics
    WHERE stat_id = %s
"""
TABLES_SQL = """
    SELECT seq, caption, n_rows, n_cols, body, table_md
    FROM stat_tables
    WHERE stat_id = %s
    ORDER BY seq
"""
FOOTNOTES_SQL = """
    SELECT seq, note_no, content
    FROM footnotes
    WHERE stat_id = %s
    ORDER BY seq
"""
SOURCE_SQL = """
    SELECT dept, officer, phone, source_system, source_url
    FROM contacts
    WHERE stat_id = %s
"""


# stat_id에 해당하는 통계표 원천 데이터를 조회한다.
def fetch_table_data(stat_id: int) -> tuple[dict | None, list, list, list]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(STAT_SQL, (stat_id,))
        stat = cur.fetchone()
        if stat is None:
            return None, [], [], []

        cur.execute(TABLES_SQL, (stat_id,))
        tables = cur.fetchall()

        cur.execute(FOOTNOTES_SQL, (stat_id,))
        footnotes = cur.fetchall()

        cur.execute(SOURCE_SQL, (stat_id,))
        source = cur.fetchall()

    return stat, tables, footnotes, source


# 시각화 도구가 그대로 사용할 수 있는 원본 표 객체를 만든다.
def cached_table(stat: dict, row: dict) -> dict:
    body = row["body"]
    if isinstance(body, str):
        body = json.loads(body)
    return {
        "stat_id": stat["stat_id"],
        "ref_id": stat["ref_id"],
        "publication_year": stat["publication_year"],
        "title_ko": stat["title_ko"],
        "title_en": stat["title_en"],
        "unit": stat["unit"],
        "base_date": stat["base_date"],
        "table_seq": row["seq"],
        "caption": row["caption"],
        "n_rows": row["n_rows"],
        "n_cols": row["n_cols"],
        "body": body,
        "table_md": row["table_md"],
    }


# 표 행을 API 응답 형태로 바꾸고 후속 호출용 핸들을 발급한다.
def table_result(stat: dict, row: dict) -> dict:
    table_handle = cache_table(cached_table(stat, row))
    return {
        "seq": row["seq"],
        "table_handle": table_handle,
        "caption": row["caption"],
        "n_rows": row["n_rows"],
        "n_cols": row["n_cols"],
        "table_md": row["table_md"],
    }


# 주석 행을 API 응답 형태로 바꾼다.
def footnote_result(row: dict) -> dict:
    return {
        "seq": row["seq"],
        "note_no": row["note_no"],
        "content": row["content"],
    }


# 출처 행을 API 응답 형태로 바꾼다.
def source_result(row: dict) -> dict:
    return {
        "dept": row["dept"],
        "officer": row["officer"],
        "phone": row["phone"],
        "source_system": row["source_system"],
        "source_url": row["source_url"],
    }


# 통계표 조회 결과를 MCP 응답 dict로 만든다.
def build_response(stat: dict, tables: list, footnotes: list, source: list) -> dict:
    return {
        "found": True,
        "stat_id": stat["stat_id"],
        "ref_id": stat["ref_id"],
        "publication_year": stat["publication_year"],
        "title_ko": stat["title_ko"],
        "title_en": stat["title_en"],
        "unit": stat["unit"],
        "base_date": stat["base_date"],
        "tables": [table_result(stat, row) for row in tables],
        "footnotes": [footnote_result(row) for row in footnotes],
        "source": [source_result(row) for row in source],
    }


# search_tables MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # stat_id에 해당하는 표 본문과 메타데이터를 가져온다.
    @mcp.tool(description=SEARCH_TABLES)
    def search_tables(stat_id: int) -> dict:
        stat, tables, footnotes, source = fetch_table_data(stat_id)
        if stat is None:
            return {"found": False, "stat_id": stat_id, "tables": []}
        return build_response(stat, tables, footnotes, source)
