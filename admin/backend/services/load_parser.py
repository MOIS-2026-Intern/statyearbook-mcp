# 이 파일은 HWPX 문서 구조를 통계연보 JSON으로 파싱하고 검수용 Markdown을 렌더링한다.
# 계층 복원은 load_outline이 맡고, 여기서는 표 병합 셀, 본문, 주석과 연락처 추출을 담당한다.
from __future__ import annotations

import html
import json
import os
import re
import zipfile
from copy import deepcopy
from xml.etree import ElementTree as ET

from admin.backend.services.load_outline import (
    APPENDIX_CHAPTER_NO,
    Heading,
    OutlineNode,
    TocCatalog,
    build_outline,
    build_toc_catalog,
    is_colophon,
    parse_heading_cell,
    parse_section_cover,
    parse_toc_chapter_row,
)

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

RE_SECTION_XML = re.compile(r"^Contents/section(\d+)\.xml$")
RE_BASEDATE = re.compile(r"\(?\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\s*기준\s*\)?")
RE_UNIT = re.compile(r"\(?\s*단위\s*[:：]\s*([^)\n]+?)\s*\)")
RE_PHONE = re.compile(r"0\d{1,2}[-)]\s?\d{3,4}[-]\d{4}")
RE_URL = re.compile(r"((?:https?://|www\.)[^\s()]+)")
RE_NOTE_NO = re.compile(r"^#?\s*(주\d*\))")

TEXT_SKIP_IN_PARAGRAPH = {HP + "tbl", HP + "pic", HP + "rect", HP + "ctrl"}
TEXT_SKIP_IN_CELL = {HP + "tbl", HP + "pic", HP + "ctrl"}

HEADER_HINTS = (
    "구분", "분류", "연도", "년도", "기관", "지역", "성별", "유형",
    "classification", "year", "type", "region", "organization",
    "institution", "category",
)


# XML 정수 속성을 읽고 누락되거나 손상된 값은 지정 기본값으로 대체한다.
def xml_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


# HWPX 특수 공백과 줄바꿈을 일관된 저장용 텍스트로 정규화한다.
def clean_text(value: str, keep_newlines: bool = False) -> str:
    value = (
        value.replace("\r", "\n")
        .replace("\xa0", " ")
        .replace("\u2002", " ")
        .replace("\u2003", " ")
        .replace("\u200b", "")
    )
    if keep_newlines:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
        return "\n".join(line for line in lines if line)
    return re.sub(r"\s+", " ", value).strip()


# 제외할 개체를 건너뛰며 XML 하위 노드의 화면 표시 텍스트를 순서대로 모은다.
def visible_text(element: ET.Element, skip_tags: set[str] | None = None,
                 keep_newlines: bool = False) -> str:
    skip_tags = skip_tags or set()
    out: list[str] = []

    # 탭·줄바꿈·tail을 보존하면서 현재 노드 트리를 깊이 우선으로 순회한다.
    def walk(node: ET.Element) -> None:
        if node.tag in skip_tags:
            return
        if node.tag == HP + "tab":
            out.append(" ")
        elif node.tag == HP + "lineBreak":
            out.append("\n")
        elif node.text:
            out.append(node.text)

        for child in node:
            walk(child)
            if child.tail:
                out.append(child.tail)

    walk(element)
    return clean_text("".join(out), keep_newlines=keep_newlines)


# 표 셀의 문단별 텍스트를 추출하고 문단 구조가 없으면 셀 전체로 대체한다.
def cell_paragraphs(cell: ET.Element) -> list[str]:
    sublist = cell.find(HP + "subList")
    paragraph_parent = sublist if sublist is not None else cell
    paragraphs = []
    for paragraph in paragraph_parent.findall(HP + "p"):
        text = visible_text(paragraph, TEXT_SKIP_IN_CELL, keep_newlines=True)
        if text:
            paragraphs.append(text)
    if paragraphs:
        return paragraphs

    fallback = visible_text(cell, TEXT_SKIP_IN_CELL, keep_newlines=True)
    return [fallback] if fallback else []


# 셀 안의 문단 경계를 줄바꿈으로 보존한 단일 문자열을 만든다.
def norm_cell_text(paragraphs: list[str]) -> str:
    return "\n".join(paragraphs).strip()


# 비어 있지 않은 셀 텍스트를 행 순서대로 이어 표의 검색용 평문을 만든다.
def table_plain_text(table: dict, separator: str = " ") -> str:
    values: list[str] = []
    for row in table.get("cells", []):
        for cell in row:
            text = clean_text(cell.get("text") or "")
            if text:
                values.append(text)
    return clean_text(separator.join(values))


# 표의 모든 셀 텍스트를 원본 순서대로 반환한다.
def table_cell_texts(table: dict) -> list[str]:
    return [
        cell.get("text") or ""
        for row in table.get("cells", [])
        for cell in row
    ]


