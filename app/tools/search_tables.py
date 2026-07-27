# -*- coding: utf-8 -*-
import json
from copy import deepcopy

from mcp.server.fastmcp import FastMCP

from app.db import connect
from app.table_cache import cache_table
from app.tool_descriptions import SEARCH_TABLES


STAT_SQL = """
    SELECT stat_id, year AS publication_year, ref_id,
           chapter_no, section_no, level3_no, level4_no,
           chapter, section, level3_title, level4_title,
           title_ko, title_en, unit, base_date, page_start
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


# stat_id에 해당하는 통계표 원천 데이터를 모든 seq와 함께 조회한다.
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
        "chapter_no": stat["chapter_no"],
        "section_no": stat["section_no"],
        "level3_no": stat["level3_no"],
        "level4_no": stat["level4_no"],
        "chapter": stat["chapter"],
        "section": stat["section"],
        "level3_title": stat["level3_title"],
        "level4_title": stat["level4_title"],
        "title_ko": stat["title_ko"],
        "title_en": stat["title_en"],
        "unit": stat["unit"],
        "base_date": stat["base_date"],
        "page_start": stat["page_start"],
        "table_seq": row["seq"],
        "caption": row["caption"],
        "n_rows": row["n_rows"],
        "n_cols": row["n_cols"],
        "body": body,
        "table_md": row["table_md"],
    }


# 같은 stat_id의 여러 seq 표 본문을 columns/records 기준으로 하나의 전체 표로 이어 붙인다.
def merge_bodies(bodies: list[dict]) -> dict:
    merged = deepcopy(bodies[0])
    base_columns = merged.get("columns") or []
    records = list(merged.get("records") or [])
    for body in bodies[1:]:
        columns = body.get("columns") or []
        for record in body.get("records") or []:
            if columns == base_columns:
                records.append(dict(record))
            else:
                values = [record.get(column, "") for column in columns]
                records.append({
                    base_columns[index]: values[index] if index < len(values) else ""
                    for index in range(len(base_columns))
                })
    merged["columns"] = base_columns
    merged["records"] = records
    return merged


# 같은 stat_id의 모든 seq를 하나로 합쳐 visualize가 그대로 재사용할 원본 표를 만든다.
def merged_cached_table(stat: dict, rows: list[dict]) -> dict:
    base = cached_table(stat, rows[0])
    if len(rows) > 1:
        bodies = [
            json.loads(row["body"]) if isinstance(row["body"], str) else row["body"]
            for row in rows
        ]
        base["body"] = merge_bodies(bodies)
    return base


# 표 행을 API 응답 형태로 바꾸고 합쳐진 전체 표의 공용 핸들을 붙인다.
def table_result(row: dict, table_handle: str | None) -> dict:
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
    table_handle = cache_table(merged_cached_table(stat, tables)) if tables else None
    return {
        "found": True,
        "stat_id": stat["stat_id"],
        "ref_id": stat["ref_id"],
        "publication_year": stat["publication_year"],
        "chapter_no": stat["chapter_no"],
        "section_no": stat["section_no"],
        "level3_no": stat["level3_no"],
        "level4_no": stat["level4_no"],
        "chapter": stat["chapter"],
        "section": stat["section"],
        "level3_title": stat["level3_title"],
        "level4_title": stat["level4_title"],
        "title_ko": stat["title_ko"],
        "title_en": stat["title_en"],
        "unit": stat["unit"],
        "base_date": stat["base_date"],
        "page_start": stat["page_start"],
        "tables": [table_result(row, table_handle) for row in tables],
        "footnotes": [footnote_result(row) for row in footnotes],
        "source": [source_result(row) for row in source],
    }


# search_tables MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # stat_id에 해당하는 모든 seq의 표 본문과 메타데이터를 하나의 논리 표로 가져온다.
    @mcp.tool(description=SEARCH_TABLES)
    def search_tables(stat_id: int, table_seq: int | None = None) -> dict:
        stat, tables, footnotes, source = fetch_table_data(stat_id)
        if stat is None:
            return {"found": False, "stat_id": stat_id, "tables": []}
        return build_response(stat, tables, footnotes, source)
