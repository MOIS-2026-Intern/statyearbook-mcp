# 이 파일은 HWPX 문서 구조를 통계연보 JSON으로 파싱하고 검수용 Markdown을 렌더링한다.
# 목차 계층, 표 병합 셀, 본문, 주석과 연락처 추출을 담당한다.
from __future__ import annotations

import html
import json
import os
import re
import zipfile
from copy import deepcopy
from xml.etree import ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

RE_SECTION_XML = re.compile(r"^Contents/section(\d+)\.xml$")
RE_REFID = re.compile(r"^(\d+-\d+-\d+(?:-\d+)?)\s*(.+)$", re.S)
RE_REFID_ANYWHERE = re.compile(r"(?<![\d-])(\d+-\d+-\d+(?:-\d+)?)(?![\d-])")
RE_TOC_SECTION = re.compile(r"^제\s*(\d+)\s*절\s*(.+)$")
RE_TOC_LEVEL3 = re.compile(r"^(\d+-\d+-\d+)\s+(.+)$")
RE_TOC_LEVEL4 = re.compile(r"^(\d+)\.\s*(.+)$")
RE_BASEDATE = re.compile(r"\(?\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\s*기준\s*\)?")
RE_UNIT = re.compile(r"\(?\s*단위\s*[:：]\s*([^)\n]+?)\s*\)")
RE_PHONE = re.compile(r"0\d{1,2}[-)]\s?\d{3,4}[-]\d{4}")
RE_URL = re.compile(r"((?:https?://|www\.)[^\s()]+)")
RE_NOTE_NO = re.compile(r"^#?\s*(주\d*\))")
RE_PAGE_SUFFIX = re.compile(r"\s+\d{1,4}$")
RE_KO_EN_BOUNDARY = re.compile(r"(?<=[가-힣)\]）])\s*(?=[A-Z][A-Za-z])")
RE_EN_SPLIT = re.compile(r"\s(?=(?:[A-Z][A-Za-z-]|\d+-[A-Za-z]))")

TEXT_SKIP_IN_PARAGRAPH = {HP + "tbl", HP + "pic", HP + "rect", HP + "ctrl"}
TEXT_SKIP_IN_CELL = {HP + "tbl", HP + "pic", HP + "ctrl"}

HEADER_HINTS = (
    "구분", "분류", "연도", "년도", "기관", "지역", "성별", "유형",
    "classification", "year", "type", "region", "organization",
    "institution", "category",
)


def xml_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


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


def visible_text(element: ET.Element, skip_tags: set[str] | None = None,
                 keep_newlines: bool = False) -> str:
    skip_tags = skip_tags or set()
    out: list[str] = []

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


def paragraph_text(paragraph: ET.Element) -> str:
    return visible_text(paragraph, TEXT_SKIP_IN_PARAGRAPH, keep_newlines=True)


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


def norm_cell_text(paragraphs: list[str]) -> str:
    return "\n".join(paragraphs).strip()


def table_plain_text(table: dict, separator: str = " ") -> str:
    values: list[str] = []
    for row in table.get("cells", []):
        for cell in row:
            text = clean_text(cell.get("text") or "")
            if text:
                values.append(text)
    return clean_text(separator.join(values))


def cell_addr(cell: ET.Element, row_index: int, col_index: int) -> tuple[int, int]:
    addr = cell.find(HP + "cellAddr")
    if addr is None:
        return row_index, col_index
    return (
        xml_int(addr.get("rowAddr"), row_index),
        xml_int(addr.get("colAddr"), col_index),
    )


def cell_span(cell: ET.Element) -> tuple[int, int]:
    span = cell.find(HP + "cellSpan")
    if span is None:
        return 1, 1
    return (
        max(1, xml_int(span.get("colSpan"), 1)),
        max(1, xml_int(span.get("rowSpan"), 1)),
    )


def cell_size(cell: ET.Element) -> dict:
    size = cell.find(HP + "cellSz")
    if size is None:
        return {}
    return {
        "width": xml_int(size.get("width"), 0),
        "height": xml_int(size.get("height"), 0),
    }


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


def clean_label(value: object) -> str:
    return clean_text(str(value or ""))


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