# 명시된 셀 주소를 읽고 없으면 현재 순회 위치를 안전한 좌표로 사용한다.
def cell_addr(cell: ET.Element, row_index: int, col_index: int) -> tuple[int, int]:
    addr = cell.find(HP + "cellAddr")
    if addr is None:
        return row_index, col_index
    return (
        xml_int(addr.get("rowAddr"), row_index),
        xml_int(addr.get("colAddr"), col_index),
    )


# 셀의 열·행 병합 범위를 최소 1로 보정해 반환한다.
def cell_span(cell: ET.Element) -> tuple[int, int]:
    span = cell.find(HP + "cellSpan")
    if span is None:
        return 1, 1
    return (
        max(1, xml_int(span.get("colSpan"), 1)),
        max(1, xml_int(span.get("rowSpan"), 1)),
    )


# 존재하는 경우 셀의 원본 너비와 높이를 정수 메타데이터로 추출한다.
def cell_size(cell: ET.Element) -> dict:
    size = cell.find(HP + "cellSz")
    if size is None:
        return {}
    return {
        "width": xml_int(size.get("width"), 0),
        "height": xml_int(size.get("height"), 0),
    }


# HWPX 표 XML을 병합 좌표와 출처가 보존된 구조화 표로 변환한다.
def parse_table(tbl: ET.Element, section_name: str, page_number: int) -> dict:
    row_count = xml_int(tbl.get("rowCnt"), 0)
    col_count = xml_int(tbl.get("colCnt"), 0)
    rows: list[list[dict]] = [[] for _ in range(max(row_count, 0))]

    max_row = row_count
    max_col = col_count
    for tr_index, tr in enumerate(tbl.findall(HP + "tr")):
        fallback_col = 0
        for cell in tr.findall(HP + "tc"):
            row_addr, col_addr = cell_addr(cell, tr_index, fallback_col)
            col_span, row_span = cell_span(cell)
            paragraphs = cell_paragraphs(cell)
            record = {
                "row": row_addr,
                "col": col_addr,
                "text": norm_cell_text(paragraphs),
                "paragraphs": paragraphs,
                "colSpan": col_span,
                "rowSpan": row_span,
            }
            record.update(cell_size(cell))

            while len(rows) <= row_addr:
                rows.append([])
            rows[row_addr].append(record)

            max_row = max(max_row, row_addr + row_span)
            max_col = max(max_col, col_addr + col_span)
            fallback_col = col_addr + col_span

    while len(rows) < max_row:
        rows.append([])
    for row in rows:
        row.sort(key=lambda item: item["col"])

    table = {
        "rows": max_row,
        "cols": max_col,
        "cells": rows[:max_row],
        "hasHeader": True,
        "source": {
            "section": section_name,
            "page": page_number,
            "table_id": tbl.get("id"),
        },
    }
    enrich_table_body(table)
    return table


# 병합 셀의 값을 차지하는 모든 좌표에 펼쳐 직사각형 문자열 grid를 만든다.
def cells_to_grid(table: dict) -> list[list[str]]:
    n_rows = table.get("rows", 0)
    n_cols = table.get("cols", 0)
    grid = [[""] * n_cols for _ in range(n_rows)]
    for row in table.get("cells", []):
        for cell in row:
            text = cell.get("text") or ""
            row_addr = cell.get("row", 0)
            col_addr = cell.get("col", 0)
            for dr in range(cell.get("rowSpan", 1) or 1):
                for dc in range(cell.get("colSpan", 1) or 1):
                    rr = row_addr + dr
                    cc = col_addr + dc
                    if 0 <= rr < n_rows and 0 <= cc < n_cols:
                        grid[rr][cc] = text
    return grid


# 실제 텍스트 셀이 시작되는 열만 골라 불필요한 빈 열을 제외한다.
def active_column_indexes(table: dict) -> list[int]:
    columns = {
        cell.get("col", 0)
        for row in table.get("cells", [])
        for cell in row
        if clean_label(cell.get("text"))
    }
    if not columns:
        return list(range(table.get("cols", 0)))
    return sorted(column for column in columns if 0 <= column < table.get("cols", 0))


# 표 전체를 가로지르는 제목·기준일·단위 행을 데이터 행과 분리한다.
def caption_row_indexes(table: dict) -> set[int]:
    n_cols = table.get("cols", 0)
    indexes: set[int] = set()
    for row_index, row in enumerate(table.get("cells", [])):
        nonempty = [cell for cell in row if clean_text(cell.get("text") or "")]
        if len(nonempty) != 1:
            continue
        cell = nonempty[0]
        if (cell.get("colSpan", 1) or 1) >= n_cols:
            text = cell.get("text") or ""
            if row_index <= 2 or RE_BASEDATE.search(text) or RE_UNIT.search(text):
                indexes.add(row_index)
    return indexes


# 임의 셀 값을 비교와 헤더 생성에 쓰는 정규화된 문자열로 만든다.
def clean_label(value: object) -> str:
    return clean_text(str(value or ""))


