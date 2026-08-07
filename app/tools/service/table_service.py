# -*- coding: utf-8 -*-
import json
from copy import deepcopy

from app.tools.repository.table_repository import TableRepository
from app.tools.service.contact_service import ContactService
from app.table_cache import cache_table


TABLE_REPOSITORY = TableRepository()


# stat_id에 해당하는 통계표 원천 데이터를 모든 seq와 함께 조회한다.
def fetch_table_data(stat_id: int) -> tuple[dict | None, list, list, list]:
    stat, tables, footnotes, contacts = TABLE_REPOSITORY.select_table_data(stat_id)
    source = [ContactService.contact_result(row) for row in contacts]
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


# 넓은 표는 지역 열만 되풀이하고 나머지 열을 다음 쪽으로 넘겨 seq가 나뉜다. 이런 조각은
# 행이 아니라 열이 이어지는 것이므로, 행 라벨이 순서까지 같을 때만 오른쪽으로 붙여야 한다.
def _continues_columns(
    columns: list[str],
    records: list[dict],
    body_columns: list[str],
    body_records: list[dict],
) -> bool:
    if not columns or not body_columns or columns[0] != body_columns[0]:
        return False
    if not records or len(records) != len(body_records):
        return False

    label = columns[0]
    return all(
        str(record.get(label, "")) == str(other.get(label, ""))
        for record, other in zip(records, body_records)
    )


# 같은 stat_id의 여러 seq 표 본문을 columns/records 기준으로 하나의 전체 표로 이어 붙인다.
def merge_bodies(bodies: list[dict]) -> dict:
    merged = deepcopy(bodies[0])
    columns = list(merged.get("columns") or [])
    records = [dict(record) for record in merged.get("records") or []]
    for body in bodies[1:]:
        body_columns = list(body.get("columns") or [])
        body_records = [dict(record) for record in body.get("records") or []]

        if body_columns == columns:
            records.extend(body_records)
            continue

        if _continues_columns(columns, records, body_columns, body_records):
            added = [column for column in body_columns[1:] if column not in columns]
            columns.extend(added)
            for record, other in zip(records, body_records):
                for column in added:
                    record[column] = other.get(column, "")
            continue

        # 머리글 표기만 어긋난 같은 표로 보고 위치를 기준으로 맞춘다.
        for record in body_records:
            values = [record.get(column, "") for column in body_columns]
            records.append({
                columns[index]: values[index] if index < len(values) else ""
                for index in range(len(columns))
            })

    merged["columns"] = columns
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
        body = merge_bodies(bodies)
        base["body"] = body
        # seq 1의 크기가 남아 있으면 합쳐진 표의 실제 행·열 수와 어긋난다.
        if body.get("columns") and body.get("records"):
            base["n_rows"] = len(body["records"])
            base["n_cols"] = len(body["columns"])
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
        "dept": row["department"],
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
        "source": [source_result(row) for row in source],
        "footnotes": [footnote_result(row) for row in footnotes],
        "tables": [table_result(row, table_handle) for row in tables],
    }


# stat_id에 해당하는 전체 표와 메타데이터를 조회한다.
def search_tables_data(stat_id: int) -> dict:
    stat, tables, footnotes, source = fetch_table_data(stat_id)
    if stat is None:
        return {"found": False, "stat_id": stat_id, "tables": []}
    return build_response(stat, tables, footnotes, source)