def parse_year(value: object) -> int | None:
    match = re.match(r"^\s*((?:18|19|20)\d{2})", str(value or ""))
    return int(match.group(1)) if match else None


def numeric_profile(row: list[str]) -> tuple[int, int, int]:
    nonempty = [clean_label(value) for value in row if clean_label(value)]
    numeric_count = sum(1 for value in nonempty if parse_number(value) is not None)
    year_count = sum(1 for value in nonempty if parse_year(value) is not None)
    return len(nonempty), numeric_count, year_count


def looks_like_header_row(row: list[str]) -> bool:
    nonempty_count, numeric_count, year_count = numeric_profile(row)
    text = " ".join(clean_label(value).lower() for value in row)
    if any(hint in text for hint in HEADER_HINTS):
        return True
    if nonempty_count >= 2 and numeric_count > 0 and numeric_count == year_count:
        return True
    return False


def looks_like_data_row(row: list[str]) -> bool:
    nonempty_count, numeric_count, _ = numeric_profile(row)
    if nonempty_count == 0:
        return False
    return numeric_count >= 2 or (numeric_count >= 1 and nonempty_count >= 2)


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


def first_data_row_offset(rows: list[list[str]]) -> int:
    if len(rows) <= 1:
        return 0
    for offset, row in enumerate(rows):
        if offset == 0:
            continue
        if looks_like_data_row(row) and not looks_like_header_row(row):
            return offset
    return 1


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


def unique_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for index, header in enumerate(headers, start=1):
        base = header or f"column_{index}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        result.append(base if count == 1 else f"{base}_{count}")
    return result