# 쉼표·백분율·회계식 음수를 허용해 숫자 셀만 실수로 해석한다.
def parse_number(value: object) -> float | None:
    text = clean_label(value)
    if not text or text in {"-", "－", "—", "–"}:
        return None
    normalized = (
        text.replace(",", "")
        .replace("%", "")
        .replace("−", "-")
        .replace("△", "-")
        .replace("▲", "-")
        .replace(" ", "")
    )
    if re.fullmatch(r"\([-+]?\d+(?:\.\d+)?\)", normalized):
        normalized = "-" + normalized.strip("()")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized):
        return None
    return float(normalized)


# 셀 앞부분의 1800~2099년 표기를 연도로 인식한다.
def parse_year(value: object) -> int | None:
    match = re.match(r"^\s*((?:18|19|20)\d{2})", str(value or ""))
    return int(match.group(1)) if match else None


# 행의 비어 있지 않은 값, 숫자, 연도 개수를 헤더 판별 특징으로 계산한다.
def numeric_profile(row: list[str]) -> tuple[int, int, int]:
    nonempty = [clean_label(value) for value in row if clean_label(value)]
    numeric_count = sum(1 for value in nonempty if parse_number(value) is not None)
    year_count = sum(1 for value in nonempty if parse_year(value) is not None)
    return len(nonempty), numeric_count, year_count


# 알려진 헤더 단어와 연도 패턴을 이용해 머리글 행 가능성을 판정한다.
def looks_like_header_row(row: list[str]) -> bool:
    nonempty_count, numeric_count, year_count = numeric_profile(row)
    text = " ".join(clean_label(value).lower() for value in row)
    if any(hint in text for hint in HEADER_HINTS):
        return True
    if nonempty_count >= 2 and numeric_count > 0 and numeric_count == year_count:
        return True
    return False


# 숫자 밀도를 기준으로 실제 관측값 행 가능성을 판정한다.
def looks_like_data_row(row: list[str]) -> bool:
    nonempty_count, numeric_count, _ = numeric_profile(row)
    if nonempty_count == 0:
        return False
    return numeric_count >= 2 or (numeric_count >= 1 and nonempty_count >= 2)


# caption과 빈 행을 제외하고 활성 열만 남긴 원본 행 번호·값 쌍을 만든다.
def usable_grid_rows(table: dict) -> list[tuple[int, list[str]]]:
    caption_rows = set(table.get("caption_rows", []))
    active_cols = table.get("active_cols") or list(range(table.get("cols", 0)))
    rows = []
    for row_index, row in enumerate(table.get("grid", [])):
        if row_index in caption_rows:
            continue
        compact_row = [row[col_index] if col_index < len(row) else "" for col_index in active_cols]
        if any(clean_label(value) for value in compact_row):
            rows.append((row_index, compact_row))
    return rows


# 첫 실제 데이터 행을 찾아 그 앞 행들을 다단 헤더로 분리할 경계를 정한다.
def first_data_row_offset(rows: list[list[str]]) -> int:
    if len(rows) <= 1:
        return 0
    for offset, row in enumerate(rows):
        if offset == 0:
            continue
        if looks_like_data_row(row) and not looks_like_header_row(row):
            return offset
    return 1


# 다단 헤더의 열별 조각을 중복 없이 합쳐 평면 컬럼 이름을 만든다.
def combine_header_rows(header_rows: list[list[str]], width: int) -> list[str]:
    headers: list[str] = []
    for col_index in range(width):
        parts: list[str] = []
        for row in header_rows:
            value = clean_label(row[col_index]) if col_index < len(row) else ""
            if value and value not in parts:
                parts.append(value)
        headers.append("_".join(parts) if parts else f"column_{col_index + 1}")
    return unique_headers(headers)


# 빈 헤더를 보완하고 중복 이름에 순번을 붙여 레코드 키 충돌을 막는다.
def unique_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for index, header in enumerate(headers, start=1):
        base = header or f"column_{index}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        result.append(base if count == 1 else f"{base}_{count}")
    return result