def repeated_header(row: list[str], columns: list[str]) -> bool:
    cleaned = [clean_label(value) for value in row]
    matches = sum(1 for left, right in zip(cleaned, columns) if left == right)
    return matches >= max(2, len(columns) // 2)


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


def markdown_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def markdown_row(cells: list[object]) -> str:
    return "| " + " | ".join(markdown_cell(cell) for cell in cells) + " |"


def records_to_markdown(columns: list[str], records: list[dict[str, str]]) -> str:
    if not columns or not records:
        return ""
    lines = [markdown_row(columns), markdown_row(["---"] * len(columns))]
    for record in records:
        lines.append(markdown_row([record.get(column, "") for column in columns]))
    return "\n".join(lines)


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


def title_from_table(table: dict) -> tuple[str, str] | None:
    if table.get("cols") != 1:
        return None
    text = table_plain_text(table)
    matches = list(RE_REFID_ANYWHERE.finditer(text))
    if not matches:
        return None
    # 상위 제목과 첫 하위 제목이 한 표에 함께 있으면 실제 통계 단위인 가장
    # 깊은(마지막) ref_id를 선택한다. 제목 자체는 아래 목차 catalog가 보정한다.
    match = matches[-1]
    return match.group(1), text[match.end():].strip()


def strip_title_page(raw_title: str) -> str:
    title = clean_text(raw_title)
    return RE_PAGE_SUFFIX.sub("", title).strip()


def split_title(raw_title: str) -> tuple[str, str | None]:
    text = strip_title_page(raw_title)
    if "\n" in text:
        ko, en = text.split("\n", 1)
        return clean_text(ko), clean_text(en) or None
    match = RE_KO_EN_BOUNDARY.search(text) or RE_EN_SPLIT.search(text)
    if match:
        return clean_text(text[:match.start()]), clean_text(text[match.start():]) or None
    return text, None


def ref_numbers(
    ref_id: str,
) -> tuple[int | None, int | None, int | None, int | None]:
    nums = ref_id.split("-")
    chapter_no = int(nums[0]) if len(nums) > 0 and nums[0].isdigit() else None
    section_no = int(nums[1]) if len(nums) > 1 and nums[1].isdigit() else None
    level3_no = int(nums[2]) if len(nums) > 2 and nums[2].isdigit() else None
    level4_no = int(nums[3]) if len(nums) > 3 and nums[3].isdigit() else None
    return chapter_no, section_no, level3_no, level4_no


def make_unit(ref_id: str, raw_title: str, page_start: int | None,
              chapter: str | None, section: str | None,
              toc_entry: dict | None = None) -> dict:
    title_ko, title_en = split_title(raw_title)
    chapter_no, section_no, level3_no, level4_no = ref_numbers(ref_id)
    if toc_entry:
        chapter_no = toc_entry.get("chapter_no", chapter_no)
        section_no = toc_entry.get("section_no", section_no)
        level3_no = toc_entry.get("level3_no", level3_no)
        level4_no = toc_entry.get("level4_no", level4_no)
        chapter = toc_entry.get("chapter") or chapter
        section = toc_entry.get("section") or section
        level3_title = toc_entry.get("level3_title") or title_ko or ref_id
        level4_title = toc_entry.get("level4_title") or level3_title
        title_ko = level4_title
        title_en = toc_entry.get("level4_title_en") or title_en
    else:
        level3_title = title_ko or ref_id
        level4_title = title_ko or level3_title
    return {
        "ref_id": ref_id,
        "chapter_no": chapter_no,
        "section_no": section_no,
        "level3_no": level3_no,
        "level4_no": level4_no,
        "chapter": chapter,
        "section": section,
        "level3_title": level3_title,
        "level4_title": level4_title,
        "title_ko": title_ko or ref_id,
        "title_en": title_en,
        "unit": None,
        "base_date": None,
        "page_start": page_start,
        "tables": [],
        "footnotes": [],
        "contacts": [],
    }


def data_table(table: dict) -> bool:
    if table.get("cols", 0) < 2 or table.get("rows", 0) < 2:
        return False
    return any(clean_label(cell.get("text")) for row in table.get("cells", []) for cell in row)


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


def apply_table_meta(unit: dict, base_date: str | None, unit_name: str | None) -> None:
    if base_date and not unit.get("base_date"):
        unit["base_date"] = base_date
    if unit_name and not unit.get("unit"):
        unit["unit"] = unit_name


def add_table(unit: dict, table: dict) -> None:
    base_date, unit_name, caption = extract_meta_from_table(table)
    apply_table_meta(unit, base_date, unit_name)
    unit["tables"].append(table_record(table, len(unit["tables"]) + 1, caption))


def norm_phone(text: str) -> str | None:
    match = RE_PHONE.search(text)
    if not match:
        return None
    phone = re.sub(r"[)\s]", "-", match.group(0))
    return re.sub(r"-+", "-", phone).strip("-")


def split_source(text: str) -> tuple[str, str | None, str | None]:
    if "/" not in text:
        return text, None, None
    left, right = text.split("/", 1)
    url_match = RE_URL.search(right)
    source_url = url_match.group(1) if url_match else None
    source_system = re.sub(r"\(.*?\)", "", right).strip() or None
    return left.strip(), source_system, source_url


def split_officer(text: str, phone: str | None) -> tuple[str | None, str | None]:
    who = RE_PHONE.split(text)[0].strip() if phone else text
    who = who.strip(" ()")
    if not who:
        return None, None
    parts = who.split()
    return parts[0], " ".join(parts[1:]) or None


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


def is_note_text(text: str) -> bool:
    return text.startswith("#주") or bool(RE_NOTE_NO.match(text))


def note_record(text: str, seq: int) -> dict:
    match = RE_NOTE_NO.match(text)
    return {
        "seq": seq,
        "note_no": match.group(1) if match else None,
        "content": re.sub(r"^#", "", text).strip(),
    }


def handle_paragraph(unit: dict, text: str, pending_note: dict | None) -> dict | None:
    if not text:
        return pending_note
    if is_note_text(text):
        note = note_record(text, len(unit["footnotes"]) + 1)
        unit["footnotes"].append(note)
        return note
    if text.startswith("-") and pending_note:
        pending_note["content"] = f'{pending_note["content"]} {text}'
        return pending_note
    if text.startswith("*"):
        contact = parse_contact(text)
        if contact.get("phone") or contact.get("dept"):
            unit["contacts"].append(contact)
    return None


def context_from_title_table(table: dict, chapter: str | None,
                             section: str | None) -> tuple[str | None, str | None]:
    if table.get("cols") != 1:
        return chapter, section
    text = table_plain_text(table)
    if RE_REFID.match(text):
        return chapter, section
    if "제" in text and "절" in text:
        return chapter, text
    if text and table.get("rows", 0) <= 5 and "GOVERNMENT" in text.upper():
        return text, section
    return chapter, section


def toc_chapter_row(row: list[dict]) -> tuple[int, str, str | None] | None:
    values = [clean_text(cell.get("text") or "", keep_newlines=True) for cell in row]
    if len(values) < 2 or not values[0].isdigit():
        return None
    raw_title = next((value for value in values[1:] if value), "")
    if not raw_title:
        return None
    title_ko, title_en = split_title(raw_title)
    return int(values[0]), title_ko, title_en


def build_toc_catalog(tables: list[dict]) -> dict[str, dict]:
    """목차 표에서 실제 통계 leaf별 4계층 제목 catalog를 만든다."""
    chapters: dict[int, dict] = {}
    groups: dict[str, dict] = {}
    entries: dict[str, dict] = {}
    chapter_no: int | None = None
    chapter: str | None = None
    section_no: int | None = None
    section: str | None = None
    current_group: dict | None = None
    pending: dict | None = None

    def normalized_pending_title(parts: list[str]) -> tuple[str, str | None]:
        raw = " ".join(strip_title_page(part) for part in parts if part)
        return split_title(raw)

    def finish_pending() -> None:
        nonlocal pending, section_no, section, current_group
        if not pending:
            return
        title_ko, title_en = normalized_pending_title(pending["parts"])
        if pending["kind"] == "section":
            section_no = pending["number"]
            section = title_ko
            current_group = None
        elif pending["kind"] == "level3":
            ref_id = pending["ref_id"]
            ref_chapter, ref_section, level3_no, _ = ref_numbers(ref_id)
            current_group = {
                "ref_id": ref_id,
                "chapter_no": ref_chapter or chapter_no,
                "section_no": ref_section or section_no,
                "level3_no": level3_no,
                "chapter": (chapters.get(ref_chapter or chapter_no or -1) or {}).get(
                    "title", chapter
                ),
                "section": section,
                "level3_title": title_ko or ref_id,
                "level3_title_en": title_en,
                "children": [],
            }
            groups[ref_id] = current_group
        elif pending["kind"] == "level4" and current_group:
            level4_no = pending["number"]
            ref_id = f'{current_group["ref_id"]}-{level4_no}'
            entry = {
                key: value for key, value in current_group.items() if key != "children"
            }
            entry.update({
                "ref_id": ref_id,
                "level4_no": level4_no,
                "level4_title": title_ko or current_group["level3_title"],
                "level4_title_en": title_en,
            })
            entries[ref_id] = entry
            current_group["children"].append(ref_id)
        pending = None

    def consume_line(line: str) -> None:
        nonlocal pending
        line = clean_text(line)
        if not line:
            return
        match = RE_TOC_SECTION.match(line)
        if match:
            finish_pending()
            pending = {
                "kind": "section",
                "number": int(match.group(1)),
                "parts": [match.group(2)],
            }
            return
        match = RE_TOC_LEVEL3.match(line)
        if match:
            finish_pending()
            pending = {
                "kind": "level3",
                "ref_id": match.group(1),
                "parts": [match.group(2)],
            }
            return
        match = RE_TOC_LEVEL4.match(line)
        if match:
            finish_pending()
            pending = {
                "kind": "level4",
                "number": int(match.group(1)),
                "parts": [match.group(2)],
            }
            return
        if pending:
            pending["parts"].append(line)

    for table in tables:
        for row in table.get("cells", []):
            chapter_record = toc_chapter_row(row)
            if chapter_record:
                finish_pending()
                chapter_no, chapter, chapter_en = chapter_record
                chapters[chapter_no] = {
                    "title": chapter,
                    "title_en": chapter_en,
                }
                section_no = None
                section = None
                current_group = None
                continue
            for cell in row:
                text = cell.get("text") or ""
                if not ("제" in text or RE_REFID_ANYWHERE.search(text)):
                    continue
                for line in text.splitlines():
                    consume_line(line)
    finish_pending()

    # 하위 항목이 없는 n-n-n은 그 자체가 실제 표 제목이다. 이때 4계층 제목은
    # 요구사항대로 3계층 제목과 동일하게 채우고 level4_no만 NULL로 둔다.
    for ref_id, group in groups.items():
        if group["children"]:
            continue
        entry = {key: value for key, value in group.items() if key != "children"}
        entry.update({
            "level4_no": None,
            "level4_title": group["level3_title"],
            "level4_title_en": group.get("level3_title_en"),
        })
        entries[ref_id] = entry
    return entries


def toc_tables(hwpx_path: str) -> list[dict]:
    tables: list[dict] = []
    for block in iter_blocks(hwpx_path):
        if block["type"] != "table":
            continue
        table = block["table"]
        has_chapter_row = any(toc_chapter_row(row) for row in table.get("cells", []))
        has_toc_refs = bool(RE_REFID_ANYWHERE.search(table_plain_text(table)))
        if has_chapter_row and has_toc_refs:
            tables.append(table)
            continue
        if tables:
            break
    return tables


def append_unit(units: list[dict], unit: dict | None) -> None:
    if unit and unit.get("tables"):
        units.append(unit)


def section_names(zip_file: zipfile.ZipFile) -> list[str]:
    names = []
    for name in zip_file.namelist():
        if RE_SECTION_XML.match(name):
            names.append(name)
    return sorted(names, key=lambda value: int(RE_SECTION_XML.match(value).group(1)))


def iter_blocks(hwpx_path: str):
    page_number = 1
    with zipfile.ZipFile(hwpx_path) as zip_file:
        for section_name in section_names(zip_file):
            root = ET.fromstring(zip_file.read(section_name))
            for paragraph in root.findall(HP + "p"):
                if paragraph.get("pageBreak") == "1":
                    page_number += 1

                text_parts: list[str] = []

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


def default_publication(page_count: int | None) -> dict:
    return {
        "year": 2025,
        "pub_no": None,
        "title": "2025 행정안전통계연보",
        "page_count": page_count,
    }


def estimate_page_count(hwpx_path: str) -> int | None:
    page_count = 1
    with zipfile.ZipFile(hwpx_path) as zip_file:
        for section_name in section_names(zip_file):
            root = ET.fromstring(zip_file.read(section_name))
            page_count += sum(1 for paragraph in root.findall(HP + "p") if paragraph.get("pageBreak") == "1")
    return page_count


def parse(
    hwpx_path: str,
    publication_year: int | None = None,
    publication_title: str | None = None,
    publication_no: str | None = None,
) -> dict:
    units: list[dict] = []
    current: dict | None = None
    pending_note: dict | None = None
    chapter: str | None = None
    section: str | None = None
    toc_catalog = build_toc_catalog(toc_tables(hwpx_path))

    for block in iter_blocks(hwpx_path):
        block_type = block["type"]

        if block_type == "table":
            table = block["table"]
            title = title_from_table(table)
            if title:
                append_unit(units, current)
                ref_id, raw_title = title
                current = make_unit(
                    ref_id,
                    raw_title,
                    block.get("pageNumber"),
                    chapter,
                    section,
                    toc_catalog.get(ref_id),
                )
                pending_note = None
                continue

            chapter, section = context_from_title_table(table, chapter, section)
            if current and data_table(table):
                add_table(current, table)
                pending_note = None
            continue

        if current is None:
            continue

        if block_type == "paragraph":
            pending_note = handle_paragraph(current, block.get("text") or "", pending_note)

    append_unit(units, current)
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
                "HWPX 목차에서 chapter/section/3계층/4계층 제목 catalog를 만든 뒤 "
                "Contents/section*.xml 본문의 ref_id와 매칭하고, "
                "hp:cellAddr/hp:cellSpan으로 병합 셀을 보존한 뒤 grid/records/markdown을 생성"
            ),
        },
        "statistics": units,
    }


def parsed_to_markdown(data: dict) -> str:
    out = [f"# {data['publication']['title']}", ""]
    for unit in data.get("statistics", []):
        title = f"{unit['ref_id']} {unit['title_ko']}".strip()
        out.extend([f"## {title}", ""])
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


def write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