# 페이지 중간에 반복된 헤더 행을 컬럼 일치 비율로 식별한다.
def repeated_header(row: list[str], columns: list[str]) -> bool:
    cleaned = [clean_label(value) for value in row]
    matches = sum(1 for left, right in zip(cleaned, columns) if left == right)
    return matches >= max(2, len(columns) // 2)


# 표 grid를 헤더·데이터 행 번호, 고유 컬럼과 레코드 목록으로 구조화한다.
def table_records(table: dict) -> tuple[list[int], list[int], list[str], list[dict[str, str]]]:
    usable = usable_grid_rows(table)
    if not usable:
        return [], [], [], []

    rows = [row for _, row in usable]
    width = max((len(row) for row in rows), default=0)
    data_offset = first_data_row_offset(rows)
    header_pairs = usable[:data_offset] or usable[:1]
    data_pairs = usable[data_offset:] if data_offset else usable[1:]

    columns = combine_header_rows([row for _, row in header_pairs], width)
    records: list[dict[str, str]] = []
    data_indexes: list[int] = []
    for original_index, row in data_pairs:
        if repeated_header(row, columns):
            continue
        record = {
            columns[col_index]: clean_label(row[col_index]) if col_index < len(row) else ""
            for col_index in range(len(columns))
        }
        if any(record.values()):
            records.append(record)
            data_indexes.append(original_index)

    return [index for index, _ in header_pairs], data_indexes, columns, records


# 셀의 파이프와 줄바꿈을 Markdown 표 안에서 안전한 표현으로 바꾼다.
def markdown_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


# 셀 목록을 하나의 GitHub Markdown 표 행으로 직렬화한다.
def markdown_row(cells: list[object]) -> str:
    return "| " + " | ".join(markdown_cell(cell) for cell in cells) + " |"


# 구조화된 컬럼과 레코드를 검수 가능한 Markdown 표로 렌더링한다.
def records_to_markdown(columns: list[str], records: list[dict[str, str]]) -> str:
    if not columns or not records:
        return ""
    lines = [markdown_row(columns), markdown_row(["---"] * len(columns))]
    for record in records:
        lines.append(markdown_row([record.get(column, "") for column in columns]))
    return "\n".join(lines)


# 레코드 추론이 실패한 표를 활성 grid 기반 Markdown으로 보존한다.
def grid_to_markdown(table: dict) -> str:
    active_cols = table.get("active_cols") or list(range(table.get("cols", 0)))
    rows = [
        [row[col_index] if col_index < len(row) else "" for col_index in active_cols]
        for index, row in enumerate(table.get("grid", []))
        if index not in set(table.get("caption_rows", []))
        and any(clean_label(value) for value in row)
    ]
    if not rows:
        return ""
    lines = [markdown_row(rows[0]), markdown_row(["---"] * len(rows[0]))]
    for row in rows[1:]:
        lines.append(markdown_row(row))
    return "\n".join(lines)


# 원본 병합 범위와 추론된 헤더 셀을 보존한 HTML 표를 생성한다.
def table_to_html(table: dict) -> str:
    header_rows = set(table.get("header_rows", []))
    out = ["<table>"]
    for row_index, row in enumerate(table.get("cells", [])):
        out.append("<tr>")
        tag = "th" if row_index in header_rows else "td"
        for cell in row:
            attrs = []
            if (cell.get("colSpan", 1) or 1) > 1:
                attrs.append(f'colspan="{cell["colSpan"]}"')
            if (cell.get("rowSpan", 1) or 1) > 1:
                attrs.append(f'rowspan="{cell["rowSpan"]}"')
            attr_text = (" " + " ".join(attrs)) if attrs else ""
            text = html.escape(cell.get("text") or "").replace("\n", "<br>")
            out.append(f"<{tag}{attr_text}>{text}</{tag}>")
        out.append("</tr>")
    out.append("</table>")
    return "\n".join(out)


# 파싱 표에 grid, 행 역할, 레코드와 HTML 파생 표현을 제자리에서 추가한다.
def enrich_table_body(table: dict) -> None:
    table["grid"] = cells_to_grid(table)
    table["active_cols"] = active_column_indexes(table)
    table["caption_rows"] = sorted(caption_row_indexes(table))
    header_rows, data_rows, columns, records = table_records(table)
    table["header_rows"] = header_rows
    table["data_rows"] = data_rows
    table["columns"] = columns
    table["records"] = records
    table["html"] = table_to_html(table)


# 최소 2×2이며 텍스트가 하나 이상 있는 표만 통계 데이터 표로 인정한다.
def data_table(table: dict) -> bool:
    if table.get("cols", 0) < 2 or table.get("rows", 0) < 2:
        return False
    return any(clean_label(cell.get("text")) for row in table.get("cells", []) for cell in row)


# caption 또는 표 평문에서 기준일, 단위와 표시용 caption을 추출한다.
def extract_meta_from_table(table: dict) -> tuple[str | None, str | None, str | None]:
    caption_parts = []
    for row_index in table.get("caption_rows", []):
        row = table.get("grid", [])[row_index]
        values = [clean_label(value) for value in row if clean_label(value)]
        if values:
            caption_parts.append(values[0])
    caption = " ".join(caption_parts) or None

    blob = caption or table_plain_text(table)
    base_date_match = RE_BASEDATE.search(blob)
    unit_match = RE_UNIT.search(blob)
    base_date = base_date_match.group(1).replace(" ", "") if base_date_match else None
    unit_name = unit_match.group(1).strip() if unit_match else None
    return base_date, unit_name, caption


# 원본 표 파생 구조와 최선의 Markdown 표현을 저장용 레코드로 묶는다.
def table_record(table: dict, seq: int, caption: str | None) -> dict:
    body = deepcopy(table)
    table_md = records_to_markdown(body.get("columns", []), body.get("records", []))
    if not table_md:
        table_md = grid_to_markdown(body)
    return {
        "seq": seq,
        "caption": caption,
        "n_rows": body.get("rows"),
        "n_cols": body.get("cols"),
        "body": body,
        "table_md": table_md,
    }


# 통계 단위의 기준일과 단위를 최초로 발견한 표 값으로만 채운다.
def apply_table_meta(unit: dict, base_date: str | None, unit_name: str | None) -> None:
    if base_date and not unit.get("base_date"):
        unit["base_date"] = base_date
    if unit_name and not unit.get("unit"):
        unit["unit"] = unit_name


# 표 메타데이터를 통계 단위에 반영하고 다음 순번의 표 레코드를 추가한다.
def add_table(unit: dict, table: dict) -> None:
    base_date, unit_name, caption = extract_meta_from_table(table)
    apply_table_meta(unit, base_date, unit_name)
    unit["tables"].append(table_record(table, len(unit["tables"]) + 1, caption))


# 문장에서 국내 전화번호를 찾아 일관된 하이픈 형식으로 정규화한다.
def norm_phone(text: str) -> str | None:
    match = RE_PHONE.search(text)
    if not match:
        return None
    phone = re.sub(r"[)\s]", "-", match.group(0))
    return re.sub(r"-+", "-", phone).strip("-")


# 슬래시 뒤 출처 설명과 URL을 담당자 문구에서 분리한다.
def split_source(text: str) -> tuple[str, str | None, str | None]:
    if "/" not in text:
        return text, None, None
    left, right = text.split("/", 1)
    url_match = RE_URL.search(right)
    source_url = url_match.group(1) if url_match else None
    source_system = re.sub(r"\(.*?\)", "", right).strip() or None
    return left.strip(), source_system, source_url


# 전화번호 앞 담당자 문구를 부서와 담당자 이름으로 나눈다.
def split_officer(text: str, phone: str | None) -> tuple[str | None, str | None]:
    who = RE_PHONE.split(text)[0].strip() if phone else text
    who = who.strip(" ()")
    if not who:
        return None, None
    parts = who.split()
    return parts[0], " ".join(parts[1:]) or None


# 별표로 시작하는 출처 문단을 부서·담당자·전화·시스템 필드로 구조화한다.
def parse_contact(text: str) -> dict:
    body = text.lstrip("*").strip()
    phone = norm_phone(body)
    body, source_system, source_url = split_source(body)
    dept, officer = split_officer(body, phone)
    return {
        "dept": dept,
        "officer": officer,
        "phone": phone,
        "source_system": source_system,
        "source_url": source_url,
    }


# 문단이 통계 주석 번호 패턴으로 시작하는지 판별한다.
def is_note_text(text: str) -> bool:
    return text.startswith("#주") or bool(RE_NOTE_NO.match(text))


# 주석 문단을 순번, 선택 주석 번호와 정리된 본문으로 변환한다.
def note_record(text: str, seq: int) -> dict:
    match = RE_NOTE_NO.match(text)
    return {
        "seq": seq,
        "note_no": match.group(1) if match else None,
        "content": re.sub(r"^#", "", text).strip(),
    }


# 같은 내용의 주석·출처가 쪽 분할 때문에 반복 수록되는 것을 막는다.
def _append_unique(items: list[dict], candidate: dict, keys: tuple[str, ...]) -> bool:
    signature = tuple(candidate.get(key) for key in keys)
    for item in items:
        if tuple(item.get(key) for key in keys) == signature:
            return False
    items.append(candidate)
    return True


# 본문 문단을 주석·연속 주석·출처로 분류해 현재 통계 단위에 반영한다.
def handle_paragraph(unit: dict, text: str, pending_note: dict | None) -> dict | None:
    if not text:
        return pending_note
    if is_note_text(text):
        note = note_record(text, len(unit["footnotes"]) + 1)
        if _append_unique(unit["footnotes"], note, ("content",)):
            note["seq"] = len(unit["footnotes"])
            return note
        return None
    if text.startswith("-") and pending_note:
        pending_note["content"] = f'{pending_note["content"]} {text}'
        return pending_note
    if text.startswith("*"):
        contact = parse_contact(text)
        if contact.get("phone") or contact.get("dept"):
            _append_unique(unit["contacts"], contact, ("dept", "officer", "phone"))
    return None


# HWPX ZIP 안의 본문 section XML 이름을 숫자 순서로 정렬한다.
def section_names(zip_file: zipfile.ZipFile) -> list[str]:
    names = []
    for name in zip_file.namelist():
        if RE_SECTION_XML.match(name):
            names.append(name)
    return sorted(names, key=lambda value: int(RE_SECTION_XML.match(value).group(1)))


# HWPX 본문을 원래 순서와 페이지 번호가 붙은 문단·표 block으로 스트리밍한다.
def iter_blocks(hwpx_path: str):
    page_number = 1
    with zipfile.ZipFile(hwpx_path) as zip_file:
        for section_name in section_names(zip_file):
            root = ET.fromstring(zip_file.read(section_name))
            for paragraph in root.findall(HP + "p"):
                if paragraph.get("pageBreak") == "1":
                    page_number += 1

                text_parts: list[str] = []

                # 표·이미지 경계 전까지 모인 run 텍스트를 하나의 문단 block으로 비운다.
                def flush_text():
                    if not text_parts:
                        return None
                    text = clean_text("".join(text_parts), keep_newlines=True)
                    text_parts.clear()
                    if text:
                        return {"type": "paragraph", "text": text, "pageNumber": page_number}
                    return None

                for run in paragraph.findall(HP + "run"):
                    for child in run:
                        if child.tag == HP + "tbl":
                            block = flush_text()
                            if block:
                                yield block
                            yield {
                                "type": "table",
                                "table": parse_table(child, section_name, page_number),
                                "pageNumber": page_number,
                            }
                        elif child.tag == HP + "pic":
                            block = flush_text()
                            if block:
                                yield block
                            # 통계표 파싱에는 이미지를 사용하지 않으며 산출물/DB에도 저장하지 않는다.
                        elif child.tag not in TEXT_SKIP_IN_PARAGRAPH:
                            text_parts.append(visible_text(child, TEXT_SKIP_IN_PARAGRAPH, keep_newlines=True))

                block = flush_text()
                if block:
                    yield block


# 문서 앞머리에서 장 행과 계층 번호를 함께 가진 연속 목차 표만 모은다.
def collect_toc_tables(blocks: list[dict]) -> list[dict]:
    tables: list[dict] = []
    for block in blocks:
        if block["type"] != "table":
            continue
        table = block["table"]
        rows = [[cell.get("text") or "" for cell in row] for row in table.get("cells", [])]
        has_chapter_row = any(parse_toc_chapter_row(row) for row in rows)
        has_refs = bool(re.search(r"\d+-\d+-\d+|부록\s*\d", table_plain_text(table)))
        if has_chapter_row and has_refs:
            tables.append(table)
            continue
        if tables:
            break
    return tables


# 목차 표 이후의 본문에서 표제 표, 절 표지와 데이터 표를 순서대로 골라낸다.
def scan_body(blocks: list[dict], toc_table_count: int) -> tuple[
    list[tuple[Heading, int | None]],
    dict[tuple[int, int], tuple[str, str | None]],
    list[dict],
]:
    headings: list[tuple[Heading, int | None]] = []
    section_covers: dict[tuple[int, int], tuple[str, str | None]] = {}
    body: list[dict] = []
    seen_tables = 0
    pending_section: tuple[int, str, str | None] | None = None

    for block in blocks:
        if block["type"] == "table":
            seen_tables += 1
            if seen_tables <= toc_table_count:
                continue

            table = block["table"]
            plain = table_plain_text(table)
            if is_colophon(plain):
                break

            if table.get("cols") == 1:
                texts = table_cell_texts(table)
                cover = parse_section_cover(texts)
                if cover:
                    pending_section = cover
                    body.append({"kind": "section_cover"})
                    continue

                found = [
                    parsed
                    for parsed in (parse_heading_cell(text) for text in texts)
                    if parsed is not None
                ]
                if found:
                    for heading in found:
                        if pending_section and heading.section_no is not None:
                            number, title_ko, title_en = pending_section
                            if number == heading.section_no and heading.chapter_no is not None:
                                section_covers.setdefault(
                                    (heading.chapter_no, number), (title_ko, title_en)
                                )
                            pending_section = None
                        headings.append((heading, block.get("pageNumber")))
                        body.append({"kind": "heading", "index": len(headings) - 1})
                    continue

            if data_table(table):
                body.append({"kind": "table", "table": table})
            continue

        if block["type"] == "paragraph":
            body.append({"kind": "paragraph", "text": block.get("text") or ""})

    return headings, section_covers, body


# 확정된 계층 노드를 표·주석·출처를 담을 수 있는 통계 단위 dict로 만든다.
def node_to_unit(node: OutlineNode) -> dict:
    title_ko = node.level4_title or node.level3_title or node.ref_id
    title_en = node.level4_title_en if node.level4_title else node.level3_title_en
    return {
        "ref_id": node.ref_id,
        "ordinal": node.ordinal,
        "chapter_no": node.chapter_no,
        "section_no": node.section_no,
        "level3_no": node.level3_no,
        "level4_no": node.level4_no,
        "chapter": node.chapter,
        "section": node.section,
        "level3_title": node.level3_title,
        "level3_title_en": node.level3_title_en,
        "level4_title": node.level4_title,
        "level4_title_en": node.level4_title_en,
        "title_ko": title_ko,
        "title_en": title_en,
        "unit": None,
        "base_date": None,
        "page_start": node.page_start,
        "tables": [],
        "footnotes": [],
        "contacts": [],
    }


# 본문 순서를 따라 각 표·주석·출처를 직전 표제가 가리키는 통계 단위에 붙인다.
def attach_content(
    body: list[dict],
    headings: list[tuple[Heading, int | None]],
    units_by_ref: dict[str, dict],
) -> list[str]:
    warnings: list[str] = []
    current: dict | None = None
    pending_note: dict | None = None

    for item in body:
        kind = item["kind"]
        if kind == "section_cover":
            current = None
            pending_note = None
            continue

        if kind == "heading":
            heading = headings[item["index"]][0]
            unit = units_by_ref.get(heading.ref_id)
            if unit is None:
                # 하위 제목을 가진 3계층 묶음 제목이다. 표는 하위 제목이 받는다.
                current = None
            else:
                # 영문 전용 표제는 앞 쪽에서 이어지는 같은 통계의 계속 표시다.
                # 국문 쪽에 영문 제목이 없었다면 이때 채운다.
                if unit is not current and not unit.get("title_en") and heading.title_en:
                    unit["title_en"] = heading.title_en
                    if unit.get("level4_no") is not None:
                        unit["level4_title_en"] = heading.title_en
                    else:
                        unit["level3_title_en"] = heading.title_en
                current = unit
            pending_note = None
            continue

        if current is None:
            if kind == "table":
                warnings.append("표제 없이 등장한 데이터 표를 건너뛰었습니다.")
            continue

        if kind == "table":
            add_table(current, item["table"])
            pending_note = None
        elif kind == "paragraph":
            pending_note = handle_paragraph(current, item["text"], pending_note)

    return warnings


# 본문에서 복원한 계층을 앞머리 목차와 대조해 검수용 불일치 목록을 만든다.
def reconcile_with_toc(units: list[dict], catalog: TocCatalog) -> dict:
    body_titles: dict[str, str] = {}
    for unit in units:
        title = unit.get("title_ko") or ""
        body_titles.setdefault(re.sub(r"\s+", "", title), unit["ref_id"])

    ref_mismatch: list[dict] = []
    toc_only: list[dict] = []
    for leaf in catalog.leaves:
        if leaf.get("children"):
            continue
        title = re.sub(r"\s+", "", leaf.get("title_ko") or "")
        if not title:
            continue
        body_ref = body_titles.get(title)
        if body_ref is None:
            toc_only.append({
                "toc_ref_id": leaf["ref_id"],
                "title_ko": leaf.get("title_ko"),
                "toc_page": leaf.get("page"),
            })
        elif body_ref != leaf["ref_id"]:
            ref_mismatch.append({
                "title_ko": leaf.get("title_ko"),
                "toc_ref_id": leaf["ref_id"],
                "body_ref_id": body_ref,
            })

    toc_titles = {
        re.sub(r"\s+", "", leaf.get("title_ko") or "")
        for leaf in catalog.leaves
        if not leaf.get("children")
    }
    body_only = [
        {"ref_id": unit["ref_id"], "title_ko": unit.get("title_ko")}
        for unit in units
        if re.sub(r"\s+", "", unit.get("title_ko") or "") not in toc_titles
    ]
    return {
        "toc_ref_mismatch": ref_mismatch,
        "toc_only_entries": toc_only,
        "body_only_entries": body_only,
    }


# 적재 전에 반드시 잡아야 할 중복·누락·계층 결손을 통계 목록에서 검사한다.
def check_units(units: list[dict]) -> dict:
    seen: dict[str, int] = {}
    duplicate_refs: list[str] = []
    for unit in units:
        ref = unit["ref_id"]
        seen[ref] = seen.get(ref, 0) + 1
        if seen[ref] == 2:
            duplicate_refs.append(ref)

    duplicate_titles: dict[str, list[str]] = {}
    for unit in units:
        key = "|".join([
            str(unit.get("chapter_no")),
            str(unit.get("section_no")),
            re.sub(r"\s+", "", unit.get("title_ko") or ""),
        ])
        duplicate_titles.setdefault(key, []).append(unit["ref_id"])

    return {
        "statistics": len(units),
        "tables": sum(len(unit["tables"]) for unit in units),
        "duplicate_ref_ids": duplicate_refs,
        "duplicate_titles_in_section": [
            {"key": key, "ref_ids": refs}
            for key, refs in duplicate_titles.items()
            if len(refs) > 1
        ],
        "statistics_without_tables": [
            {"ref_id": unit["ref_id"], "title_ko": unit.get("title_ko")}
            for unit in units
            if not unit["tables"]
        ],
        "statistics_without_chapter": [
            unit["ref_id"] for unit in units if not unit.get("chapter")
        ],
        "statistics_without_section": [
            unit["ref_id"]
            for unit in units
            if unit.get("section_no") is not None and not unit.get("section")
        ],
    }


# 호출자가 덮어쓸 수 있는 기본 발간물 메타데이터를 페이지 수와 함께 만든다.
def default_publication(page_count: int | None) -> dict:
    return {
        "year": 2025,
        "pub_no": None,
        "title": "2025 행정안전통계연보",
        "page_count": page_count,
    }


# 모든 section의 명시적 pageBreak를 합산해 문서 페이지 수를 추정한다.
def estimate_page_count(hwpx_path: str) -> int | None:
    page_count = 1
    with zipfile.ZipFile(hwpx_path) as zip_file:
        for section_name in section_names(zip_file):
            root = ET.fromstring(zip_file.read(section_name))
            page_count += sum(1 for paragraph in root.findall(HP + "p") if paragraph.get("pageBreak") == "1")
    return page_count


# HWPX 목차와 본문을 결합해 적재 가능한 발간물·통계 JSON을 생성한다.
def parse(
    hwpx_path: str,
    publication_year: int | None = None,
    publication_title: str | None = None,
    publication_no: str | None = None,
) -> dict:
    blocks = list(iter_blocks(hwpx_path))
    toc_tables = collect_toc_tables(blocks)
    catalog = build_toc_catalog(toc_tables)
    headings, section_covers, body = scan_body(blocks, len(toc_tables))
    nodes, _ = build_outline(headings, catalog, section_covers)

    units = [node_to_unit(node) for node in nodes]
    units_by_ref = {unit["ref_id"]: unit for unit in units}
    warnings = attach_content(body, headings, units_by_ref)

    publication = default_publication(estimate_page_count(hwpx_path))
    if publication_year is not None:
        publication["year"] = publication_year
    if publication_title:
        publication["title"] = publication_title
    elif publication_year is not None:
        publication["title"] = f"{publication_year} 행정안전통계연보"
    if publication_no is not None:
        publication["pub_no"] = publication_no or None

    return {
        "publication": publication,
        "metadata": {
            "source": os.path.abspath(hwpx_path),
            "parser": "admin/backend/services/load_parser.py",
            "method": (
                "본문 표제 표(n-n-n / n-n-n-n / 부록N-M)를 계층의 정본으로 삼아 "
                "장·절·3계층·4계층과 최종 제목을 확정하고, 앞머리 목차는 장·절 이름과 "
                "교차검증에만 사용한다. 표는 hp:cellAddr/hp:cellSpan으로 병합 셀을 "
                "보존한 뒤 grid/records/markdown으로 파생한다."
            ),
            "toc_tables": len(toc_tables),
            "warnings": sorted(set(warnings)),
        },
        "checks": check_units(units),
        "toc_reconciliation": reconcile_with_toc(units, catalog),
        "statistics": units,
    }


# 파싱 결과를 통계·표·주석·출처 순서의 사람이 검수할 Markdown으로 렌더링한다.
def parsed_to_markdown(data: dict) -> str:
    checks = data.get("checks") or {}
    reconciliation = data.get("toc_reconciliation") or {}
    out = [f"# {data['publication']['title']}", ""]
    out.extend([
        "## 파싱 요약",
        "",
        f"- 통계 수: {checks.get('statistics')}",
        f"- 표 수: {checks.get('tables')}",
        f"- 중복 ref_id: {len(checks.get('duplicate_ref_ids') or [])}",
        f"- 표가 없는 통계: {len(checks.get('statistics_without_tables') or [])}",
        f"- 장이 비어 있는 통계: {len(checks.get('statistics_without_chapter') or [])}",
        f"- 절이 비어 있는 통계: {len(checks.get('statistics_without_section') or [])}",
        "",
    ])

    for label, key in (
        ("본문과 목차의 번호가 다른 항목", "toc_ref_mismatch"),
        ("목차에만 있는 항목", "toc_only_entries"),
        ("본문에만 있는 항목", "body_only_entries"),
    ):
        rows = reconciliation.get(key) or []
        out.extend([f"### {label} ({len(rows)}건)", ""])
        for row in rows:
            parts = [f"{name}={value}" for name, value in row.items() if value is not None]
            out.append("- " + ", ".join(parts))
        out.append("")

    for unit in data.get("statistics", []):
        out.extend([f"## {unit['ref_id']} {unit['title_ko']}".rstrip(), ""])
        hierarchy = [
            f"장: {unit.get('chapter')}",
            f"절: {unit.get('section')}",
            f"3계층: {unit.get('level3_title')}",
            f"4계층: {unit.get('level4_title')}",
        ]
        out.extend([" / ".join(hierarchy), ""])
        if unit.get("title_en"):
            out.extend([unit["title_en"], ""])

        meta = []
        if unit.get("base_date"):
            meta.append(f"기준일: {unit['base_date']}")
        if unit.get("unit"):
            meta.append(f"단위: {unit['unit']}")
        if meta:
            out.extend(["; ".join(meta), ""])

        for table in unit.get("tables", []):
            heading = f"### 표 {table['seq']}"
            if table.get("caption"):
                heading += f" - {table['caption']}"
            out.extend([heading, "", table.get("table_md") or "", ""])

        if unit.get("footnotes"):
            out.extend(["#### 주석", ""])
            for note in unit["footnotes"]:
                out.append(f"- {note.get('content')}")
            out.append("")

        if unit.get("contacts"):
            out.extend(["#### 출처", ""])
            for contact in unit["contacts"]:
                parts = [
                    contact.get("dept"),
                    contact.get("officer"),
                    contact.get("phone"),
                    contact.get("source_system"),
                    contact.get("source_url"),
                ]
                out.append("- " + " / ".join(part for part in parts if part))
            out.append("")

    return "\n".join(out).rstrip() + "\n"


# 대상 디렉터리를 보장하고 파싱 결과를 읽기 쉬운 UTF-8 JSON으로 저장한다.
def write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


# 대상 디렉터리를 보장하고 주어진 검수 텍스트를 UTF-8로 저장한다.
def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
